"""
Fetch full financial statements for GMD (or given symbol) and dump 2025 fields.
Shows all columns/fields returned by VNStock for balance_sheet, income_statement, cash_flow.
Run from project root: python debug/fetch_gmd_2025_financials.py [SYMBOL] [--provider VCI|KBS] [--save]
"""

import argparse
import json
import sys
import time

try:
    import pandas as pd
except ImportError:
    print("pandas required: pip install pandas")
    sys.exit(1)

try:
    from vnstock import Vnstock
except ImportError:
    print("vnstock required: pip install vnstock")
    sys.exit(1)

DELAY = 2.5


def fetch_df(provider: str, symbol: str, report: str, period: str = "year"):
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        time.sleep(DELAY)
        if report == "balance_sheet":
            method = stock.finance.balance_sheet
        elif report == "income_statement":
            method = stock.finance.income_statement
        elif report == "cash_flow":
            method = stock.finance.cash_flow
        else:
            return None
        kwargs = {"period": period}
        if provider.lower() == "vci":
            kwargs["lang"] = "en"
        df = method(**kwargs)
        return df if df is not None and not df.empty else None
    except Exception as e:
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch full financial statement fields for a symbol (e.g. GMD 2025)")
    parser.add_argument("symbol", nargs="?", default="GMD", help="Stock symbol (default: GMD)")
    parser.add_argument("--provider", choices=["VCI", "KBS"], default="VCI", help="Data provider (default: VCI)")
    parser.add_argument("--save", action="store_true", help="Save output to debug/gmd_2025_financials_fields_{provider}.json")
    args = parser.parse_args()
    symbol = args.symbol.upper().strip()
    provider = args.provider.upper()

    print(f"Fetching full financial statements for {symbol} ({provider}), annual period (includes 2025 if available)...\n")
    out = {"symbol": symbol, "provider": provider, "reports": {}}

    for report in ["balance_sheet", "income_statement", "cash_flow"]:
        print(f"  {report}...")
        df = fetch_df(provider, symbol, report, period="year")
        if df is None or df.empty:
            print(f"    -> No data")
            out["reports"][report] = {"error": "No data or fetch failed", "columns": None, "shape": None}
            continue

        columns = list(df.columns)
        shape = list(df.shape)
        out["reports"][report] = {"columns": columns, "shape": shape, "dtypes": {str(c): str(df[c].dtype) for c in columns}}

        # VCI: row key is yearReport (and lengthReport for quarter). KBS: year columns like "2025", "2024"...
        if "yearReport" in df.columns:
            # VCI wide: filter row(s) where yearReport == 2025
            rows_2025 = df[df["yearReport"] == 2025]
        else:
            # KBS long: columns ARE years; no yearReport. So "2025" is a column; we list item_id and 2025 values
            year_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 4]
            if "2025" in year_cols:
                rows_2025 = df[["item_id", "item"] + ["2025"]].copy() if "item" in df.columns else df[["item_id", "2025"]].copy()
            else:
                rows_2025 = None

        if rows_2025 is not None and not rows_2025.empty:
            # Serialize 2025 data for output
            if "yearReport" in df.columns:
                rec = rows_2025.iloc[0].to_dict()
                clean = {}
                for k, v in rec.items():
                    if pd.isna(v):
                        clean[str(k)] = None
                    elif isinstance(v, (int, float)) and (v != v or v == float("inf") or v == float("-inf")):
                        clean[str(k)] = None
                    else:
                        clean[str(k)] = v.item() if hasattr(v, "item") and callable(getattr(v, "item")) else v
                out["reports"][report]["row_2025"] = clean
            else:
                out["reports"][report]["rows_2025"] = rows_2025.to_dict(orient="records")
        else:
            # Still attach full sample of first few rows (for KBS or when 2025 missing)
            try:
                sample = df.head(5).to_dict(orient="records")
                def _clean(v):
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return None
                    if hasattr(v, "item"):
                        try:
                            return v.item()
                        except (ValueError, AttributeError):
                            pass
                    return v
                out["reports"][report]["sample_rows"] = [{str(k): _clean(v) for k, v in r.items()} for r in sample]
            except Exception:
                pass

        print(f"    columns ({len(columns)}): {columns[:15]}{'...' if len(columns) > 15 else ''}")
        if "row_2025" in out["reports"][report]:
            print(f"    -> 2025 row attached (VCI wide)")
        elif "rows_2025" in out["reports"][report]:
            print(f"    -> 2025 values attached (KBS long)")
        else:
            print(f"    -> sample_rows attached (no 2025 filter)")

    print("\n--- Full field list by report ---\n")
    for report, data in out["reports"].items():
        cols = data.get("columns")
        if cols:
            print(f"{report}:")
            for c in cols:
                print(f"  - {c}")
            print()

    if args.save:
        path = f"debug/financials_fields_{symbol}_{provider}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False, default=str)
        print(f"Saved to {path}")


if __name__ == "__main__":
    main()
