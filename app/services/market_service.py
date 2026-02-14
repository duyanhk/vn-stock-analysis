"""
Market data service using VNStock library.
Handles share price and trading data (separate from financial statements).
"""
import os
import json
import time
from datetime import datetime, timezone, date
from typing import List, Dict, Optional, Tuple
from flask import current_app
import pandas as pd


def _market_samples_path() -> str:
    """Return path to market_samples.json"""
    sample_dir = os.path.join(current_app.root_path, "sample_data")
    return os.path.join(sample_dir, "market_samples.json")


def _load_market_samples() -> Dict:
    """Load market samples from JSON file"""
    path = _market_samples_path()
    if not os.path.exists(path):
        return {"samples": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"samples": []}


def _save_market_samples(data: Dict) -> None:
    """Save market samples to JSON file"""
    path = _market_samples_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_market_sample(symbol: str, data_type: str) -> Tuple[Optional[List[Dict]], Optional[float]]:
    """
    Get market sample for a symbol and data type.
    Returns (data, shares_outstanding) or (None, None) if not found.
    """
    samples_data = _load_market_samples()
    samples = samples_data.get("samples", [])
    
    for sample in samples:
        if sample.get("symbol") == symbol.upper() and sample.get("data_type") == data_type:
            data = sample.get("data", [])
            shares = sample.get("shares_outstanding")
            return data, shares
    
    return None, None


def _fetch_shares_outstanding(symbol: str, source: str) -> Optional[float]:
    """
    Fetch shares outstanding from VNStock Company API.
    Quote.history() does NOT include shares - must use separate Company API.
    Raises RateLimitError (from vnstock or converted) on rate limit so caller can wait and retry.
    """
    import re
    try:
        from vnstock import Company
        from vnstock.core.exceptions import RateLimitError

        company = Company(source=source, symbol=symbol, show_log=False)

        if source.upper() == "VCI":
            info = getattr(company, "raw_data", {}) or {}
            info = info.get("CompanyListingInfo") or info.get("company_listing_info") or {}
            if isinstance(info, dict):
                val = info.get("issueShare") or info.get("issue_share")
                return _sanitize_for_json(val)
            return None

        if source.upper() == "KBS":
            df = company.overview()
            if df is not None and not df.empty and "outstanding_shares" in df.columns:
                val = df["outstanding_shares"].iloc[0]
                return _sanitize_for_json(val)
            return None

        return None
    except RateLimitError:
        raise
    except Exception as e:
        # vnstock/vnai may not raise RateLimitError; convert rate-limit-like messages so caller can wait
        msg = str(e).lower()
        if "rate limit" in msg or "giới hạn" in str(e) or "chờ" in str(e).lower() or "retry" in msg:
            retry_after = 60
            for pat in [r"chờ (\d+) giây", r"(\d+) giây để tiếp tục", r"retry after (\d+)"]:
                m = re.search(pat, str(e), re.IGNORECASE)
                if m:
                    try:
                        retry_after = int(m.group(1))
                        break
                    except (TypeError, ValueError):
                        pass
            raise RateLimitError(provider=source, retry_after=retry_after) from e
        return None


def _add_market_sample(symbol: str, data_type: str, data: List[Dict], params: Optional[Dict] = None, shares_outstanding: Optional[float] = None) -> None:
    """
    Add or update a market sample.
    Keeps only the last MARKET_SAMPLE_LIMIT samples.
    
    Args:
        symbol: Stock symbol
        data_type: Type of data (e.g., "daily_summary")
        data: List of historical records
        params: Optional parameters used for fetching
        shares_outstanding: Single value for shares outstanding (not repeated in each record)
    """
    samples_data = _load_market_samples()
    samples = samples_data.get("samples", [])
    
    # Remove existing sample for this symbol+data_type
    samples = [s for s in samples if not (s.get("symbol") == symbol.upper() and s.get("data_type") == data_type)]
    
    # Add new sample
    new_sample = {
        "symbol": symbol.upper(),
        "data_type": data_type,
        "updated": datetime.now(timezone.utc).isoformat(),
        "data": data
    }
    if params:
        new_sample["params"] = params
    if shares_outstanding is not None:
        new_sample["shares_outstanding"] = shares_outstanding
    
    samples.append(new_sample)
    
    # Keep only last N samples
    limit = current_app.config.get("MARKET_SAMPLE_LIMIT", 3)
    if len(samples) > limit:
        samples = samples[-limit:]
    
    samples_data["samples"] = samples
    _save_market_samples(samples_data)


def _sanitize_for_json(obj):
    """Convert NaN/inf to None for JSON serialization"""
    if isinstance(obj, float):
        if pd.isna(obj) or obj == float('inf') or obj == float('-inf'):
            return None
    return obj


def _df_to_records(df: pd.DataFrame) -> List[Dict]:
    """Convert DataFrame to JSON-serializable records"""
    if df.empty:
        return []
    
    records = df.reset_index().to_dict(orient="records")
    
    # Sanitize NaN/inf values
    for record in records:
        for key, value in record.items():
            record[key] = _sanitize_for_json(value)
    
    return records


def get_daily_summary(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = None,
    skip_store: bool = False,
) -> Tuple[List[Dict], Optional[str], Optional[float]]:
    """
    Get daily summary data for a symbol: closing price, average price, and shares outstanding.

    Args:
        symbol: Stock symbol (e.g., "HPG", "VCB")
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        source: Data source - "VCI" or "KBS" (uses config default if None)
        skip_store: If True, do not write to market_samples.json (e.g. when storing elsewhere).

    Returns:
        Tuple of (records, error_message, shares_outstanding)
        records: List of dicts with keys: date, close, average
        error_message: Error string if failed, None if successful
        shares_outstanding: Single value for number of shares (or None)
    """
    if not symbol:
        return [], "Symbol is required", None
    
    symbol = symbol.strip().upper()
    
    # Check if using sample data mode
    if current_app.config.get("USE_SAMPLE_DATA", False):
        data, shares = _get_market_sample(symbol, "daily_summary")
        if data is not None:
            return data, None, shares
        # If not found, return error
        return [], f"No sample data found for {symbol}", None
    
    # Live data mode - use VNStock
    if source is None:
        source = current_app.config.get("VNSTOCK_DEFAULT_SOURCE", "KBS")
    
    fallback_sources = current_app.config.get("VNSTOCK_FALLBACK_SOURCES", ["VCI", "TCBS"])
    sources_to_try = [source] + [s for s in fallback_sources if s != source]
    
    last_error = None
    for src in sources_to_try:
        try:
            from vnstock import Quote
            
            quote = Quote(symbol=symbol, source=src)
            
            # Get historical data: when no dates given, use N-year range from Jan 1 of start year
            if start_date and end_date:
                df = quote.history(start=start_date, end=end_date, interval="1D")
            elif start_date:
                df = quote.history(start=start_date, interval="1D")
            else:
                years = current_app.config.get("MARKET_PRICE_YEARS", 5)
                end_d = date.today()
                start_d = date(end_d.year - years, 1, 1)  # First day of year, N years ago
                start_date = start_d.isoformat()
                end_date = end_d.isoformat()
                df = quote.history(start=start_date, end=end_date, interval="1D")
            
            if df.empty:
                last_error = f"No data returned for {symbol}"
                continue
            
            # Extract only the fields we need
            # Calculate average price as (high + low) / 2
            # Note: Quote.history() does NOT include shares - fetch separately via Company API
            records = []
            
            for idx, row in df.iterrows():
                # Handle different index types (datetime, string, int, etc.)
                if isinstance(idx, str):
                    date_val = idx
                elif hasattr(idx, 'strftime'):
                    date_val = idx.strftime('%Y-%m-%d')
                else:
                    # If index is numeric or other type, try to get date from row
                    date_val = str(row.get('time', row.get('date', idx)))
                
                close_price = _sanitize_for_json(row.get('close'))
                high_price = _sanitize_for_json(row.get('high'))
                low_price = _sanitize_for_json(row.get('low'))
                
                # Calculate average price
                average_price = None
                if high_price is not None and low_price is not None:
                    average_price = (high_price + low_price) / 2
                
                records.append({
                    "date": date_val,
                    "close": close_price,
                    "average": average_price
                })
            
            # Fetch shares outstanding from Company API (separate call - not in Quote.history)
            shares_outstanding = _fetch_shares_outstanding(symbol, src)
            if shares_outstanding is None:
                # Try other sources (VCI/KBS) if primary failed
                for alt_src in ["VCI", "KBS"]:
                    if alt_src != src:
                        shares_outstanding = _fetch_shares_outstanding(symbol, alt_src)
                        if shares_outstanding is not None:
                            break
            if shares_outstanding is None and src != source:
                # Try primary source if fallback was used for history
                shares_outstanding = _fetch_shares_outstanding(symbol, source)
            
            if not skip_store:
                params = {
                    "start_date": start_date,
                    "end_date": end_date,
                    "source": src
                }
                _add_market_sample(symbol, "daily_summary", records, params, shares_outstanding)

            return records, None, shares_outstanding
            
        except Exception as e:
            try:
                from vnstock.core.exceptions import RateLimitError
                if isinstance(e, RateLimitError):
                    raise
            except ImportError:
                pass
            last_error = f"Error with {src}: {str(e)}"
            continue

    # All sources failed
    return [], last_error or f"Failed to fetch daily summary for {symbol}", None


def get_trading_stats(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    source: Optional[str] = None
) -> Tuple[List[Dict], Optional[str]]:
    """
    Get trading statistics for a symbol.
    
    Args:
        symbol: Stock symbol
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        source: Data source (uses config default if None)
    
    Returns:
        Tuple of (records, error_message)
        records: List of dicts with trading stats
    """
    if not symbol:
        return [], "Symbol is required"
    
    symbol = symbol.strip().upper()
    
    # Check if using sample data mode
    if current_app.config.get("USE_SAMPLE_DATA", False):
        data = _get_market_sample(symbol, "trading_stats")
        if data is not None:
            return data, None
        return [], f"No sample data found for {symbol}"
    
    # Live data mode
    if source is None:
        source = current_app.config.get("VNSTOCK_DEFAULT_SOURCE", "KBS")
    
    fallback_sources = current_app.config.get("VNSTOCK_FALLBACK_SOURCES", ["VCI", "TCBS"])
    sources_to_try = [source] + [s for s in fallback_sources if s != source]
    
    last_error = None
    for src in sources_to_try:
        try:
            from vnstock import Trading
            
            trading = Trading(source=src, symbol=symbol)
            
            # Get trading stats
            if start_date and end_date:
                df = trading.trading_stats(start=start_date, end=end_date)
            elif start_date:
                df = trading.trading_stats(start=start_date)
            else:
                # Default to last 30 days
                from datetime import datetime, timedelta
                end = datetime.now().strftime("%Y-%m-%d")
                start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                df = trading.trading_stats(start=start, end=end)
            
            if df.empty:
                last_error = f"No trading stats returned for {symbol}"
                continue
            
            records = _df_to_records(df)
            
            # Store in samples
            params = {
                "start_date": start_date,
                "end_date": end_date,
                "source": src
            }
            _add_market_sample(symbol, "trading_stats", records, params)
            
            return records, None
            
        except Exception as e:
            last_error = f"Error with {src}: {str(e)}"
            continue
    
    return [], last_error or f"Failed to fetch trading stats for {symbol}"


def get_intraday_data(
    symbol: str,
    page_size: int = 1000,
    source: Optional[str] = None
) -> Tuple[List[Dict], Optional[str]]:
    """
    Get intraday tick-by-tick data for a symbol.
    
    Args:
        symbol: Stock symbol
        page_size: Number of records to fetch (default 1000)
        source: Data source (uses config default if None)
    
    Returns:
        Tuple of (records, error_message)
        records: List of dicts with intraday tick data
    """
    if not symbol:
        return [], "Symbol is required"
    
    symbol = symbol.strip().upper()
    
    # Check if using sample data mode
    if current_app.config.get("USE_SAMPLE_DATA", False):
        data = _get_market_sample(symbol, "intraday")
        if data is not None:
            return data, None
        return [], f"No sample data found for {symbol}"
    
    # Live data mode
    if source is None:
        source = current_app.config.get("VNSTOCK_DEFAULT_SOURCE", "KBS")
    
    fallback_sources = current_app.config.get("VNSTOCK_FALLBACK_SOURCES", ["VCI", "TCBS"])
    sources_to_try = [source] + [s for s in fallback_sources if s != source]
    
    last_error = None
    for src in sources_to_try:
        try:
            from vnstock import Quote
            
            quote = Quote(symbol=symbol, source=src)
            df = quote.intraday(page_size=page_size)
            
            if df.empty:
                last_error = f"No intraday data returned for {symbol}"
                continue
            
            records = _df_to_records(df)
            
            # Store in samples
            params = {"page_size": page_size, "source": src}
            _add_market_sample(symbol, "intraday", records, params)
            
            return records, None
            
        except Exception as e:
            last_error = f"Error with {src}: {str(e)}"
            continue
    
    return [], last_error or f"Failed to fetch intraday data for {symbol}"


def get_price_board(
    symbols: List[str],
    source: Optional[str] = None,
    get_all: bool = False,
) -> Tuple[List[Dict], Optional[str]]:
    """
    Get current price board for multiple symbols.
    
    Args:
        symbols: List of stock symbols
        source: Data source (uses config default if None)
        get_all: If True, include all columns (e.g. listed_shares, organ_name) to avoid extra API calls for peers.
    
    Returns:
        Tuple of (records, error_message)
        records: List of dicts with current price info for each symbol
    """
    if not symbols or len(symbols) == 0:
        return [], "At least one symbol is required"

    symbols = [s.strip().upper() for s in symbols]

    # Note: Price board is real-time data, so we don't cache it in sample mode
    if current_app.config.get("USE_SAMPLE_DATA", False):
        return [], "Price board not available in sample data mode (real-time only)"

    if source is None:
        source = current_app.config.get("VNSTOCK_DEFAULT_SOURCE", "KBS")

    def _is_transient(err: Exception) -> bool:
        s = str(err).lower()
        return (
            "connectionerror" in s
            or "retryerror" in s
            or "timeout" in s
            or "connection" in s
            or isinstance(err, (ConnectionError, OSError))
        )

    max_attempts = 3
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            from vnstock import Trading

            trading = Trading(source=source)
            df = trading.price_board(symbols, get_all=get_all)

            if df.empty:
                return [], "No price board data returned"

            records = _df_to_records(df)
            return records, None
        except Exception as e:
            last_error = e
            if attempt < max_attempts and _is_transient(e):
                wait_sec = 4
                if current_app.config.get("DEBUG"):
                    print(f"[price_board] attempt {attempt} failed ({e!r}), retrying in {wait_sec}s ...")
                time.sleep(wait_sec)
                continue
            break
    return [], f"Failed to fetch price board: {str(last_error)}"
