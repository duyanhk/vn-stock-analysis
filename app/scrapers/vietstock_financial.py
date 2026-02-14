from __future__ import annotations

import os
import re
import time
from typing import List, Dict

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


def scrape_and_analyze(
    symbol: str,
    output_dir: str,
    *,
    headless: bool = True,
    timeout: int = 20,
    window_size: str = "1920,1080",
    save_csv: bool = True,
) -> pd.DataFrame:
    """
    Scrape Vietstock for a given symbol and compute key ratios.

    This is largely adapted from the existing reference implementation.
    When save_csv is False, the CSV is not written to output_dir (used when
    data is served from the app and CSV is only written on explicit Download).
    """

    url = f"https://finance.vietstock.vn/{symbol}/tai-chinh.htm?tab=BCTT"
    target_indices = [3, 5, 7]
    section_names = [
        f"Kết quả kinh doanh - {symbol}",
        f"Cân đối kế toán - {symbol}",
        f"Chỉ số tài chính - {symbol}",
    ]

    def setup_driver() -> webdriver.Chrome:
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument(f"window-size={window_size}")
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )

    def wait_for_table_stabilize(driver: webdriver.Chrome, timeout_sec: int = timeout) -> bool:
        last_row_count = -1
        for _ in range(timeout_sec):
            try:
                tables = driver.find_elements(By.CSS_SELECTOR, "table.table-hover")
                if not tables:
                    time.sleep(1)
                    continue
                last_table = tables[-1]
                rows = last_table.find_elements(By.TAG_NAME, "tr")
                if len(rows) != last_row_count:
                    last_row_count = len(rows)
                    time.sleep(1)
                    continue
                return True
            except Exception:
                time.sleep(1)
        return False

    def get_header_texts(driver: webdriver.Chrome) -> List[str]:
        return driver.execute_script(
            """
            const tables = document.querySelectorAll("table.table-hover");
            if (!tables.length) return [];
            const lastTable = tables[tables.length - 1];
            const headers = Array.from(lastTable.querySelectorAll("thead th"));
            return headers.map(h => h.innerText.trim()).filter(h => h);
        """
        )

    def wait_for_table_update(
        driver: webdriver.Chrome, old_headers: List[str], label: str
    ) -> None:
        def headers_changed(drv: webdriver.Chrome) -> bool:
            try:
                new_headers = get_header_texts(drv)
                return len(new_headers) >= 2 and new_headers[1:] != old_headers[1:]
            except Exception:
                return False

        try:
            WebDriverWait(driver, timeout).until(headers_changed)
            wait_for_table_stabilize(driver)
        except Exception:
            driver.save_screenshot(f"debug_update_fail_{label}.png")
            with open(
                f"debug_update_fail_{label}.html", "w", encoding="utf-8"
            ) as f:
                f.write(driver.page_source)
            driver.quit()
            raise Exception(f"❌ Table did not update after selecting: {label}")

    def extract_data(driver: webdriver.Chrome) -> List[Dict]:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        all_rows: List[Dict] = []

        for i, idx in enumerate(target_indices):
            if idx >= len(tables):
                print(f"⚠️ Table {idx + 1} not found, skipping.")
                continue

            section = section_names[i] if i < len(section_names) else f"Table {idx + 1}"
            table = tables[idx]
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            if not headers or len(headers) < 2:
                print(f"⚠️ Skipping Table {idx + 1} due to missing headers.")
                continue

            headers[0] = "Metric"

            for tr in table.find_all("tr")[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if not cols:
                    continue
                while len(cols) < len(headers):
                    cols.append("")
                row_dict = dict(zip(headers, cols))
                row_dict["Section"] = section
                all_rows.append(row_dict)

            print(f"✅ Extracted {len(all_rows)} rows from {section}")
        return all_rows

    driver = setup_driver()
    driver.get(url)
    driver.execute_script("document.body.style.zoom='80%'")

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.NAME, "NumberPeriod"))
    )
    WebDriverWait(driver, 15).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table"))
    )
    wait_for_table_stabilize(driver)
    print("📥 Loading financial tables...")

    # Step 1: Set unit to "Triệu đồng"
    unit_select = Select(driver.find_element(By.NAME, "UnitDong"))
    unit_select.select_by_value("1000000")
    time.sleep(1)
    wait_for_table_stabilize(driver)

    # Step 2: Detect current frequency
    freq_select = Select(driver.find_element(By.NAME, "NumberPeriod"))
    selected_value = freq_select.first_selected_option.get_attribute("value")
    current_freq = "Năm" if selected_value == "NAM" else "Quý"
    alt_freq = "Quý" if current_freq == "Năm" else "Năm"
    alt_freq_value = "QUY" if current_freq == "Năm" else "NAM"
    print(f"📊 Starting with {current_freq} frequency, will also extract {alt_freq}")

    # Step 3: Select 'Tất cả'
    initial_headers = get_header_texts(driver)
    Select(driver.find_element(By.NAME, "period")).select_by_value("-1")
    time.sleep(1)
    wait_for_table_stabilize(driver)
    driver.execute_script("window.scrollTo(0, 1000);")
    wait_for_table_update(driver, initial_headers, "Tất cả")

    # Step 4: Extract data for current frequency
    print(f"📥 Extracting {current_freq} data...")
    data_current = extract_data(driver)
    
    # Verify columns for current frequency
    current_headers = get_header_texts(driver)
    if current_freq == "Quý":
        quarterly_headers = [h for h in current_headers if re.match(r"^Q[1-4]/\d{4}$", h)]
        if quarterly_headers:
            print(f"✅ {len(quarterly_headers)} quarterly columns detected")
        else:
            print("⚠️ Warning: No quarterly columns detected!")
    elif current_freq == "Năm":
        annual_headers = [h for h in current_headers if re.match(r"^\d{4}$", h)]
        if annual_headers:
            print(f"✅ {len(annual_headers)} annual columns detected")
        else:
            print("⚠️ Warning: No annual columns detected!")

    # Step 5: Switch to alternate frequency
    headers_before_alt = get_header_texts(driver)
    Select(driver.find_element(By.NAME, "NumberPeriod")).select_by_value(alt_freq_value)
    print(f"🔄 Switching to {alt_freq} frequency...")
    time.sleep(1)
    wait_for_table_stabilize(driver)
    driver.execute_script("window.scrollTo(0, 1000);")
    wait_for_table_update(driver, headers_before_alt, alt_freq)
    
    # Additional wait and verification for alternate frequency
    if alt_freq == "Năm":
        time.sleep(2)  # Extra wait for annual data to fully render
        wait_for_table_stabilize(driver)
        final_headers = get_header_texts(driver)
        annual_headers = [h for h in final_headers if re.match(r"^\d{4}$", h)]
        if annual_headers:
            print(f"✅ {len(annual_headers)} annual columns detected")
        else:
            print("⚠️ Warning: No annual columns detected!")
    elif alt_freq == "Quý":
        final_headers = get_header_texts(driver)
        quarterly_headers = [h for h in final_headers if re.match(r"^Q[1-4]/\d{4}$", h)]
        if quarterly_headers:
            print(f"✅ {len(quarterly_headers)} quarterly columns detected")
        else:
            print("⚠️ Warning: No quarterly columns detected!")
    
    print(f"📥 Extracting {alt_freq} data...")
    data_alt = extract_data(driver)

    driver.quit()

    # Step 6: Merge and clean
    all_data = data_current + data_alt
    if not all_data:
        raise ValueError(f"No financial table data found for symbol '{symbol}'.")

    df = pd.DataFrame(all_data)

    # Ensure all columns exist and preserve original order
    all_columns = []
    seen = set()
    for row in all_data:
        for col in row:
            if col not in seen:
                all_columns.append(col)
                seen.add(col)

    for col in all_columns:
        if col not in df.columns:
            df[col] = ""

    # Store original row order
    df["_original_order"] = range(len(df))

    # --- Step 6.1: Group by Section & Metric, keep first non-empty distinct value ---
    # Metrics we care about for debugging
    target_metrics = [
        "Doanh thu thuần về bán hàng và cung cấp dịch vụ",  # revenue
        "Lợi nhuận sau thuế thu nhập doanh nghiệp",  # net income
        "Doanh thu hoạt động tài chính",  # financial income
        "Lợi nhuận thuần từ hoạt động kinh doanh",  # operating income
        "Vốn chủ sở hữu",  # equity
        "Nợ phải trả",  # liability (total liabilities)
        "Tiền và các khoản tương đương tiền",  # cash and equivalent
        "Các khoản đầu tư tài chính ngắn hạn",  # cash investment
    ]
    
    def merge_group(group: pd.DataFrame) -> pd.Series:
        merged: Dict = {}
        # Check if this is one of our target metrics
        is_target_metric = False
        metric_name = ""
        if len(group) > 0 and "Metric" in group.columns:
            try:
                metric_name = str(group.iloc[0]["Metric"]).strip()
                is_target_metric = metric_name in target_metrics
            except Exception as e:
                pass
        
        # Only debug for target metrics with multiple rows and annual columns
        annual_cols_in_group = [col for col in group.columns if re.match(r"^\d{4}$", col)]
        should_debug = is_target_metric and len(group) > 1 and len(annual_cols_in_group) > 0
        
        if should_debug:
            print(f"\n🔀 Merging {len(group)} rows for: {metric_name[:50]}...")
            # Check both quarterly and annual data for each row
            quarterly_cols_in_group = [col for col in group.columns if re.match(r"^Q[1-4]/\d{4}$", str(col))]
            
            for idx, row in group.iterrows():
                # Check quarterly data
                has_quarterly = False
                if quarterly_cols_in_group:
                    sample_quarterly = {col: str(row[col]).strip() for col in quarterly_cols_in_group[:3] if col in row}
                    non_empty_quarterly = {k: v for k, v in sample_quarterly.items() if v and v not in ["", "nan", "NaN", "None"]}
                    has_quarterly = len(non_empty_quarterly) > 0
                
                # Check annual data
                has_annual = False
                if annual_cols_in_group:
                    sample_annual = {col: str(row[col]).strip() for col in annual_cols_in_group[:3] if col in row}
                    non_empty_annual = {k: v for k, v in sample_annual.items() if v and v not in ["", "nan", "NaN", "None"]}
                    has_annual = len(non_empty_annual) > 0
                
                # Report what data this row has
                data_types = []
                if has_quarterly:
                    data_types.append("quarterly")
                if has_annual:
                    data_types.append("annual")
                
                if data_types:
                    print(f"   Row {idx}: Has {', '.join(data_types)} data")
                else:
                    print(f"   Row {idx}: No data found")
        
        for col in group.columns:
            if col in ["Section", "Metric", "_original_order"]:
                if len(group) > 0:
                    merged[col] = group.iloc[0][col]
                else:
                    merged[col] = ""
            else:
                # Get all non-empty values from all rows in the group
                # First filter out pandas NaN/None values, then convert to string
                mask_not_na = pd.notna(group[col])
                values = group[col][mask_not_na].astype(str).str.strip()
                # Filter out empty strings and string representations of NaN
                non_empty = values[~values.isin(["", "nan", "NaN", "None", "null", "Null"])]
                
                # Debug: Show merge result for annual columns in target metrics
                is_annual_col = bool(re.match(r"^\d{4}$", col))
                if should_debug and is_annual_col and len(non_empty) > 0:
                    selected_value = str(non_empty.iloc[0])
                    selected_idx = non_empty.index[0]
                    print(f"   {col}: Selected '{selected_value}' from row {selected_idx}")
                
                if len(non_empty):
                    # Take the first non-empty value (this preserves both quarterly and annual data)
                    merged[col] = str(non_empty.iloc[0])
                else:
                    merged[col] = ""
        
        # Debug: Summary of what was merged
        if should_debug:
            quarterly_cols_merged = [col for col in merged.keys() if re.match(r"^Q[1-4]/\d{4}$", str(col))]
            annual_cols_merged = [col for col in merged.keys() if re.match(r"^\d{4}$", str(col))]
            
            quarterly_with_data = sum(1 for col in quarterly_cols_merged[:5] if merged.get(col, "").strip() not in ["", "nan", "NaN", "None"])
            annual_with_data = sum(1 for col in annual_cols_merged[:5] if merged.get(col, "").strip() not in ["", "nan", "NaN", "None"])
            
            summary_parts = []
            if quarterly_with_data > 0:
                summary_parts.append(f"{quarterly_with_data} quarterly columns")
            if annual_with_data > 0:
                summary_parts.append(f"{annual_with_data} annual columns")
            
            if summary_parts:
                print(f"   ✅ Merged result: {', '.join(summary_parts)} with data")
            else:
                print(f"   ⚠️ Merged result: No data found")
        
        return pd.Series(merged)

    # Debug: Check revenue metric before merge - check both quarterly and annual
    revenue_rows_before = df[df["Metric"].str.strip() == "Doanh thu thuần về bán hàng và cung cấp dịch vụ"]
    if not revenue_rows_before.empty:
        quarterly_cols_before = [col for col in revenue_rows_before.columns if re.match(r"^Q[1-4]/\d{4}$", str(col))]
        annual_cols_before = [col for col in revenue_rows_before.columns if re.match(r"^\d{4}$", col)]
        
        if quarterly_cols_before or annual_cols_before:
            print(f"\n📊 Pre-merge check: {len(revenue_rows_before)} revenue rows")
            for idx, row in revenue_rows_before.iterrows():
                # Check quarterly data
                has_quarterly = False
                if quarterly_cols_before:
                    sample_quarterly = {col: str(row[col]).strip() for col in quarterly_cols_before[:3] if col in row}
                    non_empty_quarterly = {k: v for k, v in sample_quarterly.items() if v and v not in ["", "nan", "NaN", "None"]}
                    has_quarterly = len(non_empty_quarterly) > 0
                
                # Check annual data
                has_annual = False
                if annual_cols_before:
                    sample_annual = {col: str(row[col]).strip() for col in annual_cols_before[:3] if col in row}
                    non_empty_annual = {k: v for k, v in sample_annual.items() if v and v not in ["", "nan", "NaN", "None"]}
                    has_annual = len(non_empty_annual) > 0
                
                # Report what data this row has
                data_types = []
                if has_quarterly:
                    data_types.append("quarterly")
                if has_annual:
                    data_types.append("annual")
                
                if data_types:
                    print(f"   Row {idx}: Has {', '.join(data_types)} data")
                else:
                    print(f"   Row {idx}: No data found")
    
    
    df = (
        df.groupby(["Section", "Metric"], sort=False, as_index=False)
        .apply(merge_group)
        .reset_index(drop=True)
    )
    
    # Debug: Verify merge result - check both quarterly and annual data are preserved
    revenue_rows_after = df[df["Metric"].str.strip() == "Doanh thu thuần về bán hàng và cung cấp dịch vụ"]
    if not revenue_rows_after.empty:
        row = revenue_rows_after.iloc[0]
        
        # Check quarterly data
        quarterly_cols_after = [col for col in revenue_rows_after.columns if re.match(r"^Q[1-4]/\d{4}$", str(col))]
        has_quarterly_after = False
        if quarterly_cols_after:
            sample_quarterly = {col: str(row[col]).strip() for col in quarterly_cols_after[:3] if col in row}
            non_empty_quarterly = {k: v for k, v in sample_quarterly.items() if v and v not in ["", "nan", "NaN", "None"]}
            has_quarterly_after = len(non_empty_quarterly) > 0
        
        # Check annual data
        annual_cols_after = [col for col in revenue_rows_after.columns if re.match(r"^\d{4}$", col)]
        has_annual_after = False
        if annual_cols_after:
            sample_annual = {col: str(row[col]).strip() for col in annual_cols_after[:3] if col in row}
            non_empty_annual = {k: v for k, v in sample_annual.items() if v and v not in ["", "nan", "NaN", "None"]}
            has_annual_after = len(non_empty_annual) > 0
        
        # Report preservation status
        preserved = []
        if has_quarterly_after:
            preserved.append("quarterly")
        if has_annual_after:
            preserved.append("annual")
        
        if preserved:
            print(f"✅ Post-merge: Preserved {', '.join(preserved)} data")
        else:
            print(f"⚠️ Post-merge: No data preserved")

    # --- Step 6.2: Normalize and drop full duplicates (excluding Section) ---
    dedup_columns = [
        col for col in df.columns if col not in ["Section", "_original_order"]
    ]

    # pandas 3 removed DataFrame.applymap; use column-wise map instead
    df[dedup_columns] = df[dedup_columns].apply(
        lambda col: col.map(lambda x: str(x).strip() if pd.notna(x) else x)
    )
    df = df.drop_duplicates(subset=dedup_columns, keep="first")

    # --- Step 6.3: Sort and reorder columns ---
    df = df.sort_values("_original_order")
    fixed = ["Section", "Metric"]
    rest = [col for col in all_columns if col not in fixed]
    df = df[fixed + rest + ["_original_order"]]
    df = df.drop(columns="_original_order")

    # Normalize column names for time periods
    def normalize_columns(cols):
        new_cols = []
        year_pattern = re.compile(r"\b(19\d{2}|20\d{2})\b")
        for col in cols:
            # Already-normalized form like 2014-Q1 or 2014-FY
            if re.match(r"^\d{4}-(Q[1-4]|FY)$", col):
                new_cols.append(col)
                continue

            # Typical quarterly header: Q2/2014
            if re.match(r"^Q[1-4]/\d{4}$", col):
                q, y = col.split("/")
                new_cols.append(f"{y}-{q}")
                continue

            # More flexible handling for annual headers that contain a 4-digit year,
            # possibly with surrounding text like "Năm 2014" or "2014 (YoY)".
            m = year_pattern.search(col)
            if m:
                year = m.group(1)
                new_cols.append(f"{year}-FY")
            else:
                new_cols.append(col)
        return new_cols

    df.columns = normalize_columns(df.columns)

    # Sort columns: Section, Metric, then time periods
    time_cols = [col for col in df.columns if re.match(r"^\d{4}-(Q[1-4]|FY)$", col)]
    annual_cols = [col for col in time_cols if "-FY" in col]
    quarterly_cols = [col for col in time_cols if "-Q" in col]
    print(f"\n📈 Data summary: {len(annual_cols)} annual periods, {len(quarterly_cols)} quarterly periods")
    time_cols_sorted = sorted(
        time_cols,
        key=lambda x: (
            int(x[:4]),
            {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}[x[-2:]],
        ),
    )
    df = df[["Section", "Metric"] + time_cols_sorted]

    # Drop rows where all values (except 'Section' and 'Metric') are blank
    value_columns = [col for col in df.columns if col not in ["Section", "Metric"]]
    df = df[
        ~df[value_columns].apply(
            lambda row: all(str(v).strip() == "" for v in row), axis=1
        )
    ].copy()

    def is_numeric(val: str) -> bool:
        try:
            float(str(val).replace(",", ""))
            return True
        except Exception:
            return False

    # Fill blank cells with "0" under certain conditions
    for section in df["Section"].unique():
        section_df = df[df["Section"] == section]
        for col in time_cols_sorted:
            col_values = section_df[col].astype(str).str.replace(",", "").str.strip()
            numeric_mask = col_values.apply(is_numeric)
            if numeric_mask.sum() > len(section_df) / 2:
                for idx, row in section_df.iterrows():
                    row_vals = row[time_cols_sorted].astype(str).str.strip()
                    if all(
                        val == "" or is_numeric(val.replace(",", ""))
                        for val in row_vals
                    ):
                        if not is_numeric(str(row[col]).replace(",", "").strip()):
                            df.at[idx, col] = "0"

    # ----- Ratio calculations -----

    def extract_series(metric_name: str) -> pd.Series:
        row = df[df["Metric"].str.strip() == metric_name]
        if row.empty:
            raise ValueError(f"❌ Metric '{metric_name}' not found.")
        series = row.iloc[0].drop(["Section", "Metric"])
        return pd.to_numeric(
            series.replace({",": ""}, regex=True), errors="coerce"
        )

    revenue = extract_series("Doanh thu thuần về bán hàng và cung cấp dịch vụ")
    net_income = extract_series("Lợi nhuận sau thuế thu nhập doanh nghiệp")
    # Optional: Vietstock does not provide interest-bearing debt / loan (short-term & long-term)
    try:
        financial_income = extract_series("Doanh thu hoạt động tài chính")
    except ValueError:
        financial_income = pd.Series(dtype="float64")
    try:
        operating_income = extract_series("Lợi nhuận thuần từ hoạt động kinh doanh")
    except ValueError:
        operating_income = pd.Series(dtype="float64")
    equity = extract_series("Vốn chủ sở hữu")
    liability = extract_series("Nợ phải trả")
    cash_and_equivalent = extract_series("Tiền và các khoản tương đương tiền")
    cash_equivalent_investment = extract_series(
        "Các khoản đầu tư tài chính ngắn hạn"
    )
    
    # Debug: Verify annual data in final series
    annual_cols_in_series = [col for col in revenue.index if "-FY" in col]
    if annual_cols_in_series:
        sample_annual_values = revenue[annual_cols_in_series[:3]]
        non_null_count = sample_annual_values.notna().sum()
        if non_null_count > 0:
            print(f"✅ Final validation: {non_null_count}/3 annual revenue values present")
        else:
            print(f"⚠️ Final validation: No annual revenue values found")

    # Some metrics may be partially missing by period. For financial ratios it is
    # usually better to treat missing balances as 0 than to let them propagate
    # NaNs everywhere.
    revenue = revenue.fillna(0)
    net_income = net_income.fillna(0)
    if not financial_income.empty:
        financial_income = financial_income.reindex(liability.index).fillna(0)
    else:
        financial_income = pd.Series(0.0, index=liability.index)
    if not operating_income.empty:
        operating_income = operating_income.reindex(liability.index).fillna(0)
    else:
        operating_income = pd.Series(0.0, index=liability.index)
    equity = equity.fillna(0)
    liability = liability.fillna(0)
    cash_and_equivalent = cash_and_equivalent.fillna(0)
    cash_equivalent_investment = cash_equivalent_investment.fillna(0)

    quarterly_idx = [col for col in net_income.index if "-Q" in col]
    annual_idx = [col for col in net_income.index if "-FY" in col]

    roe = pd.Series(dtype="float64", index=net_income.index)
    roic = pd.Series(dtype="float64", index=net_income.index)
    npm = pd.Series(index=net_income.index, dtype="float64")

    roe[annual_idx] = net_income[annual_idx] / equity[annual_idx]
    roic[annual_idx] = net_income[annual_idx] / (
        equity[annual_idx]
        + liability[annual_idx]
        - cash_and_equivalent[annual_idx]
        - cash_equivalent_investment[annual_idx]
    )
    npm[annual_idx] = net_income[annual_idx] / revenue[annual_idx]

    quarterly_df = pd.DataFrame(
        {
            "Revenue": revenue[quarterly_idx],
            "NetIncome": net_income[quarterly_idx],
            "Financial Income": financial_income.reindex(quarterly_idx).fillna(0),
            "Operating Income": operating_income.reindex(quarterly_idx).fillna(0),
            "Equity": equity[quarterly_idx],
            "Liability": liability[quarterly_idx],
            "CashAndEquivalent": cash_and_equivalent[quarterly_idx],
            "CashInvestment": cash_equivalent_investment[quarterly_idx],
        }
    )

    quarterly_df = quarterly_df.loc[
        sorted(quarterly_df.index, key=lambda x: (int(x[:4]), int(x[-1])))
    ]

    # --- Trailing-4-quarter (T4Q) logic: only use 4 *consecutive* calendar quarters ---
    # If a quarter doesn't have 4 consecutive quarters of data, ratio/growth = blank.

    def trailing_four_quarters(period: str) -> List[str]:
        """Return the 4 consecutive quarter labels ending at period (e.g. 2012-Q2 -> [2011-Q3, 2011-Q4, 2012-Q1, 2012-Q2])."""
        if "-Q" not in period or len(period) < 7:
            return []
        year = int(period[:4])
        q = int(period[-1])
        out: List[str] = []
        for _ in range(4):
            out.append(f"{year}-Q{q}")
            q -= 1
            if q == 0:
                q = 4
                year -= 1
        return list(reversed(out))

    q_index = set(quarterly_df.index)
    roe_q = pd.Series(index=quarterly_df.index, dtype="float64")
    roic_q = pd.Series(index=quarterly_df.index, dtype="float64")
    npm_q = pd.Series(index=quarterly_df.index, dtype="float64")
    rolling_revenue = pd.Series(index=quarterly_df.index, dtype="float64")
    rolling_net_income = pd.Series(index=quarterly_df.index, dtype="float64")

    for period in quarterly_df.index:
        t4q = trailing_four_quarters(period)
        if len(t4q) != 4 or not all(p in q_index for p in t4q):
            continue
        rev_sum = quarterly_df.loc[t4q, "Revenue"].sum()
        ni_sum = quarterly_df.loc[t4q, "NetIncome"].sum()
        eq_mean = quarterly_df.loc[t4q, "Equity"].mean()
        inv_mean = (
            quarterly_df.loc[t4q, "Equity"].values
            + quarterly_df.loc[t4q, "Liability"].values
            - quarterly_df.loc[t4q, "CashAndEquivalent"].values
            - quarterly_df.loc[t4q, "CashInvestment"].values
        ).mean()
        rolling_revenue[period] = rev_sum
        rolling_net_income[period] = ni_sum
        if eq_mean and eq_mean != 0:
            roe_q[period] = ni_sum / eq_mean
        if inv_mean and inv_mean != 0:
            roic_q[period] = ni_sum / inv_mean
        if rev_sum and rev_sum != 0:
            npm_q[period] = ni_sum / rev_sum

    roe.update(roe_q)
    roic.update(roic_q)
    npm.update(npm_q)

    # --- Single-quarter (non-T4Q) metrics: use only that quarter's data ---
    roe_single = pd.Series(dtype="float64", index=net_income.index)
    roic_single = pd.Series(dtype="float64", index=net_income.index)
    npm_single = pd.Series(index=net_income.index, dtype="float64")
    roe_single[annual_idx] = roe[annual_idx]
    roic_single[annual_idx] = roic[annual_idx]
    npm_single[annual_idx] = npm[annual_idx]
    for period in quarterly_df.index:
        eq = quarterly_df.loc[period, "Equity"]
        inv = (
            quarterly_df.loc[period, "Equity"]
            + quarterly_df.loc[period, "Liability"]
            - quarterly_df.loc[period, "CashAndEquivalent"]
            - quarterly_df.loc[period, "CashInvestment"]
        )
        rev = quarterly_df.loc[period, "Revenue"]
        ni = quarterly_df.loc[period, "NetIncome"]
        if eq and eq != 0:
            roe_single[period] = ni / eq
        if inv and inv != 0:
            roic_single[period] = ni / inv
        if rev and rev != 0:
            npm_single[period] = ni / rev

    revenue_growth = pd.Series(index=revenue.index, dtype="float64")
    net_income_growth = pd.Series(index=net_income.index, dtype="float64")
    revenue_growth_single = pd.Series(index=revenue.index, dtype="float64")
    net_income_growth_single = pd.Series(index=net_income.index, dtype="float64")

    # Annual YoY growth
    for i in range(1, len(annual_idx)):
        this_year = annual_idx[i]
        last_year = annual_idx[i - 1]
        if this_year[:4].isdigit() and last_year[:4].isdigit():
            rev_this = revenue[this_year]
            rev_last = revenue[last_year]
            ni_this = net_income[this_year]
            ni_last = net_income[last_year]

            if pd.notna(rev_this) and pd.notna(rev_last) and rev_last != 0:
                revenue_growth[this_year] = (rev_this - rev_last) / abs(rev_last)
                revenue_growth_single[this_year] = revenue_growth[this_year]
            if pd.notna(ni_this) and pd.notna(ni_last) and ni_last != 0:
                net_income_growth[this_year] = (ni_this - ni_last) / abs(ni_last)
                net_income_growth_single[this_year] = net_income_growth[this_year]

    # Quarterly single-quarter YoY growth: this quarter vs same quarter last year
    for period in quarterly_df.index:
        cur_year = int(period[:4])
        cur_quarter = period[-1]
        prev_period = f"{cur_year - 1}-Q{cur_quarter}"
        if prev_period not in q_index:
            continue
        cur_rev = revenue[period]
        prev_rev = revenue[prev_period]
        cur_ni = net_income[period]
        prev_ni = net_income[prev_period]
        if pd.notna(prev_rev) and prev_rev != 0 and pd.notna(cur_rev):
            revenue_growth_single[period] = (cur_rev - prev_rev) / abs(prev_rev)
        if pd.notna(prev_ni) and prev_ni != 0 and pd.notna(cur_ni):
            net_income_growth_single[period] = (cur_ni - prev_ni) / abs(prev_ni)

    # Quarterly trailing 4Q YoY growth: only when both current and same-quarter-last-year T4Q exist
    for period in quarterly_df.index:
        if "-Q" not in period:
            continue
        cur_rev = rolling_revenue.get(period)
        cur_ni = rolling_net_income.get(period)
        if pd.isna(cur_rev) or pd.isna(cur_ni):
            continue
        cur_year = int(period[:4])
        cur_quarter = period[-1]
        prev_period = f"{cur_year - 1}-Q{cur_quarter}"
        if prev_period not in q_index:
            continue
        prev_rev = rolling_revenue.get(prev_period)
        prev_ni = rolling_net_income.get(prev_period)
        if pd.isna(prev_rev) or pd.isna(prev_ni):
            continue
        if prev_rev and prev_rev != 0:
            revenue_growth[period] = (cur_rev - prev_rev) / abs(prev_rev)
        if prev_ni and prev_ni != 0:
            net_income_growth[period] = (cur_ni - prev_ni) / abs(prev_ni)

    # --- Step 6: Build final output with both absolute values and ratios ---
    # Note: Vietstock scraping does not provide interest-bearing debt / loan (short-term & long-term).
    output_df = pd.DataFrame(
        {
            # Absolute metrics (already aligned to the same index)
            "Revenue": revenue,
            "Net Income": net_income,
            "Financial Income": financial_income,
            "Operating Income": operating_income,
            "Equity": equity,
            "Liability": liability,
            "Cash And Equivalent": cash_and_equivalent,
            "Cash Investment": cash_equivalent_investment,
            # Ratios (T4Q for quarters where 4 consecutive quarters exist)
            "ROE": roe,
            "ROIC": roic,
            "Net Profit Margin": npm,
            "Revenue YoY Growth": revenue_growth,
            "Net Income YoY Growth": net_income_growth,
            # Single-quarter (non-T4Q) metrics
            "ROE (Q)": roe_single,
            "ROIC (Q)": roic_single,
            "Net Profit Margin (Q)": npm_single,
            "Revenue YoY Growth (Q)": revenue_growth_single,
            "Net Income YoY Growth (Q)": net_income_growth_single,
        }
    )

    # Drop rows where absolutely everything is missing
    output_df = output_df.dropna(how="all")

    # Name the index and add a PeriodType column (Quarter vs Year)
    output_df.index.name = "Period"
    period_index = output_df.index.astype(str)
    output_df["PeriodType"] = [
        "Quarter" if "-Q" in p else "Year" if p.endswith("-FY") else "Unknown"
        for p in period_index
    ]

    if save_csv:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{symbol}_result.csv")
        output_df.to_csv(output_path, encoding="utf-8-sig")

    return output_df

