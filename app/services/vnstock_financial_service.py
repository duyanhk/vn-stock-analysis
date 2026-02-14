"""
VNStock Financial Data Service

Fetches financial data using the VNStock library (primary data source).
Provides balance sheet, income statement, and cash flow data with calculated ratios.
VCI is default (more years, IBD, Financial Income); KBS is fallback.

Interest-bearing debt (short-term & long-term):
- VNStock (KBS and VCI) provides these (e.g. Short-term/Long-term borrowings).
- Vietstock scraping does NOT provide interest-bearing debt / loan; values will be null.
"""

from __future__ import annotations

import math
import time
from datetime import date
from typing import List, Dict, Tuple, Optional, Any
import pandas as pd
import numpy as np

# VNStock imports
try:
    from vnstock import Vnstock
except ImportError:
    Vnstock = None

# Rate limit handling
# VNStock Guest tier: 20 requests/minute = 1 request per 3 seconds
# Each API call takes ~3s naturally, so 2s added delay = 5s total per call (12 calls/min)
RATE_LIMIT_DELAY = 2  # seconds between API calls to avoid rate limits


def _sanitize_for_json(value):
    """Recursively replace NaN/inf values with None for strict JSON."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    return value


def _normalize_period(fiscal_year: Any, fiscal_quarter: Any = None, period_type: str = "annual") -> str:
    """
    Normalize period to format: YYYY-FY or YYYY-QN.
    
    Args:
        fiscal_year: Year value (int or string)
        fiscal_quarter: Quarter value (int or string), optional
        period_type: 'annual' or 'quarter'
    
    Returns:
        Normalized period string like "2024-FY" or "2024-Q3"
    """
    try:
        year = int(fiscal_year) if fiscal_year is not None else None
        if year is None:
            return None
        
        if period_type == "quarter" and fiscal_quarter is not None:
            quarter = int(fiscal_quarter)
            return f"{year}-Q{quarter}"
        else:
            return f"{year}-FY"
    except (ValueError, TypeError):
        return None


def _finance_call_kwargs(provider: str, period: str) -> Dict[str, Any]:
    """Kwargs for finance balance_sheet/income_statement/cash_flow. VCI uses lang=; KBS has no lang."""
    vnstock_period = "year" if period == "annual" else "quarter"
    kwargs: Dict[str, Any] = {"period": vnstock_period}
    if str(provider).lower() == "vci":
        kwargs["lang"] = "en"
    return kwargs


def _fetch_balance_sheet(symbol: str, period: str = "annual", provider: str = "vci") -> Optional[pd.DataFrame]:
    """
    Fetch balance sheet data from VNStock.
    
    Returns DataFrame with columns: fiscal_year, fiscal_quarter, period, items, values
    """
    if Vnstock is None:
        return None
    
    kwargs = _finance_call_kwargs(provider, period)
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        time.sleep(RATE_LIMIT_DELAY)  # Avoid rate limits
        df = stock.finance.balance_sheet(**kwargs)
        
        if df is None or df.empty:
            return None
        
        return df
    except Exception as e:
        error_msg = str(e).lower()
        if "rate limit" in error_msg:
            print(f"Rate limit hit for {symbol} balance sheet. Waiting 10 seconds...")
            time.sleep(10)
            try:
                df = stock.finance.balance_sheet(**kwargs)
                return df if df is not None and not df.empty else None
            except:
                pass
        print(f"Error fetching balance sheet for {symbol}: {e}")
        return None


def _fetch_income_statement(symbol: str, period: str = "annual", provider: str = "vci") -> Optional[pd.DataFrame]:
    """
    Fetch income statement data from VNStock.
    
    Returns DataFrame with columns: fiscal_year, fiscal_quarter, period, items, values
    """
    if Vnstock is None:
        return None
    
    kwargs = _finance_call_kwargs(provider, period)
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        time.sleep(RATE_LIMIT_DELAY)  # Avoid rate limits
        df = stock.finance.income_statement(**kwargs)
        
        if df is None or df.empty:
            return None
        
        return df
    except Exception as e:
        error_msg = str(e).lower()
        if "rate limit" in error_msg:
            print(f"Rate limit hit for {symbol} income statement. Waiting 10 seconds...")
            time.sleep(10)
            try:
                df = stock.finance.income_statement(**kwargs)
                return df if df is not None and not df.empty else None
            except:
                pass
        print(f"Error fetching income statement for {symbol}: {e}")
        return None


def _fetch_cash_flow(symbol: str, period: str = "annual", provider: str = "vci") -> Optional[pd.DataFrame]:
    """
    Fetch cash flow statement data from VNStock.
    
    Returns DataFrame with columns: fiscal_year, fiscal_quarter, period, items, values
    """
    if Vnstock is None:
        return None
    
    kwargs = _finance_call_kwargs(provider, period)
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        time.sleep(RATE_LIMIT_DELAY)  # Avoid rate limits
        df = stock.finance.cash_flow(**kwargs)
        
        if df is None or df.empty:
            return None
        
        return df
    except Exception as e:
        error_msg = str(e).lower()
        if "rate limit" in error_msg:
            print(f"Rate limit hit for {symbol} cash flow. Waiting 10 seconds...")
            time.sleep(10)
            try:
                df = stock.finance.cash_flow(**kwargs)
                return df if df is not None and not df.empty else None
            except:
                pass
        print(f"Error fetching cash flow for {symbol}: {e}")
        return None


def _get_income_value(row: Any, keys: List[str]) -> Optional[float]:
    """Get first matching income-statement value from row; convert VND to millions VND."""
    for k in keys:
        val = row.get(k) if hasattr(row, 'get') else None
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                return float(val) / 1_000_000
            except (TypeError, ValueError):
                pass
    return None


def _get_balance_value(row: Any, keys: List[str]) -> Optional[float]:
    """Get first matching balance-sheet value from row; convert VND to millions VND."""
    for k in keys:
        val = row.get(k) if hasattr(row, 'get') else None
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                return float(val) / 1_000_000
            except (TypeError, ValueError):
                pass
    return None


def _get_cash_flow_value(
    cash_df: Optional[pd.DataFrame],
    year: int,
    quarter: Optional[Any],
    keys: List[str],
) -> Optional[float]:
    """Get first matching cash-flow value for the given period; convert VND to millions VND."""
    if cash_df is None or cash_df.empty or "yearReport" not in cash_df.columns:
        return None
    if quarter is not None and not pd.isna(quarter):
        rows = cash_df[(cash_df["yearReport"] == year) & (cash_df["lengthReport"] == quarter)]
    else:
        has_len = "lengthReport" in cash_df.columns
        if has_len:
            rows = cash_df[(cash_df["yearReport"] == year) & (cash_df["lengthReport"].isna())]
        else:
            rows = cash_df[cash_df["yearReport"] == year]
    if rows.empty:
        return None
    row = rows.iloc[0]
    for k in keys:
        val = row.get(k)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                return float(val) / 1_000_000
            except (TypeError, ValueError):
                pass
    return None


# ---------------------------------------------------------------------------
# KBS long-format support (each row = line item, columns = years)
# Note: KBS (KB Securities) API returns only 4 periods (years) per response.
# The number of years is determined by the API response Head; VNStock does not
# expose a lookback/years parameter for KBS. For more history, use VCI provider.
# ---------------------------------------------------------------------------

def _is_kbs_long_format(balance_df: pd.DataFrame, income_df: pd.DataFrame) -> bool:
    """True if DataFrames are KBS long format: have item_id and year columns, no yearReport."""
    if balance_df is None or income_df is None or balance_df.empty or income_df.empty:
        return False
    bc = set(balance_df.columns)
    ic = set(income_df.columns)
    has_item_id = "item_id" in bc and "item_id" in ic
    has_year_report = "yearReport" in bc or "yearReport" in ic
    year_cols = [c for c in bc if str(c).isdigit() and len(str(c)) == 4]
    return bool(has_item_id and not has_year_report and year_cols)


def _get_kbs_year_columns(df: pd.DataFrame) -> List[str]:
    """Return column names that are 4-digit years, sorted descending."""
    year_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 4]
    return sorted(year_cols, key=int, reverse=True)


def _kbs_long_value(
    df: pd.DataFrame,
    item_id_candidates: List[str],
    year_col: str,
) -> Optional[float]:
    """
    From KBS long-format DataFrame, find row where item_id matches any candidate,
    return value for year_col; convert to millions VND.
    KBS API returns values in thousands VND, so divide by 1,000 to get millions.
    Prefer exact match, then first partial match by candidate order.
    """
    if df is None or df.empty or "item_id" not in df.columns or year_col not in df.columns:
        return None
    candidates_set = {c.lower() for c in item_id_candidates}
    partial_matches: List[Tuple[str, float]] = []
    for _, row in df.iterrows():
        item_id = row.get("item_id")
        if item_id is None or pd.isna(item_id):
            continue
        if not isinstance(item_id, str):
            continue
        val = row.get(year_col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        try:
            # KBS returns thousands VND; ÷ 1,000 → millions VND (match VCI output unit)
            v = float(val) / 1_000
        except (TypeError, ValueError):
            continue
        if item_id.lower() in candidates_set:
            return v
        for c in item_id_candidates:
            if c.lower() in item_id.lower():
                partial_matches.append((c, v))
                break
    for c in item_id_candidates:
        for cand, v in partial_matches:
            if cand == c:
                return v
    return None


# KBS item_id candidates (long format): try exact then partial match
_KBS_REVENUE_IDS = ["n_3.net_revenue", "n_1.revenue", "net_revenue", "revenue"]
_KBS_NET_INCOME_IDS = [
    "net_profit_after_tax", "net_profit", "profit_after_tax", "loi_nhuan_sau_thue",
    "net_profit_attributable_parent", "n_13.net_profit", "n_14.net_profit",
]
_KBS_EQUITY_IDS = [
    "i.owners_equity", "b.owners_equity", "owners_equity",
    "equity", "total_equity", "von_chu_so_huu", "owner_equity",
    "i_von_chu_so_huu", "b_von_chu_so_huu",
]
_KBS_LIABILITY_IDS = ["a.liabilities", "liabilities", "total_liabilities", "tong_no_phai_tra"]
_KBS_FINANCIAL_INCOME_IDS = [
    "doanh_thu_hoat_dong_tai_chinh",
    "doanh_thu_tu_hoat_dong_tai_chinh",
    "financial_income",
    "financial_revenue",
    "income_from_financial_activities",
    "thu_nhap_hoat_dong_tai_chinh",
    "thu_nhap_tu_hoat_dong_tai_chinh",
    "revenue_from_financial_activities",
]
_KBS_CASH_IDS = ["i.cash_and_cash_equivalents", "cash_and_cash_equivalents"]
_KBS_CASH_INVESTMENT_IDS = ["short_term_financial_investments", "short_term_investments", "financial_investments"]
_KBS_LONG_TERM_INVESTMENTS_IDS = ["v.long_term_financial_investments", "long_term_financial_investments"]
_KBS_PROFIT_BEFORE_TAX_IDS = ["n_15.profit_before_tax", "profit_before_tax"]
_KBS_INTEREST_EXPENSE_IDS = ["of_which_interest_expenses", "interest_expenses"]
_KBS_FINANCIAL_EXPENSES_IDS = ["n_7.financial_expenses", "financial_expenses"]
_KBS_DEPRECIATION_CF_IDS = [
    "depreciation_of_fixed_assets_and_properties_investment",
    "depreciation_and_amortisation",
]


def _build_financial_records_from_kbs_long(
    balance_df: pd.DataFrame,
    income_df: pd.DataFrame,
    cash_df: Optional[pd.DataFrame] = None,
    quarters_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Build financial records from KBS long-format DataFrames.
    Each row = line item (item_id), columns = years (e.g. 2024, 2023).
    One record per year (annual only for now; quarterly would need period columns).
    KBS API returns only 4 years per request; we use whatever year columns exist.
    """
    if balance_df is None or balance_df.empty or income_df is None or income_df.empty:
        return []
    year_cols = _get_kbs_year_columns(balance_df)
    if not year_cols:
        return []
    if quarters_only:
        return []  # KBS annual long format: no quarter columns in same shape
    records = []
    for year_col in year_cols:
        year = int(year_col)
        period_str = f"{year}-FY"
        revenue = _kbs_long_value(income_df, _KBS_REVENUE_IDS, year_col)
        net_income = _kbs_long_value(income_df, _KBS_NET_INCOME_IDS, year_col)
        equity = _kbs_long_value(balance_df, _KBS_EQUITY_IDS, year_col)
        liability = _kbs_long_value(balance_df, _KBS_LIABILITY_IDS, year_col)
        cash = _kbs_long_value(balance_df, _KBS_CASH_IDS, year_col)
        cash_investment = _kbs_long_value(balance_df, _KBS_CASH_INVESTMENT_IDS, year_col)
        long_term_investments = _kbs_long_value(balance_df, _KBS_LONG_TERM_INVESTMENTS_IDS, year_col)
        financial_income = _kbs_long_value(income_df, _KBS_FINANCIAL_INCOME_IDS, year_col)
        operating_income = _kbs_long_value(income_df, ["operating_profit", "loi_nhuan_thuan_hoat_dong_kinh_doanh"], year_col)
        profit_before_tax = _kbs_long_value(income_df, _KBS_PROFIT_BEFORE_TAX_IDS, year_col)
        interest_expense = _kbs_long_value(income_df, _KBS_INTEREST_EXPENSE_IDS, year_col)
        financial_expense = _kbs_long_value(income_df, _KBS_FINANCIAL_EXPENSES_IDS, year_col)
        ibd_short = _kbs_long_value(balance_df, ["short_term_borrowings", "short_term_loans", "vay_ngan_han"], year_col)
        ibd_long = _kbs_long_value(balance_df, ["long_term_borrowings", "long_term_loans", "vay_dai_han"], year_col)
        depreciation_expense = (
            _kbs_long_value(cash_df, _KBS_DEPRECIATION_CF_IDS, year_col)
            if cash_df is not None and not cash_df.empty else None
        )
        record = {
            "Period": period_str,
            "PeriodType": "Year",
            "Revenue": revenue,
            "Net Income": net_income,
            "Financial Income": financial_income,
            "Operating Income": operating_income,
            "Equity": equity,
            "Liability": liability,
            "Cash And Equivalent": cash,
            "Cash Investment": cash_investment,
            "Long Term Investments": long_term_investments,
            "Profit Before Tax": profit_before_tax,
            "Interest Expense": interest_expense,
            "Financial Expense": financial_expense,
            "Depreciation Expense": depreciation_expense,
            "Interest Bearing Debt Short Term": ibd_short,
            "Interest Bearing Debt Long Term": ibd_long,
        }
        if net_income is not None and equity is not None and equity != 0:
            record["ROE"] = net_income / equity
        else:
            record["ROE"] = None
        if net_income is not None and equity is not None and liability is not None:
            invested = equity + liability
            if cash is not None:
                invested -= cash
            if cash_investment is not None:
                invested -= cash_investment
            record["ROIC"] = net_income / invested if invested != 0 else None
        else:
            record["ROIC"] = None
        if net_income is not None and revenue is not None and revenue != 0:
            record["Net Profit Margin"] = net_income / revenue
        else:
            record["Net Profit Margin"] = None
        records.append(record)
    records = _calculate_yoy_growth(records)
    return records


def _extract_line_item(df: pd.DataFrame, search_terms: List[str], fiscal_year: int, fiscal_quarter: Optional[int] = None) -> Optional[float]:
    """
    Extract a specific line item value from financial statement DataFrame.
    
    Args:
        df: Financial statement DataFrame
        search_terms: List of possible names for the line item (case-insensitive)
        fiscal_year: Year to filter
        fiscal_quarter: Quarter to filter (optional)
    
    Returns:
        The value if found, None otherwise
    """
    if df is None or df.empty:
        return None
    
    # Filter by fiscal period
    filtered = df[df['fiscal_year'] == fiscal_year]
    if fiscal_quarter is not None and 'fiscal_quarter' in df.columns:
        filtered = filtered[filtered['fiscal_quarter'] == fiscal_quarter]
    
    if filtered.empty:
        return None
    
    # Search for line item
    for term in search_terms:
        matches = filtered[filtered['items'].str.contains(term, case=False, na=False)]
        if not matches.empty:
            value = matches.iloc[0]['values']
            if pd.notna(value):
                return float(value)
    
    return None


def _build_financial_records(
    balance_df: pd.DataFrame,
    income_df: pd.DataFrame,
    cash_df: Optional[pd.DataFrame] = None,
    quarters_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Build financial records from VNStock DataFrames.
    
    VNStock returns data in wide format (each metric is a column).
    We need to convert it to our record format.
    
    When quarters_only=True (used for quarterly DataFrames), skip rows without
    a valid quarter (lengthReport). This avoids emitting duplicate FY entries
    when the quarterly API also returns full-year summary rows.
    
    Returns:
        List of records, each containing Period and financial metrics
    """
    if balance_df is None or balance_df.empty or income_df is None or income_df.empty:
        return []
    
    records = []
    
    # VNStock format: each row is a period, columns are metrics
    # Merge balance and income data by year (and quarter if present)
    for idx, balance_row in balance_df.iterrows():
        year = balance_row.get('yearReport')
        quarter = balance_row.get('lengthReport')  # For quarterly data
        
        if year is None or pd.isna(year):
            continue
        
        # When building from quarterly DataFrames, only emit rows that have a quarter
        # (avoid duplicate FY when API returns full-year summary rows in quarterly response)
        if quarters_only:
            if quarter is None or pd.isna(quarter):
                continue
            period_str = f"{int(year)}-Q{int(quarter)}"
            period_type = 'Quarter'
        elif quarter is not None and not pd.isna(quarter):
            # Quarterly data
            period_str = f"{int(year)}-Q{int(quarter)}"
            period_type = 'Quarter'
        else:
            # Annual data
            period_str = f"{int(year)}-FY"
            period_type = 'Year'
        
        # Find matching income row
        if quarter is not None and not pd.isna(quarter):
            income_row = income_df[
                (income_df['yearReport'] == year) & 
                (income_df['lengthReport'] == quarter)
            ]
        else:
            income_row = income_df[
                (income_df['yearReport'] == year) & 
                (income_df['lengthReport'].isna() if 'lengthReport' in income_df.columns else True)
            ]
        
        if income_row.empty:
            continue
        
        income_row = income_row.iloc[0]
        
        # Extract values
        # VNStock column names say "(Bn. VND)" but actually return raw VND values
        # Convert: VND → Millions VND (÷ 1,000,000) to match Vietstock scraper
        # Revenue: Use Net Sales to match Vietstock "Doanh thu thuần" (net revenue)
        revenue = income_row.get('Net Sales')
        if pd.isna(revenue):
            revenue = income_row.get('Revenue (Bn. VND)')
        revenue = float(revenue) / 1_000_000 if pd.notna(revenue) else None
        
        # Net Income: Use Net Profit For the Year to match Vietstock "Lợi nhuận sau thuế"
        net_income = income_row.get('Net Profit For the Year')
        if pd.isna(net_income):
            net_income = income_row.get('Attribute to parent company (Bn. VND)')
        net_income = float(net_income) / 1_000_000 if pd.notna(net_income) else None
        
        equity = balance_row.get("OWNER'S EQUITY(Bn.VND)")
        equity = float(equity) / 1_000_000 if pd.notna(equity) else None
        
        liability = balance_row.get('LIABILITIES (Bn. VND)')
        liability = float(liability) / 1_000_000 if pd.notna(liability) else None
        
        cash = balance_row.get('Cash and cash equivalents (Bn. VND)')
        cash = float(cash) / 1_000_000 if pd.notna(cash) else None
        
        cash_investment = balance_row.get('Short-term investments (Bn. VND)')
        cash_investment = float(cash_investment) / 1_000_000 if pd.notna(cash_investment) else None
        
        long_term_investments = _get_balance_value(balance_row, [
            'Long-term investments (Bn. VND)', 'Long-term investments',
        ])
        
        # Financial income (VCI uses "Financial Income"; also try (Bn. VND) variants)
        financial_income = _get_income_value(income_row, [
            'Financial Income', 'Financial income (Bn. VND)', 'Financial income',
            'Income from financial activities (Bn. VND)', 'Income from financial activities',
        ])
        # Operating income (VCI uses "Operating Profit/Loss"; also try other variants)
        operating_income = _get_income_value(income_row, [
            'Operating Profit/Loss', 'Operating profit (Bn. VND)', 'Operating profit',
            'Net profit from operating activities (Bn. VND)', 'Net profit from operating activities',
            'Profit from operating activities (Bn. VND)',
        ])
        # Profit before tax, interest expense, financial expense (income statement)
        profit_before_tax = _get_income_value(income_row, [
            'Profit before tax', 'Profit before tax (Bn. VND)',
        ])
        interest_expense = _get_income_value(income_row, [
            'Interest Expenses', 'Interest expenses (Bn. VND)', 'Interest expenses',
        ])
        financial_expense = _get_income_value(income_row, [
            'Financial Expenses', 'Financial expenses (Bn. VND)', 'Financial expenses',
        ])
        # Depreciation from cash flow statement (VCI: raw VND → millions)
        depreciation_expense = _get_cash_flow_value(cash_df, int(year), int(quarter) if quarter is not None and not pd.isna(quarter) else None, [
            'Depreciation and Amortisation', 'Depreciation and Amortisation (Bn. VND)',
            'Depreciation and Amortization', 'Depreciation and Amortization (Bn. VND)',
        ]) if cash_df is not None else None
        
        # Interest-bearing debt: VNStock only (Vietstock scraping does not provide these)
        ibd_short = _get_balance_value(balance_row, [
            'Short-term borrowings (Bn. VND)', 'Short-term borrowings',
            'Short-term loans (Bn. VND)', 'Short-term loans',
            'Short-term debt (Bn. VND)', 'Short-term debt',
        ])
        ibd_long = _get_balance_value(balance_row, [
            'Long-term borrowings (Bn. VND)', 'Long-term borrowings',
            'Long-term loans (Bn. VND)', 'Long-term loans',
            'Long-term debt (Bn. VND)', 'Long-term debt',
        ])
        
        # Build record
        record = {
            'Period': period_str,
            'PeriodType': period_type,
            'Revenue': revenue,
            'Net Income': net_income,
            'Financial Income': financial_income,
            'Operating Income': operating_income,
            'Equity': equity,
            'Liability': liability,
            'Cash And Equivalent': cash,
            'Cash Investment': cash_investment,
            'Long Term Investments': long_term_investments,
            'Profit Before Tax': profit_before_tax,
            'Interest Expense': interest_expense,
            'Financial Expense': financial_expense,
            'Depreciation Expense': depreciation_expense,
            'Interest Bearing Debt Short Term': ibd_short,
            'Interest Bearing Debt Long Term': ibd_long,
        }
        
        # Calculate ratios
        # ROE = Net Income / Equity
        if net_income is not None and equity is not None and equity != 0:
            record['ROE'] = net_income / equity
        else:
            record['ROE'] = None
        
        # ROIC = Net Income / (Equity + Liability - Cash - Cash Investment)
        if net_income is not None and equity is not None and liability is not None:
            invested_capital = equity + liability
            if cash is not None:
                invested_capital -= cash
            if cash_investment is not None:
                invested_capital -= cash_investment
            
            if invested_capital != 0:
                record['ROIC'] = net_income / invested_capital
            else:
                record['ROIC'] = None
        else:
            record['ROIC'] = None
        
        # Net Profit Margin = Net Income / Revenue
        if net_income is not None and revenue is not None and revenue != 0:
            record['Net Profit Margin'] = net_income / revenue
        else:
            record['Net Profit Margin'] = None
        
        records.append(record)
    
    # Calculate YoY growth rates
    records = _calculate_yoy_growth(records)
    
    return records


def _trailing_four_quarter_periods(year: int, quarter: int) -> List[str]:
    """Return the 4 consecutive quarter period strings ending at (year, quarter). E.g. 2024, 2 -> ['2023-Q3', '2023-Q4', '2024-Q1', '2024-Q2']."""
    out: List[str] = []
    y, q = year, quarter
    for _ in range(4):
        out.append(f"{y}-Q{q}")
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    out.reverse()
    return out


def _add_t4q_to_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add trailing-four-quarters (T4Q) metrics to quarterly records for valuation trend.
    For each quarter, Revenue T4Q = sum(Revenue) over last 4 quarters; Net Income T4Q = sum(Net Income).
    Only quarters that have 4 consecutive quarters of data get T4Q fields.
    """
    if not records:
        return records
    by_period = {r["Period"]: r for r in records if r.get("Period")}
    for record in records:
        period = record.get("Period")
        if not period or "-Q" not in period:
            continue
        try:
            y_str, q_str = period.split("-Q")
            y, q = int(y_str), int(q_str)
        except (ValueError, IndexError):
            continue
        t4q_periods = _trailing_four_quarter_periods(y, q)
        if not all(p in by_period for p in t4q_periods):
            continue
        rev_t4q = sum(
            (by_period[p].get("Revenue") or 0) for p in t4q_periods
            if isinstance(by_period[p].get("Revenue"), (int, float))
        )
        ni_t4q = sum(
            (by_period[p].get("Net Income") or 0) for p in t4q_periods
            if isinstance(by_period[p].get("Net Income"), (int, float))
        )
        if rev_t4q != 0 or ni_t4q != 0:
            record["Revenue T4Q"] = rev_t4q
            record["Net Income T4Q"] = ni_t4q
    return records


def _calculate_yoy_growth(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calculate Year-over-Year growth rates for Revenue and Net Income.
    
    Only calculates for annual (FY) periods, comparing to the same period one year prior.
    """
    if not records:
        return records
    
    # Sort by period
    records = sorted(records, key=lambda r: r['Period'])
    
    # Build lookup for annual records
    annual_lookup = {}
    for record in records:
        period = record['Period']
        if period.endswith('-FY'):
            year = int(period.split('-')[0])
            annual_lookup[year] = record
    
    # Calculate YoY growth
    for record in records:
        period = record['Period']
        
        if period.endswith('-FY'):
            year = int(period.split('-')[0])
            prev_year_record = annual_lookup.get(year - 1)
            
            if prev_year_record:
                # Revenue YoY Growth
                curr_rev = record.get('Revenue')
                prev_rev = prev_year_record.get('Revenue')
                if curr_rev is not None and prev_rev is not None and prev_rev > 0:
                    record['Revenue YoY Growth'] = (curr_rev - prev_rev) / prev_rev
                else:
                    record['Revenue YoY Growth'] = None
                
                # Net Income YoY Growth
                curr_income = record.get('Net Income')
                prev_income = prev_year_record.get('Net Income')
                if curr_income is not None and prev_income is not None and prev_income > 0:
                    record['Net Income YoY Growth'] = (curr_income - prev_income) / prev_income
                else:
                    record['Net Income YoY Growth'] = None
            else:
                record['Revenue YoY Growth'] = None
                record['Net Income YoY Growth'] = None
        
        # For quarterly data, calculate quarter-specific metrics if needed
        elif '-Q' in period:
            # Quarterly YoY growth (compare to same quarter last year)
            year = int(period.split('-')[0])
            quarter = period.split('-Q')[1]
            
            # Find same quarter last year
            prev_year_period = f"{year - 1}-Q{quarter}"
            prev_year_record = next((r for r in records if r['Period'] == prev_year_period), None)
            
            if prev_year_record:
                # Revenue YoY Growth (Q)
                curr_rev = record.get('Revenue')
                prev_rev = prev_year_record.get('Revenue')
                if curr_rev is not None and prev_rev is not None and prev_rev > 0:
                    record['Revenue YoY Growth (Q)'] = (curr_rev - prev_rev) / prev_rev
                else:
                    record['Revenue YoY Growth (Q)'] = None
                
                # Net Income YoY Growth (Q)
                curr_income = record.get('Net Income')
                prev_income = prev_year_record.get('Net Income')
                if curr_income is not None and prev_income is not None and prev_income > 0:
                    record['Net Income YoY Growth (Q)'] = (curr_income - prev_income) / prev_income
                else:
                    record['Net Income YoY Growth (Q)'] = None
    
    return records


def fetch_financial_data_vnstock(
    symbol: str,
    provider: str = "vci",
    include_quarterly: bool = True
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    Fetch financial data from VNStock and return structured records.
    
    Args:
        symbol: Stock ticker symbol
        provider: Data provider ('vci', 'kbs', etc.; VCI default, KBS fallback)
        include_quarterly: Whether to include quarterly data (default True)
    
    Returns:
        Tuple of (records, error_message)
        - records: List of financial records if successful, None if error
        - error_message: Error description if failed, None if successful
    """
    if Vnstock is None:
        return None, "VNStock library not installed. Please install with: pip install vnstock"
    
    if not symbol:
        return None, "Symbol is required"
    
    symbol = symbol.upper().strip()
    
    try:
        # Fetch annual data (3 API calls with delays)
        balance_annual = _fetch_balance_sheet(symbol, period="annual", provider=provider)
        income_annual = _fetch_income_statement(symbol, period="annual", provider=provider)
        cash_annual = _fetch_cash_flow(symbol, period="annual", provider=provider)
        
        if balance_annual is None or income_annual is None:
            return None, f"Failed to fetch annual financial data for {symbol} from {provider}"
        
        # Build records: KBS returns long format (item_id + year columns), VCI returns wide (yearReport + metric columns)
        if _is_kbs_long_format(balance_annual, income_annual):
            records = _build_financial_records_from_kbs_long(
                balance_annual, income_annual, cash_annual, quarters_only=False
            )
            if include_quarterly:
                balance_quarter = _fetch_balance_sheet(symbol, period="quarter", provider=provider)
                income_quarter = _fetch_income_statement(symbol, period="quarter", provider=provider)
                cash_quarter = _fetch_cash_flow(symbol, period="quarter", provider=provider)
                if balance_quarter is not None and income_quarter is not None and _is_kbs_long_format(balance_quarter, income_quarter):
                    q_year_cols = _get_kbs_year_columns(balance_quarter)
                    if q_year_cols:
                        quarterly_records = _build_financial_records_from_kbs_long(
                            balance_quarter, income_quarter, cash_quarter, quarters_only=True
                        )
                        if quarterly_records:
                            records.extend(quarterly_records)
        else:
            records = _build_financial_records(balance_annual, income_annual, cash_annual)
            if include_quarterly:
                balance_quarter = _fetch_balance_sheet(symbol, period="quarter", provider=provider)
                income_quarter = _fetch_income_statement(symbol, period="quarter", provider=provider)
                cash_quarter = _fetch_cash_flow(symbol, period="quarter", provider=provider)
                if balance_quarter is not None and income_quarter is not None:
                    quarterly_records = _build_financial_records(
                        balance_quarter, income_quarter, cash_quarter, quarters_only=True
                    )
                    records.extend(quarterly_records)
        
        # Deduplicate by Period (keep first = annual wins over any duplicate FY from quarterly)
        seen_periods: set = set()
        deduped: List[Dict[str, Any]] = []
        for r in records:
            period = r.get("Period")
            if period is None:
                continue
            if period in seen_periods:
                continue
            seen_periods.add(period)
            deduped.append(r)
        records = sorted(deduped, key=lambda r: r["Period"])
        
        # Add T4Q (trailing four quarters) to quarterly records for valuation trend
        records = _add_t4q_to_records(records)
        
        if not records:
            return None, f"No financial data available for {symbol}"
        
        # Sanitize for JSON
        records = _sanitize_for_json(records)
        
        return records, None
    
    except Exception as e:
        return None, f"Error fetching financial data from VNStock: {str(e)}"
