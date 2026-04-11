#!/usr/bin/env python3
"""
feature_engineering.py — Compute financial ratios, DCF inputs, and CCA multiples.

Transforms raw financial data into analysis-ready features for all three
valuation methods (DCF, CCA, Precedent Transactions).

Usage:
    python scripts/feature_engineering.py --input data/raw/financials.json --config config.json --output data/features.json
"""

import argparse
import json
import math
import os
import sys

# Damodaran Jan 2026 data: US ERP = 4.46% (implied), risk-free ~4.37% (10Y Treasury)
# Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html
DEFAULT_CONFIG = {
    "risk_free_rate": 0.0437,
    "equity_risk_premium": 0.0446,
    "projection_years": 5,
    "terminal_growth_rate": 0.025,
    "tax_rate": 0.21,
}


def compute_ratios(records: list) -> list:
    """Compute financial ratios for each fiscal year record."""
    enriched = []
    prev = None

    for r in sorted(records, key=lambda x: x.get("fiscal_year", 0)):
        # Skip records where critical fields are missing
        if r.get("revenue") is None and r.get("total_assets") is None:
            continue

        feat = dict(r)  # Copy original fields

        rev = r.get("revenue", 0) or 1  # avoid division by zero
        cogs = r.get("cost_of_revenue", 0) or 0
        op_inc = r.get("operating_income", 0) or 0
        ni = r.get("net_income", 0) or 0
        ta = r.get("total_assets", 0) or 1
        tl = r.get("total_liabilities", 0) or 0
        te = r.get("total_equity", 0) or 1
        ocf = r.get("operating_cash_flow", 0) or 0
        capex = r.get("capex", 0) or 0
        shares = r.get("shares_outstanding", 0) or 1
        price = r.get("stock_price", 0) or 1
        int_exp = r.get("interest_expense") or 0
        depr = r.get("depreciation") or 0
        ebitda = r.get("ebitda") or (op_inc + depr)
        total_debt = r.get("total_debt") or (tl * 0.5)
        cash = r.get("cash_and_equivalents") or 0

        # Profitability
        feat["gross_margin"] = round((rev - cogs) / rev, 4)
        feat["operating_margin"] = round(op_inc / rev, 4)
        feat["net_margin"] = round(ni / rev, 4)
        feat["roe"] = round(ni / te, 4) if te != 0 else None
        feat["roa"] = round(ni / ta, 4) if ta != 0 else None

        # Leverage
        feat["debt_to_equity"] = round(tl / te, 4) if te != 0 else None
        feat["interest_coverage"] = round(op_inc / int_exp, 2) if int_exp > 0 else None
        feat["net_debt"] = round(total_debt - cash, 2)
        feat["net_debt_to_ebitda"] = round((total_debt - cash) / ebitda, 2) if ebitda > 0 else None

        # Cash flow
        feat["fcff"] = round(ocf - capex, 2)
        feat["fcf_margin"] = round((ocf - capex) / rev, 4) if rev > 0 else None

        # Per-share
        feat["eps"] = round(ni / shares, 2)
        feat["book_value_per_share"] = round(te / shares, 2)
        feat["fcf_per_share"] = round((ocf - capex) / shares, 2)

        # Valuation multiples (for CCA)
        market_cap = price * shares
        ev = market_cap + total_debt - cash
        feat["market_cap"] = round(market_cap, 2)
        feat["enterprise_value"] = round(ev, 2)
        feat["ev_ebitda"] = round(ev / ebitda, 2) if ebitda > 0 else None
        feat["ev_revenue"] = round(ev / rev, 2) if rev > 0 else None
        feat["pe_ratio"] = round(price / (ni / shares), 2) if ni > 0 else None
        feat["pb_ratio"] = round(price / (te / shares), 2) if te > 0 else None

        # EBITDA (ensure it's in record)
        feat["ebitda"] = round(ebitda, 2)

        # Growth (YoY)
        if prev is not None:
            prev_rev = prev.get("revenue", 0) or 1
            prev_ni = prev.get("net_income")
            prev_fcf = prev.get("fcff")

            feat["revenue_growth_yoy"] = round((rev - prev_rev) / abs(prev_rev), 4)
            if prev_ni and prev_ni != 0:
                feat["earnings_growth_yoy"] = round((ni - prev_ni) / abs(prev_ni), 4)
            if prev_fcf and prev_fcf != 0:
                feat["fcf_growth_yoy"] = round(((ocf - capex) - prev_fcf) / abs(prev_fcf), 4)

        prev = feat
        enriched.append(feat)

    # Compute CAGR over the full period
    if len(enriched) >= 2:
        first_rev = enriched[0].get("revenue", 0)
        last_rev = enriched[-1].get("revenue", 0)
        n = len(enriched) - 1
        if first_rev > 0 and last_rev > 0 and n > 0:
            cagr = (last_rev / first_rev) ** (1 / n) - 1
            for e in enriched:
                e["revenue_cagr"] = round(cagr, 4)

    return enriched


def compute_wacc(latest_record: dict, config: dict) -> dict:
    """Compute Weighted Average Cost of Capital (WACC) using CAPM."""
    rf = config.get("risk_free_rate", DEFAULT_CONFIG["risk_free_rate"])
    erp = config.get("equity_risk_premium", DEFAULT_CONFIG["equity_risk_premium"])
    tax_rate = config.get("tax_rate", DEFAULT_CONFIG["tax_rate"])

    beta = latest_record.get("beta") or 1.0
    market_cap = latest_record.get("market_cap", 0)
    total_debt = latest_record.get("total_debt") or (latest_record.get("total_liabilities", 0) * 0.5)
    cash = latest_record.get("cash_and_equivalents") or 0
    net_debt = total_debt - cash
    int_exp = latest_record.get("interest_expense") or 0

    # Cost of equity (CAPM): Re = Rf + beta * ERP
    cost_of_equity = rf + beta * erp

    # Cost of debt — synthetic rating approach (Damodaran method)
    # Estimate interest coverage ratio, derive synthetic rating, get default spread
    op_inc = latest_record.get("operating_income") or latest_record.get("ebitda", 0)
    if int_exp > 0 and op_inc > 0:
        coverage = op_inc / int_exp
    else:
        coverage = 100  # Effectively no debt

    # Synthetic rating default spreads (Damodaran, Jan 2026)
    # Maps interest coverage → default spread over risk-free rate
    if coverage > 12.5:
        default_spread = 0.0063   # AAA/AA
    elif coverage > 9.5:
        default_spread = 0.0088   # A+/A
    elif coverage > 7.5:
        default_spread = 0.0101   # A-
    elif coverage > 6.0:
        default_spread = 0.0115   # BBB+
    elif coverage > 4.5:
        default_spread = 0.0143   # BBB
    elif coverage > 4.0:
        default_spread = 0.0177   # BBB-
    elif coverage > 3.0:
        default_spread = 0.0217   # BB+
    elif coverage > 2.5:
        default_spread = 0.0267   # BB
    elif coverage > 2.0:
        default_spread = 0.0367   # B+
    elif coverage > 1.5:
        default_spread = 0.0467   # B
    elif coverage > 1.0:
        default_spread = 0.0667   # B-/CCC
    else:
        default_spread = 0.1067   # CC/D

    cost_of_debt = rf + default_spread

    # Capital structure weights — use market value of equity, book value of debt
    # Per Damodaran: D/(D+E) uses total debt (not net debt). Net debt only in EV→equity bridge.
    total_capital = market_cap + total_debt
    if total_capital > 0:
        weight_equity = market_cap / total_capital
        weight_debt = total_debt / total_capital
    else:
        weight_equity = 1.0
        weight_debt = 0.0

    wacc = weight_equity * cost_of_equity + weight_debt * cost_of_debt * (1 - tax_rate)

    return {
        "risk_free_rate": rf,
        "equity_risk_premium": erp,
        "beta": beta,
        "cost_of_equity": round(cost_of_equity, 4),
        "cost_of_debt": round(cost_of_debt, 4),
        "default_spread": round(default_spread, 4),
        "interest_coverage": round(coverage, 2),
        "tax_rate": tax_rate,
        "market_cap": round(market_cap, 2),
        "total_debt": round(total_debt, 2),
        "net_debt": round(net_debt, 2),
        "weight_equity": round(weight_equity, 4),
        "weight_debt": round(weight_debt, 4),
        "wacc": round(wacc, 4),
    }


def project_cash_flows(records: list, wacc_data: dict, config: dict) -> dict:
    """Project future free cash flows for DCF model.

    Uses a revenue-driven projection approach (industry standard):
    1. Project revenue using the best available growth rate
    2. Apply FCF margin to projected revenue
    This avoids the pitfall of directly extrapolating FCF, which can be
    distorted by lumpy capex cycles (e.g., AI data center buildouts).
    """
    projection_years = config.get("projection_years", DEFAULT_CONFIG["projection_years"])
    terminal_growth = config.get("terminal_growth_rate", DEFAULT_CONFIG["terminal_growth_rate"])
    wacc = wacc_data["wacc"]

    sorted_records = sorted(records, key=lambda r: r.get("fiscal_year", 0))
    recent = sorted_records[-1]
    latest_fcf = recent.get("fcff", 0)
    latest_revenue = recent.get("revenue", 0) or 1
    latest_ebitda = recent.get("ebitda", 0) or latest_revenue * 0.2

    # --- Compute multiple growth rate estimates and pick the best ---

    # 1. Revenue CAGR (most stable, least distorted by capex cycles)
    rev_values = [r.get("revenue") for r in sorted_records if r.get("revenue") and r["revenue"] > 0]
    if len(rev_values) >= 2:
        n = len(rev_values) - 1
        revenue_cagr = (rev_values[-1] / rev_values[0]) ** (1 / n) - 1
    else:
        revenue_cagr = 0.05

    # 2. Earnings (net income) CAGR
    ni_values = [r.get("net_income") for r in sorted_records if r.get("net_income") and r["net_income"] > 0]
    if len(ni_values) >= 2:
        n = len(ni_values) - 1
        earnings_cagr = (ni_values[-1] / ni_values[0]) ** (1 / n) - 1
    else:
        earnings_cagr = revenue_cagr

    # 3. EBITDA CAGR (less affected by capex than FCF, more operative than net income)
    ebitda_values = [r.get("ebitda") for r in sorted_records if r.get("ebitda") and r["ebitda"] > 0]
    if len(ebitda_values) >= 2:
        n = len(ebitda_values) - 1
        ebitda_cagr = (ebitda_values[-1] / ebitda_values[0]) ** (1 / n) - 1
    else:
        ebitda_cagr = revenue_cagr

    # 4. FCF CAGR (can be distorted by capex cycles — used as one input, not sole driver)
    fcf_values = [r.get("fcff") for r in sorted_records if r.get("fcff") is not None and r["fcff"] > 0]
    if len(fcf_values) >= 2:
        n = len(fcf_values) - 1
        fcf_cagr = (fcf_values[-1] / fcf_values[0]) ** (1 / n) - 1
    else:
        fcf_cagr = revenue_cagr

    # Use the MEDIAN of all available growth rates to dampen outliers
    # (e.g., if capex spike depresses FCF CAGR, revenue/earnings compensate)
    growth_candidates = sorted([revenue_cagr, earnings_cagr, ebitda_cagr, fcf_cagr])
    # Median of 4 values = average of middle 2
    base_growth = (growth_candidates[1] + growth_candidates[2]) / 2

    # Cap at reasonable bounds
    base_growth = max(-0.05, min(0.30, base_growth))

    # --- Revenue-driven FCF projection ---
    # Compute average FCF margin over recent years (smooths capex lumpiness)
    fcf_margins = []
    for r in sorted_records[-3:]:  # Last 3 years
        rev = r.get("revenue", 0)
        fcf = r.get("fcff", 0)
        if rev and rev > 0:
            fcf_margins.append(fcf / rev)

    if fcf_margins:
        # Use the average FCF margin, but floor at half the latest margin
        # to avoid penalizing companies in a capex investment phase
        avg_fcf_margin = sum(fcf_margins) / len(fcf_margins)
        latest_fcf_margin = fcf_margins[-1] if fcf_margins else 0.1
        # For companies in heavy capex phases, margins should recover
        # Use the higher of average and a conservative recovery estimate
        projected_fcf_margin = max(avg_fcf_margin, latest_fcf_margin)
    else:
        projected_fcf_margin = 0.15  # Default 15% FCF margin

    # Project using concave decay: growth fades slowly at first, faster later
    # This better models how high-growth companies sustain growth before maturing
    projections = []
    revenue = latest_revenue
    for year in range(1, projection_years + 1):
        # Concave decay: (year/n)^1.5 instead of linear (year/n)
        blend = (year / projection_years) ** 1.5
        growth = base_growth * (1 - blend) + terminal_growth * blend
        revenue = revenue * (1 + growth)
        fcf = revenue * projected_fcf_margin
        discount_factor = 1 / ((1 + wacc) ** year)
        pv = fcf * discount_factor
        projections.append({
            "year": year,
            "growth_rate": round(growth, 4),
            "projected_fcf": round(fcf, 2),
            "discount_factor": round(discount_factor, 4),
            "present_value": round(pv, 2),
        })

    # Terminal value — Gordon Growth
    final_fcf = projections[-1]["projected_fcf"]
    if wacc > terminal_growth:
        tv_gordon = final_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    else:
        tv_gordon = final_fcf * 20  # Fallback: 20x terminal FCF

    tv_gordon_pv = tv_gordon / ((1 + wacc) ** projection_years)

    # Terminal value — Exit Multiple
    # Per CFI/Damodaran: use PEER MEDIAN EV/EBITDA, not the target's own multiple
    # (using target's own multiple is circular — it just recreates current market cap)
    exit_multiple = config.get("exit_ev_ebitda_multiple") or 12.0
    # Project EBITDA using same revenue growth + EBITDA margin
    ebitda_margin = latest_ebitda / latest_revenue if latest_revenue > 0 else 0.2
    final_ebitda_proj = revenue * ebitda_margin  # revenue is already projected at end
    tv_exit = final_ebitda_proj * exit_multiple
    tv_exit_pv = tv_exit / ((1 + wacc) ** projection_years)

    sum_pv_fcf = sum(p["present_value"] for p in projections)

    return {
        "latest_fcf": round(latest_fcf, 2),
        "base_growth_rate": round(base_growth, 4),
        "growth_components": {
            "revenue_cagr": round(revenue_cagr, 4),
            "earnings_cagr": round(earnings_cagr, 4),
            "ebitda_cagr": round(ebitda_cagr, 4),
            "fcf_cagr": round(fcf_cagr, 4),
            "selected_method": "median of all four CAGRs",
        },
        "projected_fcf_margin": round(projected_fcf_margin, 4),
        "projection_years": projection_years,
        "terminal_growth_rate": terminal_growth,
        "projections": projections,
        "terminal_value_gordon": round(tv_gordon, 2),
        "terminal_value_gordon_pv": round(tv_gordon_pv, 2),
        "terminal_value_exit_multiple": round(tv_exit, 2),
        "terminal_value_exit_pv": round(tv_exit_pv, 2),
        "exit_ev_ebitda_multiple": round(exit_multiple, 2),
        "sum_pv_fcf": round(sum_pv_fcf, 2),
    }


def compute_peer_multiples(peer_data: list) -> dict:
    """Compute CCA multiples from peer company data."""
    multiples = {
        "ev_ebitda": [], "ev_revenue": [], "pe_ratio": [], "pb_ratio": [],
    }
    peer_details = []

    for peer in peer_data:
        records = peer.get("records", [])
        if not records:
            continue
        # Use the most recent year
        latest = sorted(records, key=lambda r: r.get("fiscal_year", 0))[-1]
        # Compute features for peer
        enriched = compute_ratios(records)
        if not enriched:
            continue
        latest_feat = enriched[-1]

        detail = {
            "ticker": peer.get("ticker"),
            "company_name": peer.get("company_name"),
        }

        for mult_name in multiples:
            val = latest_feat.get(mult_name)
            if val is not None and val > 0:
                multiples[mult_name].append(val)
                detail[mult_name] = val

        peer_details.append(detail)

    # Compute statistics
    stats = {}
    for mult_name, values in multiples.items():
        if values:
            sorted_vals = sorted(values)
            stats[mult_name] = {
                "values": [round(v, 2) for v in sorted_vals],
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "mean": round(sum(values) / len(values), 2),
                "median": round(sorted_vals[len(sorted_vals) // 2], 2),
                "count": len(values),
            }

    return {
        "peer_details": peer_details,
        "multiple_stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compute financial features for company valuation"
    )
    parser.add_argument(
        "--input", required=True, help="Input financials JSON (from fetch_data.py)"
    )
    parser.add_argument(
        "--config", default=None, help="Optional config JSON with analysis parameters"
    )
    parser.add_argument(
        "--output", default="data/features.json", help="Output features JSON"
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r") as f:
        data = json.load(f)

    # Load config
    config = dict(DEFAULT_CONFIG)
    if args.config and os.path.exists(args.config):
        with open(args.config, "r") as f:
            user_config = json.load(f)
            config.update(user_config)

    # Compute target features
    target = data.get("target", {})
    target_records = target.get("records", [])
    target_features = compute_ratios(target_records)

    if not target_features:
        print("ERROR: No target company features could be computed.")
        sys.exit(1)

    latest = target_features[-1]

    # Compute WACC
    wacc_data = compute_wacc(latest, config)

    # Check terminal growth < WACC
    tg = config.get("terminal_growth_rate", DEFAULT_CONFIG["terminal_growth_rate"])
    if tg >= wacc_data["wacc"]:
        print(f"WARNING: Terminal growth rate ({tg:.2%}) >= WACC ({wacc_data['wacc']:.2%}). "
              f"Adjusting terminal growth to {wacc_data['wacc'] - 0.01:.2%}")
        config["terminal_growth_rate"] = wacc_data["wacc"] - 0.01

    # Compute peer multiples
    peers = data.get("peers", [])
    peer_multiples = compute_peer_multiples(peers)

    # Set exit multiple to peer median EV/EBITDA (avoids circular valuation)
    peer_ev_ebitda = peer_multiples.get("multiple_stats", {}).get("ev_ebitda", {})
    if peer_ev_ebitda and "median" in peer_ev_ebitda:
        config["exit_ev_ebitda_multiple"] = peer_ev_ebitda["median"]
        print(f"  Exit EV/EBITDA multiple (peer median): {peer_ev_ebitda['median']:.1f}x")
    else:
        config.setdefault("exit_ev_ebitda_multiple", 12.0)

    # Project cash flows (needs peer median for exit multiple)
    dcf_projections = project_cash_flows(target_features, wacc_data, config)

    # Assemble output
    output = {
        "config": config,
        "target": {
            "ticker": target.get("ticker"),
            "company_name": target.get("company_name"),
            "sector": target.get("sector"),
            "features": target_features,
            "latest": latest,
        },
        "wacc": wacc_data,
        "dcf_projections": dcf_projections,
        "peer_multiples": peer_multiples,
        "precedent_transactions": data.get("precedent_transactions", []),
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Feature engineering complete.")
    print(f"  Target: {target.get('company_name')} ({target.get('ticker')})")
    print(f"  Years: {len(target_features)}")
    print(f"  WACC: {wacc_data['wacc']:.2%}")
    print(f"  Latest FCF: ${dcf_projections['latest_fcf']:,.0f}")
    print(f"  Peers with multiples: {len(peer_multiples.get('peer_details', []))}")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
