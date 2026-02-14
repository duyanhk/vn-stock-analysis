"""
Separate store for peer valuation data (52w price + financials).
Does not touch samples.json or market_samples.json.

- icb_peers: up to 3 target symbols; each has peers (ICB-filtered) for that target.
- industry_top5: up to 3 industry codes; each has top 5 companies by market cap for that industry.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

PEER_STORE_FILENAME = "peer_valuation_samples.json"
MAX_ICB_TARGETS = 3
MAX_INDUSTRIES = 3
INDUSTRY_TOP_N = 5


def _store_path() -> str:
    sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
    return os.path.join(sample_dir, PEER_STORE_FILENAME)


def _fallback_path() -> str:
    try:
        from flask import current_app
        return os.path.join(current_app.root_path, "sample_data", PEER_STORE_FILENAME)
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_json(obj: Any) -> Any:
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    return obj


def load_peer_store() -> Dict[str, Any]:
    path = _store_path()
    if not os.path.isfile(path):
        alt = _fallback_path()
        if alt and os.path.isfile(alt):
            path = alt
    if not os.path.isfile(path):
        return {"icb_peers": [], "industry_top5": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("icb_peers", [])
            data.setdefault("industry_top5", [])
            return data
    except Exception:
        pass
    return {"icb_peers": [], "industry_top5": []}


def save_peer_store(data: Dict[str, Any]) -> None:
    path = _store_path()
    if not path or not os.path.isdir(os.path.dirname(path)):
        try:
            path = _fallback_path()
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            return
    data = dict(data)
    data.setdefault("icb_peers", [])
    data.setdefault("industry_top5", [])
    data = _sanitize_json(data)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_icb_peers_for_target(target_symbol: str) -> Optional[List[Dict[str, Any]]]:
    """Return list of peer data (market_data, records, shares_outstanding) for target_symbol, or None."""
    target_symbol = (target_symbol or "").strip().upper()
    if not target_symbol:
        return None
    data = load_peer_store()
    for entry in data.get("icb_peers") or []:
        if (entry.get("target_symbol") or "").strip().upper() == target_symbol:
            return entry.get("peers") or []
    return None


def get_industry_top5(industry_code) -> Optional[List[Dict[str, Any]]]:
    """Return list of top 5 company data for industry_code, or None."""
    key = str(industry_code) if industry_code is not None else ""
    if not key:
        return None
    data = load_peer_store()
    for entry in data.get("industry_top5") or []:
        if str(entry.get("industry_code")) == key:
            return entry.get("companies") or []
    return None


def save_icb_peers(target_symbol: str, peer_list: List[Dict[str, Any]]) -> None:
    """Save ICB peers for target_symbol. Keeps max MAX_ICB_TARGETS entries (newest by update)."""
    target_symbol = (target_symbol or "").strip().upper()
    if not target_symbol:
        return
    data = load_peer_store()
    entries = [e for e in (data.get("icb_peers") or []) if (e.get("target_symbol") or "").strip().upper() != target_symbol]
    entries.append({
        "target_symbol": target_symbol,
        "updated": _now_iso(),
        "peers": peer_list,
    })
    data["icb_peers"] = entries[-MAX_ICB_TARGETS:]
    save_peer_store(data)


def save_industry_top5(
    industry_code,
    industry_name: str,
    company_list: List[Dict[str, Any]],
    market_caps: Optional[Dict[str, float]] = None,
) -> None:
    """Save top 5 companies by market cap for industry. Keeps max MAX_INDUSTRIES entries."""
    key = str(industry_code) if industry_code is not None else ""
    if not key:
        return
    if market_caps:
        caps = {str(s).strip().upper(): float(c) for s, c in market_caps.items()}
        company_list = sorted(
            company_list,
            key=lambda c: caps.get((c.get("symbol") or "").strip().upper()) or 0,
            reverse=True,
        )[:INDUSTRY_TOP_N]
    else:
        company_list = company_list[:INDUSTRY_TOP_N]
    data = load_peer_store()
    entries = [e for e in (data.get("industry_top5") or []) if str(e.get("industry_code")) != key]
    entries.append({
        "industry_code": industry_code,
        "industry_name": industry_name or "",
        "updated": _now_iso(),
        "companies": company_list,
    })
    data["industry_top5"] = entries[-MAX_INDUSTRIES:]
    save_peer_store(data)
