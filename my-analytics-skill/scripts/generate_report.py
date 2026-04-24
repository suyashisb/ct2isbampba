#!/usr/bin/env python3
"""
generate_report.py — Generate professional HTML and PDF valuation reports.

Reads valuation results and features, creates charts, and renders a multi-section
report using the HTML template.

Usage:
    python scripts/generate_report.py --input data/valuation_results.json --format both --output reports/
    python scripts/generate_report.py --input data/valuation_results.json --format html --output reports/
"""

import argparse
import base64
import io
import json
import os
import sys
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from jinja2 import Template


def fig_to_base64(fig) -> str:
    """Convert a matplotlib figure to a base64-encoded PNG for HTML embedding."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{b64}" alt="chart">'


def make_ratio_charts(features: list) -> str:
    """Create financial ratio trend charts."""
    years = [f.get("fiscal_year") for f in features]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Financial Ratio Trends", fontsize=14, fontweight="bold")

    # Margin trends
    ax = axes[0, 0]
    ax.plot(years, [f.get("gross_margin", 0) * 100 for f in features], "o-", label="Gross Margin", color="#3182ce")
    ax.plot(years, [f.get("operating_margin", 0) * 100 for f in features], "s-", label="Operating Margin", color="#38a169")
    ax.plot(years, [f.get("net_margin", 0) * 100 for f in features], "^-", label="Net Margin", color="#d69e2e")
    ax.set_title("Profitability Margins (%)")
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.grid(True, alpha=0.3)

    # ROE / ROA
    ax = axes[0, 1]
    ax.plot(years, [f.get("roe", 0) * 100 for f in features], "o-", label="ROE", color="#3182ce")
    ax.plot(years, [f.get("roa", 0) * 100 for f in features], "s-", label="ROA", color="#e53e3e")
    ax.set_title("Return Metrics (%)")
    ax.legend(fontsize=8)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax.grid(True, alpha=0.3)

    # Revenue & FCF
    ax = axes[1, 0]
    rev = [f.get("revenue", 0) / 1e9 for f in features]
    fcf = [f.get("fcff", 0) / 1e9 for f in features]
    x = np.arange(len(years))
    ax.bar(x - 0.2, rev, 0.4, label="Revenue", color="#3182ce", alpha=0.8)
    ax.bar(x + 0.2, fcf, 0.4, label="FCF", color="#38a169", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.set_title("Revenue & FCF ($B)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # Leverage
    ax = axes[1, 1]
    de = [f.get("debt_to_equity") for f in features]
    ax.plot(years, de, "o-", label="Debt/Equity", color="#e53e3e")
    ax.set_title("Leverage (Debt-to-Equity)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig_to_base64(fig)


def make_sensitivity_chart(sensitivity: dict, cs: str = "$") -> str:
    """Create heatmap of DCF sensitivity to WACC and terminal growth rate."""
    matrix = sensitivity.get("matrix", [])
    wacc_labels = sensitivity.get("wacc_range", [])
    growth_labels = sensitivity.get("growth_range", [])

    if not matrix or not growth_labels:
        return "<p>Sensitivity data not available.</p>"

    data = []
    for row in matrix:
        vals = []
        for g in growth_labels:
            v = row["values"].get(str(g))
            vals.append(v if v is not None else 0)
        data.append(vals)

    arr = np.array(data, dtype=float)

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(arr, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(growth_labels)))
    ax.set_xticklabels([f"{g*100:.1f}%" for g in growth_labels])
    ax.set_yticks(range(len(wacc_labels)))
    ax.set_yticklabels([f"{w*100:.1f}%" for w in wacc_labels])
    ax.set_xlabel("Terminal Growth Rate")
    ax.set_ylabel("WACC")
    ax.set_title(f"DCF Sensitivity: Implied Price per Share ({cs})")

    # Add text annotations
    for i in range(len(wacc_labels)):
        for j in range(len(growth_labels)):
            val = arr[i, j]
            if val != 0:
                txt = f"{cs}{val:,.0f}"
                color = "white" if abs(val - arr.mean()) > arr.std() else "black"
                ax.text(j, i, txt, ha="center", va="center", fontsize=7, color=color)

    fig.colorbar(im, ax=ax, shrink=0.8)
    plt.tight_layout()
    return fig_to_base64(fig)


def make_football_field_chart(cross_validation: dict, current_price: float, cs: str = "$") -> str:
    """Create a football field chart comparing valuation ranges from all methods."""
    methods = cross_validation.get("method_summary", [])
    if not methods:
        return "<p>No valuation data for football field chart.</p>"

    fig, ax = plt.subplots(figsize=(10, 4))

    colors = {"DCF": "#3182ce", "CCA": "#38a169", "Precedent Transactions": "#d69e2e"}
    y_pos = list(range(len(methods)))

    all_vals = [m["low"] for m in methods] + [m["high"] for m in methods] + [current_price]
    valid_vals = [v for v in all_vals if v > 0]
    if not valid_vals:
        return "<p>No valid valuation ranges to display.</p>"

    for i, m in enumerate(methods):
        low, mid, high = m["low"], m["mid"], m["high"]
        color = colors.get(m["method"], "#718096")
        ax.barh(i, high - low, left=low, height=0.5, color=color, alpha=0.7, label=m["method"])
        ax.plot(mid, i, "D", color="white", markersize=8, markeredgecolor=color, markeredgewidth=2)
        ax.text(high + (max(valid_vals) * 0.01), i, f"{cs}{mid:,.0f}", va="center", fontsize=9, fontweight="bold")

    # Current price line
    ax.axvline(x=current_price, color="#e53e3e", linestyle="--", linewidth=2, label=f"Current: {cs}{current_price:,.0f}")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([m["method"] for m in methods])
    ax.set_xlabel("Price per Share ($)")
    ax.set_title("Valuation Football Field")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3, axis="x")

    plt.tight_layout()
    return fig_to_base64(fig)


def build_table(headers: list, rows: list) -> str:
    """Build an HTML table from headers and list of row dicts/lists."""
    html = "<table><thead><tr>"
    for h in headers:
        html += f"<th>{h}</th>"
    html += "</tr></thead><tbody>"
    for row in rows:
        html += "<tr>"
        if isinstance(row, dict):
            for h in headers:
                val = row.get(h, "")
                html += f"<td>{val}</td>"
        elif isinstance(row, (list, tuple)):
            for val in row:
                html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html


def fmt_num(val, prefix="", suffix="", decimals=2):
    """Format a number for display."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if abs(val) >= 1e9:
            return f"{prefix}{val/1e9:,.{decimals}f}B{suffix}"
        if abs(val) >= 1e6:
            return f"{prefix}{val/1e6:,.{decimals}f}M{suffix}"
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    return str(val)


def fmt_pct(val, decimals=1):
    """Format a decimal as percentage."""
    if val is None:
        return "N/A"
    return f"{val*100:,.{decimals}f}%"


def generate_report(results_path: str, output_dir: str, fmt: str = "both"):
    """Generate the full valuation report."""
    with open(results_path, "r") as f:
        data = json.load(f)

    target = data["target"]
    config = data.get("config", {})
    features = data.get("features", [])
    dcf = data.get("dcf", {})
    cca = data.get("cca", {})
    pt = data.get("precedent_transactions", {})
    cv = data.get("cross_validation", {})

    ticker = target["ticker"]
    company = target["company_name"]
    sector = target.get("sector", "Unknown")
    price = target.get("current_price", 0)
    shares = target.get("shares_outstanding", 0)

    # Currency symbol from data (Yahoo Finance provides currency code)
    currency_code = target.get("currency", "USD")
    currency_symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥",
        "INR": "₹", "KRW": "₩", "CHF": "CHF ", "CAD": "C$", "AUD": "A$",
        "HKD": "HK$", "SGD": "S$", "SEK": "kr", "NOK": "kr", "DKK": "kr",
        "BRL": "R$", "MXN": "MX$", "ZAR": "R", "TWD": "NT$", "THB": "฿",
    }
    cs = currency_symbols.get(currency_code, f"{currency_code} ")

    # Load template
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "report_template.html")
    if not os.path.exists(template_path):
        template_path = "templates/report_template.html"
    with open(template_path, "r") as f:
        template = Template(f.read())

    # Generate charts
    ratio_charts = make_ratio_charts(features) if features else ""
    sensitivity_chart = make_sensitivity_chart(dcf.get("sensitivity", {}), cs)
    football_chart = make_football_field_chart(cv, price, cs)

    # Verdict class for CSS
    rec = cv.get("recommendation", "HOLD")
    if rec in ("BUY",):
        verdict_class = "buy"
    elif rec in ("SELL",):
        verdict_class = "sell"
    else:
        verdict_class = "hold"

    # Executive summary text
    exec_text = (
        f"Based on a three-method valuation analysis (DCF, Comparable Company, Precedent Transactions), "
        f"{company} appears to be {cv.get('verdict', 'N/A').lower()} at the current price of {cs}{price:,.2f}. "
        f"Our analysis yields a fair value range of ${cv.get('overall_range', {}).get('low', 0):,.2f} &ndash; "
        f"${cv.get('overall_range', {}).get('high', 0):,.2f} per share, with a midpoint of "
        f"${cv.get('overall_range', {}).get('mid', 0):,.2f}. {cv.get('confidence_note', '')}"
    )

    # Company overview
    latest = features[-1] if features else {}
    overview_rows = [
        ("Ticker", ticker), ("Sector", sector),
        ("Revenue (Latest)", fmt_num(latest.get("revenue"), cs)),
        ("Net Income", fmt_num(latest.get("net_income"), cs)),
        ("EBITDA", fmt_num(latest.get("ebitda"), cs)),
        ("Free Cash Flow", fmt_num(latest.get("fcff"), cs)),
        ("Market Cap", fmt_num(latest.get("market_cap"), cs)),
        ("Shares Outstanding", fmt_num(shares)),
        ("Stock Price", f"{cs}{price:,.2f}"),
        ("EPS", fmt_num(latest.get("eps"), cs)),
    ]
    company_overview = build_table(["Metric", "Value"], overview_rows)

    # Data quality
    dq_rows = [
        ("Fiscal Years", str(len(features))),
        ("Peer Companies", str(len(cca.get("peer_details", [])))),
        ("Precedent Transactions", str(len(pt.get("transactions", [])))),
    ]
    if cv.get("all_warnings"):
        for w in cv["all_warnings"]:
            dq_rows.append(("Warning", w))
    dq_html = build_table(["Check", "Result"], dq_rows)

    # Ratio table
    ratio_headers = ["Year", "Gross Margin", "Op Margin", "Net Margin", "ROE", "ROA", "D/E", "FCF Margin"]
    ratio_rows = []
    for feat in features:
        ratio_rows.append([
            feat.get("fiscal_year"),
            fmt_pct(feat.get("gross_margin")),
            fmt_pct(feat.get("operating_margin")),
            fmt_pct(feat.get("net_margin")),
            fmt_pct(feat.get("roe")),
            fmt_pct(feat.get("roa")),
            fmt_num(feat.get("debt_to_equity"), decimals=2) if feat.get("debt_to_equity") else "N/A",
            fmt_pct(feat.get("fcf_margin")),
        ])
    ratio_table = build_table(ratio_headers, ratio_rows)

    # WACC table
    wacc = dcf.get("wacc", {})
    wacc_rows = [
        ("Risk-Free Rate", fmt_pct(wacc.get("risk_free_rate"))),
        ("Beta", fmt_num(wacc.get("beta"))),
        ("Equity Risk Premium", fmt_pct(wacc.get("equity_risk_premium"))),
        ("Cost of Equity", fmt_pct(wacc.get("cost_of_equity"))),
        ("Cost of Debt (pre-tax)", fmt_pct(wacc.get("cost_of_debt"))),
        ("Tax Rate", fmt_pct(wacc.get("tax_rate"))),
        ("Equity Weight", fmt_pct(wacc.get("weight_equity"))),
        ("Debt Weight", fmt_pct(wacc.get("weight_debt"))),
        ("WACC", f"<strong>{fmt_pct(wacc.get('wacc'))}</strong>"),
    ]
    wacc_table = build_table(["Component", "Value"], wacc_rows)

    # DCF projections table
    proj = dcf.get("projections", [])
    proj_headers = ["Year", "Growth Rate", "Projected FCF", "Discount Factor", "Present Value"]
    proj_rows = [[
        p["year"], fmt_pct(p["growth_rate"]), fmt_num(p["projected_fcf"], cs),
        fmt_num(p["discount_factor"]), fmt_num(p["present_value"], cs),
    ] for p in proj]
    proj_table = build_table(proj_headers, proj_rows)

    # DCF result
    dcf_res_rows = [
        ("Sum of PV(FCFs)", fmt_num(dcf.get("blended", {}).get("enterprise_value", 0) - dcf.get("gordon_growth", {}).get("enterprise_value", 0) + dcf.get("blended", {}).get("enterprise_value", 0), cs)),
        ("Gordon Growth - Price/Share", fmt_num(dcf.get("gordon_growth", {}).get("price_per_share"), cs)),
        ("Exit Multiple - Price/Share", fmt_num(dcf.get("exit_multiple", {}).get("price_per_share"), cs)),
        ("Blended - Price/Share", f"<strong>{fmt_num(dcf.get('blended', {}).get('price_per_share'), '$')}</strong>"),
    ]
    dcf_result_table = build_table(["Metric", "Value"], dcf_res_rows)

    # Sensitivity table
    sens = dcf.get("sensitivity", {})
    sens_matrix = sens.get("matrix", [])
    growth_labels = sens.get("growth_range", [])
    sens_html = ""
    if sens_matrix and growth_labels:
        sens_html = '<table><thead><tr><th>WACC \\ Growth</th>'
        for g in growth_labels:
            sens_html += f'<th>{g*100:.1f}%</th>'
        sens_html += '</tr></thead><tbody>'
        base_wacc = wacc.get("wacc", 0)
        base_tg = config.get("terminal_growth_rate", 0.025)
        for row in sens_matrix:
            w = row["wacc"]
            is_base_row = abs(w - base_wacc) < 0.001
            sens_html += '<tr>'
            sens_html += f'<td><strong>{w*100:.1f}%</strong></td>'
            for g in growth_labels:
                val = row["values"].get(str(g))
                is_base = is_base_row and abs(g - base_tg) < 0.001
                cls = ' class="highlight"' if is_base else ''
                sens_html += f'<td{cls}>{fmt_num(val, cs) if val else "N/A"}</td>'
            sens_html += '</tr>'
        sens_html += '</tbody></table>'

    # Peer multiples table
    peers = cca.get("peer_details", [])
    peer_headers = ["Ticker", "Company", "EV/EBITDA", "EV/Revenue", "P/E", "P/B"]
    peer_rows = [[
        p.get("ticker", ""), p.get("company_name", ""),
        fmt_num(p.get("ev_ebitda")), fmt_num(p.get("ev_revenue")),
        fmt_num(p.get("pe_ratio")), fmt_num(p.get("pb_ratio")),
    ] for p in peers]
    # Add stats row
    ms = cca.get("multiple_stats", {})
    peer_rows.append(["<strong>Median</strong>", "",
        fmt_num(ms.get("ev_ebitda", {}).get("median")),
        fmt_num(ms.get("ev_revenue", {}).get("median")),
        fmt_num(ms.get("pe_ratio", {}).get("median")),
        fmt_num(ms.get("pb_ratio", {}).get("median")),
    ])
    peer_table = build_table(peer_headers, peer_rows)

    # CCA implied
    implied = cca.get("implied_values", {})
    cca_rows = []
    for mult_name, levels in implied.items():
        for level in ["min", "median", "max"]:
            if level in levels:
                d = levels[level]
                cca_rows.append([mult_name, level.title(), fmt_num(d.get("multiple")),
                                fmt_num(d.get("implied_price"), cs)])
    cca_implied_table = build_table(["Multiple", "Level", "Peer Multiple", "Implied Price"], cca_rows)

    # Precedent transactions table
    txns = pt.get("transactions", [])
    txn_headers = ["Date", "Target", "Acquirer", "Deal Value", "EV/Rev", "EV/EBITDA", "Premium"]
    txn_rows = [[
        t.get("transaction_date", ""), t.get("target_name", ""), t.get("acquirer_name", ""),
        fmt_num(t.get("deal_value"), cs), fmt_num(t.get("ev_revenue_multiple")),
        fmt_num(t.get("ev_ebitda_multiple")), f"{t.get('premium_paid', 0)}%",
    ] for t in txns]
    txn_table = build_table(txn_headers, txn_rows)

    # PT implied
    pt_implied = pt.get("implied_values", {})
    pt_rows = []
    for mult_name, levels in pt_implied.items():
        for level in ["min", "median", "max"]:
            if level in levels:
                d = levels[level]
                pt_rows.append([mult_name, level.title(), fmt_num(d.get("multiple")),
                               fmt_num(d.get("implied_price"), cs)])
    pt_implied_table = build_table(["Multiple", "Level", "Transaction Multiple", "Implied Price"], pt_rows) if pt_rows else "<p>No implied values from transactions.</p>"

    # Valuation summary table
    ms_list = cv.get("method_summary", [])
    vs_headers = ["Method", "Low", "Mid", "High"]
    vs_rows = [[m["method"], fmt_num(m["low"], cs), f"<strong>{fmt_num(m['mid'], '$')}</strong>", fmt_num(m["high"], cs)] for m in ms_list]
    vs_rows.append(["<strong>Overall</strong>",
        fmt_num(cv.get("overall_range", {}).get("low"), cs),
        f"<strong>{fmt_num(cv.get('overall_range', {}).get('mid'), '$')}</strong>",
        fmt_num(cv.get("overall_range", {}).get("high"), cs),
    ])
    val_summary_table = build_table(vs_headers, vs_rows)

    # Recommendations
    upside = cv.get("implied_upside_pct")
    rec_html = f"""
    <div class="verdict-box {verdict_class}">
        <div class="verdict-label">{cv.get('recommendation', 'N/A')}</div>
        <div class="verdict-detail">{cv.get('verdict', 'N/A')} | Implied Upside: {upside}% | Confidence: {cv.get('confidence', 'N/A')}</div>
    </div>
    <p>{cv.get('confidence_note', '')}</p>
    <h3>Key Value Drivers</h3>
    <ul>
        <li>Revenue CAGR: {fmt_pct(latest.get('revenue_cagr'))}</li>
        <li>Operating Margin: {fmt_pct(latest.get('operating_margin'))}</li>
        <li>Free Cash Flow: {fmt_num(latest.get('fcff'), '$')}</li>
        <li>WACC: {fmt_pct(wacc.get('wacc'))}</li>
    </ul>
    """

    # Assumptions
    assumptions = f"""
    <ul>
        <li>Risk-free rate: {fmt_pct(config.get('risk_free_rate'))} (based on 10-year Treasury yield)</li>
        <li>Equity risk premium: {fmt_pct(config.get('equity_risk_premium'))}</li>
        <li>Terminal growth rate: {fmt_pct(config.get('terminal_growth_rate'))}</li>
        <li>Projection period: {config.get('projection_years', 5)} years</li>
        <li>Tax rate: {fmt_pct(config.get('tax_rate'))}</li>
        <li>Financial data sourced from Yahoo Finance API / synthetic generator</li>
        <li>Precedent transactions are representative samples; actual M&A data may differ</li>
        <li>Past performance does not guarantee future results</li>
        <li>This report is for educational/analytical purposes only &mdash; not financial advice</li>
    </ul>
    <h3>Limitations</h3>
    <ul>
        <li>DCF is highly sensitive to WACC and terminal growth assumptions</li>
        <li>CCA depends on peer selection &mdash; different peers may yield different results</li>
        <li>Precedent transactions may not reflect current market conditions</li>
        <li>Does not account for qualitative factors (management quality, competitive moat, regulatory risk)</li>
    </ul>
    """

    # Appendix
    appendix_headers = ["Year", "Revenue", "Net Income", "EBITDA", "FCF", "Total Assets", "Total Equity"]
    appendix_rows = [[
        f.get("fiscal_year"), fmt_num(f.get("revenue"), cs), fmt_num(f.get("net_income"), cs),
        fmt_num(f.get("ebitda"), cs), fmt_num(f.get("fcff"), cs),
        fmt_num(f.get("total_assets"), cs), fmt_num(f.get("total_equity"), cs),
    ] for f in features]
    appendix_table = build_table(appendix_headers, appendix_rows)

    # Render template
    html_content = template.render(
        company_name=company,
        ticker=ticker,
        sector=sector,
        currency_symbol=cs,
        analysis_date=datetime.now().strftime("%Y-%m-%d"),
        report_format=fmt,
        current_price=f"{price:,.2f}",
        fair_value_mid=f"{cv.get('overall_range', {}).get('mid', 0):,.2f}",
        fair_value_low=f"{cv.get('overall_range', {}).get('low', 0):,.2f}",
        fair_value_high=f"{cv.get('overall_range', {}).get('high', 0):,.2f}",
        implied_upside=f"{upside:+.1f}" if upside is not None else "N/A",
        recommendation=cv.get("recommendation", "N/A"),
        verdict=cv.get("verdict", "N/A"),
        confidence=cv.get("confidence", "N/A"),
        verdict_class=verdict_class,
        executive_summary_text=exec_text,
        company_overview_html=company_overview,
        data_quality_html=dq_html,
        projection_years=config.get("projection_years", 5),
        wacc=f"{wacc.get('wacc', 0)*100:.1f}",
        terminal_growth=f"{config.get('terminal_growth_rate', 0.025)*100:.1f}",
        exit_multiple=f"{dcf.get('exit_multiple', {}).get('exit_ev_ebitda', 12):.1f}",
        peer_count=len(peers),
        transaction_count=len(txns),
        avg_premium=f"{pt.get('average_control_premium_pct', 30):.0f}",
        ratio_tables_html=ratio_table,
        ratio_charts=ratio_charts,
        wacc_table_html=wacc_table,
        dcf_projections_table_html=proj_table,
        dcf_result_html=dcf_result_table,
        sensitivity_table_html=sens_html,
        sensitivity_chart=sensitivity_chart,
        dcf_warnings=dcf.get("warnings", []),
        peer_multiples_table_html=peer_table,
        cca_implied_html=cca_implied_table,
        cca_chart="",
        precedent_table_html=txn_table,
        precedent_implied_html=pt_implied_table,
        football_field_chart=football_chart,
        valuation_summary_table_html=val_summary_table,
        recommendations_html=rec_html,
        assumptions_html=assumptions,
        appendix_html=appendix_table,
    )

    # Write outputs
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, f"{ticker}_valuation_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML report saved to {html_path}")

    if fmt in ("pdf", "both"):
        try:
            from weasyprint import HTML
            pdf_path = os.path.join(output_dir, f"{ticker}_valuation_report.pdf")
            HTML(string=html_content).write_pdf(pdf_path)
            print(f"PDF report saved to {pdf_path}")
        except ImportError:
            print("WARNING: weasyprint not installed. Skipping PDF generation.")
            print("  Install with: pip install weasyprint")
        except Exception as e:
            print(f"WARNING: PDF generation failed: {e}")

    return html_path


def main():
    parser = argparse.ArgumentParser(description="Generate valuation report (HTML/PDF)")
    parser.add_argument("--input", required=True, help="Valuation results JSON (from run_models.py)")
    parser.add_argument("--format", default="both", choices=["html", "pdf", "both"], help="Output format")
    parser.add_argument("--output", default="reports/", help="Output directory")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    generate_report(args.input, args.output, args.format)
    print("\nReport generation complete.")


if __name__ == "__main__":
    main()
