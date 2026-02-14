# Debug & Operations Guide

This document combines all project documentation used for debugging, migration, rate limits, and data comparison. Debug and comparison scripts live in **`debug/`**. Run them from the **project root** so paths like `app/sample_data/samples.json` resolve correctly, e.g. `python debug/quick_compare.py FRT`. This document lives in `debug/DEBUG.md`.

---

# Folder layout

| Type | Contents |
|------|----------|
| **Scripts** | `*.py` — run from project root (e.g. `python debug/script_name.py`) |
| **Generated** | `*.json` — outputs from scripts with `--save`; safe to delete and regenerate |
| **Doc** | `DEBUG.md` — this file |

**Generated files (can be cleaned):**

- `compare_kbs_vci_structure.json` — from `compare_kbs_vci_structure.py [SYMBOL] --save`
- `gmd_2025_financials_fields_VCI.json` — from `fetch_gmd_2025_financials.py [SYMBOL] --provider VCI --save`
- `gmd_2025_financials_fields_KBS.json` — from `fetch_gmd_2025_financials.py [SYMBOL] --provider KBS --save`

To **clean**: delete the `*.json` files in `debug/` when you don’t need them; re-run the relevant script with `--save` to regenerate. Optionally add `debug/*.json` to `.gitignore` if you don’t want to commit these outputs.

---

# Part 1: Rate Limit Solution

## Problem Identified

**VNStock Guest Tier Limits**:
- 20 requests per minute
- Each symbol fetch = 6 API calls (balance + income + cash × 2 for annual + quarterly)
- With 6 calls per symbol, you can only fetch ~3 symbols per minute
- Previous 2-second delays were too aggressive (30 calls/minute)

## Solution Implemented

### 1. Increased Delay
```python
RATE_LIMIT_DELAY = 2  # seconds (configurable in vnstock_financial_service.py)
```
- 60 seconds ÷ 2 seconds = 30 requests/minute (buffer for 20/min limit when combined with natural latency)
- 3 API calls (annual only) = ~6+ seconds per symbol
- 6 API calls (annual + quarterly) = ~12+ seconds per symbol

### 2. Disabled Quarterly Data by Default
```python
VNSTOCK_INCLUDE_QUARTERLY = False  # Only fetch annual data (3 API calls instead of 6)
```
- Reduces API calls by 50%
- Annual data is usually sufficient for analysis

### 3. Automatic Retry
- If rate limit is hit: wait 10 seconds, retry once, then fall back to Vietstock scraping if still fails

## Testing

```bash
# From project root
python debug/debug_rate_limit.py
python debug/quick_compare.py FRT
```

## API Call Budget (Guest Tier 20 req/min)

| Configuration           | API Calls | Time/Symbol | Symbols/Min |
|-------------------------|-----------|-------------|-------------|
| Annual Only (2s delay)  | 3         | ~6–12s      | 4–5         |
| Annual + Quarterly (2s) | 6         | ~12–24s     | 2–3         |

## Configuration Options

```bash
# Include quarterly data
export VNSTOCK_INCLUDE_QUARTERLY=True

# Disable VNStock (scraping only)
export USE_VNSTOCK_PRIMARY=False

# Use cached data only
export USE_SAMPLE_DATA=True
```

---

# Part 2: VNStock Rate Limits & Tiers

| Tier       | Requests/Minute | How to Get                    |
|------------|-----------------|-------------------------------|
| **Guest**  | 20              | Default (no registration)     |
| **Community** | 60           | Register at vnstocks.com      |
| **Sponsor**   | 180–600      | Insiders program              |

## Solutions Implemented

1. **Rate limit delays** between API calls
2. **Automatic retry** (wait 10s, retry once)
3. **Removed SSI** from financial providers where not supported
4. **Fallback** to Vietstock scraping when VNStock fails

## Error Messages

**Rate Limit Exceeded**: Wait 60 seconds or get API key.

**No Data Available**: System automatically tries Vietstock scraping.

---

# Part 3: VNStock Financial Data Migration

## Architecture

1. **Primary**: VNStock API (fast, no browser)
2. **Fallback**: Vietstock web scraping (Selenium)

Flow: Try VNStock (VCI, then KBS) → if fail, try Vietstock scraping → return data or error.

## Configuration

- `USE_VNSTOCK_PRIMARY=True` (default)
- `VNSTOCK_FINANCIAL_PROVIDERS = ["vci", "kbs"]` — VCI default (more years, IBD, Financial Income); KBS fallback
- VCI uses wide format (yearReport + metric columns); KBS uses long format (item_id + year columns). Both are supported.

## File Structure

- `app/services/vnstock_financial_service.py` — VNStock financial service (includes KBS long-format parsing)
- `app/services/financial_service.py` — Primary/fallback orchestration
- `debug/test_vnstock_financial.py` — Test script (run from project root)

## Data Format (Unified Output)

- Period: `YYYY-FY` (annual) or `YYYY-QN` (quarterly)
- Values in millions VND
- Ratios: ROE, ROIC, Net Profit Margin, YoY growth
- Terminology: **Liability** (not Debt); **Interest Bearing Debt** (short/long) from VNStock only; Vietstock scraping does not provide interest-bearing debt

## Providers

| Provider | Status   | Notes                          |
|----------|----------|---------------------------------|
| **VCI**  | Active   | Default; wide-format; more years, IBD, Financial Income |
| **KBS**  | Active   | Fallback; long-format data (4 years)  |
| ~~TCBS~~ | Deprecated | Removed                        |
| ~~SSI~~  | Not supported for financials | Removed |

---

# Part 4: TCBS Provider Deprecation Fix

## Issue

TCBS deprecated as of December 2024: 401 Unauthorized, parameter validation errors.

## Solution

- Default provider: VCI first, then KBS fallback
- Period parameter: use `year` / `quarter` (not `annual` / `quarter`) when calling VNStock API
- Provider list: `["vci", "kbs"]` (TCBS and SSI removed for financials where not supported)

## VCI vs KBS

- **VCI** (default): Uses `lang="en"`; returns wide format (yearReport + metric columns); more years, IBD, Financial Income. Use `_build_financial_records`.
- **KBS** (fallback): No `lang` parameter; returns long format (item_id + year columns); 4 years per request. Use `_build_financial_records_from_kbs_long`.

---

# Part 5: Implementation Summary

## Files Created

- `app/services/vnstock_financial_service.py` — Fetch balance/income/cash, build records, KBS long-format support
- `test_vnstock_financial.py` — Test VNStock fetch
- `compare_kbs_vci_structure.py` — Compare KBS vs VCI DataFrame structure

## Files Modified

- `app/services/financial_service.py` — Try VNStock providers, then Vietstock fallback
- `config.py` — VNSTOCK_FINANCIAL_PROVIDERS, USE_VNSTOCK_PRIMARY, etc.

## Data Flow

```
User Request → VNStock (VCI then KBS) → Response
                     ↓ (if fails)
              Vietstock Scraping → Response
```

## Backward Compatibility

- Same API and frontend
- Same record shape (Liability, Financial Income, Operating Income, etc.)
- Vietstock scraping unchanged

---

# Part 6: Data Source Comparison Guide

## Why Compare?

- Validate VNStock vs Vietstock consistency
- Find discrepancies
- Decide acceptable tolerance

## Tools (run from project root)

### Quick Compare
```bash
python debug/quick_compare.py [SYMBOL] [provider]
# e.g. python debug/quick_compare.py FRT
# e.g. python debug/quick_compare.py GVT vci
```
- Side-by-side table, last 10 annual periods, key metrics, match indicators (✓ ~ ✗)

### Detailed Compare
```bash
python debug/compare_data_sources.py FRT [provider] [--export]
# e.g. python debug/compare_data_sources.py FRT vci --export
```
- Full periods, all metrics, statistics, optional JSON export

### KBS vs VCI Structure
```bash
python debug/compare_kbs_vci_structure.py [SYMBOL] [--save]
# e.g. python debug/compare_kbs_vci_structure.py GMD --save
```
- Prints shape/columns for balance_sheet, income_statement, cash_flow from KBS and VCI
- `--save` writes `compare_kbs_vci_structure.json` in `debug/`

### Full statement fields (VCI or KBS)
```bash
python debug/fetch_gmd_2025_financials.py [SYMBOL] [--provider VCI|KBS] [--save]
# e.g. python debug/fetch_gmd_2025_financials.py GMD --provider VCI --save
# e.g. python debug/fetch_gmd_2025_financials.py FRT --provider KBS --save
```
- Fetches full balance_sheet, income_statement, cash_flow for a symbol (default GMD)
- Prints all column names (VCI) or item_id/item (KBS) and 2025 row if available
- `--save` writes `debug/financials_fields_{SYMBOL}_{provider}.json` (used for mapping docs, e.g. `docs/vnstock_financial_items.md`)

## Workflow

1. Ensure sample data exists (run app and fetch a symbol, or use samples.json).
2. Quick check: `python debug/quick_compare.py FRT`
3. If needed, detailed: `python debug/compare_data_sources.py FRT vci --export`
4. Review match rates; &lt; 1% diff is often acceptable.

## Match Rates

- **90–100%**: Excellent
- **70–89%**: Good
- **50–69%**: Fair, review
- **&lt; 50%**: Investigate

## Common Issues

- **Symbol not in samples.json**: Fetch that symbol via app first, or use another symbol.
- **VNStock provider fails**: Try other provider (e.g. kbs if vci fails).
- **No common periods**: Check period formats and coverage in both sources.

---

# Debug Scripts Reference (project root)

| Script | Purpose |
|--------|---------|
| `debug_rate_limit.py` | Test API call timing and rate limits |
| `debug_vnstock.py` | Raw VNStock API: one symbol + provider, print balance/income/cash columns and sample rows |
| `diagnose_vnstock.py` | Matrix: test multiple symbols × providers (VCI/KBS), which succeed for balance/income/cash |
| `test_simple_vnstock.py` | Minimal smoke test: create stock, fetch balance_sheet (year), print shape (no args) |
| `test_vnstock_financial.py` | Test our service `fetch_financial_data_vnstock`: one symbol + provider, prints unified records |
| `quick_compare.py` | Quick VNStock vs Vietstock table (key metrics, last 10 periods) |
| `compare_data_sources.py` | Full VNStock vs Vietstock comparison and optional JSON export |
| `compare_kbs_vci_structure.py` | KBS vs VCI DataFrame structure (columns, shape); `--save` → JSON |
| `fetch_gmd_2025_financials.py` | Full statement field list for a symbol (default GMD), VCI or KBS; `--save` → `gmd_2025_financials_fields_{provider}.json` |

**Which script when (VNStock):**

- **Quick smoke test:** `test_simple_vnstock.py` (no args).
- **One-symbol deep dive (raw API):** `debug_vnstock.py [SYMBOL] [provider]`.
- **Which symbols work with which provider:** `diagnose_vnstock.py`.
- **Our pipeline (unified records):** `test_vnstock_financial.py [SYMBOL] [provider]`.
- **Full statement columns / item_ids for mapping:** `fetch_gmd_2025_financials.py [SYMBOL] --provider VCI|KBS --save`.

Run from **project root**, e.g.:
```bash
cd "D:\Dev Projects\Financial Scraping"
python debug/quick_compare.py FRT
```

---

# Cleanup checklist

When tidying the `debug/` folder:

1. **Delete generated JSONs** (optional): Remove `compare_kbs_vci_structure.json`, `gmd_2025_financials_fields*.json` if you don’t need them. Regenerate with the same script and `--save`.
2. **Keep all `*.py` scripts** — they are the debug tools; see the table above.
3. **Keep `DEBUG.md`** — this guide.
4. **Optional:** Add `debug/*.json` to the project `.gitignore` so generated outputs are not committed.
