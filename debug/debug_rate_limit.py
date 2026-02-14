"""
Debug Rate Limiting and API Calls

Shows exactly what happens during each API call to understand rate limiting.
"""

import time
from datetime import datetime
from vnstock import Vnstock

def log_with_time(message):
    """Print message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")

def test_single_call(symbol: str, provider: str, statement_type: str, period: str):
    """Test a single API call and measure timing."""
    log_with_time(f"Starting {statement_type} fetch...")
    start = time.time()
    
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        
        if statement_type == "balance":
            df = stock.finance.balance_sheet(period=period, lang="en")
        elif statement_type == "income":
            df = stock.finance.income_statement(period=period, lang="en")
        elif statement_type == "cash":
            df = stock.finance.cash_flow(period=period, lang="en")
        else:
            return None, "Unknown type"
        
        elapsed = time.time() - start
        
        if df is not None and not df.empty:
            log_with_time(f"✓ Success! Got {len(df)} rows in {elapsed:.2f}s")
            return df, None
        else:
            log_with_time(f"✗ Empty result in {elapsed:.2f}s")
            return None, "Empty DataFrame"
    
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        log_with_time(f"✗ Error in {elapsed:.2f}s: {error_msg[:100]}")
        return None, error_msg

def main():
    symbol = "FRT"
    provider = "vci"
    
    print("\n" + "="*100)
    print("RATE LIMIT DEBUG - Detailed API Call Analysis")
    print("="*100 + "\n")
    
    print(f"Symbol: {symbol}")
    print(f"Provider: {provider}")
    print(f"Testing with different delays to find optimal rate...\n")
    
    # Test 1: Sequential calls with no delay
    print("\n" + "-"*100)
    print("TEST 1: Sequential calls with NO delay (will likely hit rate limit)")
    print("-"*100 + "\n")
    
    test_start = time.time()
    
    balance_annual, err1 = test_single_call(symbol, provider, "balance", "year")
    income_annual, err2 = test_single_call(symbol, provider, "income", "year")
    cash_annual, err3 = test_single_call(symbol, provider, "cash", "year")
    
    test_elapsed = time.time() - test_start
    
    print(f"\nTest 1 Summary:")
    print(f"  Total time: {test_elapsed:.2f}s")
    print(f"  Balance: {'✓' if balance_annual is not None else '✗'}")
    print(f"  Income: {'✓' if income_annual is not None else '✗'}")
    print(f"  Cash: {'✓' if cash_annual is not None else '✗'}")
    
    if err1 and "rate limit" in err1.lower():
        print(f"\n⚠️  Rate limit hit! Error: {err1[:200]}")
        print(f"  Waiting 60 seconds for rate limit to reset...")
        time.sleep(60)
    
    # Test 2: Sequential calls with 2s delay
    print("\n" + "-"*100)
    print("TEST 2: Sequential calls with 2-second delays")
    print("-"*100 + "\n")
    
    test_start = time.time()
    
    balance_annual, err1 = test_single_call(symbol, provider, "balance", "year")
    time.sleep(2)
    log_with_time("Waited 2 seconds...")
    
    income_annual, err2 = test_single_call(symbol, provider, "income", "year")
    time.sleep(2)
    log_with_time("Waited 2 seconds...")
    
    cash_annual, err3 = test_single_call(symbol, provider, "cash", "year")
    
    test_elapsed = time.time() - test_start
    
    print(f"\nTest 2 Summary:")
    print(f"  Total time: {test_elapsed:.2f}s")
    print(f"  Balance: {'✓' if balance_annual is not None else '✗'}")
    print(f"  Income: {'✓' if income_annual is not None else '✗'}")
    print(f"  Cash: {'✓' if cash_annual is not None else '✗'}")
    
    # Test 3: Check if we can fetch quarterly data
    if balance_annual is not None:
        print("\n" + "-"*100)
        print("TEST 3: Fetching quarterly data (with delays)")
        print("-"*100 + "\n")
        
        time.sleep(2)
        log_with_time("Waited 2 seconds...")
        
        test_start = time.time()
        balance_quarter, err = test_single_call(symbol, provider, "balance", "quarter")
        test_elapsed = time.time() - test_start
        
        print(f"\nTest 3 Summary:")
        print(f"  Total time: {test_elapsed:.2f}s")
        print(f"  Quarterly balance: {'✓' if balance_quarter is not None else '✗'}")
    
    # Final summary
    print("\n" + "="*100)
    print("ANALYSIS & RECOMMENDATIONS")
    print("="*100 + "\n")
    
    success_count = sum([
        balance_annual is not None,
        income_annual is not None,
        cash_annual is not None
    ])
    
    print(f"Success Rate: {success_count}/3 statements fetched\n")
    
    if success_count == 3:
        print("✅ All API calls succeeded!")
        print("\nRecommendations:")
        print("  1. Use 2-second delays between API calls")
        print("  2. This allows ~6-8 API calls per minute")
        print("  3. Fetch annual + quarterly = 6 calls per symbol")
        print("  4. Can safely process 1 symbol per minute")
    elif success_count > 0:
        print("⚠️  Partial success")
        print("\nRecommendations:")
        print("  1. Increase delay to 3-4 seconds")
        print("  2. Consider fetching only annual data (skip quarterly)")
        print("  3. Or get free API key for higher limits")
    else:
        print("❌ All API calls failed")
        print("\nPossible issues:")
        print("  1. Rate limit still active (wait longer)")
        print("  2. Symbol not available in VCI database")
        print("  3. API authentication issue")
        print("  4. Network connectivity problem")
        print("\nNext steps:")
        print("  1. Wait 2-3 minutes and try again")
        print("  2. Try different symbol: python debug_rate_limit.py")
        print("  3. Get free API key from https://vnstocks.com/login")
    
    print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Debug cancelled")
    except Exception as e:
        print(f"\n❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
