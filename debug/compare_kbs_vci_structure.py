"""
Compare KBS vs VCI financial data structure from VNStock.

Fetches balance_sheet, income_statement, cash_flow from both providers
and prints shape, columns, and sample data so we can align parsing.

Structure difference (why KBS fails in our pipeline):
- VCI: WIDE format — each ROW = one period (year), COLUMNS = metric names
  (yearReport, lengthReport, "Net Sales", "LIABILITIES (Bn. VND)", etc.).
- KBS: LONG format — each ROW = one line item (metric), COLUMNS = item, item_id, "2024", "2023", ...
  Values are in year columns; no yearReport/lengthReport. item_id examples:
  balance: total_liabilities, equity/owner's equity, cash_and_cash_equivalents, ...
  income:  n_3.net_revenue (revenue), net_profit / profit_after_tax, ...

Usage (from project root):
  python debug/compare_kbs_vci_structure.py [SYMBOL]
  python debug/compare_kbs_vci_structure.py GMD --save
"""

import argparse
import json
import os
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

# Delay to avoid rate limits
DELAY = 2


def fetch_df(provider: str, symbol: str, report: str, period: str = "year") -> pd.DataFrame | None:
    """Fetch one report (balance_sheet, income_statement, cash_flow) from provider."""
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
        print(f"  Error: {e}")
        return None


def describe_df(name: str, df: pd.DataFrame | None) -> dict:
    """Return a JSON-serializable description of a DataFrame for comparison."""
    if df is None:
        return {"error": "None or empty", "shape": None, "columns": None, "sample": None}
    out = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {str(k): str(v) for k, v in df.dtypes.items()},
    }
    try:
        sample = df.head(1).to_dict(orient="records")
        if sample:
            row = sample[0]
            clean = {}
            for k, v in row.items():
                if pd.isna(v):
                    clean[str(k)] = None
                elif isinstance(v, (int, float, str, bool, type(None))):
                    clean[str(k)] = v
                else:
                    clean[str(k)] = str(v)
            out["sample_row"] = clean
    except Exception:
        out["sample_row"] = None
    if df.shape[0] > 1 and df.shape[1] <= 15:
        rows = df.head(3).to_dict(orient="records")
        def _clean(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            if hasattr(v, "item"):
                try:
                    return v.item()
                except (ValueError, AttributeError):
                    return str(v)
            return v
        out["first_3_rows"] = [{str(k): _clean(v) for k, v in r.items()} for r in rows]
    return out


def main():
    parser = argparse.ArgumentParser(description="Compare KBS vs VCI financial data structure")
    parser.add_argument("symbol", nargs="?", default="GMD", help="Stock symbol (default: GMD)")
    parser.add_argument("--save", action="store_true", help="Save comparison to debug/compare_kbs_vci_structure.json")
    parser.add_argument("--period", choices=["year", "quarter"], default="year", help="year or quarter")
    args = parser.parse_args()
    symbol = args.symbol.upper().strip()

    print(f"Comparing KBS vs VCI structure for {symbol} (period={args.period})\n")
    print("=" * 70)

    reports = ["balance_sheet", "income_statement", "cash_flow"]
    comparison = {"symbol": symbol, "period": args.period, "kbs": {}, "vci": {}}

    for provider in ["kbs", "vci"]:
        print(f"\n--- {provider.upper()} ---\n")
        comparison[provider] = {}
        for report in reports:
            print(f"  {report} ... ", end="", flush=True)
            df = fetch_df(provider, symbol, report, period=args.period)
            desc = describe_df(report, df)
            comparison[provider][report] = desc
            if desc.get("error"):
                print(desc["error"])
                continue
            print(f"shape={desc['shape']}, columns={len(desc['columns'])}")
            print(f"    columns: {desc['columns'][:15]}{'...' if len(desc['columns']) > 15 else ''}")
            if desc.get("sample_row"):
                keys_we_need = [
                    "yearReport", "lengthReport",
                    "Net Sales", "Revenue (Bn. VND)", "Net Profit For the Year",
                    "OWNER'S EQUITY(Bn.VND)", "LIABILITIES (Bn. VND)",
                    "item", "item_en", "item_id",
                ]
                for k in keys_we_need:
                    if k in desc["sample_row"] and desc["sample_row"][k] is not None:
                        val = desc["sample_row"][k]
                        safe = str(val).encode("ascii", "replace").decode("ascii") if isinstance(val, str) else val
                        print(f"    sample {k!r}: {safe!r}")
            if desc.get("first_3_rows"):
                print("    first 3 rows (long format): see --save JSON for content")

    print("\n" + "=" * 70)
    print("COLUMN COMPARISON (balance_sheet)")
    print("=" * 70)
    kbs_cols = set(comparison.get("kbs", {}).get("balance_sheet", {}).get("columns") or [])
    vci_cols = set(comparison.get("vci", {}).get("balance_sheet", {}).get("columns") or [])
    print(f"  KBS only: {sorted(kbs_cols - vci_cols)[:20]}{'...' if len(kbs_cols - vci_cols) > 20 else ''}")
    print(f"  VCI only: {sorted(vci_cols - kbs_cols)[:20]}{'...' if len(vci_cols - kbs_cols) > 20 else ''}")
    print(f"  Common:  {len(kbs_cols & vci_cols)} columns")

    print("\nCOLUMN COMPARISON (income_statement)")
    kbs_i = set(comparison.get("kbs", {}).get("income_statement", {}).get("columns") or [])
    vci_i = set(comparison.get("vci", {}).get("income_statement", {}).get("columns") or [])
    print(f"  KBS only: {sorted(kbs_i - vci_i)[:20]}{'...' if len(kbs_i - vci_i) > 20 else ''}")
    print(f"  VCI only: {sorted(vci_i - kbs_i)[:20]}{'...' if len(vci_i - kbs_i) > 20 else ''}")
    print(f"  Common:  {len(kbs_i & vci_i)} columns")

    if args.save:
        _dir = os.path.dirname(os.path.abspath(__file__))
        out_path = os.path.join(_dir, "compare_kbs_vci_structure.json")
        def to_json(obj):
            if isinstance(obj, dict):
                return {k: to_json(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [to_json(x) for x in obj]
            if isinstance(obj, (pd.Timestamp,)):
                return str(obj)
            if pd.isna(obj):
                return None
            if hasattr(obj, "item") and callable(getattr(obj, "item", None)):
                return obj.item()
            if isinstance(obj, (float, int)) and (obj != obj or abs(obj) == 1e300):
                return None
            return obj

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(to_json(comparison), f, ensure_ascii=False, indent=2)
        print(f"\nSaved to {os.path.abspath(out_path)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
