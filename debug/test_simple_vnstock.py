"""
Simple VNStock test to verify basic functionality.
"""

from vnstock import Vnstock

# Test 1: Basic stock quote
print("Test 1: Creating Vnstock object...")
try:
    stock = Vnstock().stock(symbol="FRT", source="VCI")
    print("✓ Success\n")
except Exception as e:
    print(f"✗ Failed: {e}\n")
    exit(1)

# Test 2: Get balance sheet
print("Test 2: Fetching balance sheet (year)...")
try:
    df = stock.finance.balance_sheet(period="year", lang="en")
    print(f"✓ Got DataFrame: {type(df)}")
    print(f"  Shape: {df.shape if df is not None else 'None'}")
    print(f"  Empty: {df.empty if df is not None else 'N/A'}")
    if df is not None and not df.empty:
        print(f"  Columns: {list(df.columns)[:5]}...")
        print(f"\n  Sample data:")
        print(df.head(2))
    print()
except Exception as e:
    print(f"✗ Failed: {e}\n")

# Test 3: Get income statement
print("Test 3: Fetching income statement (year)...")
try:
    df = stock.finance.income_statement(period="year", lang="en")
    print(f"✓ Got DataFrame: {type(df)}")
    print(f"  Shape: {df.shape if df is not None else 'None'}")
    print(f"  Empty: {df.empty if df is not None else 'N/A'}")
    if df is not None and not df.empty:
        print(f"  Columns: {list(df.columns)[:5]}...")
        print(f"\n  Sample data:")
        print(df.head(2))
    print()
except Exception as e:
    print(f"✗ Failed: {e}\n")

print("\nTest complete. If you see empty DataFrames, try:")
print("  1. Different symbol")
print("  2. Update vnstock: pip install vnstock --upgrade")
print("  3. Check VNStock docs: https://vnstocks.com/docs")
