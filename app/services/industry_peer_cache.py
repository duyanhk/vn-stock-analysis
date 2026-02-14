"""
Persistent cache of industry peers (symbol, company_name, market_cap).
Stored in sample_data/industry_peers.json. First analysis of an industry fetches all;
later analyses use cache and return 5 around target cap + top 5. Cache is gradually
updated with fresh market caps on each use.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any

CACHE_FILENAME = "industry_peers.json"
REFRESH_BATCH_SIZE = 5  # How many symbols to refresh with live data on each use
COUNT_AROUND = 5
COUNT_TOP = 5


def _cache_path() -> str:
    # Use path relative to this package (app/services/) so we hit app/sample_data/ even when
    # Flask root_path is the project root (parent of app/).
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample_dir = os.path.join(app_dir, "sample_data")
    return os.path.join(sample_dir, CACHE_FILENAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_industry_cache() -> Dict[str, Any]:
    """Load full cache from disk. Returns { 'updated': str, 'industries': { code: industry_dict } }."""
    path = _cache_path()
    if not os.path.isfile(path):
        # Fallback when Flask root_path is project root (parent of app/)
        try:
            from flask import current_app
            alt = os.path.join(current_app.root_path, "app", "sample_data", CACHE_FILENAME)
            if os.path.isfile(alt):
                path = alt
        except Exception:
            pass
    if not os.path.isfile(path):
        try:
            print(f"[peers] cache: file not found at {path!r}")
        except Exception:
            pass
        return {"updated": None, "industries": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            ind = data.get("industries") or {}
            n = len(ind)
            try:
                print(f"[peers] cache: loaded from {path!r}, industries={n}")
            except Exception:
                pass
            return data
    except Exception as e:
        try:
            print(f"[peers] cache: failed to load {path!r}: {e}")
        except Exception:
            pass
    return {"updated": None, "industries": {}}


def _sanitize_for_json(obj: Any) -> Any:
    """Convert numpy/pandas scalars to native Python so json.dump doesn't raise."""
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def save_industry_cache(data: Dict[str, Any]) -> None:
    """Write full cache to disk. Sanitizes data so int64/float64 are JSON-serializable."""
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dict(data)
    data["updated"] = _now_iso()
    data = _sanitize_for_json(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Coerce value to float; return default for None, invalid, or non-numeric."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_industry_from_cache(industry_code) -> Optional[Dict[str, Any]]:
    """Get one industry's data from cache. industry_code can be int or str."""
    key = str(industry_code) if industry_code is not None else ""
    data = load_industry_cache()
    ind = data.get("industries") or {}
    return ind.get(key)


def find_industry_by_symbol(symbol: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Find industry_code and industry_name for a symbol by scanning industry_peers.json.
    Used in sample mode so the UI can show cached peers without calling live APIs.
    Returns (industry_code, industry_name) or (None, None) if not found.
    """
    if not symbol:
        return None, None
    sym = str(symbol).strip().upper()
    data = load_industry_cache()
    industries = data.get("industries") or {}
    try:
        print(f"[peers] find_industry_by_symbol({sym!r}): scanning {len(industries)} industries")
    except Exception:
        pass
    for code_key, ind in industries.items():
        if not isinstance(ind, dict):
            continue
        companies = ind.get("companies") or []
        for c in companies:
            if (str(c.get("symbol") or "").strip().upper() == sym):
                out_code = ind.get("industry_code") or (int(code_key) if code_key.isdigit() else code_key)
                out_name = ind.get("industry_name") or None
                try:
                    print(f"[peers] find_industry_by_symbol: found {sym!r} in industry {out_code!r} ({out_name!r}), {len(companies)} companies")
                except Exception:
                    pass
                return (out_code, out_name)
    try:
        print(f"[peers] find_industry_by_symbol: {sym!r} not in any cached industry")
    except Exception:
        pass
    return None, None


def save_industry_to_cache(
    industry_code,
    industry_name: str,
    companies: List[Dict[str, Any]],
    pending_symbols: Optional[List[str]] = None,
) -> None:
    """Save or overwrite one industry's peer list. companies = [{ symbol, company_name, market_cap }, ...].
    pending_symbols = symbols not fetched (e.g. due to rate limit) to prioritize next run."""
    try:
        code = int(industry_code) if industry_code is not None else None
    except (TypeError, ValueError):
        code = industry_code
    key = str(code) if code is not None else ""
    data = load_industry_cache()
    if "industries" not in data or not isinstance(data["industries"], dict):
        data["industries"] = {}
    data["industries"][key] = {
        "industry_code": code,
        "industry_name": industry_name or "",
        "updated": _now_iso(),
        "companies": companies,
        "pending_symbols": list(pending_symbols) if pending_symbols else [],
    }
    save_industry_cache(data)


def get_peers_from_cache(
    industry_code,
    target_symbol: str,
    target_market_cap: Optional[float],
    target_company_name: Optional[str],
    count_around: int = COUNT_AROUND,
    count_top: int = COUNT_TOP,
) -> List[Dict[str, Any]]:
    """
    Build peer list from cache: our company first, then count_around around our cap, then count_top by cap.
    Returns list of { symbol, company_name, market_cap, is_our_company, rank }.
    """
    ind = get_industry_from_cache(industry_code)
    if not ind:
        return []

    target_symbol = (target_symbol or "").strip().upper()
    companies = ind.get("companies") or []
    if not companies:
        if not target_symbol:
            return []
        return [{
            "symbol": target_symbol,
            "company_name": target_company_name or target_symbol,
            "market_cap": target_market_cap,
            "is_our_company": True,
            "rank": None,
        }]

    # Sort by market_cap desc; skip entries with invalid or missing market_cap
    sorted_list = sorted(
        [c for c in companies if _safe_float(c.get("market_cap")) is not None],
        key=lambda x: _safe_float(x["market_cap"], 0.0) or 0.0,
        reverse=True,
    )
    if not sorted_list and not target_market_cap:
        return []

    # Find target's cap and rank; prefer cache over request so our company sorts correctly among peers
    our_cap = target_market_cap
    our_rank = None
    for i, c in enumerate(sorted_list):
        sym = (c.get("symbol") or "").strip().upper()
        if sym == target_symbol:
            if _safe_float(c.get("market_cap")) is not None:
                our_cap = c.get("market_cap")
            elif our_cap is None:
                our_cap = c.get("market_cap")
            our_rank = i + 1
            break
    if our_cap is None and target_symbol:
        for c in companies:
            if (str(c.get("symbol") or "").strip().upper() == target_symbol and _safe_float(c.get("market_cap")) is not None):
                our_cap = c.get("market_cap")
                break

    seen = set()
    result: List[Dict[str, Any]] = []
    target_sector = None
    for c in companies:
        if (c.get("symbol") or "").strip().upper() == target_symbol:
            target_sector = (c.get("sector_industry") or "").strip() or None
            break

    def add(sym: str, cap: Optional[float], is_ours: bool, rank: Optional[int], cname: Optional[str] = None, sector: Optional[str] = None):
        if sym in seen:
            return
        seen.add(sym)
        entry: Dict[str, Any] = {
            "symbol": sym,
            "company_name": cname or sym,
            "market_cap": cap,
            "is_our_company": is_ours,
            "rank": rank,
        }
        if sector:
            entry["sector_industry"] = sector
        result.append(entry)

    add(target_symbol, our_cap, True, None, target_company_name, target_sector)

    if not sorted_list:
        return result

    if our_rank is not None and count_around > 0:
        start = max(0, our_rank - 1 - (count_around // 2))
        end = min(len(sorted_list), start + count_around)
        for i in range(start, end):
            c = sorted_list[i]
            sym = (c.get("symbol") or "").strip().upper()
            add(sym, c.get("market_cap"), False, i + 1, c.get("company_name"), (c.get("sector_industry") or "").strip() or None)

    for i, c in enumerate(sorted_list[:count_top]):
        sym = (c.get("symbol") or "").strip().upper()
        add(sym, c.get("market_cap"), False, i + 1, c.get("company_name"), (c.get("sector_industry") or "").strip() or None)

    return result


def get_all_peers_from_cache(
    industry_code,
    target_symbol: str,
    target_market_cap: Optional[float],
    target_company_name: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Return the full list of all companies in the industry from cache.
    Frontend can filter (e.g. by sector_industry) and build "5 around" / "top 5" as needed.
    Returns list of { symbol, company_name, market_cap, is_our_company, rank, sector_industry? }.
    """
    ind = get_industry_from_cache(industry_code)
    if not ind:
        return []

    target_symbol = (target_symbol or "").strip().upper()
    companies = ind.get("companies") or []
    if not companies:
        if not target_symbol:
            return []
        return [{
            "symbol": target_symbol,
            "company_name": target_company_name or target_symbol,
            "market_cap": target_market_cap,
            "is_our_company": True,
            "rank": None,
        }]

    sorted_list = sorted(
        [c for c in companies if _safe_float(c.get("market_cap")) is not None],
        key=lambda x: _safe_float(x["market_cap"], 0.0) or 0.0,
        reverse=True,
    )
    result: List[Dict[str, Any]] = []
    for i, c in enumerate(sorted_list):
        sym = (c.get("symbol") or "").strip().upper()
        sector = (c.get("sector_industry") or "").strip() or None
        entry: Dict[str, Any] = {
            "symbol": sym,
            "company_name": (c.get("company_name") or sym),
            "market_cap": c.get("market_cap"),
            "is_our_company": sym == target_symbol,
            "rank": i + 1,
        }
        if sector:
            entry["sector_industry"] = sector
        result.append(entry)
    if target_symbol and not any(r.get("is_our_company") for r in result):
        our_cap = target_market_cap
        for c in companies:
            if (c.get("symbol") or "").strip().upper() == target_symbol:
                our_cap = c.get("market_cap") if our_cap is None else our_cap
                break
        result.insert(0, {
            "symbol": target_symbol,
            "company_name": target_company_name or target_symbol,
            "market_cap": our_cap,
            "is_our_company": True,
            "rank": None,
        })
    return result


def refresh_market_caps_for_symbols(
    symbols: List[str],
    price_by_symbol: Dict[str, float],
) -> Dict[str, float]:
    """
    Fetch shares for given symbols and return symbol -> market_cap (VND).
    price_by_symbol: from price_board; may be VND per share or thousands VND (see company_peer_service heuristic).
    """
    import time
    from .market_service import _fetch_shares_outstanding

    delay = 1.5
    cap_by_symbol: Dict[str, float] = {}
    for sym in symbols:
        price = price_by_symbol.get(sym)
        if price is None:
            continue
        time.sleep(delay)
        shares = _fetch_shares_outstanding(sym, "KBS")
        if shares is None:
            shares = _fetch_shares_outstanding(sym, "VCI")
        if shares is not None and shares > 0:
            p = float(price)
            cap_by_symbol[sym] = (p * 1000 * shares) if 0 < p < 1000 else (p * shares)
    return cap_by_symbol


def update_cache_with_refreshed_caps(
    industry_code,
    updates: Dict[str, float],
) -> None:
    """Update market_cap for given symbols in the industry cache and bump updated time."""
    data = load_industry_cache()
    key = str(industry_code)
    ind = (data.get("industries") or {}).get(key)
    if not ind or not ind.get("companies"):
        return
    companies = ind["companies"]
    upper_updates = {(s or "").strip().upper(): cap for s, cap in updates.items()}
    for c in companies:
        sym = (c.get("symbol") or "").strip().upper()
        if sym in upper_updates:
            c["market_cap"] = upper_updates[sym]
    ind["updated"] = _now_iso()
    save_industry_cache(data)


def update_cache_with_sector_industry(
    industry_code,
    symbol_to_sector: Dict[str, str],
) -> None:
    """Set sector_industry (VCI sector·industry) for given symbols in the industry cache."""
    if not symbol_to_sector:
        return
    data = load_industry_cache()
    key = str(industry_code)
    ind = (data.get("industries") or {}).get(key)
    if not ind or not ind.get("companies"):
        return
    companies = ind["companies"]
    upper_map = {(s or "").strip().upper(): v for s, v in symbol_to_sector.items() if v}
    for c in companies:
        sym = (c.get("symbol") or "").strip().upper()
        if sym in upper_map:
            c["sector_industry"] = upper_map[sym]
    ind["updated"] = _now_iso()
    save_industry_cache(data)


def pick_symbols_to_refresh(
    industry_code,
    target_symbol: str,
    peer_result: List[Dict],
    max_pick: int = REFRESH_BATCH_SIZE,
    target_sector_industry: Optional[str] = None,
) -> List[str]:
    """
    Choose up to max_pick symbols to refresh (target + others).
    Priority order for vnstock requests:
    1. Target symbol
    2. Same VCI sector·industry as target
    3. Pending symbols (no data yet due to rate limit)
    4. Peers with similar market cap (5 around our rank)
    5. Top 5 by market cap
    """
    target_symbol = (target_symbol or "").strip().upper()
    target_sector = (target_sector_industry or "").strip()
    ind = get_industry_from_cache(industry_code)
    companies = (ind or {}).get("companies") or []
    pending_raw = (ind or {}).get("pending_symbols") or []

    # Sorted by market_cap desc (same as get_peers_from_cache)
    sorted_list = [
        c for c in companies
        if _safe_float(c.get("market_cap")) is not None
    ]
    sorted_list.sort(key=lambda x: _safe_float(x["market_cap"], 0.0) or 0.0, reverse=True)

    our_rank = None
    for i, c in enumerate(sorted_list):
        if (c.get("symbol") or "").strip().upper() == target_symbol:
            our_rank = i + 1
            break

    def _norm(s: str) -> str:
        return (s or "").strip().upper()

    same_sector: List[str] = []
    if target_sector:
        for c in companies:
            sym = _norm(c.get("symbol"))
            if not sym or sym == target_symbol:
                continue
            if (c.get("sector_industry") or "").strip() == target_sector:
                same_sector.append(sym)

    pending = [_norm(s) for s in pending_raw if _norm(s) and _norm(s) != target_symbol]

    # "5 around" our rank (peer analysis logic)
    around: List[str] = []
    if our_rank is not None and COUNT_AROUND > 0:
        start = max(0, our_rank - 1 - (COUNT_AROUND // 2))
        end = min(len(sorted_list), start + COUNT_AROUND)
        for i in range(start, end):
            sym = _norm(sorted_list[i].get("symbol"))
            if sym and sym != target_symbol:
                around.append(sym)

    # Top 5 by market cap
    top: List[str] = []
    for i in range(min(COUNT_TOP, len(sorted_list))):
        sym = _norm(sorted_list[i].get("symbol"))
        if sym and sym != target_symbol:
            top.append(sym)

    picked: set = set()
    picks: List[str] = []

    def _add_batch(batch: List[str]) -> None:
        for sym in batch:
            if len(picks) >= max_pick:
                return
            if sym and sym not in picked:
                picked.add(sym)
                picks.append(sym)

    if target_symbol:
        picks.append(target_symbol)
        picked.add(target_symbol)
    _add_batch(same_sector)
    _add_batch(pending)
    _add_batch(around)
    _add_batch(top)
    # Any remaining from peer_result not yet picked
    for p in peer_result:
        sym = _norm(p.get("symbol"))
        if sym and sym not in picked:
            _add_batch([sym])
        if len(picks) >= max_pick:
            break

    return picks[:max_pick]
