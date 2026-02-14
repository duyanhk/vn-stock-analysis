"""
Data Source Comparison Tool

Compares financial data from VNStock API vs Vietstock scraping.
Helps validate VNStock integration and identify data discrepancies.
"""

import json
import sys
from typing import Dict, List, Optional, Tuple
from app.services.vnstock_financial_service import fetch_financial_data_vnstock


def load_vietstock_sample(symbol: str, samples_path: str = "app/sample_data/samples.json") -> Optional[List[Dict]]:
    """Load scraped Vietstock data from samples.json."""
    try:
        with open(samples_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        samples = data.get('samples', [])
        symbol_upper = symbol.upper()
        
        for sample in samples:
            if sample.get('symbol', '').upper() == symbol_upper:
                return sample.get('data', [])
        
        print(f"❌ Symbol {symbol} not found in samples.json")
        print(f"Available symbols: {', '.join([s.get('symbol', 'N/A') for s in samples])}")
        return None
    
    except FileNotFoundError:
        print(f"❌ File not found: {samples_path}")
        return None
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in {samples_path}")
        return None
    except Exception as e:
        print(f"❌ Error loading sample data: {e}")
        return None


def normalize_period(period: str) -> str:
    """Normalize period format for comparison."""
    if not period:
        return ""
    return str(period).strip()


def find_matching_record(period: str, records: List[Dict]) -> Optional[Dict]:
    """Find a record matching the given period."""
    period_norm = normalize_period(period)
    for record in records:
        if normalize_period(record.get('Period', '')) == period_norm:
            return record
    return None


def format_value(value, is_ratio: bool = False, is_millions: bool = False) -> str:
    """Format value for display."""
    if value is None:
        return "N/A"
    
    try:
        val = float(value)
        if is_ratio:
            return f"{val * 100:.2f}%"
        elif is_millions:
            return f"{val:.2f}M"
        else:
            return f"{val:.4f}"
    except (ValueError, TypeError):
        return str(value)


def calculate_difference(vnstock_val, vietstock_val) -> Tuple[Optional[float], str]:
    """Calculate absolute and percentage difference."""
    if vnstock_val is None or vietstock_val is None:
        return None, "N/A"
    
    try:
        vn = float(vnstock_val)
        vs = float(vietstock_val)
        
        if vs == 0:
            if vn == 0:
                return 0.0, "0.00%"
            else:
                return None, "∞"
        
        diff = vn - vs
        pct_diff = (diff / abs(vs)) * 100
        
        return diff, f"{pct_diff:+.2f}%"
    except (ValueError, TypeError):
        return None, "N/A"


def compare_records(vnstock_records: List[Dict], vietstock_records: List[Dict]) -> Dict:
    """Compare records from both sources."""
    comparison = {
        'periods_compared': 0,
        'periods_only_vnstock': [],
        'periods_only_vietstock': [],
        'metrics': {},
        'details': []
    }
    
    # Get all unique periods
    vnstock_periods = {normalize_period(r.get('Period', '')) for r in vnstock_records}
    vietstock_periods = {normalize_period(r.get('Period', '')) for r in vietstock_records}
    
    all_periods = sorted(vnstock_periods | vietstock_periods)
    
    comparison['periods_only_vnstock'] = sorted(vnstock_periods - vietstock_periods)
    comparison['periods_only_vietstock'] = sorted(vietstock_periods - vnstock_periods)
    
    # Metrics to compare (Vietstock does not provide Interest Bearing Debt Short/Long Term)
    metrics_to_compare = [
        ('Revenue', True, False),
        ('Net Income', True, False),
        ('Financial Income', True, False),
        ('Operating Income', True, False),
        ('Equity', True, False),
        ('Liability', True, False),
        ('ROE', False, True),
        ('ROIC', False, True),
        ('Net Profit Margin', False, True),
        ('Revenue YoY Growth', False, True),
        ('Net Income YoY Growth', False, True),
    ]
    
    for period in all_periods:
        if not period:
            continue
        
        vn_record = find_matching_record(period, vnstock_records)
        vs_record = find_matching_record(period, vietstock_records)
        
        if vn_record and vs_record:
            comparison['periods_compared'] += 1
            
            period_detail = {
                'period': period,
                'metrics': {}
            }
            
            for metric, is_millions, is_ratio in metrics_to_compare:
                vn_val = vn_record.get(metric)
                vs_val = vs_record.get(metric)
                
                diff, pct_diff = calculate_difference(vn_val, vs_val)
                
                period_detail['metrics'][metric] = {
                    'vnstock': vn_val,
                    'vietstock': vs_val,
                    'diff': diff,
                    'pct_diff': pct_diff
                }
                
                # Track metric-level statistics
                if metric not in comparison['metrics']:
                    comparison['metrics'][metric] = {
                        'total_comparisons': 0,
                        'matches': 0,
                        'avg_pct_diff': 0,
                        'max_pct_diff': 0,
                        'differences': []
                    }
                
                metric_stats = comparison['metrics'][metric]
                metric_stats['total_comparisons'] += 1
                
                if diff is not None and abs(diff) < 0.01:  # Consider < 0.01 as match
                    metric_stats['matches'] += 1
                
                if diff is not None:
                    metric_stats['differences'].append(abs(diff))
            
            comparison['details'].append(period_detail)
    
    # Calculate average differences
    for metric, stats in comparison['metrics'].items():
        if stats['differences']:
            stats['avg_diff'] = sum(stats['differences']) / len(stats['differences'])
            stats['max_diff'] = max(stats['differences'])
        else:
            stats['avg_diff'] = 0
            stats['max_diff'] = 0
    
    return comparison


def print_summary(comparison: Dict, symbol: str):
    """Print comparison summary."""
    print(f"\n{'='*80}")
    print(f"DATA SOURCE COMPARISON: {symbol}")
    print(f"{'='*80}\n")
    
    print(f"📊 Overview:")
    print(f"  • Periods compared: {comparison['periods_compared']}")
    print(f"  • Only in VNStock: {len(comparison['periods_only_vnstock'])}")
    if comparison['periods_only_vnstock']:
        print(f"    → {', '.join(comparison['periods_only_vnstock'][:5])}")
    print(f"  • Only in Vietstock: {len(comparison['periods_only_vietstock'])}")
    if comparison['periods_only_vietstock']:
        print(f"    → {', '.join(comparison['periods_only_vietstock'][:5])}")
    
    print(f"\n📈 Metric Comparison:\n")
    print(f"{'Metric':<25} {'Comparisons':<12} {'Matches':<10} {'Avg Diff':<15} {'Max Diff':<15}")
    print("-" * 80)
    
    for metric, stats in comparison['metrics'].items():
        total = stats['total_comparisons']
        matches = stats['matches']
        match_rate = (matches / total * 100) if total > 0 else 0
        avg_diff = stats.get('avg_diff', 0)
        max_diff = stats.get('max_diff', 0)
        
        print(f"{metric:<25} {total:<12} {matches} ({match_rate:.0f}%){'':<3} {avg_diff:<15.4f} {max_diff:<15.4f}")


def print_detailed_comparison(comparison: Dict, limit: int = 10):
    """Print detailed period-by-period comparison."""
    print(f"\n{'='*80}")
    print(f"DETAILED COMPARISON (Latest {limit} periods)")
    print(f"{'='*80}\n")
    
    details = comparison['details'][-limit:]  # Last N periods
    
    for detail in details:
        period = detail['period']
        print(f"\n📅 Period: {period}")
        print(f"{'─'*80}")
        print(f"{'Metric':<25} {'VNStock':<15} {'Vietstock':<15} {'Diff':<15} {'% Diff':<10}")
        print(f"{'─'*80}")
        
        for metric, values in detail['metrics'].items():
            vn_val = values['vnstock']
            vs_val = values['vietstock']
            diff = values['diff']
            pct_diff = values['pct_diff']
            
            # Determine if it's a ratio or millions
            is_ratio = metric in ['ROE', 'ROIC', 'Net Profit Margin', 'Revenue YoY Growth', 'Net Income YoY Growth']
            is_millions = metric in ['Revenue', 'Net Income', 'Financial Income', 'Operating Income', 'Equity', 'Liability']
            
            vn_str = format_value(vn_val, is_ratio, is_millions)
            vs_str = format_value(vs_val, is_ratio, is_millions)
            diff_str = format_value(diff, False, is_millions) if diff is not None else "N/A"
            
            # Color code based on difference
            if diff is not None and abs(diff) < 0.01:
                status = "✓"
            elif diff is not None and abs(diff) < 1.0:
                status = "~"
            else:
                status = "✗"
            
            print(f"{metric:<25} {vn_str:<15} {vs_str:<15} {diff_str:<15} {pct_diff:<10} {status}")


def export_comparison(comparison: Dict, symbol: str, filename: Optional[str] = None):
    """Export comparison to JSON file."""
    if filename is None:
        filename = f"comparison_{symbol}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Comparison exported to: {filename}")


def main():
    """Main comparison workflow."""
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python compare_data_sources.py <SYMBOL> [provider] [--export]")
        print("\nExample:")
        print("  python compare_data_sources.py FRT")
        print("  python compare_data_sources.py GVT vci")
        print("  python compare_data_sources.py FRT vci --export")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    provider = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else "vci"
    export = "--export" in sys.argv
    
    print(f"\n🔍 Comparing data sources for {symbol}...")
    print(f"   VNStock Provider: {provider}")
    print(f"   Vietstock Source: samples.json\n")
    
    # Load Vietstock scraped data
    print("📥 Loading Vietstock scraped data...")
    vietstock_records = load_vietstock_sample(symbol)
    if vietstock_records is None:
        sys.exit(1)
    print(f"   ✓ Loaded {len(vietstock_records)} records from Vietstock")
    
    # Fetch VNStock data
    print(f"\n📥 Fetching VNStock data (provider: {provider})...")
    vnstock_records, error = fetch_financial_data_vnstock(symbol, provider=provider, include_quarterly=True)
    
    if error or vnstock_records is None:
        print(f"   ❌ Error: {error}")
        sys.exit(1)
    
    print(f"   ✓ Fetched {len(vnstock_records)} records from VNStock")
    
    # Compare data
    print("\n🔄 Comparing data sources...")
    comparison = compare_records(vnstock_records, vietstock_records)
    
    # Print results
    print_summary(comparison, symbol)
    print_detailed_comparison(comparison, limit=10)
    
    # Export if requested
    if export:
        export_comparison(comparison, symbol)
    
    # Overall assessment
    print(f"\n{'='*80}")
    print("📊 ASSESSMENT")
    print(f"{'='*80}\n")
    
    total_metrics = sum(m['total_comparisons'] for m in comparison['metrics'].values())
    total_matches = sum(m['matches'] for m in comparison['metrics'].values())
    match_rate = (total_matches / total_metrics * 100) if total_metrics > 0 else 0
    
    print(f"Overall Match Rate: {match_rate:.1f}%")
    
    if match_rate >= 90:
        print("✅ Excellent: VNStock data closely matches Vietstock scraping")
    elif match_rate >= 70:
        print("⚠️  Good: Some differences exist but data is generally consistent")
    elif match_rate >= 50:
        print("⚠️  Fair: Significant differences detected, review recommended")
    else:
        print("❌ Poor: Major discrepancies, investigation required")
    
    print("\n💡 Tips:")
    print("  • Small differences (<1%) are normal due to rounding or data source timing")
    print("  • Large differences may indicate different calculation methods")
    print("  • Missing periods in one source are expected (data availability varies)")
    print("  • Use --export flag to save detailed comparison to JSON")
    
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Comparison cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
