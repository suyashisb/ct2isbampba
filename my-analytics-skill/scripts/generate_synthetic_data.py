#!/usr/bin/env python3
"""
generate_synthetic_data.py — Generate realistic synthetic financial statement data.

Creates synthetic but internally consistent financial data for testing the
valuation pipeline when live API data is unavailable.

Usage:
    python scripts/generate_synthetic_data.py --num-companies 5 --years 5 --sector Technology --output data/raw/financials.json
    python scripts/generate_synthetic_data.py --target-ticker SYNTH --peers PEER1,PEER2,PEER3 --output data/raw/financials.json
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np


SEED = 42


def generate_company_financials(
    ticker: str,
    company_name: str,
    sector: str,
    years: int,
    base_revenue: float,
    revenue_growth: float,
    gross_margin: float,
    operating_margin: float,
    net_margin: float,
    capex_pct: float,
    debt_equity: float,
    stock_price_base: float,
    shares_outstanding: float,
    rng: np.random.Generator,
) -> dict:
    """Generate internally consistent financial statements for one company."""
    records = []
    current_year = datetime.now().year - 1
    revenue = base_revenue

    for i in range(years):
        fy = current_year - (years - 1 - i)

        # Add noise to growth and margins
        yr_growth = revenue_growth + rng.normal(0, 0.02)
        if i > 0:
            revenue = revenue * (1 + yr_growth)

        yr_gross_margin = max(0.1, gross_margin + rng.normal(0, 0.015))
        yr_op_margin = max(0.02, min(yr_gross_margin - 0.05, operating_margin + rng.normal(0, 0.01)))
        yr_net_margin = max(0.01, min(yr_op_margin - 0.02, net_margin + rng.normal(0, 0.008)))

        cost_of_revenue = revenue * (1 - yr_gross_margin)
        operating_income = revenue * yr_op_margin
        net_income = revenue * yr_net_margin

        # Tax
        pre_tax_income = net_income / (1 - 0.21) if net_income > 0 else net_income * 1.2
        tax_provision = pre_tax_income - net_income if pre_tax_income > net_income else 0
        interest_expense = abs(rng.normal(0.02, 0.005)) * revenue * debt_equity * 0.3

        # Balance sheet
        total_assets = revenue * rng.uniform(1.5, 3.0)
        total_liabilities = total_assets * (debt_equity / (1 + debt_equity))
        total_equity = total_assets - total_liabilities
        total_debt = total_liabilities * rng.uniform(0.4, 0.7)
        cash = revenue * rng.uniform(0.05, 0.25)

        # Cash flow
        depreciation = revenue * rng.uniform(0.03, 0.08)
        ebitda = operating_income + depreciation
        operating_cf = net_income + depreciation + rng.normal(0, revenue * 0.02)
        capex = revenue * max(0.02, capex_pct + rng.normal(0, 0.01))
        dividends = max(0, net_income * rng.uniform(0.0, 0.4)) if net_income > 0 else 0

        # Stock price grows roughly with earnings
        price_growth = yr_growth + rng.normal(0, 0.05)
        stock_price = stock_price_base * ((1 + price_growth) ** i)
        stock_price = max(1.0, stock_price)

        records.append({
            "ticker": ticker,
            "fiscal_year": fy,
            "company_name": company_name,
            "sector": sector,
            "revenue": round(revenue, 2),
            "cost_of_revenue": round(cost_of_revenue, 2),
            "operating_income": round(operating_income, 2),
            "net_income": round(net_income, 2),
            "ebitda": round(ebitda, 2),
            "interest_expense": round(interest_expense, 2),
            "tax_provision": round(tax_provision, 2),
            "total_assets": round(total_assets, 2),
            "total_liabilities": round(total_liabilities, 2),
            "total_equity": round(total_equity, 2),
            "total_debt": round(total_debt, 2),
            "cash_and_equivalents": round(cash, 2),
            "operating_cash_flow": round(operating_cf, 2),
            "capex": round(capex, 2),
            "depreciation": round(depreciation, 2),
            "dividends_paid": round(dividends, 2),
            "shares_outstanding": shares_outstanding,
            "stock_price": round(stock_price, 2),
            "beta": round(float(rng.uniform(0.7, 1.8)), 2),
        })

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": f"{sector} - Synthetic",
        "currency": "USD",
        "records": records,
    }


SECTOR_PROFILES = {
    "Technology": {
        "revenue_range": (5e9, 400e9), "growth": 0.12, "gross_margin": 0.60,
        "op_margin": 0.25, "net_margin": 0.18, "capex_pct": 0.06,
        "de": 0.5, "price_range": (50, 300), "shares_range": (500e6, 15e9),
    },
    "Healthcare": {
        "revenue_range": (2e9, 100e9), "growth": 0.08, "gross_margin": 0.65,
        "op_margin": 0.20, "net_margin": 0.15, "capex_pct": 0.05,
        "de": 0.6, "price_range": (30, 200), "shares_range": (500e6, 5e9),
    },
    "Consumer": {
        "revenue_range": (5e9, 200e9), "growth": 0.05, "gross_margin": 0.35,
        "op_margin": 0.12, "net_margin": 0.08, "capex_pct": 0.04,
        "de": 0.8, "price_range": (20, 150), "shares_range": (500e6, 10e9),
    },
    "Energy": {
        "revenue_range": (10e9, 400e9), "growth": 0.03, "gross_margin": 0.30,
        "op_margin": 0.10, "net_margin": 0.07, "capex_pct": 0.08,
        "de": 1.0, "price_range": (20, 120), "shares_range": (1e9, 10e9),
    },
    "Financials": {
        "revenue_range": (5e9, 150e9), "growth": 0.06, "gross_margin": 0.50,
        "op_margin": 0.30, "net_margin": 0.22, "capex_pct": 0.03,
        "de": 2.0, "price_range": (30, 200), "shares_range": (500e6, 10e9),
    },
}


def generate_dataset(
    num_companies: int,
    years: int,
    sector: str,
    target_ticker: str = None,
    peer_tickers: list = None,
    seed: int = SEED,
) -> dict:
    """Generate a full dataset with target + peer companies."""
    rng = np.random.default_rng(seed)
    profile = SECTOR_PROFILES.get(sector, SECTOR_PROFILES["Technology"])

    # Generate ticker names if not provided
    if target_ticker is None:
        target_ticker = "TGT"
    if peer_tickers is None:
        peer_tickers = [f"PEER{i+1}" for i in range(max(3, num_companies - 1))]

    all_tickers = [target_ticker] + peer_tickers
    companies = []

    for idx, ticker in enumerate(all_tickers):
        rev_low, rev_high = profile["revenue_range"]
        base_rev = rng.uniform(rev_low, rev_high)
        s_low, s_high = profile["shares_range"]
        shares = rng.uniform(s_low, s_high)
        p_low, p_high = profile["price_range"]
        price = rng.uniform(p_low, p_high)

        company = generate_company_financials(
            ticker=ticker,
            company_name=f"Synthetic {ticker} Corp",
            sector=sector,
            years=years,
            base_revenue=base_rev,
            revenue_growth=profile["growth"] + rng.normal(0, 0.03),
            gross_margin=profile["gross_margin"] + rng.normal(0, 0.05),
            operating_margin=profile["op_margin"] + rng.normal(0, 0.03),
            net_margin=profile["net_margin"] + rng.normal(0, 0.02),
            capex_pct=profile["capex_pct"],
            debt_equity=max(0.1, profile["de"] + rng.normal(0, 0.2)),
            stock_price_base=price,
            shares_outstanding=shares,
            rng=rng,
        )
        companies.append(company)

    # Precedent transactions (synthetic)
    transactions = _generate_synthetic_transactions(sector, rng)

    return {
        "fetch_date": datetime.now().isoformat(),
        "target": companies[0],
        "peers": companies[1:],
        "precedent_transactions": transactions,
        "metadata": {
            "synthetic": True,
            "seed": seed,
            "sector": sector,
            "num_companies": len(companies),
            "years": years,
        },
    }


def _generate_synthetic_transactions(sector: str, rng: np.random.Generator) -> list:
    """Generate synthetic M&A transactions for precedent transaction analysis."""
    profile = SECTOR_PROFILES.get(sector, SECTOR_PROFILES["Technology"])
    transactions = []
    for i in range(5):
        rev = rng.uniform(*profile["revenue_range"]) * 0.3
        ev_rev = rng.uniform(1.5, 8.0)
        deal_value = rev * ev_rev
        ebitda = rev * (profile["op_margin"] + rng.uniform(0.02, 0.08))
        ev_ebitda = deal_value / ebitda if ebitda > 0 else None

        transactions.append({
            "transaction_date": f"{2020 + i}-{rng.integers(1,13):02d}-{rng.integers(1,29):02d}",
            "target_name": f"Synthetic Target {i+1}",
            "acquirer_name": f"Synthetic Acquirer {i+1}",
            "sector": sector,
            "deal_value": round(deal_value, 2),
            "target_revenue": round(rev, 2),
            "target_ebitda": round(ebitda, 2),
            "ev_revenue_multiple": round(ev_rev, 2),
            "ev_ebitda_multiple": round(ev_ebitda, 2) if ev_ebitda else None,
            "premium_paid": round(float(rng.uniform(15, 50)), 1),
        })
    return transactions


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic financial data for valuation testing"
    )
    parser.add_argument(
        "--num-companies", type=int, default=5, help="Total companies to generate (default: 5)"
    )
    parser.add_argument("--years", type=int, default=5, help="Years of history (default: 5)")
    parser.add_argument(
        "--sector", default="Technology",
        choices=list(SECTOR_PROFILES.keys()),
        help="Industry sector profile (default: Technology)",
    )
    parser.add_argument("--target-ticker", default=None, help="Target company ticker")
    parser.add_argument("--peers", default=None, help="Comma-separated peer tickers")
    parser.add_argument("--seed", type=int, default=SEED, help=f"Random seed (default: {SEED})")
    parser.add_argument(
        "--output", default="data/raw/financials.json", help="Output file path"
    )
    args = parser.parse_args()

    peer_list = None
    if args.peers:
        peer_list = [p.strip().upper() for p in args.peers.split(",") if p.strip()]

    dataset = generate_dataset(
        num_companies=args.num_companies,
        years=args.years,
        sector=args.sector,
        target_ticker=args.target_ticker,
        peer_tickers=peer_list,
        seed=args.seed,
    )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    target = dataset["target"]
    print(f"Synthetic data generated (seed={args.seed}):")
    print(f"  Target: {target['company_name']} ({target['ticker']})")
    print(f"  Peers: {len(dataset['peers'])} companies")
    print(f"  Years: {args.years} fiscal years")
    print(f"  Sector: {args.sector}")
    print(f"  Transactions: {len(dataset['precedent_transactions'])}")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
