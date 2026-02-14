"""
Standalone script to backfill sector_industry (VCI sector · industry) for all companies
in app/sample_data/industry_peers.json that don't have it yet.

- Saves cache to disk after each successful fetch (and immediately on rate limit).
- On rate limit: saves progress, waits (parsed from error or default 60s), then retries.
- Repeats until every existing ticker has sector_industry or the API returns nothing.

Run from project root (with venv active):
  python debug/backfill_industry_sectors.py

Optional:
  python debug/backfill_industry_sectors.py --delay 2   (seconds between requests, default 1.5)
  python debug/backfill_industry_sectors.py --dry-run   (list missing only, no fetch/save)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional


def _cache_path():
    """Path to app/sample_data/industry_peers.json (script lives in debug/)."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(this_dir)
    return os.path.join(root, "app", "sample_data", "industry_peers.json")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sanitize(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def load_cache():
    path = _cache_path()
    if not os.path.isfile(path):
        print(f"[backfill] Cache not found: {path}")
        return None, path
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data, path


def save_cache(data, path):
    """Write cache to disk. Updates top-level 'updated'."""
    data = dict(data)
    data["updated"] = _now_iso()
    # Sanitize for JSON (e.g. numpy types)
    def _sanitize_for_json(obj):
        if hasattr(obj, "item") and callable(getattr(obj, "item")):
            return obj.item()
        if isinstance(obj, dict):
            return {k: _sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize_for_json(v) for v in obj]
        return obj
    data = _sanitize_for_json(data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[backfill] Saved to {path}")


def parse_wait_seconds(exc):
    """Parse retry-after from RateLimitError or message. Default 60."""
    if hasattr(exc, "details") and isinstance(getattr(exc, "details"), dict):
        sec = getattr(exc, "details", {}).get("retry_after")
        if sec is not None:
            try:
                return int(sec)
            except (TypeError, ValueError):
                pass
    msg = str(exc) or ""
    for pat in [r"[Rr]etry after (\d+) seconds?", r"Chờ (\d+) giây", r"(\d+) giây để tiếp tục"]:
        m = re.search(pat, msg)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                pass
    return 60


def fetch_sector_industry(symbol: str) -> Optional[str]:
    """Get VCI sector · industry for symbol. Returns None on failure or empty."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None
    try:
        from vnstock import Company
        company = Company(source="VCI", symbol=symbol, show_log=False)
        raw = getattr(company, "raw_data", None) or {}
        info = raw.get("CompanyListingInfo") or raw.get("company_listing_info") or {}
        if not isinstance(info, dict):
            return None
        n2 = info.get("enIcbName2") or info.get("icbName2")
        n4 = info.get("enIcbName4") or info.get("icbName4")
        if n2 or n4:
            return " · ".join(filter(None, [_sanitize(n2), _sanitize(n4)]))
    except Exception:
        pass
    return None


def collect_missing(data):
    """Return list of (industry_key, company_index, symbol) for companies missing sector_industry."""
    missing = []
    industries = data.get("industries") or {}
    for key, ind in industries.items():
        companies = ind.get("companies") or []
        for i, c in enumerate(companies):
            sym = (c.get("symbol") or "").strip().upper()
            if not sym:
                continue
            if (c.get("sector_industry") or "").strip():
                continue
            missing.append((key, i, sym))
    return missing


def run(delay_sec: float = 1.5, dry_run: bool = False):
    data, path = load_cache()
    if data is None:
        return 1
    missing = collect_missing(data)
    if not missing:
        print("[backfill] All companies already have sector_industry. Nothing to do.")
        return 0
    print(f"[backfill] Found {len(missing)} companies missing sector_industry.")
    if dry_run:
        for key, i, sym in missing[:50]:
            print(f"  {key} companies[{i}] {sym}")
        if len(missing) > 50:
            print(f"  ... and {len(missing) - 50} more")
        return 0

    industries = data.setdefault("industries", {})
    filled = 0
    while missing:
        key, idx, symbol = missing.pop(0)
        ind = industries.get(key)
        if not ind:
            continue
        companies = ind.get("companies") or []
        if idx >= len(companies):
            continue
        entry = companies[idx]
        if (entry.get("sector_industry") or "").strip():
            continue

        try:
            sector_industry = fetch_sector_industry(symbol)
        except Exception as exc:
            msg = str(exc).lower()
            try:
                from vnstock.core.exceptions import RateLimitError
                is_rate_limit = isinstance(exc, RateLimitError)
            except ImportError:
                is_rate_limit = False
            if is_rate_limit or "rate" in msg or "limit" in msg or "chờ" in msg or "retry" in msg:
                wait = parse_wait_seconds(exc)
                print(f"[backfill] Rate limit hit. Saving progress, then waiting {wait}s before retry...")
                save_cache(data, path)
                print(f"[backfill] Waiting {wait} seconds...")
                import time
                time.sleep(wait)
                missing.insert(0, (key, idx, symbol))
                continue
            print(f"[backfill] Error fetching {symbol}: {exc}")
            continue

        if sector_industry:
            entry["sector_industry"] = sector_industry
            ind["updated"] = _now_iso()
            filled += 1
            print(f"[backfill] [{filled}] {symbol} -> {sector_industry!r}")
            save_cache(data, path)
        else:
            print(f"[backfill] No sector_industry for {symbol} (API returned empty); skipping.")

        if delay_sec > 0 and missing:
            import time
            time.sleep(delay_sec)

    print(f"[backfill] Done. Filled sector_industry for {filled} companies.")
    return 0


def main():
    delay = 1.5
    dry_run = False
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--dry-run":
            dry_run = True
        elif a.startswith("--delay="):
            try:
                delay = float(a.split("=", 1)[1])
            except (IndexError, ValueError):
                pass
        elif a == "--delay" and i + 1 < len(argv):
            try:
                delay = float(argv[i + 1])
            except (ValueError, TypeError):
                pass
            break
    return run(delay_sec=delay, dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
