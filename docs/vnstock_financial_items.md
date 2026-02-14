# VNStock Financial Items Reference — Full Statement Mapping

This document maps **full financial statement line items** (BCTC: balance sheet, income statement, cash flow) from **VNStock** to **VCI** and **KBS** API fields. Item names only; no values. Based on real GMD 2025 structure and `app/services/vnstock_financial_service.py`. Coverage has been validated with **GMD**, **VTP**, **QNS**, **HPG** (industrial) and **SHB** (bank).

---

## Overview

| Aspect | VCI | KBS |
|--------|-----|-----|
| **Format** | Wide — each row = one period (year/quarter), columns = metric names | Long — each row = one line item (`item_id`), columns = years (e.g. `2024`, `2023`) |
| **Period key** | `yearReport`, `lengthReport` (quarter) | Year columns (4-digit strings) |
| **History** | More years typically available | API returns ~4 years per request |
| **Language** | `lang=en` for English column names | `item` = Vietnamese label in API |
| **Quarterly** | Supported | Supported; annual long-format common |

**API:** `stock.finance.balance_sheet(...)`, `stock.finance.income_statement(...)`, `stock.finance.cash_flow(...)` with `period="year"` or `"quarter"`; VCI uses `lang="en"`.

### Unit differences (VCI vs KBS)

| Source | Raw API / DataFrame units | Conversion to millions VND (for app) |
|--------|----------------------------|--------------------------------------|
| **VCI** | **Raw VND** — column labels say "(Bn. VND)" but returned values are in full VND (e.g. 1,618,300,914,264) | ÷ 1,000,000 |
| **KBS** | **Thousands VND** — year-column values are in thousands (e.g. 1,618,300,914 means 1,618.3 bn VND) | ÷ 1,000 |

The app normalizes both to **millions VND** so downstream (Vietstock parity, UI) sees one unit. In `vnstock_financial_service.py`, VCI values are divided by 1,000,000; KBS values from the long-format DataFrame are divided by 1,000 (KBS returns thousands VND).

---

## Coverage and Variants

This mapping is primarily based on **GMD** (Gemadept Corporation) and validated with other industrial companies like **VTP** (Viettel Post), **QNS** (Quang Ngai Sugar), **HPG** (Hoa Phat Group), and **SHB** (Saigon-Hanoi Commercial Joint Stock Bank) for banking-specific items.

### Industrial vs. Bank Templates

The tables below describe the **industrial** (non-bank) BCTC (Báo cáo tài chính) format. **Banks** (e.g., SHB) utilize a distinct VCI template, and KBS may also show variations.

*   **Bank Balance Sheet (VCI examples):** `Balances with the SBV`, `Placements with and loans to other credit institutions`, `Trading Securities`, `Loans and advances to customers`, `Deposits from customers`, `Due to other credit institutions`, `Valuable papers issued`, etc.
*   **Bank Income Statement (VCI examples):** `Interest and Similar Income`, `Interest and Similar Expenses`, `Net Interest Income`, `Net fee and commission income`, `Net income from trading securities`, etc.
*   **Bank Cash Flow Statement:** Typically a reduced set of items compared to industrial companies.

### Symbol-Specific VCI Columns (Industrial)

While the core mapping is consistent, some VCI columns appear only for specific industrial symbols, reflecting their particular operations or historical accounting practices. These are often included in the general categories within the main tables below but might not be universally present across all industrial companies.

Examples observed during validation:
*   `Long-term loans receivables`, `Investment in properties`, `Goodwill`, `MINORITY INTERESTS`, `Good will (Bn. VND)`: Appears in GMD/HPG.
*   `Budget sources and other funds`: Appears in QNS.
*   `Interest income and dividends` (Cash Flow): Appears in QNS.

---

## 1. Balance Sheet — Bảng cân đối kế toán

### 1.1 Assets — TÀI SẢN

| Line item (BCTC / typical name) | VCI field | KBS item_id | KBS item (label) |
|----------------------------------|-----------|-------------|-------------------|
| **A. Tài sản ngắn hạn** | `CURRENT ASSETS (Bn. VND)` | `a.short_term_assets` | A. TÀI SẢN NGẮN HẠN |
| Tiền và tương đương tiền | `Cash and cash equivalents (Bn. VND)` | `i.cash_and_cash_equivalents` | I. Tiền và các khoản tương đương tiền |
| Tiền | — | `n_1.cash` | 1. Tiền |
| Các khoản tương đương tiền | — | `n_2.cash_equivalents` | 2. Các khoản tương đương tiền |
| Đầu tư tài chính ngắn hạn | `Short-term investments (Bn. VND)` | `ii.short_term_financial_investments` | II. Đầu tư tài chính ngắn hạn |
| Chứng khoán kinh doanh | — | `n_1.available_for_sale_securities` | 1. Chứng khoán kinh doanh |
| Đầu tư nắm giữ đến ngày đáo hạn | — | `n_3.held_to_maturity_investments` | 3. Đầu tư nắm giữ đến ngày đáo hạn |
| Phải thu ngắn hạn | `Accounts receivable (Bn. VND)` | `iii.short_term_receivables` | III. Các khoản phải thu ngắn hạn |
| Phải thu khách hàng | — | `n_1.short_term_trade_accounts_receivable` | 1. Phải thu ngắn hạn của khách hàng |
| Trả trước cho người bán | `Prepayments to suppliers (Bn. VND)` | `n_2.short_term_prepayments_to_suppliers` | 2. Trả trước cho người bán ngắn hạn |
| Phải thu về cho vay ngắn hạn | `Short-term loans receivables (Bn. VND)` | `n_5.short_term_loan_receivables` | 5. Phải thu về cho vay ngắn hạn |
| Phải thu ngắn hạn khác | — | `n_6.other_short_term_receivables` | 6. Phải thu ngắn hạn khác |
| Dự phòng phải thu ngắn hạn khó đòi | — | `n_7.provision_for_short_term_doubtful_debts` | 7. Dự phòng phải thu ngắn hạn khó đòi (*) |
| Hàng tồn kho | `Net Inventories`, `Inventories, Net (Bn. VND)` | `iv.inventories`, `n_1.inventories` | IV. Hàng tồn kho |
| Tài sản ngắn hạn khác | `Other current assets` | `v.other_short_term_assets` | V. Tài sản ngắn hạn khác |
| Chi phí trả trước ngắn hạn | — | `n_1.short_term_prepayments` | 1. Chi phí trả trước ngắn hạn |
| Thuế GTGT được khấu trừ | — | `n_2.value_added_tax_to_be_reclaimed` | 2. Thuế GTGT được khấu trừ |
| **B. Tài sản dài hạn** | `LONG-TERM ASSETS (Bn. VND)` | `b.long_term_assets` | B. TÀI SẢN DÀI HẠN |
| Phải thu dài hạn | `Long-term loans receivables (Bn. VND)` (part) | `i.long_term_receivables` | I. Các khoản phải thu dài hạn |
| Phải thu về cho vay dài hạn | `Long-term loans receivables (Bn. VND)` | `n_5.long_term_loan_receivables` | 5. Phải thu về cho vay dài hạn |
| Phải thu dài hạn khác | `Other long-term receivables (Bn. VND)` | `n_6.other_long_term_receivables` | 6. Phải thu dài hạn khác |
| Tài sản cố định | `Fixed assets (Bn. VND)` | `ii.fixed_assets` | II. Tài sản cố định |
| Tài sản cố định hữu hình | — | `n_1.tangible_fixed_assets` | 1. Tài sản cố định hữu hình |
| Tài sản cố định thuê tài chính | — | `n_2.financial_leased_fixed_assets` | 2. Tài sản cố định thuê tài chính |
| Tài sản cố định vô hình | — | `n_3.intangible_fixed_assets` | 3. Tài sản cố định vô hình |
| Bất động sản đầu tư | `Investment in properties` | `iii.investment_properties` | III. Bất động sản đầu tư |
| Tài sản dở dang dài hạn | — | `iv.long_term_assets_in_progress` | IV. Tài sản dở dang dài hạn |
| Chi phí xây dựng cơ bản dở dang | — | `n_2.construction_in_progress` | 2. Chi phí xây dựng cơ bản dở dang |
| Đầu tư tài chính dài hạn | `Long-term investments (Bn. VND)` | `v.long_term_financial_investments` | V. Đầu tư tài chính dài hạn |
| Đầu tư vào công ty con | — | `n_1.investments_in_subsidiaries` | 1. Đầu tư vào công ty con |
| Đầu tư vào công ty liên kết, liên doanh | — | `n_2.investments_in_associates_joint_ventures` | 2. Đầu tư vào công ty liên kết, liên doanh |
| Đầu tư góp vốn vào đơn vị khác | — | `n_3.investments_in_other_entities` | 3. Đầu tư góp vốn vào đơn vị khác |
| Tài sản dài hạn khác | `Other non-current assets`, `Other long-term assets (Bn. VND)` | `vi.other_long_term_assets` | VI. Tài sản dài hạn khác |
| Chi phí trả trước dài hạn | `Long-term prepayments (Bn. VND)` | `n_1.long_term_prepayments` | 1. Chi phí trả trước dài hạn |
| Lợi thế thương mại | `Goodwill`, `Good will (Bn. VND)` | `n_5.goodwill` | 5. Lợi thế thương mại |
| **Tổng cộng tài sản** | `TOTAL ASSETS (Bn. VND)` | `total_assets` | TỔNG CỘNG TÀI SẢN |

### 1.2 Liabilities — NỢ PHẢI TRẢ

| Line item (BCTC / typical name) | VCI field | KBS item_id | KBS item (label) |
|----------------------------------|-----------|-------------|-------------------|
| **A. Nợ phải trả** | `LIABILITIES (Bn. VND)` | `a.liabilities` | A. NỢ PHẢI TRẢ |
| Nợ ngắn hạn | `Current liabilities (Bn. VND)` | `i.short_term_liabilities` | I. Nợ ngắn hạn |
| Phải trả người bán ngắn hạn | — | `n_1.short_term_trade_accounts_payable` | 1. Phải trả người bán ngắn hạn |
| Người mua trả tiền trước | `Advances from customers (Bn. VND)` | `n_2.short_term_advances_from_customers` | 2. Người mua trả tiền trước ngắn hạn |
| Thuế và các khoản phải nộp Nhà nước | — | `n_3.taxes_and_other_payables_to_state_authorities` | 3. Thuế và các khoản phải nộp Nhà nước |
| Phải trả người lao động | — | `n_4.payable_to_employees` | 4. Phải trả người lao động |
| Chi phí phải trả ngắn hạn | — | `n_5.short_term_acrrued_expenses` | 5. Chi phí phải trả ngắn hạn |
| Phải trả ngắn hạn khác | — | `n_9.other_short_term_payables` | 9. Phải trả ngắn hạn khác |
| Vay và nợ thuê tài chính ngắn hạn | `Short-term borrowings (Bn. VND)` | `n_10.short_term_borrowings_and_financial_leases` | 10. Vay và nợ thuê tài chính ngắn hạn |
| Dự phòng phải trả ngắn hạn | — | `n_11.provision_for_short_term_liabilities` | 11. Dự phòng phải trả ngắn hạn |
| Nợ dài hạn | `Long-term liabilities (Bn. VND)` | `ii.long_term_liabilities` | II. Nợ dài hạn |
| Doanh thu chưa thực hiện dài hạn | — | `n_6.long_term_unearned_revenue` | 6. Doanh thu chưa thực hiện dài hạn |
| Phải trả dài hạn khác | — | `n_7.other_long_term_liabilities` | 7. Phải trả dài hạn khác |
| Vay và nợ thuê tài chính dài hạn | `Long-term borrowings (Bn. VND)` | `n_8.long_term_borrowings_and_financial_leases` | 8. Vay và nợ thuê tài chính dài hạn |

### 1.3 Equity — VỐN CHỦ SỞ HỮU

| Line item (BCTC / typical name) | VCI field | KBS item_id | KBS item (label) |
|----------------------------------|-----------|-------------|-------------------|
| **B. Vốn chủ sở hữu** | `OWNER'S EQUITY(Bn.VND)`, `Capital and reserves (Bn. VND)` | `b.owners_equity`, `i.owners_equity` | B. VỐN CHỦ SỞ HỮU / I. Vốn chủ sở hữu |
| Vốn góp chủ sở hữu | `Common shares (Bn. VND)`, `Paid-in capital (Bn. VND)` | `n_1.owners_capital` | 1. Vốn góp của chủ sở hữu |
| Cổ phiếu phổ thông có quyền biểu quyết | — | `common_stock_with_voting_right` | Cổ phiếu phổ thông có quyền biểu quyết |
| Thặng dư vốn cổ phần | — | `n_2.share_premium` | 2. Thặng dư vốn cổ phần |
| Vốn khác của chủ sở hữu | `Other Reserves` | `n_4.other_capital_of_owners` | 4. Vốn khác của chủ sở hữu |
| Chênh lệch tỷ giá hối đoái | — | `n_7.foreign_exchange_differences` | 7. Chênh lệch tỷ giá hối đoái |
| Quỹ đầu tư phát triển | `Investment and development funds (Bn. VND)` | `n_8.investment_and_development_fund` | 8. Quỹ đầu tư phát triển |
| Quỹ khác thuộc vốn chủ sở hữu | — | `n_10.other_funds_from_owners_equity` | 10. Quỹ khác thuộc vốn chủ sở hữu |
| Lợi nhuận sau thuế chưa phân phối | `Undistributed earnings (Bn. VND)` | `n_11.undistributed_earnings_after_tax` | 11. Lợi nhuận sau thuế chưa phân phối |
| Lợi ích cổ đông không kiểm soát | `MINORITY INTERESTS` | `n_13.minoritys_interest` | 13. Lợi ích cổ đông không kiểm soát |
| **C. Lợi ích cổ đông thiểu số** | (in MINORITY INTERESTS) | `c.minoritys_interest` | C. LỢI ÍCH CỔ ĐÔNG THIỂU SỐ |
| **Tổng cộng nguồn vốn** | `TOTAL RESOURCES (Bn. VND)` | `total_owners_equity_and_liabilities` | TỔNG CỘNG NGUỒN VỐN |

---

## 2. Income Statement — Báo cáo kết quả hoạt động kinh doanh

| Line item (BCTC / typical name) | VCI field | KBS item_id | KBS item (label) |
|----------------------------------|-----------|-------------|-------------------|
| Doanh thu bán hàng và cung cấp dịch vụ | `Sales`, `Revenue (Bn. VND)` | `n_1.revenue` | 1. Doanh thu bán hàng và cung cấp dịch vụ |
| Các khoản giảm trừ doanh thu | `Sales deductions` | `n_2.deduction_from_revenue` | 2. Các khoản giảm trừ doanh thu |
| Doanh thu thuần | `Net Sales` | `n_3.net_revenue` | 3. Doanh thu thuần về bán hàng và cung cấp dịch vụ |
| Giá vốn hàng bán | `Cost of Sales` | `n_4.cost_of_goods_sold` | 4. Giá vốn hàng bán |
| Lợi nhuận gộp | `Gross Profit` | `n_5.gross_profit` | 5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ |
| Doanh thu hoạt động tài chính | `Financial Income` | `n_6.financial_income` | 6. Doanh thu hoạt động tài chính |
| Chi phí tài chính | `Financial Expenses` | `n_7.financial_expenses` | 7. Chi phí tài chính |
| Chi phí lãi vay | `Interest Expenses` | `of_which_interest_expenses` | Trong đó: Chi phí lãi vay |
| Phần lãi/lỗ trong công ty liên doanh, liên kết | `Gain/(loss) from joint ventures` | `n_8.share_of_associates_and_joint_ventures_result` | 8. Phần lãi/lỗ trong công ty liên doanh, liên kết |
| Chi phí bán hàng | `Selling Expenses` | `n_9.selling_expenses` | 9. Chi phí bán hàng |
| Chi phí quản lý doanh nghiệp | `General & Admin Expenses` | `n_10.general_and_administrative_expenses` | 10. Chi phí quản lý doanh nghiệp |
| Lợi nhuận thuần từ hoạt động kinh doanh | `Operating Profit/Loss` | `n_11.operating_profit` | 11. Lợi nhuận thuần từ hoạt động kinh doanh |
| Thu nhập khác | `Other income` | `n_12.other_income` | 12. Thu nhập khác |
| Chi phí khác | (part of Other Income/Expenses) | `n_13.other_expenses` | 13. Chi phí khác |
| Lợi nhuận khác | `Net other income/expenses` | `n_14.other_profit` | 14. Lợi nhuận khác |
| Lợi nhuận trước thuế | `Profit before tax` | `n_15.profit_before_tax` | 15. Tổng lợi nhuận kế toán trước thuế |
| Chi phí thuế TNDN hiện hành | `Business income tax - current` | `n_16.current_corporate_income_tax_expenses` | 16. Chi phí thuế TNDN hiện hành |
| Chi phí thuế TNDN hoãn lại | `Business income tax - deferred` | `n_17.deferred_income_tax_expenses` | 17. Chi phí thuế TNDN hoãn lại |
| Lợi nhuận sau thuế | `Net Profit For the Year` | `n_18.net_profit_after_tax` | 18. Lợi nhuận sau thuế thu nhập doanh nghiệp |
| Lợi ích cổ đông thiểu số | `Minority Interest` | `minoritys_interest` | Lợi ích của cổ đông thiểu số |
| Lợi nhuận thuộc công ty mẹ | `Attributable to parent company`, `Attribute to parent company (Bn. VND)` | `profit_after_tax_for_shareholders_of_parent_company` | Lợi nhuận sau thuế của cổ đông của Công ty mẹ |
| Revenue YoY (%) | `Revenue YoY (%)` | — | (KBS: year columns, no YoY in same shape) |
| Attribute to parent company YoY (%) | `Attribute to parent company YoY (%)` | — | — |

---

## 3. Cash Flow — Báo cáo lưu chuyển tiền tệ

| Line item (BCTC / typical name) | VCI field | KBS item_id | KBS item (label) |
|----------------------------------|-----------|-------------|-------------------|
| **I. Lưu chuyển tiền từ hoạt động kinh doanh** | — | `i_cash_flows_from_operating_activities` | I. Lưu chuyển tiền từ hoạt động kinh doanh |
| Lợi nhuận trước thuế | `Net Profit/Loss before tax` | `n_1.profit_before_tax` | 1. Lợi nhuận trước thuế |
| Khấu hao TSCĐ và BĐSĐT | `Depreciation and Amortisation` | `depreciation_of_fixed_assets_and_properties_investment` | Khấu hao TSCĐ và BĐSĐT |
| Các khoản dự phòng | `Provision for credit losses` | `reversal_of_provisions_provisions` | Các khoản dự phòng |
| Chênh lệch tỷ giá (đánh giá lại) | `Unrealized foreign exchange gain/loss` | `foreign_exchange_gain_loss_from_revaluation_of_monetary_items_denominated_in_foreign_currencies` | Lãi, lỗ chênh lệch tỷ giá... |
| Lãi, lỗ từ hoạt động đầu tư | `Profit/Loss from investing activities` | `loss_profit_from_investment_activities` | Lãi, lỗ từ hoạt động đầu tư |
| Chi phí lãi vay | `Interest Expense` | `interest_expense` | Chi phí lãi vay |
| Lợi nhuận trước thay đổi vốn lưu động | `Operating profit before changes in working capital` | `n_3.operating_profit_before_changes_in_working_capital` | 3. Lợi nhuận từ HĐKD trước thay đổi vốn lưu động |
| Tăng, giảm các khoản phải thu | `Increase/Decrease in receivables` | `increase_decrease_in_receivables` | Tăng, giảm các khoản phải thu |
| Tăng, giảm hàng tồn kho | `Increase/Decrease in inventories` | `increase_decrease_in_inventories` | Tăng, giảm hàng tồn kho |
| Tăng, giảm các khoản phải trả | `Increase/Decrease in payables` | `increase_decrease_in_payables_other_than_interest_corporate_income_tax` | Tăng, giảm các khoản phải trả |
| Tăng, giảm chi phí trả trước | `Increase/Decrease in prepaid expenses` | `increase_decrease_in_prepaid_expenses` | Tăng, giảm chi phí trả trước |
| Tiền lãi vay đã trả | `Interest paid` | `interest_paid` | Tiền lãi vay đã trả |
| Thuế TNDN đã nộp | `Business Income Tax paid` | `corporate_income_tax_paid` | Thuế thu nhập doanh nghiệp đã nộp |
| Tiền thu/chi khác từ HĐKD | `Other receipts from operating activities`, `Other payments on operating activities` | `other_receipts_from_operating_activities`, `other_payments_for_operating_activities` | Tiền thu/chi khác từ hoạt động kinh doanh |
| **Lưu chuyển tiền thuần từ HĐKD** | `Net cash inflows/outflows from operating activities` | `net_cash_flows_from_operating_activities` | Lưu chuyển tiền thuần từ hoạt động kinh doanh |
| **II. Lưu chuyển tiền từ hoạt động đầu tư** | — | `ii_cash_flows_from_investing_activities` | II. Lưu chuyển tiền từ hoạt động đầu tư |
| Tiền chi mua sắm, xây dựng TSCĐ | `Purchase of fixed assets` | `n_1.payment_for_fixed_assets_constructions_and_other_long_term_assets` | 1. Tiền chi để mua sắm, xây dựng TSCĐ... |
| Tiền thu từ thanh lý, nhượng bán TSCĐ | `Proceeds from disposal of fixed assets` | `n_2.receipts_from_disposal_of_fixed_assets_and_other_long_term_assets` | 2. Tiền thu từ thanh lý, nhượng bán TSCĐ |
| Tiền chi cho vay, mua công cụ nợ | `Loans granted, purchases of debt instruments (Bn. VND)` | `n_3.loans_purchases_of_other_entities_debt_instruments` | 3. Tiền chi cho vay, mua các công cụ nợ |
| Tiền thu hồi cho vay, bán công cụ nợ | `Collection of loans, proceeds from sales of debts instruments (Bn. VND)` | `n_4.receipts_from_loan_repayments_sale_of_other_entities_debt_instruments` | 4. Tiền thu hồi cho vay, bán lại công cụ nợ |
| Tiền chi đầu tư góp vốn | `Investment in other entities` | `n_5.payments_for_investment_in_other_entities` | 5. Tiền chi đầu tư góp vốn vào đơn vị khác |
| Tiền thu hồi đầu tư | `Proceeds from divestment in other entities` | `n_6.collections_on_investment_in_other_entities` | 6. Tiền thu hồi đầu tư góp vốn |
| Tiền thu lãi, cổ tức và lợi nhuận được chia | `Gain on Dividend` | `n_7.dividends_interest_and_profit_received` | 7. Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia |
| **Lưu chuyển tiền thuần từ HĐĐT** | `Net Cash Flows from Investing Activities` | `net_cash_flows_from_investing_activities` | Lưu chuyển tiền thuần từ hoạt động đầu tư |
| **III. Lưu chuyển tiền từ hoạt động tài chính** | — | `iii_cash_flows_from_financing_activities` | III. Lưu chuyển tiền từ hoạt động tài chính |
| Tiền thu từ phát hành cổ phiếu, nhận vốn góp | `Increase in charter captial` | `n_1.receipts_from_equity_issue_and_owners_capital_contribution` | 1. Tiền thu từ phát hành cổ phiếu, nhận vốn góp |
| Tiền chi trả vốn, mua lại cổ phiếu | `Payments for share repurchases` | `n_2.payment_for_share_repurchases` | 2. Tiền chi trả vốn góp, mua lại cổ phiếu |
| Tiền thu từ đi vay | `Proceeds from borrowings` | `n_3.proceeds_from_borrowings` | 3. Tiền thu từ đi vay |
| Tiền trả nợ gốc vay | `Repayment of borrowings` | `n_4_principal_repayments` | 4. Tiền trả nợ gốc vay |
| Tiền trả nợ gốc thuê tài chính | `Finance lease principal payments` | `n_5.repayment_of_financial_leases` | 5. Tiền trả nợ gốc thuê tài chính |
| Cổ tức, lợi nhuận đã trả cho chủ sở hữu | `Dividends paid` | `n_6.dividends_paid_profits_distributed_to_owners` | 6. Cổ tức, lợi nhuận đã trả cho chủ sở hữu |
| **Lưu chuyển tiền thuần từ HĐTC** | `Cash flows from financial activities` | `net_cash_flows_from_financing_activities` | Lưu chuyển tiền thuần từ hoạt động tài chính |
| Lưu chuyển tiền thuần trong kỳ | `Net increase/decrease in cash and cash equivalents` | `net_cash_flows_during_the_period` | Lưu chuyển tiền thuần trong kỳ |
| Tiền và tương đương tiền đầu kỳ | `Cash and cash equivalents` | `cash_and_cash_equivalents_at_beginning_of_the_period` | Tiền và tương đương tiền đầu kỳ |
| Ảnh hưởng thay đổi tỷ giá quy đổi ngoại tệ | `Foreign exchange differences Adjustment` | `exchange_difference_due_to_re_valuation_of_ending_balances` | Ảnh hưởng của thay đổi tỷ giá... |
| Tiền và tương đương tiền cuối kỳ | `Cash and Cash Equivalents at the end of period` | `cash_and_cash_equivalents_at_end_of_the_period` | Tiền và tương đương tiền cuối kỳ |

---

## 4. Market / Company Data (not from financial statements)

| Item | VCI | KBS |
|------|-----|-----|
| Shares outstanding | `Company` → `CompanyListingInfo.issueShare` (or `issue_share`) | `Company.overview()` → column `outstanding_shares` |
| OHLC / close price, volume | `Quote.history()` with `source="VCI"` | Same with `source="KBS"` |

---

## 5. Metrics we use in the app (mapped from above)

The app currently maps a **subset** of the full statement into unified records. Those fields are derived from:

- **Balance sheet:** Cash and cash equivalents, Short-term investments, **Long-term investments**, Equity, Liability (total), Short-term borrowings, Long-term borrowings (see table 1.1–1.3).
- **Income statement:** Net Sales (revenue), Net Profit For the Year / Attributable to parent (net income), Financial Income, Operating Profit/Loss, **Profit before tax**, **Interest expense**, **Financial expense** (see table 2).
- **Cash flow:** **Depreciation and Amortisation** (depreciation expense; see table 3).
- **Calculated:** ROE, ROIC, Net Profit Margin, YoY growth, T4Q (trailing four quarters) for quarterly data.

Exact VCI column names and KBS `item_id` candidates used in code are in `app/services/vnstock_financial_service.py` (e.g. `_get_income_value`, `_get_balance_value`, `_KBS_*_IDS`).

---

## 6. Where to extend

- **VCI:** Add or change column names in `_build_financial_records()` and in `_get_income_value` / `_get_balance_value` key lists in `app/services/vnstock_financial_service.py`.
- **KBS:** Add or change `item_id` candidates in the `_KBS_*_IDS` lists and inline lists in `_build_financial_records_from_kbs_long()`.
- **Cash flow:** Both providers expose `cash_flow`; to add items (e.g. operating cash flow, FCF), extend the builders to parse the cash flow DataFrame and map the desired line items from the tables above.

Last updated from GMD 2025 structure and codebase: January 2026.
