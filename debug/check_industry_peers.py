"""
Standalone script to check how KBS vs VCI classify a symbol's industry and peers.

Does NOT modify the app. Run from project root:
  python debug/check_industry_peers.py [SYMBOL]
  e.g. python debug/check_industry_peers.py HPG

Shows:
- KBS: industry_code, industry_name, and all peer symbols in that industry.
- VCI: for the symbol and a few peers, icbName2 (sector) and icbName4 (industry)
  so you can see if peers are "Basic Resources - Steel" or broader "Basic Resources".
"""

import sys


def _safe_print_str(s):
    """Encode to ASCII for console; avoid UnicodeEncodeError on Windows."""
    if s is None:
        return "(none)"
    t = str(s)
    return t.encode("ascii", errors="replace").decode("ascii")


def main():
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "HPG").strip().upper()
    print(f"Checking industry classification for {symbol}")
    print("=" * 60)

    peers = []
    # 1) KBS: industry code and peer list
    print("\n[KBS] symbols_by_industries (Listing source=KBS):")
    try:
        from vnstock import Listing
        listing = Listing(source="KBS", show_log=False)
        df = listing.symbols_by_industries(show_log=False)
        if df is None or df.empty:
            print("  No data returned.")
        else:
            df = df.dropna(subset=["symbol"]).copy()
            df["_sym"] = df["symbol"].astype(str).str.strip().str.upper()
            row = df[df["_sym"] == symbol]
            if row.empty:
                print(f"  {symbol} not found in KBS industry list.")
            else:
                industry_code = row["industry_code"].iloc[0]
                industry_name = row["industry_name"].iloc[0] if "industry_name" in df.columns else "(no column)"
                peers = df[df["industry_code"] == industry_code]["_sym"].tolist()
                print(f"  industry_code: {industry_code}")
                print(f"  industry_name: {_safe_print_str(industry_name)!r}")
                print(f"  peer count: {len(peers)}")
                print(f"  peer symbols: {peers[:15]}{'...' if len(peers) > 15 else ''}")
    except Exception as e:
        print(f"  Error: {e}")

    # 2) VCI: sector · industry (icbName2 · icbName4) for symbol and a few peers
    print("\n[VCI] Company sector · industry (icbName2 · icbName4):")
    try:
        from vnstock import Company
        to_check = [symbol] + peers[:4]
        for sym in to_check:
            try:
                company = Company(source="VCI", symbol=sym, show_log=False)
                raw = getattr(company, "raw_data", None) or {}
                info = raw.get("CompanyListingInfo") or raw.get("company_listing_info") or {}
                if isinstance(info, dict):
                    n2 = info.get("enIcbName2") or info.get("icbName2") or ""
                    n4 = info.get("enIcbName4") or info.get("icbName4") or ""
                    label = " · ".join(filter(None, [n2, n4])) or "(empty)"
                else:
                    label = "(no info)"
                print(f"  {sym}: {_safe_print_str(label)!r}")
            except Exception as e:
                print(f"  {sym}: error {e}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\nDone. (KBS defines who is a peer; VCI is only for the sector/industry label.)")


if __name__ == "__main__":
    main()
