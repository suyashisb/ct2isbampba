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
│   ├── generate_report.py            # HTML/PDF report with charts
│   └── mcp_server.py                 # MCP server (JSON-RPC over stdio)
├── templates/
│   └── report_template.html          # 12-section Jinja2 template
├── data/
│   ├── data_dictionary.md            # Column definitions & constraints
│   └── transactions.json             # 33 curated M&A transactions (6 sectors)
├── reports/                           # Generated valuation reports
│   ├── MSFT_valuation_report.html
│   ├── AAPL_valuation_report.html
│   ├── JNJ_valuation_report.html
│   ├── MORN_valuation_report.html
│   └── ...
├── evaluation_report.html            # 7+ test scenario results
└── design_walkthrough.html           # Design decisions document (5 sections)
```

## Assignment 2 Deliverables Checklist

### Deliverable 1: Skill Package (GitHub)

| Requirement | File | Status |
|-------------|------|--------|
| SKILL.md (full 6-stage pipeline) | `SKILL.md` (v2.0, 21 KB) | ✅ |
| REFERENCE.md (domain knowledge) | `REFERENCE.md` (13 KB) | ✅ |
| Scripts (minimum 3) | 7 scripts in `scripts/` | ✅ |
| Data dictionary | `data/data_dictionary.md` | ✅ |
| Report template | `templates/report_template.html` | ✅ |
| Multi-algorithm comparison | DCF + CCA + Precedent Txns (3 methods) | ✅ |
| Professional report (HTML + charts) | 12-section HTML, 3 embedded charts, 300+ KB | ✅ |
| Live data via MCP | `scripts/mcp_server.py` + `fetch_data.py` (Yahoo Finance) | ✅ |
| Real-world dataset | Yahoo Finance live API (MSFT, AAPL, JNJ, MORN, NAUKRI.NS) | ✅ |
| Curated M&A dataset | `data/transactions.json` (33 deals, 6 sectors, 2020-2026) | ✅ |
| Synthetic data generator | `scripts/generate_synthetic_data.py` (seed=42) | ✅ |

### Deliverable 2: Execution Evidence (3+ full runs)

| Run | Data Source | Company | Report |
|-----|------------|---------|--------|
| 1 | Yahoo Finance (live) | Microsoft (MSFT) — **FAIRLY VALUED** | `reports/MSFT_valuation_report.html` |
| 2 | Yahoo Finance (live) | Apple (AAPL) — Technology | `reports/AAPL_valuation_report.html` |
| 3 | Yahoo Finance (live) | Johnson & Johnson (JNJ) — Healthcare | `reports/JNJ_valuation_report.html` |
| 4 | Yahoo Finance (live) | Morningstar (MORN) — Financials | `reports/MORN_valuation_report.html` |
| 5 | Yahoo Finance (live) | Info Edge India (NAUKRI.NS) — Emerging Market | `reports/NAUKRI.NS_valuation_report.html` |
| 6 | Synthetic (seed=42) | SYNTH Corp — Technology | `reports/SYNTH_valuation_report.html` |
| 7 | Modified synthetic | BURN Corp — Negative FCF edge case | `reports/BURN_valuation_report.html` |

### Deliverable 3: Evaluation Report (3+ test scenarios)

`evaluation_report.html` — 7 test scenarios:

1. AAPL (real-world, Technology) — PASS
2. JNJ (real-world, Healthcare, cross-sector) — PASS
3. Bad data (missing columns, <3 years, <3 peers) — PASS (graceful error)
4. Negative FCF company — PASS (DCF warns, CCA/PT valid)
5. Invalid peer tickers — PASS (graceful skip + count check)
6. WACC sensitivity (8% vs 15%) — PASS (verdict shifts)
7. Reproducibility (seed=42, two runs) — PASS (identical output)

### Deliverable 4: Design Walkthrough (3-5 pages)

`design_walkthrough.html` — 6 sections:

1. Why Company Valuation (domain rationale)
2. Pipeline Architecture & Design Decisions
3. Script Design & Interface Contracts
4. What Failed and What Was Fixed (5 hardening issues)
5. MCP Integration Architecture
6. Conclusion

### Bonus Points

| Bonus Requirement | Status |
|-------------------|--------|
| Live Data via MCP (where applicable) | ✅ MCP server + Yahoo Finance API |
| Interactive Parameter Sensitivity | ✅ WACC 8% vs 15% comparison with separate reports |
| Reproducibility Guarantee | ✅ Random seed=42, identical outputs on re-run |
| SOTA Methodology | ✅ Damodaran Jan 2026 ERP, synthetic credit rating, IQR ranges |

## SOTA Methodology

- **ERP**: 4.46% implied US equity risk premium (Damodaran, Jan 2026)
- **Cost of Debt**: Synthetic credit rating via interest coverage ratio (Damodaran method)
- **WACC Weights**: Total debt / (market cap + total debt), per Damodaran
- **Growth Estimation**: Median of 4 CAGRs (revenue, earnings, EBITDA, FCF) — dampens capex cycle distortions
- **FCF Projection**: Revenue-driven with concave growth decay (industry standard)
- **Exit Multiple**: Peer median EV/EBITDA (not target's own — avoids circularity)
- **Value Ranges**: 25th-75th percentile (IQR) instead of raw min/max — eliminates outlier-driven absurd ranges
- **M&A Data**: 33 real transactions (2020-2026) from SEC filings and press releases, pluggable via `data/transactions.json`
