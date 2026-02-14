"""
Test script for VNStock financial data service.

Run from project root: python debug/test_vnstock_financial.py [SYMBOL] [provider]
"""

import sys
import json
from app.services.vnstock_financial_service import fetch_financial_data_vnstock

def test_fetch_financial_data(symbol: str = "FRT", provider: str = "vci"):
    """Test fetching financial data for a symbol."""
    print(f"\n{'='*60}")
    print(f"Testing VNStock Financial Data Service")
    print(f"Symbol: {symbol}, Provider: {provider}")
    print(f"{'='*60}\n")
    
    records, error = fetch_financial_data_vnstock(symbol, provider=provider, include_quarterly=True)
    
    if error:
        print(f"❌ Error: {error}")
        return False
    
    if not records:
        print(f"❌ No records returned")
        return False
    
    print(f"✅ Successfully fetched {len(records)} records\n")
    
    print(f"{'Period':<15} {'Revenue':<15} {'Net Income':<15} {'ROE':<10} {'ROIC':<10}")
    print("-" * 70)
    
    for record in records[-10:]:
        period = record.get('Period', 'N/A')
        revenue = record.get('Revenue')
        net_income = record.get('Net Income')
        roe = record.get('ROE')
        roic = record.get('ROIC')
        
        revenue_str = f"{revenue:.2f}M" if revenue is not None else "N/A"
        income_str = f"{net_income:.2f}M" if net_income is not None else "N/A"
        roe_str = f"{roe*100:.1f}%" if roe is not None else "N/A"
        roic_str = f"{roic*100:.1f}%" if roic is not None else "N/A"
        
        print(f"{period:<15} {revenue_str:<15} {income_str:<15} {roe_str:<10} {roic_str:<10}")
    
    print(f"\n✅ Test passed! VNStock integration is working.\n")
    
    save = input("Save full data to JSON file? (y/n): ").strip().lower()
    if save == 'y':
        filename = f"vnstock_test_{symbol}_{provider}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to {filename}")
    
    return True


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "FRT"
    provider = sys.argv[2] if len(sys.argv) > 2 else "vci"
    
    try:
        success = test_fetch_financial_data(symbol, provider)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
