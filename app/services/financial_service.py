from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional, Any

import json
import math
import os

import numpy as np
import pandas as pd
from flask import current_app

from app.services.vnstock_financial_service import fetch_financial_data_vnstock

SAMPLES_JSON = "samples.json"
MAX_SAMPLES = 3


def _sanitize_for_json(value):
    """
    Recursively make value JSON-serializable: NaN/inf -> None, numpy scalars -> native Python.
    """
    if hasattr(value, "item") and callable(getattr(value, "item")):
        return value.item()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    return value


def _samples_path(sample_dir: str) -> str:
    return os.path.join(sample_dir, SAMPLES_JSON)


def _load_samples(sample_dir: str) -> Optional[Dict[str, Any]]:
    """Load samples.json; return None if missing or invalid."""
    path = _samples_path(sample_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "samples" in data and isinstance(data["samples"], list):
            return data
    except Exception:
        pass
    return None


def _save_samples(sample_dir: str, payload: Dict[str, Any]) -> None:
    os.makedirs(sample_dir, exist_ok=True)
    path = _samples_path(sample_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _ensure_samples_from_output(sample_dir: str, output_dir: Optional[str]) -> None:
    """If samples.json does not exist, create it from output/*_result.csv (max 3)."""
    if _load_samples(sample_dir) is not None:
        return
    if not output_dir or not os.path.isdir(output_dir):
        return
    entries: List[Dict[str, Any]] = []
    files: List[Tuple[str, str, float]] = []  # (symbol, path, mtime)
    for name in os.listdir(output_dir):
        if name.endswith("_result.csv"):
            stem = name[: -len("_result.csv")]
            if stem:
                path = os.path.join(output_dir, name)
                try:
                    mtime = os.path.getmtime(path)
                    files.append((stem, path, mtime))
                except OSError:
                    pass
    files.sort(key=lambda x: x[2])  # oldest first
    for symbol, path, mtime in files[-MAX_SAMPLES:]:  # keep last 3
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            df = df.replace([np.inf, -np.inf], np.nan).where(pd.notna(df), None)
            records = df.to_dict(orient="records")
            records = _sanitize_for_json(records)
            updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            entries.append({"symbol": symbol, "updated": updated, "data": records})
        except Exception:
            continue
    if entries:
        _save_samples(sample_dir, {"samples": entries})


def _list_sample_tickers(sample_dir: str, output_dir: Optional[str] = None) -> List[str]:
    """List tickers from samples.json (create from output CSVs if missing)."""
    _ensure_samples_from_output(sample_dir, output_dir)
    data = _load_samples(sample_dir)
    if not data or not data.get("samples"):
        return []
    return [s["symbol"] for s in data["samples"]]


def _get_sample_by_symbol(
    sample_dir: str, output_dir: Optional[str], symbol: str
) -> Tuple[Optional[List[Dict]], Optional[str], List[str]]:
    """Return (records, actual_symbol, available_tickers). Fallback to newest if symbol not found."""
    _ensure_samples_from_output(sample_dir, output_dir)
    data = _load_samples(sample_dir)
    if not data or not data.get("samples"):
        return None, None, []
    samples_list = data["samples"]
    available = [s["symbol"] for s in samples_list]
    symbol_upper = symbol.upper()
    for entry in samples_list:
        if (entry.get("symbol") or "").upper() == symbol_upper:
            return entry.get("data"), entry.get("symbol"), available
    # Fallback: newest (last in list)
    last = samples_list[-1]
    return last.get("data"), last.get("symbol"), available


def get_sample_records_for_download(symbol: str) -> Optional[List[Dict]]:
    """Return records for symbol from the last-3-sample store (for CSV download)."""
    sample_dir = os.path.join(current_app.root_path, "sample_data")
    output_dir = current_app.config.get("OUTPUT_DIR")
    records, _, _ = _get_sample_by_symbol(sample_dir, output_dir, symbol)
    return records


def _add_sample(sample_dir: str, symbol: str, records: List[Dict]) -> None:
    """Add or update sample for symbol; keep last MAX_SAMPLES, drop oldest."""
    data = _load_samples(sample_dir)
    if not data:
        data = {"samples": []}
    samples_list = list(data["samples"])
    symbol_upper = symbol.upper()
    # Remove existing entry for this symbol
    samples_list = [s for s in samples_list if (s.get("symbol") or "").upper() != symbol_upper]
    updated = datetime.now(timezone.utc).isoformat()
    samples_list.append({"symbol": symbol, "updated": updated, "data": records})
    if len(samples_list) > MAX_SAMPLES:
        samples_list = samples_list[-MAX_SAMPLES:]
    _save_samples(sample_dir, {"samples": samples_list})


def get_company_meta_from_samples(symbol: str) -> Tuple[Optional[str], Optional[str], List[Dict]]:
    """
    Load saved company_name, sector_industry, and peers for a symbol from samples.json.
    Returns (company_name, sector_industry, peers). peers is [] if not stored.
    """
    sample_dir = os.path.join(current_app.root_path, "sample_data")
    data = _load_samples(sample_dir)
    if not data or not data.get("samples"):
        return None, None, []
    symbol_upper = (symbol or "").strip().upper()
    for entry in data["samples"]:
        if (entry.get("symbol") or "").upper() == symbol_upper:
            name = entry.get("company_name")
            sector = entry.get("sector_industry")
            peers = entry.get("peers")
            if not isinstance(peers, list):
                peers = []
            return name, sector, peers
    return None, None, []


def update_sample_company_meta(
    symbol: str,
    company_name: Optional[str],
    sector_industry: Optional[str],
    peers: Optional[List[Dict]],
) -> None:
    """
    Persist company_name, sector_industry, and peers for a symbol into samples.json.
    Updates the existing sample entry for that symbol if present.
    """
    if not symbol:
        return
    sample_dir = os.path.join(current_app.root_path, "sample_data")
    data = _load_samples(sample_dir)
    if not data or not data.get("samples"):
        return
    symbol_upper = symbol.strip().upper()
    for entry in data["samples"]:
        if (entry.get("symbol") or "").upper() == symbol_upper:
            if company_name is not None:
                entry["company_name"] = company_name
            if sector_industry is not None:
                entry["sector_industry"] = sector_industry
            if peers is not None:
                entry["peers"] = _sanitize_for_json(peers)
            _save_samples(sample_dir, data)
            return


def _fetch_with_vnstock(symbol: str, use_vnstock: bool, providers: List[str], include_quarterly: bool = False) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    Try to fetch financial data from VNStock with multiple providers.
    
    Returns (records, error_message).
    """
    if not use_vnstock:
        return None, "VNStock is disabled"
    
    last_error = None
    
    for provider in providers:
        try:
            print(f"Trying VNStock provider: {provider} ...")
            records, error = fetch_financial_data_vnstock(
                symbol,
                provider=provider,
                include_quarterly=include_quarterly
            )
            
            if records is not None and not error:
                print(f"Successfully fetched data for {symbol} from VNStock provider: {provider}")
                return records, None
            
            if error:
                print(f"  → {provider} failed: {error}")
            last_error = error
        except Exception as e:
            try:
                from vnstock.core.exceptions import RateLimitError
                if isinstance(e, RateLimitError):
                    raise
            except ImportError:
                pass
            last_error = f"VNStock provider {provider} failed: {str(e)}"
            print(f"  → {provider} failed: {e}")
            continue

    return None, last_error or "All VNStock providers failed"


def _fetch_with_vietstock_scraper(
    symbol: str,
    output_dir: str,
    headless: bool,
    timeout: int,
    window_size: str
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    Fallback to Vietstock web scraping (requires Selenium/Chrome).
    Only called when ENABLE_SELENIUM is True.

    Returns (records, error_message).
    """
    try:
        from app.scrapers.vietstock_financial import scrape_and_analyze

        df = scrape_and_analyze(
            symbol,
            output_dir=output_dir,
            headless=headless,
            timeout=timeout,
            window_size=window_size,
            save_csv=False,
        )
        
        if df is None or df.empty:
            return None, f"No financial data available for symbol '{symbol}' from Vietstock scraper."
        
        # Normalize values so JSON is valid: replace NaN/inf with None
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.where(pd.notna(df), None)
        
        # Ensure JSON-friendly format with Period as a column
        records = df.reset_index().to_dict(orient="records")
        records = _sanitize_for_json(records)
        
        print(f"Successfully fetched data for {symbol} from Vietstock scraper (fallback)")
        return records, None
        
    except ValueError as exc:
        # Domain errors (e.g. metric not found, no tables)
        return None, str(exc)
    except Exception as exc:
        return None, f"Vietstock scraper failed: {str(exc)}"


def get_financial_ratios(
    symbol: str,
    skip_store: bool = False,
) -> Tuple[List[Dict], Optional[str], Optional[str], Optional[List[str]]]:
    """
    Fetch financial data using VNStock (primary) with Vietstock scraping as fallback.

    Returns (records, error_message, actual_symbol, available_samples).
    - If error_message is not None, records will be an empty list.
    - When USE_SAMPLE_DATA and requested ticker is not found, we fall back to
      the latest sample file; actual_symbol is the ticker used, available_samples
      is the list of available ticker names.
    - skip_store: If True, do not write to samples.json (e.g. when storing in peer_valuation_samples).
    """
    if not symbol:
        return [], "Symbol is required.", None, None

    symbol = symbol.upper().strip()
    if not symbol:
        return [], "Symbol is required.", None, None

    cfg = current_app.config
    output_dir = cfg.get("OUTPUT_DIR")
    headless = cfg.get("SELENIUM_HEADLESS", True)
    timeout = cfg.get("SELENIUM_TIMEOUT", 20)
    window_size = cfg.get("SELENIUM_WINDOW_SIZE", "1920,1080")
    use_sample = cfg.get("USE_SAMPLE_DATA", False)
    use_vnstock = cfg.get("USE_VNSTOCK_PRIMARY", True)
    vnstock_providers = cfg.get("VNSTOCK_FINANCIAL_PROVIDERS", ["vci", "kbs"])
    vnstock_include_quarterly = cfg.get("VNSTOCK_INCLUDE_QUARTERLY", False)

    sample_dir = os.path.join(current_app.root_path, "sample_data")
    available_tickers = (
        _list_sample_tickers(sample_dir, output_dir) if use_sample else []
    )

    # If configured, serve from samples.json (last 3 samples with ticker)
    if use_sample and available_tickers:
        records, actual_symbol, available = _get_sample_by_symbol(
            sample_dir, output_dir, symbol
        )
        if records is not None:
            return records, None, actual_symbol, available
        return [], "No sample data available.", None, available_tickers

    if use_sample and not available_tickers:
        return [], "No sample data found. Run a scrape or add *_result.csv to output.", None, None

    # Try VNStock first (primary data source)
    records, vnstock_error = _fetch_with_vnstock(symbol, use_vnstock, vnstock_providers, vnstock_include_quarterly)
    
    if records is not None:
        # Success with VNStock
        if not skip_store:
            try:
                _add_sample(sample_dir, symbol, records)
            except Exception:
                pass

        return records, None, symbol, None

    # VNStock failed; try Vietstock scraper fallback only if Selenium is enabled
    enable_selenium = cfg.get("ENABLE_SELENIUM", False)
    if enable_selenium:
        print(f"VNStock failed for {symbol}: {vnstock_error}. Trying Vietstock scraper fallback...")
        records, scraper_error = _fetch_with_vietstock_scraper(
            symbol,
            output_dir,
            headless,
            timeout,
            window_size
        )
        if records is not None:
            if not skip_store:
                try:
                    _add_sample(sample_dir, symbol, records)
                except Exception:
                    pass
            return records, None, symbol, None
        combined_error = f"VNStock: {vnstock_error}. Vietstock scraper: {scraper_error}"
    else:
        combined_error = vnstock_error

    return [], combined_error, None, None

