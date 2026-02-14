"""
Quick Visual Comparison

Simple side-by-side comparison of VNStock vs Vietstock data.
Shows the same metrics in a readable table format.
"""

import json
import sys
from app.services.vnstock_financial_service import fetch_financial_data_vnstock


def load_sample(symbol: str) -> list:
    """Load sample data from samples.json."""
    with open("app/sample_data/samples.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for sample in data['samples']:
        if sample['symbol'].upper() == symbol.upper():
            return sample['data']
    
    return []


def format_val(val, is_pct=False):
    """Format value for display."""
    if val is None:
        return "—"
    if is_pct:
        return f"{val*100:.1f}%"
    return f"{val:.2f}"


def main():
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "FRT"
    provider = sys.argv[2] if len(sys.argv) > 2 else "vci"
    
    print(f"\n{'='*100}")
    print(f"QUICK COMPARISON: {symbol} (VNStock provider: {provider})")
    print(f"{'='*100}\n")
    
    # Load both sources
    print("Loading data...")
    vietstock = load_sample(symbol)
    
    print(f"\nFetching from VNStock (this will take ~15 seconds with rate limiting)...")
    vnstock, error = fetch_financial_data_vnstock(symbol, provider=provider, include_quarterly=True)
    
    if error:
        print(f"\n❌ VNStock error: {error}")
        print("\nDebug info:")
        print(f"  - Error message: {error}")
        print(f"  - This usually means the data fetch succeeded but record building failed")
        print(f"  - Check if the API returned data in expected format")
        return
    
    if not vnstock:
        print(f"\n❌ VNStock returned empty list (no error but no data)")
        print("\nThis is unexpected - API calls succeeded but no records were built")
        return
    
    if not vietstock:
        print(f"\n❌ No Vietstock data found for {symbol} in samples.json")
        return
    
    print(f"\n✓ Vietstock: {len(vietstock)} records")
    print(f"✓ VNStock: {len(vnstock)} records\n")
    
    # Get common periods (last 10 FY)
    vs_periods = {r['Period']: r for r in vietstock if r['Period'].endswith('-FY')}
    vn_periods = {r['Period']: r for r in vnstock if r['Period'].endswith('-FY')}
    
    common = sorted(set(vs_periods.keys()) & set(vn_periods.keys()))[-10:]
    
    if not common:
        print("❌ No common periods found")
        return
    
    print(f"Comparing {len(common)} common annual periods:\n")
    
    # Header
    print(f"{'Period':<12} {'Metric':<20} {'VNStock':<15} {'Vietstock':<15} {'Diff':<12} {'Match'}")
    print("─" * 100)
    
    metrics = [
        ('Revenue', False),
        ('Net Income', False),
        ('ROE', True),
        ('ROIC', True),
        ('Net Profit Margin', True),
    ]
    
    for period in common:
        vn = vn_periods[period]
        vs = vs_periods[period]
        
        for i, (metric, is_pct) in enumerate(metrics):
            vn_val = vn.get(metric)
            vs_val = vs.get(metric)
            
            vn_str = format_val(vn_val, is_pct)
            vs_str = format_val(vs_val, is_pct)
            
            # Calculate difference
            if vn_val is not None and vs_val is not None:
                diff = abs(vn_val - vs_val)
                if is_pct:
                    diff_str = f"{diff*100:.1f}pp"
                else:
                    diff_str = f"{diff:.2f}"
                
                # Match indicator
                threshold = 0.001 if is_pct else 1.0
                match = "✓" if diff < threshold else ("~" if diff < threshold * 10 else "✗")
            else:
                diff_str = "—"
                match = "?"
            
            period_str = period if i == 0 else ""
            print(f"{period_str:<12} {metric:<20} {vn_str:<15} {vs_str:<15} {diff_str:<12} {match}")
        
        print()
    
    print(f"{'='*100}")
    print("\nLegend: ✓ = Match, ~ = Close, ✗ = Different, ? = Missing data")
    print()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
