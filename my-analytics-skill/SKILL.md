# SKILL.md — Company Valuation Analytics Skill

## Skill Metadata

| Field | Value |
|-------|-------|
| **Name** | Company Valuation (DCF + CCA + Precedent Transactions) |
| **Domain** | Financial Analytics |
| **Version** | 2.0 |
| **Description** | Performs end-to-end company valuation using three methods: Discounted Cash Flow (DCF), Comparable Company Analysis (CCA), and Precedent Transactions Analysis. Uses Damodaran Jan 2026 ERP/WACC methodology, revenue-driven FCF projections with multi-metric growth estimation, synthetic credit rating for cost of debt, and IQR-based valuation ranges. Produces a professional multi-section HTML+PDF report with charts, sensitivity analysis, and investment recommendations. |

---

## Input Specification

### 1. Dataset Input

The skill accepts financial data in JSON format, structured by the `fetch_data.py` or
`generate_synthetic_data.py` scripts. The JSON must contain:

- **`target`**: Object with `ticker`, `company_name`, `sector`, and `records` (array of annual financial records).
- **`peers`**: Array of objects, each with the same structure as `target`. Minimum **3 peers** required.
- **`precedent_transactions`**: Array of M&A transaction objects (optional but recommended).

#### Required Columns per Record

| Column | Type | Constraints |
|--------|------|-------------|
| `ticker` | string | Non-null, uppercase |
| `fiscal_year` | int | Non-null, ≥ 2000 |
| `revenue` | float | Non-null, > 0 |
| `cost_of_revenue` | float | Non-null, ≥ 0 |
| `operating_income` | float | Non-null |
| `net_income` | float | Non-null |
| `total_assets` | float | Non-null, > 0 |
| `total_liabilities` | float | Non-null, ≥ 0 |
| `total_equity` | float | Non-null |
| `operating_cash_flow` | float | Non-null |
| `capex` | float | Non-null (positive = spending) |
| `shares_outstanding` | float | Non-null, > 0 |
| `stock_price` | float | Non-null, > 0 |

#### Optional Columns

`ebitda`, `depreciation`, `interest_expense`, `tax_provision`, `total_debt`,
`cash_and_equivalents`, `dividends_paid`, `beta`, `sector`, `company_name`.

Missing optional columns are estimated from available data (see `feature_engineering.py`).

### 2. User Configuration Parameters

| Parameter | Type | Default | Valid Range | Description |
|-----------|------|---------|-------------|-------------|
| `ticker` | string | *(required)* | Valid stock ticker | Target company |
| `peers` | list[str] | *(required)* | ≥ 3 tickers | Peer companies for CCA |
| `risk_free_rate` | float | 0.0437 | 0.0–0.15 | 10-year Treasury yield (Damodaran Jan 2026) |
| `equity_risk_premium` | float | 0.0446 | 0.03–0.10 | US implied ERP (Damodaran Jan 2026) |
| `projection_years` | int | 5 | 3–10 | DCF projection horizon |
| `terminal_growth_rate` | float | 0.025 | 0.0–0.05 | Long-term FCF growth (must be < WACC) |
| `tax_rate` | float | 0.21 | 0.0–0.50 | Corporate tax rate |
| `report_format` | string | "both" | "html"/"pdf"/"both" | Output format |

The user may save these parameters in a `config.json` file.

---

## MCP Server Configuration

The skill exposes an MCP (Model Context Protocol) server for live data fetching.
An LLM agent can invoke the `fetch_financials` or `generate_synthetic` tools at
runtime instead of calling CLI scripts directly.

### Server Location

```
scripts/mcp_server.py
```

### Transport

stdio (JSON-RPC 2.0 over stdin/stdout) — standard for VS Code / Copilot skills.

### Starting the Server

```bash
python scripts/mcp_server.py
```

### Available MCP Tools

#### 1. `fetch_financials`

Fetches live financial data from Yahoo Finance for a target company and peers.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `ticker` | string | Yes | Target company ticker (e.g., `MSFT`, `NAUKRI.NS`) |
| `peers` | string | Yes | Comma-separated peer tickers, min 3 (e.g., `AAPL,GOOGL,META,AMZN`) |
| `years` | integer | No | Historical years to fetch (default: 5) |

**Returns:** JSON with `target`, `peers`, and `precedent_transactions` objects (same format as `fetch_data.py` output).

#### 2. `generate_synthetic`

Generates synthetic financial data for testing without network access.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `target_ticker` | string | No | Synthetic target ticker (default: `SYNTH`) |
| `peers` | string | No | Comma-separated peer tickers (auto-generated if omitted) |
| `num_companies` | integer | No | Total companies including target (default: 5) |
| `years` | integer | No | Years of history (default: 5) |
| `sector` | string | No | Sector profile: Technology, Healthcare, Consumer, Energy, Financials |
| `seed` | integer | No | Random seed for reproducibility (default: 42) |

**Returns:** JSON in same format as `fetch_financials`.

### Example MCP Configuration (for VS Code / mcp.json)

```json
{
  "servers": {
    "company-valuation": {
      "type": "stdio",
      "command": "python",
      "args": ["scripts/mcp_server.py"],
      "cwd": "${workspaceFolder}/company-valuation-skill"
    }
  }
}
```

### Agent Workflow with MCP

1. Agent calls `fetch_financials` tool with user-provided ticker and peers
2. Agent writes the returned JSON to `data/raw/financials.json`
3. Agent proceeds with CLI scripts for Stage 1-6 (validation, features, models, report)

Alternatively, the agent can use the CLI scripts directly (Stage 0 in the pipeline below).
Both paths produce identical JSON output.

---

## Analytics Pipeline — Stage-by-Stage Instructions

### Stage 0: Data Acquisition

**Purpose:** Fetch financial data for the target and peer companies.

**Option A — Live Data (preferred):**

```bash
python scripts/fetch_data.py \
  --ticker AAPL \
  --peers MSFT,GOOGL,META,AMZN \
  --years 5 \
  --output data/raw/financials.json
```

**Option B — Synthetic Data (for testing):**

```bash
python scripts/generate_synthetic_data.py \
  --target-ticker SYNTH \
  --peers PEER1,PEER2,PEER3,PEER4 \
  --years 5 \
  --sector Technology \
  --seed 42 \
  --output data/raw/financials.json
```

**Expected Output:** `data/raw/financials.json` containing `target`, `peers`, and
`precedent_transactions` objects.

**Validation:** File exists and is valid JSON with non-empty `target.records` array.

**On Failure:**
- If API returns an error → check ticker symbol validity and network connectivity.
- If fewer than 3 peers succeed → add more peer tickers or use synthetic data.

---

### Stage 1: Data Validation & Profiling

**Purpose:** Profile incoming dataset quality and reject malformed data before analysis.

**Command:**

```bash
python scripts/validate_data.py \
  --input data/raw/financials.json \
  --output data/validation_report.json
```

**What This Script Computes:**

1. **Row/column counts** for target and each peer company
2. **Data types** per column (numeric vs categorical)
3. **Null percentages** per column — flag if any required column has >30% nulls
4. **Value distributions** for numeric columns (min, max, mean, median)
5. **Year coverage** — verify ≥3 fiscal years for target
6. **Balance sheet identity** — verify |total_assets − (total_liabilities + total_equity)| / total_assets < 5%
7. **Positive value checks** — revenue, total_assets, shares_outstanding, stock_price must be > 0
8. **Peer count check** — verify ≥3 peers with valid data
9. **Year gap detection** — flag gaps >2 years

**Expected Output:** `data/validation_report.json` with fields:
- `status`: "PASS", "PASS_WITH_WARNINGS", or "FAIL"
- `summary`: counts of errors and warnings
- `target_profile`: profiling statistics for the target
- `peer_profiles`: profiling statistics for each peer
- `issues`: array of `{severity, check, message, fix}` objects

**Validation Checks Before Proceeding:**
- If `status == "FAIL"` → STOP. Display all ERROR-level issues with their `fix`
  suggestions. Ask the user to correct the data and re-run.
- If `status == "PASS_WITH_WARNINGS"` → display warnings but proceed.
- If `status == "PASS"` → proceed to Stage 2.

**On Failure:** Do NOT proceed to feature engineering with invalid data. Present the
validation report to the user with clear fix instructions.

---

### Stage 2: Data Preparation & Feature Engineering

**Purpose:** Transform raw financial data into analysis-ready features: financial ratios,
WACC components, projected cash flows, and peer multiples.

**Command:**

```bash
python scripts/feature_engineering.py \
  --input data/raw/financials.json \
  --config config.json \
  --output data/features.json
```

(If no `config.json` exists, defaults from the table above are used.)

**What This Script Computes:**

For each fiscal year record of the target company:

1. **Profitability Ratios:**
   - Gross Margin = (Revenue − Cost of Revenue) / Revenue
   - Operating Margin = Operating Income / Revenue
   - Net Margin = Net Income / Revenue
   - ROE = Net Income / Total Equity
   - ROA = Net Income / Total Assets

2. **Leverage Ratios:**
   - Debt-to-Equity = Total Liabilities / Total Equity
   - Interest Coverage = Operating Income / Interest Expense
   - Net Debt = Total Debt − Cash & Equivalents
   - Net Debt / EBITDA

3. **Cash Flow Metrics:**
   - FCFF = Operating Cash Flow − Capital Expenditures
   - FCF Margin = FCFF / Revenue

4. **Per-Share Metrics:**
   - EPS = Net Income / Shares Outstanding
   - Book Value per Share = Total Equity / Shares Outstanding
   - FCF per Share = FCFF / Shares Outstanding

5. **Valuation Multiples** (for target and each peer):
   - Market Cap = Shares Outstanding × Stock Price
   - Enterprise Value = Market Cap + Total Debt − Cash
   - EV/EBITDA = Enterprise Value / EBITDA
   - EV/Revenue = Enterprise Value / Revenue
   - P/E = Stock Price / EPS
   - P/B = Stock Price / Book Value per Share

6. **Growth Rates:**
   - Revenue Growth YoY = (Revenue_t − Revenue_{t-1}) / |Revenue_{t-1}|
   - Earnings Growth YoY, FCF Growth YoY (same formula)
   - Revenue CAGR = (Revenue_final / Revenue_initial)^(1/years) − 1

7. **WACC Calculation** (using most recent year data + Damodaran methodology):
   - Cost of Equity = Risk-Free Rate + Beta x Equity Risk Premium (CAPM)
   - Cost of Debt = Risk-Free Rate + Default Spread (via synthetic rating from interest coverage ratio, per Damodaran). Interest coverage mapped to rating: >12.5x = AAA (0.63% spread), >9.5x = A (0.88%), >6x = BBB+ (1.15%), >4.5x = BBB (1.43%), >3x = BB+ (2.17%), etc.
   - Equity Weight = Market Cap / (Market Cap + Total Debt)
   - Debt Weight = Total Debt / (Market Cap + Total Debt)
   - Note: Capital structure uses Total Debt (not Net Debt). Net Debt is only used in the EV-to-Equity bridge.
   - WACC = Equity Weight x Cost of Equity + Debt Weight x Cost of Debt x (1 - Tax Rate)

8. **DCF Cash Flow Projections (Revenue-Driven Approach):**
   - Compute 4 growth rate estimates: Revenue CAGR, Earnings CAGR, EBITDA CAGR, FCF CAGR
   - Select the **median** of all 4 CAGRs as the base growth rate (dampens outliers from capex cycles)
   - Cap growth rate at -5% to +30%
   - Project **revenue** forward using concave growth decay: growth = base x (1 - (year/n)^1.5) + terminal x (year/n)^1.5
   - Apply average FCF margin (from last 3 years) to projected revenue to get projected FCF
   - Discount Factor per year = 1 / (1 + WACC)^year
   - Present Value of each year's FCF
   - Terminal Value (Gordon Growth) = Final FCF x (1 + g) / (WACC - g)
   - Terminal Value (Exit Multiple) = Final projected EBITDA x **Peer Median EV/EBITDA** (not target's own multiple, to avoid circularity)
   - PV of each terminal value

9. **Peer Multiple Statistics:**
   - For each multiple (EV/EBITDA, EV/Revenue, P/E, P/B): min, max, mean, median across peers

**Expected Output:** `data/features.json` with fields:
- `config`: analysis parameters used
- `target.features`: array of enriched year-by-year records
- `target.latest`: most recent year features
- `wacc`: WACC calculation breakdown
- `dcf_projections`: projected FCFs, terminal values, PV sums
- `peer_multiples.peer_details`: per-peer multiples
- `peer_multiples.multiple_stats`: aggregate statistics

**Validation Before Proceeding:**
- WACC must be between 0% and 30%. If outside this range, check inputs.
- Terminal growth rate must be strictly less than WACC. If not, the script auto-adjusts
  and prints a warning.
- At least one peer must have valid multiples for CCA.

---

### Stage 3: Modelling & Analysis

**Purpose:** Run three valuation models and generate per-model equity value estimates.

**Command:**

```bash
python scripts/run_models.py \
  --input data/features.json \
  --output data/valuation_results.json
```

**What This Script Computes:**

#### Model 1: Discounted Cash Flow (DCF)

1. Compute Enterprise Value using **Gordon Growth** terminal value:
   - EV_gordon = Sum of PV(FCFs) + PV(TV_gordon)
   - Equity_gordon = EV_gordon − Net Debt
   - Price_gordon = Equity_gordon / Shares Outstanding

2. Compute Enterprise Value using **Exit Multiple** terminal value:
   - EV_exit = Sum of PV(FCFs) + PV(TV_exit)
   - Equity_exit = EV_exit − Net Debt
   - Price_exit = Equity_exit / Shares Outstanding

3. **Blended DCF** = Average of Gordon and Exit Multiple prices

4. **Sensitivity Analysis**: Create a matrix of implied prices for:
   - WACC: base ± 2% in 1% increments (5 values)
   - Terminal Growth: base ± 1% in 0.5% increments (5 values)
   - Total: 25 scenarios

5. **Flag negative FCF**: If latest FCF < 0, add warning that DCF may be unreliable.

#### Model 2: Comparable Company Analysis (CCA)

For each multiple (EV/EBITDA, EV/Revenue, P/E, P/B):

1. Apply peer **min**, **median**, and **max** multiples to target's corresponding metric
2. For EV-based multiples: Implied EV = Target Metric × Peer Multiple, then
   Implied Equity = Implied EV − Net Debt, then
   Implied Price = Implied Equity / Shares Outstanding
3. For price-based multiples (P/E, P/B): Implied Price = Target Metric per Share × Peer Multiple

CCA value range uses **25th-75th percentile (IQR)** of all implied prices to exclude outliers
(e.g., extreme P/B from capital-light peers). Full min/max is preserved in the data for transparency.

#### Model 3: Precedent Transactions

1. Extract EV/Revenue and EV/EBITDA multiples from historical M&A transactions
2. Apply min, median, max transaction multiples to target metrics (same formula as CCA)
3. Note the average control premium (typically 20-40%)
4. Transaction-implied values inherently include control premium, so higher than CCA (expected)
5. Value range uses **25th-75th percentile (IQR)** to exclude outlier transactions

**Expected Output:** `data/valuation_results.json` with:
- `dcf`: Gordon, Exit Multiple, and Blended results + sensitivity matrix
- `cca`: peer multiples, implied values per multiple
- `precedent_transactions`: transaction multiples, implied values
- `cross_validation`: overall verdict (see Stage 4)

---

### Stage 4: Model/Result Validation

**Purpose:** Cross-validate the three valuation methods and justify the recommended value range.

This step is performed automatically within `run_models.py` (the `cross_validate` function).

**What Is Computed:**

1. **Method Summary Table**: Low / Mid / High from each of the three methods
2. **Overall Range**: min of all lows, mean of all mids, max of all highs
3. **Recommended Range**: 25th to 75th percentile of mid-values across methods
4. **Divergence Check**:
   - < 20% divergence → HIGH confidence
   - 20%–50% divergence → MODERATE confidence
   - > 50% divergence → LOW confidence (flag to user)
5. **Verdict vs Current Price**:
   - Implied Upside = (Fair Value Mid − Current Price) / Current Price
   - > +20% → UNDERVALUED / BUY
   - +5% to +20% → SLIGHTLY UNDERVALUED / BUY
   - −5% to +5% → FAIRLY VALUED / HOLD
   - −20% to −5% → SLIGHTLY OVERVALUED / SELL
   - < −20% → OVERVALUED / SELL

**Validation Checks:**
- If all methods diverge > 50%: flag LOW confidence and recommend reviewing assumptions
- If DCF produced warnings (negative FCF): weight CCA and PT results more heavily
- Ensure at least 2 of 3 methods produced valid results

**Output:** These results are included in `data/valuation_results.json` under the
`cross_validation` key.

---

### Stage 5: Insight Generation & Interpretation

**Purpose:** Translate numerical valuation results into business language using
domain knowledge from REFERENCE.md.

The LLM should perform this step by reading `data/valuation_results.json` and consulting
`REFERENCE.md`. Specifically:

1. **Look up the Interpretation Framework** (REFERENCE.md Section 4):
   - Map the `verdict` to the appropriate interpretation
   - Check cross-method consistency (Section 4.3)
   - Interpret DCF sensitivity table (Section 4.4)
   - Handle special cases if applicable (negative FCF, high debt, cyclical companies — Section 4.5)

2. **Apply Recommendation Templates** (REFERENCE.md Section 5):
   - Select the appropriate template (undervalued / fairly valued / overvalued / low-confidence)
   - Fill in: company name, fair value range, current price, implied upside, key drivers, risks

3. **Identify Key Value Drivers**:
   - Which assumptions most affect the valuation? (WACC, growth rate, margin trends)
   - Use the sensitivity table to highlight the most impactful assumptions

4. **Reference Industry Benchmarks** (REFERENCE.md Section 3):
   - Compare WACC to sector typical range
   - Compare EV/EBITDA to sector typical range
   - Flag if the company trades significantly above/below sector norms

This step does NOT call a script — it is performed by the LLM using the JSON results
and REFERENCE.md.

---

### Stage 6: Report Generation

**Purpose:** Produce a professional multi-section valuation report with embedded charts.

**Command:**

```bash
python scripts/generate_report.py \
  --input data/valuation_results.json \
  --format both \
  --output reports/
```

**What This Script Produces:**

1. **HTML Report** (`reports/{TICKER}_valuation_report.html`) containing 12 sections:
   1. **Executive Summary** — KPI cards (current price, fair value, implied upside), verdict box (buy/hold/sell with colour coding), summary paragraph
   2. **Company Overview** — Table with ticker, sector, revenue, net income, EBITDA, FCF, market cap, EPS
   3. **Data Quality Summary** — Year count, peer count, transaction count, any warnings
   4. **Methodology** — Description of DCF, CCA, Precedent Transactions approaches with parameters used
   5. **Financial Ratio Analysis** — Table of ratios by year + 4 charts: margin trends (line), return metrics (line), revenue & FCF (bar), leverage (line)
   6. **DCF Valuation** — WACC breakdown table, projected FCF table (year, growth, FCF, discount factor, PV), result table (Gordon/Exit/Blended per-share values), sensitivity heatmap (WACC × growth → implied price, base case highlighted)
   7. **Comparable Company Analysis** — Peer multiples table (ticker, EV/EBITDA, EV/Revenue, P/E, P/B with median row), implied valuation table (multiple, level, peer multiple, implied price)
   8. **Precedent Transactions** — Transaction table (date, target, acquirer, deal value, multiples, premium), implied valuation from transaction multiples
   9. **Valuation Summary** — Football field chart (horizontal bar chart: DCF blue, CCA green, PT gold; current price as red dashed vertical line; diamond markers at mid-values), summary table (method, low, mid, high)
   10. **Recommendations** — Verdict box, confidence note, key value drivers list
   11. **Assumptions & Limitations** — Bullet lists of assumptions, model limitations, data caveats, disclaimer
   12. **Data Appendix** — Raw financial data table (year, revenue, NI, EBITDA, FCF, total assets, equity)

2. **PDF Report** (`reports/{TICKER}_valuation_report.pdf`) — Same content rendered via weasyprint. If weasyprint is not installed, only HTML is generated with a warning.

**Charts Generated:**
- Financial Ratio Trends (4-panel: margins, returns, revenue/FCF bars, leverage) — `matplotlib`
- DCF Sensitivity Heatmap (WACC vs growth rate, colour-coded by implied price) — `matplotlib`
- Valuation Football Field (horizontal bar chart per method with current price line) — `matplotlib`

**Validation After Generation:**
- HTML file exists and is > 10KB (non-trivial content)
- All 12 section headings present in the HTML
- Charts are embedded as base64 images (no broken image links)
- If PDF requested: PDF file exists and is > 50KB

---

## Error Handling Summary

| Stage | Error Condition | Action |
|-------|----------------|--------|
| 0 | Invalid ticker or API failure | Print error message; suggest checking ticker or using synthetic data |
| 0 | < 3 peers fetched | Print error; suggest adding more tickers |
| 1 | Validation FAIL (critical nulls, < 3 years) | STOP pipeline; display issues with fix suggestions |
| 2 | WACC out of 0–30% range | Warning; proceed with capped value |
| 2 | Terminal growth ≥ WACC | Auto-adjust to WACC − 1%; print warning |
| 3 | Negative FCF for DCF | Flag warning; proceed but note unreliability |
| 3 | No valid CCA multiples | Skip CCA; proceed with DCF + PT only |
| 3 | No precedent transactions | Skip PT; proceed with DCF + CCA |
| 4 | > 50% divergence across methods | LOW confidence; recommend reviewing assumptions |
| 6 | weasyprint not installed | Skip PDF; generate HTML only with warning |

---

## Full Pipeline — Quick Reference

```bash
# Step 0: Fetch data (OR generate synthetic data)
python scripts/fetch_data.py --ticker AAPL --peers MSFT,GOOGL,META,AMZN --output data/raw/financials.json

# Step 1: Validate
python scripts/validate_data.py --input data/raw/financials.json --output data/validation_report.json

# Step 2: Feature engineering
python scripts/feature_engineering.py --input data/raw/financials.json --config config.json --output data/features.json

# Step 3 & 4: Modelling + cross-validation
python scripts/run_models.py --input data/features.json --output data/valuation_results.json

# Step 5: (LLM interprets results using REFERENCE.md — no script)

# Step 6: Generate report
python scripts/generate_report.py --input data/valuation_results.json --format both --output reports/
```

---

## Testing Scenarios

### Scenario 1: Successful Full Valuation (Apple Inc.)
```bash
python scripts/fetch_data.py --ticker AAPL --peers MSFT,GOOGL,META,AMZN --output data/raw/financials.json
python scripts/validate_data.py --input data/raw/financials.json --output data/validation_report.json
python scripts/feature_engineering.py --input data/raw/financials.json --output data/features.json
python scripts/run_models.py --input data/features.json --output data/valuation_results.json
python scripts/generate_report.py --input data/valuation_results.json --format both --output reports/
```
**Expected:** Complete HTML+PDF report with all 3 methods producing reasonable valuations.

### Scenario 2: Bad Data — Missing Critical Columns
Create a malformed JSON with `revenue` set to `null` for all years.
```bash
python scripts/validate_data.py --input data/raw/bad_data.json --output data/validation_report.json
```
**Expected:** Validation FAILS with clear error: "Column 'revenue' is entirely missing/null" with fix suggestion.

### Scenario 3: Negative Cash Flow Company
Use a company with negative FCF (e.g., high-growth startup).
```bash
python scripts/generate_synthetic_data.py --target-ticker BURN --peers PEER1,PEER2,PEER3 --sector Technology --output data/raw/financials.json
# Then manually set negative operating_cash_flow in the JSON
python scripts/validate_data.py --input data/raw/financials.json --output data/validation_report.json
python scripts/feature_engineering.py --input data/raw/financials.json --output data/features.json
python scripts/run_models.py --input data/features.json --output data/valuation_results.json
python scripts/generate_report.py --input data/valuation_results.json --format html --output reports/
```
**Expected:** DCF warns about negative FCF; CCA and PT still produce valid ranges; report generated with warning banner.
