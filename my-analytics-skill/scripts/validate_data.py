#!/usr/bin/env python3
"""
validate_data.py — Data profiling and validation for the Company Valuation Skill.

Profiles the incoming financial dataset, checks quality thresholds, and rejects
malformed data with clear error messages.

Usage:
    python scripts/validate_data.py --input data/raw/financials.json --output data/validation_report.json
"""

import argparse
import json
import os
import sys
from collections import defaultdict


REQUIRED_COLUMNS = [
    "ticker", "fiscal_year", "revenue", "cost_of_revenue", "operating_income",
    "net_income", "total_assets", "total_liabilities", "total_equity",
    "operating_cash_flow", "capex", "shares_outstanding", "stock_price",
]

NUMERIC_COLUMNS = [
    "revenue", "cost_of_revenue", "operating_income", "net_income",
    "total_assets", "total_liabilities", "total_equity",
    "operating_cash_flow", "capex", "shares_outstanding", "stock_price",
]

POSITIVE_REQUIRED = ["revenue", "total_assets", "shares_outstanding", "stock_price"]

MIN_YEARS = 3
MIN_PEERS = 3
BALANCE_SHEET_TOLERANCE = 0.05  # 5%
MAX_NULL_PCT = 0.30  # 30%


def profile_records(records: list, label: str) -> dict:
    """Compute data profiling statistics for a list of financial records."""
    if not records:
        return {"error": f"No records found for {label}"}

    num_records = len(records)
    years = sorted(set(r.get("fiscal_year") for r in records if r.get("fiscal_year")))

    profile = {
        "label": label,
        "row_count": num_records,
        "years_covered": years,
        "year_range": f"{min(years)}–{max(years)}" if years else "N/A",
        "year_count": len(years),
        "columns": {},
    }

    # Profile each column
    all_keys = set()
    for r in records:
        all_keys.update(r.keys())

    for col in sorted(all_keys):
        values = [r.get(col) for r in records]
        non_null = [v for v in values if v is not None]
        null_count = len(values) - len(non_null)
        null_pct = null_count / len(values) if values else 0

        col_profile = {
            "null_count": null_count,
            "null_pct": round(null_pct * 100, 1),
            "non_null_count": len(non_null),
        }

        numeric_vals = []
        for v in non_null:
            try:
                numeric_vals.append(float(v))
            except (ValueError, TypeError):
                pass

        if numeric_vals:
            col_profile.update({
                "type": "numeric",
                "min": round(min(numeric_vals), 2),
                "max": round(max(numeric_vals), 2),
                "mean": round(sum(numeric_vals) / len(numeric_vals), 2),
                "median": round(sorted(numeric_vals)[len(numeric_vals) // 2], 2),
            })
        else:
            unique = set(str(v) for v in non_null)
            col_profile.update({
                "type": "categorical",
                "unique_values": len(unique),
                "sample_values": list(unique)[:5],
            })

        profile["columns"][col] = col_profile

    return profile


def validate_company(records: list, label: str, is_target: bool = False) -> list:
    """Run validation checks on a single company's records. Returns list of issues."""
    issues = []

    if not records:
        issues.append({
            "severity": "ERROR",
            "check": "data_exists",
            "message": f"No records found for {label}",
            "fix": "Ensure the data source contains valid financial data for this company.",
        })
        return issues

    # Check required columns
    for col in REQUIRED_COLUMNS:
        nulls = sum(1 for r in records if r.get(col) is None)
        if nulls == len(records):
            issues.append({
                "severity": "ERROR",
                "check": f"required_column_{col}",
                "message": f"Column '{col}' is entirely missing/null for {label}",
                "fix": f"Ensure the dataset includes '{col}' with valid values for all fiscal years.",
            })
        elif nulls > 0:
            pct = nulls / len(records)
            sev = "ERROR" if pct > MAX_NULL_PCT else "WARNING"
            issues.append({
                "severity": sev,
                "check": f"null_pct_{col}",
                "message": f"{label}: '{col}' has {nulls}/{len(records)} null values ({pct:.0%})",
                "fix": f"Fill missing '{col}' values or use a more complete data source.",
            })

    # Check positive-required fields
    for col in POSITIVE_REQUIRED:
        for r in records:
            val = r.get(col)
            if val is not None and val <= 0:
                issues.append({
                    "severity": "ERROR",
                    "check": f"positive_{col}",
                    "message": f"{label} FY{r.get('fiscal_year')}: '{col}' = {val} (must be > 0)",
                    "fix": f"Verify '{col}' data — negative or zero values are invalid.",
                })
                break  # Report once per column

    # Check minimum years for target
    years = sorted(set(r.get("fiscal_year") for r in records if r.get("fiscal_year")))
    if is_target and len(years) < MIN_YEARS:
        issues.append({
            "severity": "ERROR",
            "check": "min_years",
            "message": f"{label}: Only {len(years)} years of data (minimum {MIN_YEARS} required for DCF)",
            "fix": f"Provide at least {MIN_YEARS} years of historical financial data.",
        })

    # Check year gaps
    for i in range(1, len(years)):
        gap = years[i] - years[i - 1]
        if gap > 2:
            issues.append({
                "severity": "WARNING",
                "check": "year_gap",
                "message": f"{label}: Gap of {gap} years between FY{years[i-1]} and FY{years[i]}",
                "fix": "Large gaps may affect growth rate calculations. Fill or acknowledge gaps.",
            })

    # Balance sheet identity check
    for r in records:
        ta = r.get("total_assets")
        tl = r.get("total_liabilities")
        te = r.get("total_equity")
        if ta is not None and tl is not None and te is not None and ta > 0:
            diff = abs(ta - (tl + te)) / ta
            if diff > BALANCE_SHEET_TOLERANCE:
                issues.append({
                    "severity": "WARNING",
                    "check": "balance_sheet_identity",
                    "message": (
                        f"{label} FY{r.get('fiscal_year')}: "
                        f"|Assets − (Liabilities + Equity)| / Assets = {diff:.1%} "
                        f"(threshold: {BALANCE_SHEET_TOLERANCE:.0%})"
                    ),
                    "fix": "Check balance sheet data consistency. Minor differences may be due to rounding.",
                })
                break  # Report once

    return issues


def validate_dataset(data: dict) -> dict:
    """Run full validation on the entire dataset (target + peers + transactions)."""
    report = {
        "status": "PASS",
        "summary": {},
        "target_profile": None,
        "peer_profiles": [],
        "issues": [],
        "error_count": 0,
        "warning_count": 0,
    }

    # Validate target
    target = data.get("target", {})
    target_records = target.get("records", [])
    target_label = f"{target.get('company_name', 'Unknown')} ({target.get('ticker', '?')})"

    report["target_profile"] = profile_records(target_records, target_label)
    target_issues = validate_company(target_records, target_label, is_target=True)
    report["issues"].extend(target_issues)

    # Validate peers
    peers = data.get("peers", [])
    if len(peers) < MIN_PEERS:
        report["issues"].append({
            "severity": "ERROR",
            "check": "min_peers",
            "message": f"Only {len(peers)} peer companies provided (minimum {MIN_PEERS} required for CCA)",
            "fix": f"Add at least {MIN_PEERS} peer companies for Comparable Company Analysis.",
        })

    for peer in peers:
        peer_records = peer.get("records", [])
        peer_label = f"{peer.get('company_name', 'Unknown')} ({peer.get('ticker', '?')})"
        report["peer_profiles"].append(profile_records(peer_records, peer_label))
        peer_issues = validate_company(peer_records, peer_label, is_target=False)
        report["issues"].extend(peer_issues)

    # Validate precedent transactions
    transactions = data.get("precedent_transactions", [])
    if not transactions:
        report["issues"].append({
            "severity": "WARNING",
            "check": "precedent_transactions",
            "message": "No precedent transaction data available",
            "fix": "Precedent Transaction analysis will use sector benchmarks instead.",
        })

    # Count errors and warnings
    report["error_count"] = sum(1 for i in report["issues"] if i["severity"] == "ERROR")
    report["warning_count"] = sum(1 for i in report["issues"] if i["severity"] == "WARNING")

    if report["error_count"] > 0:
        report["status"] = "FAIL"
    elif report["warning_count"] > 0:
        report["status"] = "PASS_WITH_WARNINGS"

    report["summary"] = {
        "status": report["status"],
        "target": target_label,
        "target_years": len(target_records),
        "peer_count": len(peers),
        "transaction_count": len(transactions),
        "errors": report["error_count"],
        "warnings": report["warning_count"],
    }

    return report


def main():
    parser = argparse.ArgumentParser(description="Validate financial data for valuation pipeline")
    parser.add_argument(
        "--input", required=True, help="Input JSON file (from fetch_data.py or generate_synthetic_data.py)"
    )
    parser.add_argument(
        "--output", default="data/validation_report.json", help="Output validation report JSON"
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(json.dumps({
            "status": "FAIL",
            "error": f"Input file not found: {args.input}",
            "fix": "Run fetch_data.py or generate_synthetic_data.py first to create the input data.",
        }, indent=2))
        sys.exit(1)

    with open(args.input, "r") as f:
        data = json.load(f)

    report = validate_dataset(data)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    s = report["summary"]
    print(f"Validation Result: {s['status']}")
    print(f"  Target: {s['target']} ({s['target_years']} years)")
    print(f"  Peers: {s['peer_count']} companies")
    print(f"  Transactions: {s['transaction_count']}")
    print(f"  Errors: {s['errors']}, Warnings: {s['warnings']}")

    if report["issues"]:
        print("\nIssues:")
        for issue in report["issues"]:
            print(f"  [{issue['severity']}] {issue['message']}")

    if s["status"] == "FAIL":
        print("\nValidation FAILED. Fix errors above before proceeding to analysis.")
        sys.exit(1)
    else:
        print(f"\nValidation report saved to {args.output}")


if __name__ == "__main__":
    main()
