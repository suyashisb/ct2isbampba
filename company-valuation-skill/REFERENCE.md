# REFERENCE.md — Company Valuation Domain Knowledge

This document encodes all domain-specific knowledge required by the Company Valuation
Analytics Skill. The LLM must consult this file for formulas, benchmarks, interpretation
frameworks, and recommendation templates. **Do not hallucinate financial formulas or
industry benchmarks — use only the definitions below.**

---

## 1. Valuation Method Definitions

### 1.1 Discounted Cash Flow (DCF)

DCF estimates the **intrinsic value** of a company by projecting future free cash flows
and discounting them to present value using the Weighted Average Cost of Capital (WACC).

#### Free Cash Flow to Firm (FCFF)

```
FCFF = Operating Cash Flow − Capital Expenditures
     = EBIT × (1 − Tax Rate) + Depreciation & Amortisation − ΔWorking Capital − CapEx
```

For this skill, the simplified formula is preferred when operating cash flow is available:

```
FCFF = Operating Cash Flow − Capital Expenditures
```

#### Weighted Average Cost of Capital (WACC)

```
WACC = (E / V) × Re + (D / V) × Rd × (1 − Tc)
```

Where:
| Symbol | Definition | Source |
|--------|-----------|--------|
| E | Market value of equity | shares_outstanding × stock_price |
| D | Market value of debt | total_liabilities (approximation) |
| V | E + D | — |
| Re | Cost of equity (from CAPM) | See below |
| Rd | Cost of debt | interest_expense / total_debt, or industry average |
| Tc | Corporate tax rate | tax_provision / pre_tax_income, or user-supplied |

#### Capital Asset Pricing Model (CAPM) — Cost of Equity

```
Re = Rf + β × (Rm − Rf)
```

| Symbol | Definition | Default |
|--------|-----------|---------|
| Rf | Risk-free rate (10-year Treasury yield) | User-supplied or 4.0% |
| β (beta) | Stock's systematic risk | Fetched from data or 1.0 |
| Rm − Rf | Equity risk premium (ERP) | User-supplied or 5.5% |

#### Terminal Value

Two methods must be computed and compared:

**Gordon Growth Model (Perpetuity Growth):**
```
TV_gordon = FCF_final × (1 + g) / (WACC − g)
```
Where g = terminal growth rate (default: 2.5%, must be < WACC).

**Exit Multiple Method:**
```
TV_exit = EBITDA_final × Exit_EV_EBITDA_Multiple
```
Where Exit_EV_EBITDA_Multiple = sector median EV/EBITDA from peer group.

#### Enterprise Value → Equity Value per Share

```
Enterprise Value (EV) = Σ [FCFt / (1 + WACC)^t] + TV / (1 + WACC)^n
Equity Value = EV − Net Debt
Net Debt = Total Debt − Cash & Cash Equivalents
Equity Value per Share = Equity Value / Shares Outstanding
```

### 1.2 Comparable Company Analysis (CCA)

CCA estimates value by comparing the target company's financial metrics to those of
similar publicly traded companies ("peers").

#### Key Multiples

| Multiple | Formula | Use Case |
|----------|---------|----------|
| EV/EBITDA | Enterprise Value / EBITDA | Most common; capital-structure-neutral |
| EV/Revenue | Enterprise Value / Revenue | For unprofitable or high-growth companies |
| P/E | Stock Price / Earnings Per Share | Widely quoted; affected by capital structure |
| P/B | Stock Price / Book Value Per Share | For asset-heavy industries (banking, real estate) |

#### Enterprise Value Bridge

```
Enterprise Value = Market Cap + Total Debt − Cash & Equivalents + Minority Interest + Preferred Stock
```

Simplified (for this skill):
```
EV = (Shares Outstanding × Stock Price) + Total Liabilities − Cash
```

#### Implied Equity Value

```
Implied EV = Target Metric × Peer Median Multiple
Implied Equity Value = Implied EV − Net Debt
Implied Price per Share = Implied Equity Value / Shares Outstanding
```

Compute for each multiple (EV/EBITDA, EV/Revenue, P/E, P/B). Report min, median, max
from peer set for each multiple.

### 1.3 Precedent Transactions Analysis

Values a company based on prices paid in historical M&A transactions in the same sector.

#### Transaction Multiples

Same multiples as CCA (EV/EBITDA, EV/Revenue) but derived from acquisition prices,
which include a **control premium**.

#### Control Premium

```
Control Premium = (Acquisition Price per Share − Pre-Announcement Price) / Pre-Announcement Price
```

Typical range: **20%–40%** depending on:
- Industry (tech premiums tend higher)
- Deal competition (multiple bidders → higher premium)
- Strategic vs. financial buyer

#### Applying Precedent Transactions

```
Implied EV = Target EBITDA × Median Transaction EV/EBITDA
Implied Equity Value = Implied EV − Net Debt
```

Note: Precedent transaction values inherently include a control premium, so they typically
produce **higher** valuations than CCA. This is expected and should be noted in interpretation.

---

## 2. Financial Ratio Definitions

### 2.1 Profitability Ratios

| Ratio | Formula | Healthy Range |
|-------|---------|---------------|
| Gross Margin | (Revenue − COGS) / Revenue | 30%–70% (varies by sector) |
| Operating Margin | Operating Income / Revenue | 10%–30% |
| Net Margin | Net Income / Revenue | 5%–20% |
| ROE | Net Income / Total Equity | 10%–25% |
| ROA | Net Income / Total Assets | 3%–15% |
| ROIC | NOPAT / Invested Capital | > WACC is value-creating |

### 2.2 Leverage Ratios

| Ratio | Formula | Healthy Range |
|-------|---------|---------------|
| Debt-to-Equity | Total Liabilities / Total Equity | 0.5–2.0 |
| Interest Coverage | Operating Income / Interest Expense | > 3.0 |
| Net Debt / EBITDA | (Total Debt − Cash) / EBITDA | < 3.0 |

### 2.3 Liquidity Ratios

| Ratio | Formula | Healthy Range |
|-------|---------|---------------|
| Current Ratio | Current Assets / Current Liabilities | 1.5–3.0 |
| Quick Ratio | (Current Assets − Inventory) / Current Liabilities | > 1.0 |

### 2.4 Growth Metrics

| Metric | Formula |
|--------|---------|
| Revenue Growth (YoY) | (Revenue_t − Revenue_{t-1}) / Revenue_{t-1} |
| Earnings Growth (YoY) | (Net Income_t − Net Income_{t-1}) / \|Net Income_{t-1}\| |
| FCF Growth (YoY) | (FCF_t − FCF_{t-1}) / \|FCF_{t-1}\| |
| Revenue CAGR | (Revenue_final / Revenue_initial)^(1/years) − 1 |

---

## 3. Industry Benchmarks

### 3.1 Typical WACC Ranges by Sector

| Sector | WACC Range | Notes |
|--------|-----------|-------|
| Technology | 8%–12% | Higher beta, lower debt |
| Healthcare / Pharma | 7%–11% | Moderate beta |
| Consumer Staples | 6%–9% | Low beta, stable cash flows |
| Energy | 8%–13% | Cyclical, commodity-exposed |
| Financials | 8%–12% | Complex capital structures |
| Industrials | 7%–10% | Moderate cyclicality |
| Utilities | 4%–7% | Regulated, low risk |
| Real Estate | 5%–8% | Asset-heavy, leverage-dependent |
| Telecommunications | 6%–9% | Stable but capital-intensive |

### 3.2 Typical EV/EBITDA Multiples by Sector

| Sector | EV/EBITDA Range | Notes |
|--------|----------------|-------|
| Technology | 15×–30× | Growth premium |
| Healthcare / Pharma | 12×–20× | Pipeline value |
| Consumer Staples | 10×–16× | Stability premium |
| Energy | 5×–10× | Cyclical discounts |
| Financials | 8×–14× | — |
| Industrials | 8×–14× | — |
| Utilities | 8×–12× | Regulated earnings |
| Real Estate | 12×–20× | NAV-driven |
| Telecommunications | 6×–10× | Mature markets |

### 3.3 Typical Control Premiums by Sector

| Sector | Control Premium Range |
|--------|----------------------|
| Technology | 25%–45% |
| Healthcare | 30%–50% |
| Consumer | 20%–35% |
| Energy | 20%–40% |
| Financials | 15%–30% |
| Industrials | 20%–35% |

---

## 4. Interpretation Framework

### 4.1 Valuation Football Field

The "football field" chart shows the valuation range from each method side-by-side.
The recommended fair value range is the **overlap region** across methods.

### 4.2 Valuation Verdict

Compare the **recommended fair value per share** to the **current stock price**:

| Condition | Verdict | Confidence |
|-----------|---------|------------|
| Implied upside > 20% | **Undervalued** | High if 3/3 methods agree |
| Implied upside 5%–20% | **Slightly Undervalued** | Moderate |
| Implied change −5% to +5% | **Fairly Valued** | — |
| Implied downside 5%–20% | **Slightly Overvalued** | Moderate |
| Implied downside > 20% | **Overvalued** | High if 3/3 methods agree |

### 4.3 Cross-Method Consistency Check

| Divergence Level | Action |
|-----------------|--------|
| All methods within 20% of each other | High confidence — use mean/median |
| One outlier > 30% from others | Investigate; explain the driver; weight other two methods more |
| All methods diverge > 50% | Low confidence — flag to user; assumptions may need revisiting |

### 4.4 DCF Sensitivity Interpretation

The sensitivity table shows how valuation changes with WACC and terminal growth rate.
Key patterns:
- **WACC dominates**: a 1% change in WACC typically causes 15%–25% change in valuation
- **Growth rate impact increases at lower WACC**: at low discount rates, terminal growth
  assumptions matter much more
- The cell where WACC = base case and g = base case is the base valuation

### 4.5 Special Cases

#### Negative Free Cash Flow Companies
If the target has negative FCF (high-growth or pre-profit):
- DCF may produce negative or unreliable values → **flag to user**
- Rely more heavily on CCA (EV/Revenue) and Precedent Transactions
- Note that DCF requires positive future FCF assumption; if growth trajectory suggests
  profitability in 3–5 years, project the FCF crossing positive

#### High-Debt Companies
If Debt-to-Equity > 3.0:
- WACC may be misleadingly low; valuation shifts to equity holders is amplified
- DCF equity value is highly sensitive to debt assumptions
- Flag leverage risk in report

#### Cyclical Companies
If in Energy, Materials, or Industrials:
- Use normalised (mid-cycle) earnings for CCA multiples
- Historical averages > trailing 12-month figures

---

## 5. Recommendation Templates

### 5.1 Undervalued Company

> **Recommendation: BUY**
> Based on our three-method valuation (DCF, CCA, Precedent Transactions), [Company]
> appears undervalued with an implied fair value range of $X–$Y per share, representing
> Z% upside from the current price of $P. Key value drivers include [strong FCF growth /
> margin expansion / underappreciated market position]. Primary risks to the thesis
> include [risk 1, risk 2].

### 5.2 Fairly Valued Company

> **Recommendation: HOLD**
> Our analysis suggests [Company] is fairly valued at $X–$Y per share, closely aligned
> with the current trading price of $P. The stock is priced consistently with peer
> multiples and our DCF model. We see limited near-term catalysts for re-rating but no
> significant downside either. Monitor [key metric] for potential changes to this view.

### 5.3 Overvalued Company

> **Recommendation: SELL / REDUCE**
> Our valuation analysis indicates [Company] is trading at a premium to fair value of
> $X–$Y, implying Z% downside from the current price of $P. The premium appears driven
> by [market optimism / multiple expansion / unsustainable growth expectations]. Key risks
> to a short thesis include [potential upside catalysts].

### 5.4 Low-Confidence Valuation

> **Recommendation: NO STRONG VIEW**
> Our three valuation methods produced a wide range of estimates ($X–$Y), reflecting
> significant uncertainty in [key assumptions]. We recommend further analysis with
> refined assumptions before making an investment decision. Key areas of uncertainty:
> [list].

---

## 6. Report Section Requirements

The final report must contain these sections in order:

1. **Executive Summary** — Valuation range, recommendation, key metrics (1 paragraph)
2. **Company Overview** — Business description, sector, key financials snapshot
3. **Data Quality Summary** — Output from validation stage; data coverage and any warnings
4. **Methodology** — Brief description of DCF, CCA, Precedent Transactions approach
5. **Financial Ratio Analysis** — Tables and charts of profitability, leverage, growth trends
6. **DCF Valuation** — Projected cash flows table, WACC calculation, terminal value,
   sensitivity heatmap, tornado chart of key assumptions
7. **Comparable Company Analysis** — Peer multiples table, implied valuation range per multiple
8. **Precedent Transactions** — Transaction table, implied values with control premium
9. **Valuation Summary** — Football field chart showing ranges from all methods,
   recommended fair value range
10. **Business Interpretation & Recommendations** — Verdict (buy/hold/sell), key drivers,
    risks, using templates from Section 5
11. **Assumptions & Limitations** — All assumptions listed, model limitations, data caveats
12. **Data Appendix** — Raw financial data tables, feature computation details
