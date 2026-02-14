"""
Comprehensive VNStock Diagnostic Tool

Tests multiple symbols and providers to identify what works.
"""

import sys
from vnstock import Vnstock

def test_provider_symbol(symbol: str, provider: str):
    """Test a specific symbol with a specific provider."""
    result = {
        'symbol': symbol,
        'provider': provider,
        'balance_sheet': False,
        'income_statement': False,
        'cash_flow': False,
        'error': None
    }
    
    try:
        stock = Vnstock().stock(symbol=symbol, source=provider)
        
        kwargs = {"period": "year"}
        if provider.lower() == "vci":
            kwargs["lang"] = "en"
        
        try:
            df = stock.finance.balance_sheet(**kwargs)
            if df is not None and not df.empty:
                result['balance_sheet'] = True
        except Exception as e:
            if result['error'] is None:
                result['error'] = str(e)
        
        try:
            df = stock.finance.income_statement(**kwargs)
            if df is not None and not df.empty:
                result['income_statement'] = True
        except Exception as e:
            if result['error'] is None:
                result['error'] = str(e)
        
        try:
            df = stock.finance.cash_flow(**kwargs)
            if df is not None and not df.empty:
                result['cash_flow'] = True
        except Exception as e:
            if result['error'] is None:
                result['error'] = str(e)
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def main():
    print("\n" + "="*100)
    print("VNSTOCK DIAGNOSTIC TOOL")
    print("="*100 + "\n")
    
    symbols = ["FRT", "GVT", "GMD", "VNM", "VCB", "HPG"]
    providers = ["vci", "kbs"]
    
    print("Testing multiple symbols and providers...\n")
    print(f"{'Symbol':<10} {'Provider':<10} {'Balance':<10} {'Income':<10} {'Cash':<10} {'Status'}")
    print("-" * 100)
    
    working_combinations = []
    
    for symbol in symbols:
        for provider in providers:
            result = test_provider_symbol(symbol, provider)
            
            balance = "✓" if result['balance_sheet'] else "✗"
            income = "✓" if result['income_statement'] else "✗"
            cash = "✓" if result['cash_flow'] else "✗"
            
            if result['balance_sheet'] and result['income_statement']:
                status = "✅ WORKING"
                working_combinations.append((symbol, provider))
            elif result['error']:
                status = f"❌ {result['error'][:40]}"
            else:
                status = "⚠️  No data"
            
            print(f"{symbol:<10} {provider:<10} {balance:<10} {income:<10} {cash:<10} {status}")
    
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100 + "\n")
    
    if working_combinations:
        print(f"✅ Found {len(working_combinations)} working combinations:\n")
        for symbol, provider in working_combinations:
            print(f"   • {symbol} with {provider}")
        
        print("\n💡 Recommendation:")
        best_symbol, best_provider = working_combinations[0]
        print(f"   Use: python debug/quick_compare.py {best_symbol} {best_provider}")
    else:
        print("❌ No working combinations found!")
        print("\n🔧 Troubleshooting steps:")
        print("   1. Update vnstock: pip install vnstock --upgrade")
        print("   2. Check internet connection")
        print("   3. Try again later (API might be temporarily down)")
        print("   4. Use Vietstock scraping fallback: export USE_VNSTOCK_PRIMARY=False")
    
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Diagnostic cancelled")
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
