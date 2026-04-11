#!/usr/bin/env python3
"""
run_models.py — Execute three valuation models and cross-validate results.

Models:
  1. Discounted Cash Flow (DCF) — Gordon Growth + Exit Multiple terminal value
  2. Comparable Company Analysis (CCA) — Peer median multiples
  3. Precedent Transactions — Historical M&A multiples with control premium

Usage:
    python scripts/run_models.py --input data/features.json --output data/valuation_results.json
"""

import argparse
import json
import os
import sys

import numpy as np


SEED = 42


def run_dcf_model(features: dict) -> dict:
    """
    Discounted Cash Flow Valuation.

    Computes Enterprise Value from projected FCFs + terminal value,
    then derives equity value per share. Includes sensitivity analysis.
    """
    wacc_data = features["wacc"]
    proj = features["dcf_projections"]
    latest = features["target"]["latest"]

    wacc = wacc_data["wacc"]
    net_debt = wacc_data["net_debt"]
    shares = latest.get("shares_outstanding", 1)

    # Gordon Growth terminal value
    ev_gordon = proj["sum_pv_fcf"] + proj["terminal_value_gordon_pv"]
    equity_gordon = ev_gordon - net_debt
    price_gordon = equity_gordon / shares if shares > 0 else 0

    # Exit Multiple terminal value
    ev_exit = proj["sum_pv_fcf"] + proj["terminal_value_exit_pv"]
    equity_exit = ev_exit - net_debt
    price_exit = equity_exit / shares if shares > 0 else 0

    # Blended (average of both methods)
    ev_blended = (ev_gordon + ev_exit) / 2
    equity_blended = ev_blended - net_debt
    price_blended = equity_blended / shares if shares > 0 else 0

    # Sensitivity analysis: WACC ±2% × terminal growth ±1%
    tg_base = proj["terminal_growth_rate"]
    sensitivity = []
    wacc_range = [round(wacc + delta, 4) for delta in [-0.02, -0.01, 0, 0.01, 0.02]]
    tg_range = [round(tg_base + delta, 4) for delta in [-0.01, -0.005, 0, 0.005, 0.01]]

    for w in wacc_range:
        row = {"wacc": round(w, 4), "values": {}}
        for g in tg_range:
            if w <= g or w <= 0:
                row["values"][str(round(g, 4))] = None
                continue
            # Recompute terminal value with different WACC and growth
            final_fcf = proj["projections"][-1]["projected_fcf"]
            tv = final_fcf * (1 + g) / (w - g)
            n = proj["projection_years"]
            tv_pv = tv / ((1 + w) ** n)
            # Recompute PV of projected FCFs with new WACC
            sum_pv = sum(
                p["projected_fcf"] / ((1 + w) ** p["year"])
                for p in proj["projections"]
            )
            ev_sens = sum_pv + tv_pv
            eq_sens = ev_sens - net_debt
            price_sens = eq_sens / shares if shares > 0 else 0
            row["values"][str(round(g, 4))] = round(price_sens, 2)
        sensitivity.append(row)

    # Flag negative FCF
    warnings = []
    if proj["latest_fcf"] < 0:
        warnings.append(
            "Target company has negative free cash flow. DCF valuation may be unreliable. "
            "Consider relying more on CCA and Precedent Transaction methods."
        )

    return {
        "method": "DCF",
        "gordon_growth": {
            "enterprise_value": round(ev_gordon, 2),
            "equity_value": round(equity_gordon, 2),
            "price_per_share": round(price_gordon, 2),
        },
        "exit_multiple": {
            "enterprise_value": round(ev_exit, 2),
            "equity_value": round(equity_exit, 2),
            "price_per_share": round(price_exit, 2),
            "exit_ev_ebitda": proj["exit_ev_ebitda_multiple"],
        },
        "blended": {
            "enterprise_value": round(ev_blended, 2),
            "equity_value": round(equity_blended, 2),
            "price_per_share": round(price_blended, 2),
        },
        "wacc": wacc_data,
        "projections": proj["projections"],
        "terminal_growth_rate": tg_base,
        "sensitivity": {
            "wacc_range": [round(w, 4) for w in wacc_range],
            "growth_range": [round(g, 4) for g in tg_range],
            "matrix": sensitivity,
        },
        "value_range": {
            "low": round(min(price_gordon, price_exit), 2),
            "mid": round(price_blended, 2),
            "high": round(max(price_gordon, price_exit), 2),
        },
        "warnings": warnings,
    }


def run_cca_model(features: dict) -> dict:
    """
    Comparable Company Analysis.

    Applies peer median multiples to target's financial metrics
    to derive implied equity value per share.
    """
    peer_data = features["peer_multiples"]
    latest = features["target"]["latest"]
    wacc_data = features["wacc"]

    shares = latest.get("shares_outstanding", 1)
    net_debt = wacc_data["net_debt"]
    stats = peer_data.get("multiple_stats", {})

    implied_values = {}
    all_prices = []

    # EV/EBITDA
    if "ev_ebitda" in stats and latest.get("ebitda", 0) > 0:
        ebitda = latest["ebitda"]
        s = stats["ev_ebitda"]
        for level in ["min", "median", "max"]:
            ev = ebitda * s[level]
            eq = ev - net_debt
            price = eq / shares if shares > 0 else 0
            implied_values.setdefault("ev_ebitda", {})[level] = {
                "multiple": s[level],
                "implied_ev": round(ev, 2),
                "implied_equity": round(eq, 2),
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # EV/Revenue
    if "ev_revenue" in stats and latest.get("revenue", 0) > 0:
        revenue = latest["revenue"]
        s = stats["ev_revenue"]
        for level in ["min", "median", "max"]:
            ev = revenue * s[level]
            eq = ev - net_debt
            price = eq / shares if shares > 0 else 0
            implied_values.setdefault("ev_revenue", {})[level] = {
                "multiple": s[level],
                "implied_ev": round(ev, 2),
                "implied_equity": round(eq, 2),
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # P/E
    if "pe_ratio" in stats and latest.get("eps", 0) > 0:
        eps = latest["eps"]
        s = stats["pe_ratio"]
        for level in ["min", "median", "max"]:
            price = eps * s[level]
            implied_values.setdefault("pe_ratio", {})[level] = {
                "multiple": s[level],
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # P/B
    if "pb_ratio" in stats and latest.get("book_value_per_share", 0) > 0:
        bvps = latest["book_value_per_share"]
        s = stats["pb_ratio"]
        for level in ["min", "median", "max"]:
            price = bvps * s[level]
            implied_values.setdefault("pb_ratio", {})[level] = {
                "multiple": s[level],
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # Compute range from median multiples
    median_prices = []
    for mult_name, levels in implied_values.items():
        if "median" in levels:
            median_prices.append(levels["median"]["implied_price"])

    value_range = {}
    if all_prices:
        valid_prices = sorted([p for p in all_prices if p > 0])
        if valid_prices:
            # Use 25th-75th percentile (IQR) to exclude outliers like extreme P/B
            low = round(float(np.percentile(valid_prices, 25)), 2)
            high = round(float(np.percentile(valid_prices, 75)), 2)
            mid = round(float(np.median(median_prices)), 2) if median_prices else round(float(np.median(valid_prices)), 2)
            value_range = {
                "low": low,
                "mid": mid,
                "high": high,
                "full_min": round(min(valid_prices), 2),
                "full_max": round(max(valid_prices), 2),
            }

    return {
        "method": "CCA",
        "peer_details": peer_data.get("peer_details", []),
        "multiple_stats": stats,
        "implied_values": implied_values,
        "value_range": value_range,
        "warnings": [],
    }


def run_precedent_transactions_model(features: dict) -> dict:
    """
    Precedent Transactions Analysis.

    Applies M&A transaction multiples to target metrics,
    including implied control premium.
    """
    transactions = features.get("precedent_transactions", [])
    latest = features["target"]["latest"]
    wacc_data = features["wacc"]

    shares = latest.get("shares_outstanding", 1)
    net_debt = wacc_data["net_debt"]

    if not transactions:
        return {
            "method": "Precedent Transactions",
            "transactions": [],
            "implied_values": {},
            "value_range": {},
            "warnings": ["No precedent transaction data available. Skipping this method."],
        }

    # Extract transaction multiples
    ev_rev_multiples = [t["ev_revenue_multiple"] for t in transactions if t.get("ev_revenue_multiple")]
    ev_ebitda_multiples = [t["ev_ebitda_multiple"] for t in transactions if t.get("ev_ebitda_multiple")]
    premiums = [t["premium_paid"] for t in transactions if t.get("premium_paid") is not None]

    implied_values = {}
    all_prices = []

    # EV/Revenue from transactions
    if ev_rev_multiples and latest.get("revenue", 0) > 0:
        revenue = latest["revenue"]
        sorted_m = sorted(ev_rev_multiples)
        for label, val in [("min", min(sorted_m)), ("median", sorted_m[len(sorted_m)//2]), ("max", max(sorted_m))]:
            ev = revenue * val
            eq = ev - net_debt
            price = eq / shares if shares > 0 else 0
            implied_values.setdefault("ev_revenue_txn", {})[label] = {
                "multiple": round(val, 2),
                "implied_ev": round(ev, 2),
                "implied_equity": round(eq, 2),
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # EV/EBITDA from transactions
    if ev_ebitda_multiples and latest.get("ebitda", 0) > 0:
        ebitda = latest["ebitda"]
        sorted_m = sorted(ev_ebitda_multiples)
        for label, val in [("min", min(sorted_m)), ("median", sorted_m[len(sorted_m)//2]), ("max", max(sorted_m))]:
            ev = ebitda * val
            eq = ev - net_debt
            price = eq / shares if shares > 0 else 0
            implied_values.setdefault("ev_ebitda_txn", {})[label] = {
                "multiple": round(val, 2),
                "implied_ev": round(ev, 2),
                "implied_equity": round(eq, 2),
                "implied_price": round(price, 2),
            }
            all_prices.append(price)

    # Average control premium
    avg_premium = round(np.mean(premiums), 1) if premiums else 30.0

    # Value range
    median_prices = []
    for mult_name, levels in implied_values.items():
        if "median" in levels:
            median_prices.append(levels["median"]["implied_price"])

    value_range = {}
    if all_prices:
        valid = sorted([p for p in all_prices if p > 0])
        if valid:
            # Use 25th-75th percentile (IQR) to exclude outlier transaction multiples
            low = round(float(np.percentile(valid, 25)), 2)
            high = round(float(np.percentile(valid, 75)), 2)
            mid = round(float(np.median(median_prices)), 2) if median_prices else round(float(np.median(valid)), 2)
            value_range = {
                "low": low,
                "mid": mid,
                "high": high,
                "full_min": round(min(valid), 2),
                "full_max": round(max(valid), 2),
            }

    return {
        "method": "Precedent Transactions",
        "transactions": transactions,
        "transaction_multiples": {
            "ev_revenue": {
                "values": [round(v, 2) for v in sorted(ev_rev_multiples)] if ev_rev_multiples else [],
                "median": round(sorted(ev_rev_multiples)[len(ev_rev_multiples)//2], 2) if ev_rev_multiples else None,
            },
            "ev_ebitda": {
                "values": [round(v, 2) for v in sorted(ev_ebitda_multiples)] if ev_ebitda_multiples else [],
                "median": round(sorted(ev_ebitda_multiples)[len(ev_ebitda_multiples)//2], 2) if ev_ebitda_multiples else None,
            },
        },
        "average_control_premium_pct": avg_premium,
        "implied_values": implied_values,
        "value_range": value_range,
        "warnings": [],
    }


def cross_validate(dcf: dict, cca: dict, pt: dict, current_price: float) -> dict:
    """
    Cross-validate results from all three valuation methods.
    Produce a combined recommendation with confidence assessment.
    """
    ranges = []
    method_summary = []

    for model in [dcf, cca, pt]:
        vr = model.get("value_range", {})
        if vr and vr.get("mid"):
            ranges.append(vr)
            method_summary.append({
                "method": model["method"],
                "low": vr.get("low", 0),
                "mid": vr.get("mid", 0),
                "high": vr.get("high", 0),
            })

    if not ranges:
        return {
            "status": "ERROR",
            "message": "No valuation methods produced valid results.",
        }

    # Overall range
    all_mids = [r["mid"] for r in ranges]
    all_lows = [r["low"] for r in ranges]
    all_highs = [r["high"] for r in ranges]

    overall_low = round(min(all_lows), 2)
    overall_mid = round(np.mean(all_mids), 2)
    overall_high = round(max(all_highs), 2)
    # Recommended range = 25th to 75th percentile of all mid values
    if len(all_mids) >= 3:
        recommended_low = round(np.percentile(all_mids, 25), 2)
        recommended_high = round(np.percentile(all_mids, 75), 2)
    else:
        recommended_low = round(min(all_mids) * 0.95, 2)
        recommended_high = round(max(all_mids) * 1.05, 2)

    # Divergence check
    if len(all_mids) >= 2:
        max_mid = max(all_mids)
        min_mid = min(all_mids)
        divergence_pct = ((max_mid - min_mid) / min_mid * 100) if min_mid > 0 else 999
    else:
        divergence_pct = 0

    # Confidence
    if divergence_pct < 20:
        confidence = "HIGH"
        confidence_note = "All valuation methods converge within 20%. High conviction in fair value estimate."
    elif divergence_pct < 50:
        confidence = "MODERATE"
        confidence_note = f"Methods diverge by {divergence_pct:.0f}%. Consider which assumptions drive the spread."
    else:
        confidence = "LOW"
        confidence_note = f"Methods diverge by {divergence_pct:.0f}%. Significant uncertainty — review key assumptions."

    # Verdict vs current price
    if current_price > 0 and overall_mid > 0:
        upside = (overall_mid - current_price) / current_price
        if upside > 0.20:
            verdict = "UNDERVALUED"
            recommendation = "BUY"
        elif upside > 0.05:
            verdict = "SLIGHTLY UNDERVALUED"
            recommendation = "BUY"
        elif upside > -0.05:
            verdict = "FAIRLY VALUED"
            recommendation = "HOLD"
        elif upside > -0.20:
            verdict = "SLIGHTLY OVERVALUED"
            recommendation = "SELL"
        else:
            verdict = "OVERVALUED"
            recommendation = "SELL"
        implied_upside_pct = round(upside * 100, 1)
    else:
        verdict = "N/A"
        recommendation = "N/A"
        implied_upside_pct = None

    # Collect warnings from all methods
    all_warnings = dcf.get("warnings", []) + cca.get("warnings", []) + pt.get("warnings", [])

    return {
        "method_summary": method_summary,
        "overall_range": {
            "low": overall_low,
            "mid": overall_mid,
            "high": overall_high,
        },
        "recommended_range": {
            "low": recommended_low,
            "high": recommended_high,
        },
        "current_price": round(current_price, 2),
        "implied_upside_pct": implied_upside_pct,
        "verdict": verdict,
        "recommendation": recommendation,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "divergence_pct": round(divergence_pct, 1),
        "all_warnings": all_warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Run three valuation models and cross-validate")
    parser.add_argument("--input", required=True, help="Input features JSON (from feature_engineering.py)")
    parser.add_argument("--output", default="data/valuation_results.json", help="Output results JSON")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        sys.exit(1)

    np.random.seed(SEED)

    with open(args.input, "r") as f:
        features = json.load(f)

    latest = features["target"]["latest"]
    current_price = latest.get("stock_price", 0)
    ticker = features["target"].get("ticker", "UNKNOWN")
    company = features["target"].get("company_name", "Unknown")

    print(f"Running valuation models for {company} ({ticker})...")
    print(f"  Current price: ${current_price:,.2f}")

    # Run all three models
    print("  [1/3] DCF Valuation...")
    dcf_result = run_dcf_model(features)
    print(f"        DCF range: ${dcf_result['value_range'].get('low', 0):,.2f} – ${dcf_result['value_range'].get('high', 0):,.2f}")

    print("  [2/3] Comparable Company Analysis...")
    cca_result = run_cca_model(features)
    vr = cca_result.get("value_range", {})
    if vr:
        print(f"        CCA range: ${vr.get('low', 0):,.2f} – ${vr.get('high', 0):,.2f}")

    print("  [3/3] Precedent Transactions...")
    pt_result = run_precedent_transactions_model(features)
    vr = pt_result.get("value_range", {})
    if vr:
        print(f"        PT range:  ${vr.get('low', 0):,.2f} – ${vr.get('high', 0):,.2f}")

    # Cross-validate
    print("  Cross-validating...")
    validation = cross_validate(dcf_result, cca_result, pt_result, current_price)

    # Assemble output
    output = {
        "target": {
            "ticker": ticker,
            "company_name": company,
            "sector": features["target"].get("sector"),
            "current_price": current_price,
            "shares_outstanding": latest.get("shares_outstanding"),
        },
        "config": features.get("config", {}),
        "features": features["target"]["features"],
        "dcf": dcf_result,
        "cca": cca_result,
        "precedent_transactions": pt_result,
        "cross_validation": validation,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    # Summary
    print(f"\n{'='*60}")
    print(f"  VALUATION SUMMARY: {company} ({ticker})")
    print(f"{'='*60}")
    print(f"  Current Price:      ${current_price:,.2f}")
    print(f"  Fair Value (mid):   ${validation['overall_range']['mid']:,.2f}")
    print(f"  Range:              ${validation['overall_range']['low']:,.2f} – ${validation['overall_range']['high']:,.2f}")
    if validation.get("implied_upside_pct") is not None:
        print(f"  Implied Upside:     {validation['implied_upside_pct']:+.1f}%")
    print(f"  Verdict:            {validation['verdict']}")
    print(f"  Recommendation:     {validation['recommendation']}")
    print(f"  Confidence:         {validation['confidence']}")
    print(f"{'='*60}")
    print(f"\nResults saved to {args.output}")

    if validation.get("all_warnings"):
        print("\nWarnings:")
        for w in validation["all_warnings"]:
            print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
