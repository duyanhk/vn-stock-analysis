from flask import Blueprint, render_template, request, jsonify, send_file, current_app
import os
import re
import time
import traceback
from datetime import date, timedelta

import pandas as pd

from .services.financial_service import (
    get_financial_ratios,
    get_sample_records_for_download,
    _list_sample_tickers,
    get_company_meta_from_samples,
    update_sample_company_meta,
)
from .services.market_service import (
    get_daily_summary,
)
from .services.company_peer_service import (
    get_company_info,
    get_industry_peers,
)
from .services.industry_peer_cache import (
    find_industry_by_symbol,
    get_industry_from_cache,
)
from .services.peer_valuation_store import (
    get_icb_peers_for_target,
    get_industry_top5,
    save_icb_peers,
    save_industry_top5,
)

try:
    from vnstock.core.exceptions import RateLimitError as VnstockRateLimitError
except ImportError:
    VnstockRateLimitError = None
try:
    from vnai.beam.quota import RateLimitExceeded as VnaiRateLimitExceeded
except ImportError:
    VnaiRateLimitExceeded = None

bp = Blueprint("main", __name__)


def _make_json_serializable(obj):
    """Convert numpy/pandas scalars to native Python so jsonify doesn't raise."""
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(v) for v in obj]
    return obj


@bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@bp.route("/favicon.ico", methods=["GET"])
def favicon():
    return "", 204  # No content - avoids 404 in console


@bp.route("/sample_tickers", methods=["GET"])
def sample_tickers():
    """Return list of available sample tickers when USE_SAMPLE_DATA is True."""
    if not current_app.config.get("USE_SAMPLE_DATA", False):
        return jsonify({"available_samples": []})
    sample_dir = os.path.join(current_app.root_path, "sample_data")
    output_dir = current_app.config.get("OUTPUT_DIR")
    tickers = _list_sample_tickers(sample_dir, output_dir)
    return jsonify({"available_samples": tickers})


def _parse_run_financials_request():
    """Parse symbol and include_peers from request."""
    if request.is_json:
        body = request.json or {}
        symbol = body.get("symbol", "").strip()
        include_peers = body.get("include_peers", True)
    else:
        symbol = request.form.get("symbol", "").strip()
        include_peers = request.form.get("include_peers", "true").lower() in ("true", "1", "yes")
    return symbol, include_peers


@bp.route("/run_financials", methods=["POST"])
def run_financials():
    symbol, include_peers = _parse_run_financials_request()
    if not symbol:
        return jsonify({"records": [], "error": "Symbol is required."}), 400
    try:
        # Fetch financial data
        print("[run_financials] Step 1: get_financial_ratios")
        data, error, actual_symbol, available_samples = get_financial_ratios(symbol)
        if error:
            return jsonify({"records": [], "error": error}), 400

        market_symbol = actual_symbol if actual_symbol else symbol
        print("[run_financials] Step 2: get_daily_summary")
        market_data, market_error, shares_outstanding = get_daily_summary(market_symbol)

        print("[run_financials] Step 3: get_company_info")
        company_name, sector_industry, _ = get_company_info(market_symbol)
        # In sample mode, load saved meta first so get_industry_peers can use industry_peers.json with company name
        saved_name, saved_sector, saved_peers = get_company_meta_from_samples(market_symbol)
        if saved_name and not company_name:
            company_name = saved_name
        if saved_sector and not sector_industry:
            sector_industry = saved_sector
        latest_close = None
        if market_data:
            last = market_data[-1]
            latest_close = last.get("close")
        our_market_cap_vnd = None
        if latest_close is not None and shares_outstanding is not None:
            try:
                our_market_cap_vnd = float(latest_close) * 1000.0 * float(shares_outstanding)
            except (TypeError, ValueError):
                our_market_cap_vnd = None

        peers = []
        peer_extra = {}
        if include_peers:
            print("[run_financials] Step 4: get_industry_peers")
            try:
                peers, peer_extra = get_industry_peers(
                    market_symbol,
                    our_market_cap_vnd,
                    shares_outstanding,
                    company_name,
                    sector_industry,
                )
            except Exception as peer_err:
                print(f"Warning: get_industry_peers failed for {market_symbol}: {peer_err}")
            print("[run_financials] Step 5: get_company_meta_from_samples (merge peers if needed)")
            if saved_peers and not peers:
                peers = saved_peers

        if not current_app.config.get("USE_SAMPLE_DATA", False) and (company_name or sector_industry or peers):
            print("[run_financials] Step 6: update_sample_company_meta")
            update_sample_company_meta(market_symbol, company_name, sector_industry, peers)

        print("[run_financials] Step 7: build payload and jsonify")
        payload = {"records": data}
        if actual_symbol is not None:
            payload["actual_symbol"] = actual_symbol
        if available_samples is not None:
            payload["available_samples"] = available_samples
        if company_name:
            payload["company_name"] = company_name
        if sector_industry:
            payload["sector_industry"] = sector_industry
        if peers:
            payload["peers"] = peers
        if peer_extra:
            if peer_extra.get("peers_pending_symbols") is not None:
                payload["peers_pending_symbols"] = peer_extra["peers_pending_symbols"]
            if peer_extra.get("peers_note"):
                payload["peers_note"] = peer_extra["peers_note"]
        payload["market"] = market_data if not market_error else []
        if shares_outstanding is not None:
            payload["shares_outstanding"] = shares_outstanding
        if market_error:
            print(f"Warning: Market data fetch failed for {market_symbol}: {market_error}")

        return jsonify(_make_json_serializable(payload))
    except Exception as exc:  # pragma: no cover - generic safety net
        err_msg = str(exc)[:500]  # truncate for safety
        print("Error in /run_financials:", exc)
        print("Traceback:\n" + traceback.format_exc())
        # Include error detail for debugging (Render/deployment)
        return jsonify({"records": [], "error": f"Server error: {err_msg}"}), 500


@bp.route("/run_peers", methods=["POST"])
def run_peers():
    """Fetch peer list only (market data + company info + industry peers)."""
    if request.is_json:
        symbol = (request.json or {}).get("symbol", "").strip()
    else:
        symbol = request.form.get("symbol", "").strip()
    if not symbol:
        return jsonify({"peers": [], "error": "Symbol is required."}), 400
    try:
        market_symbol = symbol
        print("[run_peers] Step 1: get_daily_summary")
        market_data, market_error, shares_outstanding = get_daily_summary(market_symbol)
        print("[run_peers] Step 2: get_company_info")
        company_name, sector_industry, _ = get_company_info(market_symbol)
        saved_name, saved_sector, saved_peers = get_company_meta_from_samples(market_symbol)
        if saved_name and not company_name:
            company_name = saved_name
        if saved_sector and not sector_industry:
            sector_industry = saved_sector
        latest_close = None
        if market_data:
            last = market_data[-1]
            latest_close = last.get("close")
        our_market_cap_vnd = None
        if latest_close is not None and shares_outstanding is not None:
            try:
                our_market_cap_vnd = float(latest_close) * 1000.0 * float(shares_outstanding)
            except (TypeError, ValueError):
                our_market_cap_vnd = None
        print("[run_peers] Step 3: get_industry_peers")
        peers, peer_extra = get_industry_peers(
            market_symbol,
            our_market_cap_vnd,
            shares_outstanding,
            company_name,
            sector_industry,
        )
        if saved_peers and not peers:
            peers = saved_peers
        if not current_app.config.get("USE_SAMPLE_DATA", False) and (company_name or sector_industry or peers):
            update_sample_company_meta(market_symbol, company_name, sector_industry, peers)
        payload = {
            "peers": peers,
            "actual_symbol": market_symbol,
            "company_name": company_name or None,
            "sector_industry": sector_industry or None,
            "market": market_data if not market_error else [],
            "shares_outstanding": shares_outstanding,
        }
        if peer_extra.get("peers_pending_symbols") is not None:
            payload["peers_pending_symbols"] = peer_extra["peers_pending_symbols"]
        if peer_extra.get("peers_note"):
            payload["peers_note"] = peer_extra["peers_note"]
        return jsonify(_make_json_serializable(payload))
    except Exception as exc:
        err_msg = str(exc)[:500]
        print("Error in /run_peers:", exc)
        print("Traceback:\n" + traceback.format_exc())
        return jsonify({"peers": [], "error": f"Server error: {err_msg}"}), 500


@bp.route("/download/<symbol>", methods=["GET"])
def download(symbol: str):
    symbol = (symbol or "").upper()
    output_dir = current_app.config.get("OUTPUT_DIR")
    path = os.path.join(output_dir, f"{symbol}_result.csv")
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    # Generate CSV from sample store and save to output (only on explicit Download)
    records = get_sample_records_for_download(symbol)
    if records:
        df = pd.DataFrame(records)
        os.makedirs(output_dir, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return send_file(path, as_attachment=True)
    return "File not found", 404


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ============================================================================
# Market Data Endpoints (Share Price & Trading Data)
# ============================================================================

@bp.route("/market/daily_summary", methods=["POST"])
def market_daily_summary():
    """
    Get daily summary data: closing price, average price, and market cap.
    
    Request body:
        {
            "symbol": "HPG",
            "start_date": "2024-01-01",  // optional
            "end_date": "2024-12-31",    // optional
            "source": "KBS"               // optional: KBS, VCI, TCBS
        }
    
    Response:
        {
            "records": [
                {"date": "2024-01-01", "close": 103.5, "average": 102.0, "market_cap": 1500000000000},
                ...
            ],
            "error": null  // or error message if failed
        }
    """
    if not request.is_json:
        return jsonify({"records": [], "error": "JSON request body required"}), 400
    
    symbol = (request.json or {}).get("symbol", "").strip()
    start_date = (request.json or {}).get("start_date")
    end_date = (request.json or {}).get("end_date")
    source = (request.json or {}).get("source")
    
    if not symbol:
        return jsonify({"records": [], "error": "Symbol is required"}), 400
    
    try:
        data, error, shares_outstanding = get_daily_summary(symbol, start_date, end_date, source)
        if error:
            return jsonify({"records": [], "error": error}), 400
        payload = {"records": data}
        if shares_outstanding is not None:
            payload["shares_outstanding"] = shares_outstanding
        return jsonify(_make_json_serializable(payload))
    except Exception as exc:
        print("Error in /market/daily_summary:", exc)
        return jsonify({"records": [], "error": "Unexpected server error"}), 500


# Delay between each peer symbol to stay under 20 req/min (VNStock Guest). Each symbol uses ~2–4 API calls.
PEER_VALUATION_DELAY_SEC = 18
PEER_VALUATION_RATE_LIMIT_MAX_RETRIES = 5


def _is_rate_limit_error(msg):
    """True if the error message indicates API rate limit (e.g. VNStock 'Chờ 25 giây')."""
    if not msg:
        return False
    s = str(msg).lower()
    msg_raw = str(msg)
    return (
        "rate limit" in s
        or "giới hạn" in msg_raw
        or "đạt tối đa" in msg_raw
        or ("chờ" in msg_raw and "giây" in msg_raw)
        or "giây để tiếp tục" in msg_raw
        or "retry" in s
        or "20/20" in msg_raw
        or "requests/phút" in msg_raw
    )


def _parse_wait_seconds_from_error(msg):
    """Parse retry-after seconds from rate limit error message. Default 30."""
    if not msg:
        return 30
    msg = str(msg)
    for pat in [
        r"chờ (\d+) giây",
        r"(\d+) giây để tiếp tục",
        r"[Rr]etry after (\d+) seconds?",
        r"wait (\d+)",
    ]:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            try:
                return max(1, int(m.group(1)))
            except (TypeError, ValueError):
                pass
    return 30


def _get_wait_seconds_for_rate_limit(err_msg_or_exc):
    """Get wait seconds from RateLimitError/RateLimitExceeded exception or from error message. Returns int."""
    if VnstockRateLimitError and isinstance(err_msg_or_exc, VnstockRateLimitError):
        details = getattr(err_msg_or_exc, "details", None) or {}
        sec = details.get("retry_after")
        if sec is not None:
            try:
                return max(1, int(sec))
            except (TypeError, ValueError):
                pass
    if VnaiRateLimitExceeded and isinstance(err_msg_or_exc, VnaiRateLimitExceeded):
        sec = getattr(err_msg_or_exc, "retry_after", None)
        if sec is not None:
            try:
                return max(1, int(sec))
            except (TypeError, ValueError):
                pass
    return _parse_wait_seconds_from_error(str(err_msg_or_exc) if err_msg_or_exc else None)


@bp.route("/run_peer_valuations", methods=["POST"])
def run_peer_valuations():
    """
    Fetch 52w price data + financial data for peer symbols for 52w P/E, P/B, EV/EBITDA.
    Request body: { "symbols": ["VJC", "HVN", ...], "target_symbol": "HPG", "scope": "icb"|"broader"|"all",
                    "industry_code": optional for broader, "market_caps": optional { "VJC": 98e12 } for broader }
    In sample mode (USE_SAMPLE_DATA): reads from peer_valuation_samples.json; does not write samples.json/market_samples.json.
    In live mode: fetches with skip_store=True, then saves to peer_valuation_samples.json (icb_peers or industry_top5).
    Response: { "peer_valuations": [ { "symbol", "market_data", "records", "shares_outstanding" }, ... ], "errors": { "SYM": "msg" } }
    """
    if not request.is_json:
        return jsonify({"peer_valuations": [], "errors": {}, "error": "JSON body required"}), 400
    body = request.json or {}
    symbols = body.get("symbols")
    if not isinstance(symbols, list):
        return jsonify({"peer_valuations": [], "errors": {}, "error": "symbols array required"}), 400
    symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    target_symbol = (body.get("target_symbol") or "").strip().upper()
    scope = (body.get("scope") or "icb").strip().lower() or "icb"
    industry_code = body.get("industry_code")
    market_caps = body.get("market_caps") if isinstance(body.get("market_caps"), dict) else None
    icb_symbols = body.get("icb_symbols")
    if isinstance(icb_symbols, list):
        icb_symbols = {str(s).strip().upper() for s in icb_symbols if str(s).strip()}
    else:
        icb_symbols = None

    use_sample = current_app.config.get("USE_SAMPLE_DATA", False)

    if use_sample:
        # Read from peer_valuation_samples.json. Return data for ALL requested symbols (displayed peers).
        t = target_symbol or (symbols[0] if symbols else "")
        requested = {str(s).strip().upper() for s in (symbols or []) if str(s).strip()}
        icb_data = get_icb_peers_for_target(t) or []
        code = industry_code
        if code is None and t:
            code, _ = find_industry_by_symbol(t)
        top5_data = (get_industry_top5(code) or []) if code is not None else []
        by_sym = {}
        for p in icb_data + top5_data:
            sym = (p.get("symbol") or "").strip().upper()
            if sym and sym not in by_sym:
                by_sym[sym] = p
        # Return data for all requested symbols (fetched/displayed peers); fallback to full list if none requested
        if requested:
            peer_valuations = [by_sym[s] for s in requested if s in by_sym]
        else:
            peer_valuations = icb_data if scope == "icb" else top5_data
        return jsonify(_make_json_serializable({"peer_valuations": peer_valuations, "errors": {}}))

    # Live mode: fetch with skip_store=True, then save to peer store
    if not symbols:
        return jsonify({"peer_valuations": [], "errors": {}})

    end_date = date.today()
    start_52w = end_date - timedelta(days=365)
    start_str = start_52w.isoformat()
    end_str = end_date.isoformat()

    peer_valuations = []
    errors = {}
    for i, sym in enumerate(symbols):
        if i > 0:
            time.sleep(PEER_VALUATION_DELAY_SEC)
        added = False
        for retry in range(PEER_VALUATION_RATE_LIMIT_MAX_RETRIES):
            try:
                market_data, market_err, shares_outstanding = get_daily_summary(
                    sym, start_str, end_str, skip_store=True
                )
                if market_err or not market_data:
                    if _is_rate_limit_error(market_err) and retry < PEER_VALUATION_RATE_LIMIT_MAX_RETRIES - 1:
                        wait_sec = _get_wait_seconds_for_rate_limit(market_err)
                        print(f"[run_peer_valuations] Rate limit for {sym} (market). Waiting {wait_sec}s then retry...")
                        time.sleep(wait_sec)
                        continue
                    errors[sym] = market_err or "No market data"
                    break
                records, fin_err, _, _ = get_financial_ratios(sym, skip_store=True)
                if fin_err or not records:
                    if _is_rate_limit_error(fin_err) and retry < PEER_VALUATION_RATE_LIMIT_MAX_RETRIES - 1:
                        wait_sec = _get_wait_seconds_for_rate_limit(fin_err)
                        print(f"[run_peer_valuations] Rate limit for {sym} (financials). Waiting {wait_sec}s then retry...")
                        time.sleep(wait_sec)
                        continue
                    errors[sym] = fin_err or "No financial data"
                    break
                peer_valuations.append({
                    "symbol": sym,
                    "market_data": market_data,
                    "records": records,
                    "shares_outstanding": shares_outstanding,
                })
                added = True
                break
            except Exception as e:
                err_msg = str(e)
                is_rate = (
                    (VnstockRateLimitError and isinstance(e, VnstockRateLimitError))
                    or (VnaiRateLimitExceeded and isinstance(e, VnaiRateLimitExceeded))
                    or _is_rate_limit_error(err_msg)
                )
                if is_rate and retry < PEER_VALUATION_RATE_LIMIT_MAX_RETRIES - 1:
                    wait_sec = _get_wait_seconds_for_rate_limit(e)
                    print(f"[run_peer_valuations] Rate limit for {sym}. Waiting {wait_sec}s then retry...")
                    time.sleep(wait_sec)
                    continue
                errors[sym] = err_msg
                break
        if not added and sym not in errors:
            errors[sym] = "No data after retries"

    # Persist to peer store (separate from samples.json / market_samples.json)
    t = target_symbol or (symbols[0] if symbols else "")
    # icb_peers: only peers with same ICB sector_industry (filter by icb_symbols when provided).
    # industry_top5: top 5 by market cap (scope == "broader" only).
    def _icb_peer_list():
        if not peer_valuations or not t:
            return []
        if icb_symbols is not None:
            return [p for p in peer_valuations if (p.get("symbol") or "").strip().upper() in icb_symbols]
        if scope == "icb":
            return peer_valuations
        return []

    if scope == "icb" and t and peer_valuations:
        save_icb_peers(t, _icb_peer_list() or peer_valuations)
    elif scope in ("broader", "all"):
        icb_only = _icb_peer_list()
        if t and icb_only:
            save_icb_peers(t, icb_only)
        code = industry_code
        ind_name = ""
        if code is None and t:
            code, ind_name = find_industry_by_symbol(t)
        if code is not None:
            caps = market_caps
            if not caps:
                ind = get_industry_from_cache(code)
                if ind and isinstance(ind.get("companies"), list):
                    caps = {str(c.get("symbol", "")).strip().upper(): (c.get("market_cap") or 0) for c in ind["companies"]}
            save_industry_top5(code, ind_name, peer_valuations, market_caps=caps)

    return jsonify(_make_json_serializable({"peer_valuations": peer_valuations, "errors": errors}))

