"""
Debug VNStock API to see what data is available.
"""

import sys
from vnstock import Vnstock

def test_vnstock_raw(symbol: str = "FRT", provider: str = "vci"):
    """Test raw VNStock API calls."""
    print(f"\n{'='*80}")
    print(f"DEBUG: Testing VNStock API for {symbol} with provider {provider}")
    print(f"{'='*80}\n")
    
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        print(f"✓ Stock object created\n")
        
        # Test balance sheet
        print("1. Testing Balance Sheet (year)...")
        try:
            df_balance = stock.finance.balance_sheet(period="year", lang="en")
            if df_balance is not None and not df_balance.empty:
                print(f"   ✓ Got {len(df_balance)} rows")
                print(f"   Columns: {list(df_balance.columns)}")
                print(f"   First few rows:")
                print(df_balance.head(3))
            else:
                print(f"   ✗ Empty or None")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n2. Testing Income Statement (year)...")
        try:
            df_income = stock.finance.income_statement(period="year", lang="en")
            if df_income is not None and not df_income.empty:
                print(f"   ✓ Got {len(df_income)} rows")
                print(f"   Columns: {list(df_income.columns)}")
                print(f"   First few rows:")
                print(df_income.head(3))
            else:
                print(f"   ✗ Empty or None")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n3. Testing Cash Flow (year)...")
        try:
            df_cash = stock.finance.cash_flow(period="year", lang="en")
            if df_cash is not None and not df_cash.empty:
                print(f"   ✓ Got {len(df_cash)} rows")
                print(f"   Columns: {list(df_cash.columns)}")
                print(f"   First few rows:")
                print(df_cash.head(3))
            else:
                print(f"   ✗ Empty or None")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n4. Testing Balance Sheet (quarter)...")
        try:
            df_balance_q = stock.finance.balance_sheet(period="quarter", lang="en")
            if df_balance_q is not None and not df_balance_q.empty:
                print(f"   ✓ Got {len(df_balance_q)} rows")
                print(f"   Columns: {list(df_balance_q.columns)}")
                print(f"   First few rows:")
                print(df_balance_q.head(3))
            else:
                print(f"   ✗ Empty or None")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print("\nIf all tests show '✗ Empty or None', the symbol may not be available")
        print("in this provider's database, or the API structure has changed.")
        print("\nTry:")
        print(f"  1. Different symbol: python debug/debug_vnstock.py VNM {provider}")
        print(f"  2. Different provider: python debug/debug_vnstock.py {symbol} kbs")
        
    except Exception as e:
        print(f"\n✗ Failed to create stock object: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "FRT"
    provider = sys.argv[2].lower() if len(sys.argv) > 2 else "vci"
    
    test_vnstock_raw(symbol, provider)
