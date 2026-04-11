# Data Dictionary — Company Valuation Skill

This document defines all columns, types, units, sources, and constraints for the
financial dataset used by the Company Valuation Analytics Skill.

---

## 1. Required Columns (Target Company)

| Column | Type | Unit | Description | Constraints |
|--------|------|------|-------------|-------------|
| `ticker` | string | — | Stock ticker symbol (e.g., "AAPL") | Non-null, uppercase |
| `fiscal_year` | integer | year | Fiscal year (e.g., 2024) | Non-null, ≥ 2000 |
| `revenue` | float | USD | Total revenue / net sales | Non-null, > 0 |
| `cost_of_revenue` | float | USD | Cost of goods sold (COGS) | Non-null, ≥ 0 |
| `operating_income` | float | USD | Operating income (EBIT) | Non-null |
| `net_income` | float | USD | Net income attributable to company | Non-null |
| `total_assets` | float | USD | Total assets | Non-null, > 0 |
| `total_liabilities` | float | USD | Total liabilities | Non-null, ≥ 0 |
| `total_equity` | float | USD | Total shareholders' equity | Non-null |
| `operating_cash_flow` | float | USD | Cash from operations | Non-null |
| `capex` | float | USD | Capital expenditures (positive = spending) | Non-null |
| `shares_outstanding` | float | shares | Weighted-average diluted shares | Non-null, > 0 |
| `stock_price` | float | USD | Closing stock price at fiscal year end | Non-null, > 0 |

## 2. Optional Columns (Target Company)

| Column | Type | Unit | Description | Default if Missing |
|--------|------|------|-------------|-------------------|
| `ebitda` | float | USD | Earnings before interest, taxes, depreciation, amortisation | Computed: operating_income + depreciation |
| `depreciation` | float | USD | Depreciation & amortisation | Estimated from cash flow vs operating income |
| `interest_expense` | float | USD | Interest expense | 0 (assumes no debt) |
| `tax_provision` | float | USD | Income tax expense | Estimated at 21% of pre-tax income |
| `total_debt` | float | USD | Total interest-bearing debt | Approximated as total_liabilities × 0.5 |
| `cash_and_equivalents` | float | USD | Cash & short-term investments | 0 (conservative) |
| `dividends_paid` | float | USD | Total dividends paid | 0 |
| `beta` | float | — | 5-year monthly beta vs S&P 500 | 1.0 |
| `sector` | string | — | GICS sector classification | "Unknown" |
| `company_name` | string | — | Full legal company name | ticker value |

## 3. Peer Company Data (for CCA)

Same columns as above, one row per peer per fiscal year. Additionally:

| Column | Type | Description |
|--------|------|-------------|
| `is_peer` | boolean | True for peer companies, False for target |

Minimum: **3 peer companies** with at least the most recent fiscal year of data.

## 4. Precedent Transactions Data

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `transaction_date` | date | — | Announcement or completion date |
| `target_name` | string | — | Acquired company name |
| `acquirer_name` | string | — | Acquiring company name |
| `sector` | string | — | Target company sector |
| `deal_value` | float | USD | Total deal enterprise value |
| `target_revenue` | float | USD | Target's LTM revenue at announcement |
| `target_ebitda` | float | USD | Target's LTM EBITDA at announcement |
| `ev_revenue_multiple` | float | — | deal_value / target_revenue |
| `ev_ebitda_multiple` | float | — | deal_value / target_ebitda |
| `premium_paid` | float | % | Control premium over pre-announcement price |

## 5. User Configuration Parameters

| Parameter | Type | Default | Valid Range | Description |
|-----------|------|---------|-------------|-------------|
| `ticker` | string | — (required) | Valid stock ticker | Target company ticker |
| `peers` | list[string] | — (required) | ≥ 3 tickers | Peer company tickers |
| `analysis_date` | string | today | YYYY-MM-DD | Date of analysis |
| `risk_free_rate` | float | 0.04 | 0.0–0.15 | 10-year Treasury yield |
| `equity_risk_premium` | float | 0.055 | 0.03–0.10 | Market risk premium |
| `projection_years` | int | 5 | 3–10 | Number of years to project |
| `terminal_growth_rate` | float | 0.025 | 0.0–0.05 | Long-term FCF growth rate |
| `tax_rate` | float | 0.21 | 0.0–0.50 | Corporate tax rate |
| `report_format` | string | "both" | "html", "pdf", "both" | Output format |

## 6. Validation Rules

1. **No nulls** in any required column
2. **At least 3 years** of historical data (fiscal_year) for the target company
3. **Balance sheet identity**: |total_assets − (total_liabilities + total_equity)| / total_assets < 0.05
4. **Positive stock price**: stock_price > 0
5. **Positive shares**: shares_outstanding > 0
6. **Revenue positive**: revenue > 0
7. **At least 3 peers** with matching fiscal year data
8. **Fiscal years sequential**: no duplicate years, no gaps > 2 years
9. **Terminal growth rate < WACC**: g < WACC (checked after WACC computation)

## 7. Data Sources

| Source | Type | Notes |
|--------|------|-------|
| Yahoo Finance API (`yfinance`) | Live API | Primary source; fetched via `fetch_data.py` |
| Kaggle financial datasets | Static CSV | Fallback; stored in `data/sample/` |
| Synthetic data generator | Script | `generate_synthetic_data.py` for testing |
| SEC EDGAR | API | Alternative live source (not implemented in v1) |
