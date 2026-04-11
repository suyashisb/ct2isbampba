# Company Valuation Analytics Skill

A production-quality LLM skill package that performs end-to-end company valuation using three methods: **Discounted Cash Flow (DCF)**, **Comparable Company Analysis (CCA)**, and **Precedent Transactions**. It fetches live financial data, validates it, computes financial ratios, runs all three valuation models, cross-validates results, and generates a professional 12-section HTML/PDF report with embedded charts.

## Quick Start

### Prerequisites

```bash
pip install yfinance pandas numpy matplotlib jinja2 scipy
pip install weasyprint  # Optional, for PDF output
```

### Run on Any Public Company (3 commands)

```bash
# 1. Fetch live data from Yahoo Finance
python scripts/fetch_data.py --ticker MSFT --peers AAPL,GOOGL,META,AMZN --output data/raw/financials.json

# 2. Run the full valuation pipeline (validate + features + models)
python scripts/validate_data.py --input data/raw/financials.json --output data/validation_report.json
python scripts/feature_engineering.py --input data/raw/financials.json --output data/features.json
python scripts/run_models.py --input data/features.json --output data/valuation_results.json

# 3. Generate the report
python scripts/generate_report.py --input data/valuation_results.json --format both --output reports/
```

Open `reports/MSFT_valuation_report.html` in a browser to view the full report.

### Run with Synthetic Data (no API needed)

```bash
python scripts/generate_synthetic_data.py --target-ticker TEST --peers P1,P2,P3,P4 --sector Technology --seed 42 --output data/raw/financials.json
# Then run the same pipeline commands above
```

## How to Use as an LLM Skill

This package is designed to be invoked by an LLM (e.g., GitHub Copilot, GPT-4, Claude) as a skill. The LLM reads `SKILL.md` for step-by-step pipeline instructions and consults `REFERENCE.md` for domain knowledge.

### For LLM Orchestration

1. Point the LLM at `SKILL.md` as its instruction file
2. The LLM follows the 6-stage pipeline:
   - **Stage 0**: Fetch data (calls `fetch_data.py` or `generate_synthetic_data.py`)
   - **Stage 1**: Validate data (calls `validate_data.py`)
   - **Stage 2**: Feature engineering (calls `feature_engineering.py`)
   - **Stage 3**: Run models (calls `run_models.py`)
   - **Stage 4**: Cross-validate (automatic in `run_models.py`)
   - **Stage 5**: Interpret results (LLM reads output JSON + `REFERENCE.md`)
   - **Stage 6**: Generate report (calls `generate_report.py`)
3. Each stage produces structured JSON that the LLM can inspect before proceeding
4. If validation fails, the LLM receives clear error messages with fix suggestions

### User Inputs Required

| Input | Example | Required? |
|-------|---------|-----------|
| Target ticker | `MSFT` | Yes |
| Peer tickers (min 3) | `AAPL,GOOGL,META,AMZN` | Yes |
| Risk-free rate | `0.0437` | No (default: 4.37%) |
| Equity risk premium | `0.0446` | No (default: 4.46%, Damodaran Jan 2026) |
| Projection years | `5` | No (default: 5) |
| Terminal growth rate | `0.025` | No (default: 2.5%) |
| Report format | `html`, `pdf`, or `both` | No (default: both) |

Custom parameters can be saved in a `config.json` file and passed via `--config config.json`.

## What the Report Contains

The generated report is a self-contained HTML file (~300 KB) with 12 sections:

1. **Executive Summary** - KPI cards, buy/hold/sell verdict with color coding
2. **Company Overview** - Key financials snapshot
3. **Data Quality Summary** - Validation results and data coverage
4. **Methodology** - Description of DCF, CCA, Precedent Transactions approaches
5. **Financial Ratio Analysis** - Profitability, leverage, growth trends with charts
6. **DCF Valuation** - WACC breakdown, projected FCFs, sensitivity heatmap
7. **Comparable Company Analysis** - Peer multiples table, implied valuations
8. **Precedent Transactions** - M&A transaction table, implied values
9. **Valuation Summary** - Football field chart comparing all methods
10. **Recommendations** - Buy/hold/sell with confidence level and key drivers
11. **Assumptions & Limitations** - All model assumptions and caveats
12. **Data Appendix** - Raw financial data tables

Embedded charts: financial ratio trends (4-panel), DCF sensitivity heatmap, valuation football field.

## Valuation Methodology

### DCF (Discounted Cash Flow)
- Revenue-driven FCF projection using median of 4 growth metrics (revenue, earnings, EBITDA, FCF CAGRs)
- WACC via CAPM with Damodaran Jan 2026 ERP (4.46%) and synthetic rating for cost of debt
- Two terminal value methods: Gordon Growth Model + Exit Multiple (peer median EV/EBITDA)
- 25-scenario sensitivity analysis (WACC +/-2% x terminal growth +/-1%)

### CCA (Comparable Company Analysis)
- 4 multiples: EV/EBITDA, EV/Revenue, P/E, P/B
- Min/median/max from peer group
- Implied equity value per share for each multiple

### Precedent Transactions
- Historical M&A transaction multiples for the sector
- Control premium analysis
- Implied acquisition value

### Cross-Validation
- Compares all three methods
- Confidence: HIGH (<20% divergence), MODERATE (20-50%), LOW (>50%)
- Verdict: Undervalued/Fairly Valued/Overvalued based on implied upside vs current price

## Project Structure

```
company-valuation-skill/
├── SKILL.md                          # LLM instructions (6-stage pipeline)
├── REFERENCE.md                      # Domain knowledge (formulas, benchmarks)
├── requirements.txt                  # Python dependencies
├── scripts/
│   ├── fetch_data.py                 # Yahoo Finance API data fetcher
│   ├── generate_synthetic_data.py    # Reproducible synthetic data (seed=42)
│   ├── validate_data.py              # Data profiling & validation
│   ├── feature_engineering.py        # Ratios, WACC, FCF projections
│   ├── run_models.py                 # DCF + CCA + Precedent Transactions
│   └── generate_report.py           # HTML/PDF report with charts
├── templates/
│   └── report_template.html          # 12-section Jinja2 template
├── data/
│   └── data_dictionary.md            # Column definitions & constraints
├── evaluation_report.html            # 7 test scenario results
└── design_walkthrough.html           # Design decisions document
```

## Tested Scenarios

| # | Scenario | Result |
|---|----------|--------|
| 1 | Apple Inc. (AAPL) - Technology | PASS |
| 2 | Johnson & Johnson (JNJ) - Healthcare | PASS |
| 3 | Microsoft (MSFT) - Technology | PASS |
| 4 | Bad data (missing columns, too few years) | PASS (graceful error) |
| 5 | Negative FCF company | PASS (DCF warns, CCA/PT valid) |
| 6 | Invalid peer tickers | PASS (graceful skip + count check) |
| 7 | Parameter sensitivity (WACC 8% vs 15%) | PASS (verdict shifts) |
| 8 | Reproducibility (seed=42, two runs) | PASS (identical output) |
