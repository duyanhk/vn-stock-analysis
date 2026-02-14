"""
Company profile (name, sector·industry) and industry peers with market cap.
Uses VNStock Company and Listing APIs (VCI/KBS).
"""
from __future__ import annotations

import time
from typing import List, Dict, Optional, Tuple, Any

from flask import current_app


# Delay between API calls to avoid rate limits (seconds)
_PEER_RATE_LIMIT_DELAY = 1.5
# Price board may fail or truncate with too many symbols; fetch in batches
_PRICE_BOARD_BATCH_SIZE = 35


def _sanitize(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _record_get(record: dict, *keys: Any) -> Optional[Any]:
    """Get value from a record trying multiple keys (flat or nested tuple keys from MultiIndex)."""
    for k in keys:
        v = record.get(k)
        if v is not None:
            return v
    return None


def get_company_info(symbol: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Get company name and sector·industry for a symbol.

    Returns:
        (company_name, sector_industry, industry_code) or (None, None, None) on failure/sample mode.
        industry_code is used for peer lookup (KBS industry code).
    """
    if not symbol:
        return None, None, None
    symbol = symbol.strip().upper()

    if current_app.config.get("USE_SAMPLE_DATA", False):
        return None, None, None

    company_name = None
    sector_industry = None
    industry_code = None

    # 1) Company name: KBS Listing all_symbols has organ_name per symbol
    try:
        from vnstock import Listing
        listing = Listing(source="KBS", show_log=False)
        df = listing.all_symbols(show_log=False)
        if df is not None and not df.empty and "symbol" in df.columns:
            row = df[df["symbol"].astype(str).str.upper() == symbol]
            if not row.empty:
                name_col = "organ_name" if "organ_name" in df.columns else "name"
                if name_col in df.columns:
                    company_name = _sanitize(row[name_col].iloc[0])
    except Exception:
        pass

    # 2) Sector · Industry: try VCI Company (icbName2 · icbName4), then KBS symbols_by_industries
    try:
        from vnstock import Company
        company = Company(source="VCI", symbol=symbol, show_log=False)
        raw = getattr(company, "raw_data", None) or {}
        info = raw.get("CompanyListingInfo") or raw.get("company_listing_info") or {}
        if isinstance(info, dict):
            # Prefer English labels if available
            n2 = info.get("enIcbName2") or info.get("icbName2")
            n4 = info.get("enIcbName4") or info.get("icbName4")
            if n2 or n4:
                sector_industry = " · ".join(filter(None, [_sanitize(n2), _sanitize(n4)]))
    except Exception:
        pass

    # 3) Industry code (for peers): from KBS symbols_by_industries
    try:
        from vnstock import Listing
        listing = Listing(source="KBS", show_log=False)
        df = listing.symbols_by_industries(show_log=False)
        if df is not None and not df.empty:
            row = df[df["symbol"].astype(str).str.upper() == symbol]
            if not row.empty:
                industry_code = row["industry_code"].iloc[0]
                industry_code = industry_code if industry_code is not None else None
                # If we still don't have sector_industry, use industry_name from KBS
                if not sector_industry and "industry_name" in df.columns:
                    sector_industry = _sanitize(row["industry_name"].iloc[0])
    except Exception:
        pass

    return company_name, sector_industry, industry_code


# Max wait-and-retry cycles on rate limit (each cycle waits N seconds then continues)
_PEER_RATE_LIMIT_MAX_WAIT_CYCLES = 5


def _parse_wait_seconds_from_rate_limit(exc: Exception) -> int:
    """Parse retry-after seconds from RateLimitError or Vietnamese message. Default 60."""
    import re
    # vnstock RateLimitError has .details["retry_after"]
    if hasattr(exc, "details") and isinstance(getattr(exc, "details"), dict):
        sec = getattr(exc, "details", {}).get("retry_after")
        if sec is not None:
            try:
                return int(sec)
            except (TypeError, ValueError):
                pass
    # "Retry after X seconds" or "Chờ X giây"
    msg = str(exc) or ""
    for pat in [r"[Rr]etry after (\d+) seconds?", r"Chờ (\d+) giây", r"(\d+) giây để tiếp tục"]:
        m = re.search(pat, msg)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                pass
    return 60


def get_industry_peers(
    symbol: str,
    our_market_cap_vnd: Optional[float],
    our_shares_outstanding: Optional[float],
    company_name: Optional[str],
    sector_industry: Optional[str],
    max_around: int = 10,
    top_n: int = 5,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Build ordered peer list: our company first, then peers around our market cap, then top 5 by market cap.

    Returns:
        (peers_list, extra) where extra may contain "peers_pending_symbols" and "peers_note".
    """
    _empty_extra: Dict[str, Any] = {}
    if not symbol:
        return [], _empty_extra
    symbol = symbol.strip().upper()

    if current_app.config.get("USE_SAMPLE_DATA", False):
        # Use industry_peers.json so the Peer analysis UI shows cached peers when testing with sample data
        try:
            from . import industry_peer_cache as ic
            industry_code, industry_name = ic.find_industry_by_symbol(symbol)
            if industry_code is not None:
                result = ic.get_all_peers_from_cache(
                    industry_code,
                    symbol,
                    our_market_cap_vnd,
                    company_name,
                )
                if result:
                    print(f"[peers] sample mode: industry {industry_code} ({industry_name or '?'}), returning {len(result)} peers for {symbol}")
                    return result, _empty_extra
            else:
                print(f"[peers] sample mode: no industry in cache for {symbol}")
        except Exception as e:
            print(f"[peers] sample mode: exception for {symbol}: {e}")
        return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra

    try:
        from vnstock import Listing, Trading
        from vnstock.core.exceptions import RateLimitError
        from .market_service import get_price_board, _fetch_shares_outstanding
        from . import industry_peer_cache as ic
    except ImportError:
        return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra

    # Get all symbols in our industry (KBS industry classification)
    try:
        listing = Listing(source="KBS", show_log=False)
        ind_df = listing.symbols_by_industries(show_log=False)
        if ind_df is None or ind_df.empty:
            print(f"[peers] KBS symbols_by_industries returned no data -> no peers for {symbol}")
            return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra
        # Normalize symbol column for comparison
        if "symbol" not in ind_df.columns:
            print(f"[peers] KBS symbols_by_industries has no 'symbol' column -> no peers for {symbol}")
            return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra
        ind_df = ind_df.dropna(subset=["symbol"]).copy()
        ind_df["_sym"] = ind_df["symbol"].astype(str).str.strip().str.upper()
        our_row = ind_df[ind_df["_sym"] == symbol]
        if our_row.empty:
            print(f"[peers] {symbol} not found in KBS symbols_by_industries (symbol may be missing from KBS industry list) -> no peers")
            return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra
        our_industry_code = our_row["industry_code"].iloc[0]
        peer_symbols = ind_df[ind_df["industry_code"] == our_industry_code]["_sym"].tolist()
        industry_name = (
            _sanitize(our_row["industry_name"].iloc[0])
            if "industry_name" in ind_df.columns
            else ""
        )
    except Exception:
        return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra

    if not peer_symbols:
        print("[peers] no peer_symbols in industry -> _sample_peers")
        return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra

    print(f"[peers] industry_code={our_industry_code}, peer_symbols count={len(peer_symbols)}, first 5={peer_symbols[:5]}")

    # Prefer cache: return 5 around + top 5, and optionally refresh a batch of market caps
    cached = ic.get_industry_from_cache(our_industry_code)
    cache_companies = (cached or {}).get("companies") or []
    print(f"[peers] cache: cached={cached is not None}, companies count={len(cache_companies)}")
    if cached and cache_companies:
        our_cap = our_market_cap_vnd
        result = ic.get_all_peers_from_cache(
            our_industry_code,
            symbol,
            our_cap,
            company_name,
        )
        picks = ic.pick_symbols_to_refresh(
            our_industry_code,
            symbol,
            result,
            ic.REFRESH_BATCH_SIZE,
            target_sector_industry=sector_industry,
        )
        if picks:
            price_records, err = get_price_board(picks)
            if not err and price_records:
                price_by_symbol = {}
                for r in price_records:
                    sym_raw = _record_get(r, "symbol", ("listing", "symbol"))
                    sym = (str(sym_raw or "").strip().upper())
                    if not sym:
                        continue
                    close_price = _record_get(
                        r,
                        "close_price",
                        "match_price",
                        "reference_price",
                        ("match", "match_price"),
                        ("match", "reference_price"),
                        ("listing", "ref_price"),
                    )
                    if close_price is not None:
                        try:
                            price_by_symbol[sym] = float(close_price)
                        except (TypeError, ValueError):
                            pass
                updates = ic.refresh_market_caps_for_symbols(picks, price_by_symbol)
                if updates:
                    ic.update_cache_with_refreshed_caps(our_industry_code, updates)
                    # Fill sector_industry for refreshed symbols so same-sector prioritization works
                    symbol_to_sector: Dict[str, str] = {}
                    if sector_industry:
                        symbol_to_sector[symbol] = sector_industry
                    for pick in picks:
                        if (pick or "").strip().upper() == symbol:
                            continue
                        _, si, _ = get_company_info(pick)
                        if si:
                            symbol_to_sector[pick] = si
                        time.sleep(_PEER_RATE_LIMIT_DELAY)
                    if symbol_to_sector:
                        ic.update_cache_with_sector_industry(our_industry_code, symbol_to_sector)
                    result = ic.get_all_peers_from_cache(
                        our_industry_code,
                        symbol,
                        our_cap or updates.get(symbol),
                        company_name,
                    )
        print(f"[peers] cache path -> returning {len(result)} peers")
        return result, _empty_extra

    # No cache: full fetch. Use price board with get_all=True to get listed_shares in same request (avoids 1 request per symbol).
    print("[peers] full fetch path: batching price board (get_all=True for listed_shares)")
    price_by_symbol: Dict[str, float] = {}
    shares_by_symbol: Dict[str, float] = {}
    name_by_symbol: Dict[str, Optional[str]] = {}
    for i in range(0, len(peer_symbols), _PRICE_BOARD_BATCH_SIZE):
        chunk = peer_symbols[i : i + _PRICE_BOARD_BATCH_SIZE]
        price_records, err = get_price_board(chunk, get_all=True)
        n_rec = len(price_records) if price_records else 0
        print(f"[peers] price_board batch {i // _PRICE_BOARD_BATCH_SIZE + 1}: err={err!r}, records={n_rec}")
        if price_records and price_records[0]:
            keys = list(price_records[0].keys())
            keys_preview = keys[:4] if len(keys) > 4 else keys
            print(f"[peers] record keys: {keys_preview}{' ... (' + str(len(keys)) + ' total)' if len(keys) > 4 else ''}")
        if err or not price_records:
            continue
        for r in price_records:
            sym_raw = _record_get(r, "symbol", ("listing", "symbol"))
            sym = (str(sym_raw or "").strip().upper())
            if not sym:
                continue
            close_price = _record_get(
                r,
                "close_price",
                "match_price",
                "reference_price",
                "close",
                ("match", "match_price"),
                ("match", "reference_price"),
                ("listing", "ref_price"),
            )
            if close_price is not None:
                try:
                    price_by_symbol[sym] = float(close_price)
                except (TypeError, ValueError):
                    pass
            listed_shares = _record_get(
                r,
                "listed_shares",
                ("listing", "listed_shares"),
                ("listing", "listed_share"),
            )
            if listed_shares is not None:
                try:
                    shares_by_symbol[sym] = float(listed_shares)
                except (TypeError, ValueError):
                    pass
            organ = _record_get(r, "organ_name", ("listing", "organ_name"))
            if organ is not None and str(organ).strip():
                name_by_symbol[sym] = _sanitize(str(organ).strip())
    # Market cap: price board may return price in VND per share (not thousands). Use price * shares.
    # If price were in thousands VND we'd use price * 1000 * shares; stored cache was 1000x too large, so use no extra factor.
    cap_by_symbol = {}
    for s, price in price_by_symbol.items():
        sh = shares_by_symbol.get(s)
        if sh is not None and sh > 0:
            try:
                p = float(price)
                # Heuristic: if price looks like "thousands" (< 1000) apply * 1000 to get VND per share
                if 0 < p < 1000:
                    cap_by_symbol[s] = p * 1000 * float(sh)
                else:
                    cap_by_symbol[s] = p * float(sh)
            except (TypeError, ValueError):
                pass
    print(f"[peers] after price board: price={len(price_by_symbol)}, shares={len(shares_by_symbol)}, cap={len(cap_by_symbol)}")
    if not cap_by_symbol:
        print("[peers] no cap from price board (missing listed_shares?) -> _sample_peers")
        return _sample_peers(symbol, company_name, our_market_cap_vnd), _empty_extra

    pending_this_run: List[str] = []

    # Fill any missing company names from KBS all_symbols (we may already have some from price board organ_name)
    try:
        listing = Listing(source="KBS", show_log=False)
        all_df = listing.all_symbols(show_log=False)
        name_col = "organ_name" if all_df is not None and "organ_name" in all_df.columns else "name"
        if all_df is not None and not all_df.empty and name_col in all_df.columns:
            for _, row in all_df.iterrows():
                s = (str(row.get("symbol", "") or "")).strip().upper()
                if s:
                    name_by_symbol[s] = _sanitize(row.get(name_col))
    except Exception:
        pass

    companies = []
    for s, cap in sorted(
        cap_by_symbol.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if not cap or cap <= 0:
            continue
        entry = {
            "symbol": s,
            "company_name": (name_by_symbol.get(s) or s),
            "market_cap": cap,
        }
        if s == symbol and sector_industry:
            entry["sector_industry"] = sector_industry
        companies.append(entry)
    # Save to cache (companies + pending for next run)
    if companies or pending_this_run:
        ic.save_industry_to_cache(
            our_industry_code,
            industry_name or "",
            companies,
            pending_symbols=pending_this_run or None,
        )
        print(f"[peers] saved industry to cache: {len(companies)} companies, {len(pending_this_run)} pending")

    our_cap = our_market_cap_vnd
    if our_cap is None and our_shares_outstanding and our_shares_outstanding > 0:
        our_price = price_by_symbol.get(symbol)
        if our_price is not None:
            p = float(our_price)
            our_cap = (p * 1000 * our_shares_outstanding) if 0 < p < 1000 else (p * our_shares_outstanding)
    if our_cap is None:
        our_cap = cap_by_symbol.get(symbol)

    result = ic.get_all_peers_from_cache(
        our_industry_code,
        symbol,
        our_cap,
        company_name,
    )
    print(f"[peers] full fetch path -> get_all_peers_from_cache returned {len(result)} peers")
    extra: Dict[str, Any] = {}
    if pending_this_run:
        extra["peers_pending_symbols"] = pending_this_run
        extra["peers_note"] = (
            f"Remaining {len(pending_this_run)} ticker(s) not fetched (rate limit); "
            "will be prioritized next run: " + ", ".join(pending_this_run[:15])
            + ("..." if len(pending_this_run) > 15 else "")
        )
    return result, extra


def _sample_peers(
    symbol: str,
    company_name: Optional[str],
    our_market_cap_vnd: Optional[float],
) -> List[Dict]:
    """Return a single-row peer list for sample mode (our company only)."""
    return [{
        "symbol": symbol,
        "company_name": company_name or symbol,
        "market_cap": our_market_cap_vnd,
        "is_our_company": True,
        "rank": None,
    }]
