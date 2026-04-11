#!/usr/bin/env python3
"""
fetch_data.py — Fetch financial data from Yahoo Finance API.

Retrieves income statement, balance sheet, cash flow statement, and market data
for a target company and its peers. Outputs structured JSON for downstream pipeline.

Usage:
    python scripts/fetch_data.py --ticker AAPL --peers MSFT,GOOGL,META,AMZN --output-dir data/raw
    python scripts/fetch_data.py --ticker AAPL --peers MSFT,GOOGL,META --years 5 --output data/raw/financials.json
"""

import argparse
import json
import sys
import os
from datetime import datetime

import yfinance as yf
import pandas as pd
import numpy as np


def fetch_company_data(ticker_symbol: str, years: int = 5) -> dict:
    """Fetch financial statements and market data for a single company."""
    try:
        tk = yf.Ticker(ticker_symbol)
        info = tk.info

        # Fetch financial statements (annual)
        income_stmt = tk.financials  # columns = dates, rows = line items
        balance_sheet = tk.balance_sheet
        cash_flow = tk.cashflow

        if income_stmt is None or income_stmt.empty:
            return {"error": f"No financial data available for {ticker_symbol}"}

        records = []
        available_dates = sorted(income_stmt.columns, reverse=True)[:years]

        for date in available_dates:
            year = date.year
            record = {
                "ticker": ticker_symbol.upper(),
                "fiscal_year": year,
                "company_name": info.get("longName", ticker_symbol),
                "sector": info.get("sector", "Unknown"),
            }

            # Income Statement
            record["revenue"] = _safe_get(income_stmt, "Total Revenue", date)
            record["cost_of_revenue"] = _safe_get(income_stmt, "Cost Of Revenue", date)
            record["operating_income"] = _safe_get(income_stmt, "Operating Income", date)
            record["net_income"] = _safe_get(income_stmt, "Net Income", date)
            record["ebitda"] = _safe_get(income_stmt, "EBITDA", date)
            record["interest_expense"] = _safe_get(income_stmt, "Interest Expense", date)
            record["tax_provision"] = _safe_get(income_stmt, "Tax Provision", date)

            # Balance Sheet
            if balance_sheet is not None and date in balance_sheet.columns:
                record["total_assets"] = _safe_get(balance_sheet, "Total Assets", date)
                record["total_liabilities"] = _safe_get(
                    balance_sheet, "Total Liabilities Net Minority Interest", date
                )
                record["total_equity"] = _safe_get(
                    balance_sheet, "Stockholders Equity", date
                )
                record["total_debt"] = _safe_get(balance_sheet, "Total Debt", date)
                record["cash_and_equivalents"] = _safe_get(
                    balance_sheet, "Cash And Cash Equivalents", date
                )

            # Cash Flow Statement
            if cash_flow is not None and date in cash_flow.columns:
                record["operating_cash_flow"] = _safe_get(
                    cash_flow, "Operating Cash Flow", date
                )
                record["capex"] = _safe_get(cash_flow, "Capital Expenditure", date)
                if record["capex"] is not None and record["capex"] < 0:
                    record["capex"] = abs(record["capex"])
                record["depreciation"] = _safe_get(
                    cash_flow, "Depreciation And Amortization", date
                )
                record["dividends_paid"] = _safe_get(
                    cash_flow, "Common Stock Dividend Paid", date
                )
                if record["dividends_paid"] is not None and record["dividends_paid"] < 0:
                    record["dividends_paid"] = abs(record["dividends_paid"])

            # Market data
            record["shares_outstanding"] = info.get("sharesOutstanding")
            record["stock_price"] = info.get("currentPrice") or info.get(
                "previousClose"
            )
            record["beta"] = info.get("beta")

            records.append(record)

        # Filter out records where critical fields are all null (incomplete years)
        critical_fields = ["revenue", "net_income", "total_assets", "operating_cash_flow"]
        complete_records = [
            r for r in records
            if r.get("revenue") is not None
        ]
        if len(complete_records) < len(records):
            dropped = len(records) - len(complete_records)
            print(f"    Dropped {dropped} incomplete fiscal year(s) for {ticker_symbol}")

        return {
            "ticker": ticker_symbol.upper(),
            "company_name": info.get("longName", ticker_symbol),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "currency": info.get("currency", "USD"),
            "records": sorted(complete_records, key=lambda r: r["fiscal_year"]),
        }

    except Exception as e:
        return {"error": f"Failed to fetch data for {ticker_symbol}: {str(e)}"}


def fetch_precedent_transactions(sector: str) -> list:
    """
    Return curated precedent transaction data for the sector.
    In production, this would query an M&A database or MCP tool.
    Here we provide representative sector benchmarks.
    """
    transactions_db = {
        "Technology": [
            {"transaction_date": "2023-10-28", "target_name": "Activision Blizzard",
             "acquirer_name": "Microsoft", "sector": "Technology",
             "deal_value": 68700000000, "target_revenue": 8700000000,
             "target_ebitda": 3400000000, "ev_revenue_multiple": 7.9,
             "ev_ebitda_multiple": 20.2, "premium_paid": 45.0},
            {"transaction_date": "2022-04-25", "target_name": "Twitter",
             "acquirer_name": "X Holdings", "sector": "Technology",
             "deal_value": 44000000000, "target_revenue": 5080000000,
             "target_ebitda": 800000000, "ev_revenue_multiple": 8.7,
             "ev_ebitda_multiple": 55.0, "premium_paid": 38.0},
            {"transaction_date": "2023-05-26", "target_name": "VMware",
             "acquirer_name": "Broadcom", "sector": "Technology",
             "deal_value": 61000000000, "target_revenue": 13350000000,
             "target_ebitda": 4800000000, "ev_revenue_multiple": 4.6,
             "ev_ebitda_multiple": 12.7, "premium_paid": 48.0},
            {"transaction_date": "2021-12-20", "target_name": "Citrix Systems",
             "acquirer_name": "Vista Equity / Elliott", "sector": "Technology",
             "deal_value": 16500000000, "target_revenue": 3220000000,
             "target_ebitda": 1100000000, "ev_revenue_multiple": 5.1,
             "ev_ebitda_multiple": 15.0, "premium_paid": 30.0},
        ],
        "Healthcare": [
            {"transaction_date": "2023-12-14", "target_name": "Seagen",
             "acquirer_name": "Pfizer", "sector": "Healthcare",
             "deal_value": 43000000000, "target_revenue": 2000000000,
             "target_ebitda": 300000000, "ev_revenue_multiple": 21.5,
             "ev_ebitda_multiple": 143.3, "premium_paid": 33.0},
            {"transaction_date": "2023-03-13", "target_name": "Horizon Therapeutics",
             "acquirer_name": "Amgen", "sector": "Healthcare",
             "deal_value": 28300000000, "target_revenue": 3600000000,
             "target_ebitda": 1500000000, "ev_revenue_multiple": 7.9,
             "ev_ebitda_multiple": 18.9, "premium_paid": 48.0},
        ],
        "Consumer": [
            {"transaction_date": "2022-09-01", "target_name": "Albertsons",
             "acquirer_name": "Kroger", "sector": "Consumer",
             "deal_value": 24600000000, "target_revenue": 77600000000,
             "target_ebitda": 4500000000, "ev_revenue_multiple": 0.3,
             "ev_ebitda_multiple": 5.5, "premium_paid": 33.0},
        ],
        "Energy": [
            {"transaction_date": "2023-10-11", "target_name": "Pioneer Natural Resources",
             "acquirer_name": "ExxonMobil", "sector": "Energy",
             "deal_value": 59500000000, "target_revenue": 23400000000,
             "target_ebitda": 12000000000, "ev_revenue_multiple": 2.5,
             "ev_ebitda_multiple": 5.0, "premium_paid": 18.0},
            {"transaction_date": "2023-10-23", "target_name": "Hess Corp",
             "acquirer_name": "Chevron", "sector": "Energy",
             "deal_value": 53000000000, "target_revenue": 11300000000,
             "target_ebitda": 6200000000, "ev_revenue_multiple": 4.7,
             "ev_ebitda_multiple": 8.5, "premium_paid": 10.0},
        ],
        "Financials": [
            {"transaction_date": "2023-05-01", "target_name": "First Republic Bank",
             "acquirer_name": "JPMorgan Chase", "sector": "Financials",
             "deal_value": 10600000000, "target_revenue": 6300000000,
             "target_ebitda": 2100000000, "ev_revenue_multiple": 1.7,
             "ev_ebitda_multiple": 5.0, "premium_paid": 0.0},
        ],
    }

    # Map sectors to our simplified categories
    sector_map = {
        "Technology": "Technology",
        "Communication Services": "Technology",
        "Consumer Cyclical": "Consumer",
        "Consumer Defensive": "Consumer",
        "Healthcare": "Healthcare",
        "Energy": "Energy",
        "Financial Services": "Financials",
        "Industrials": "Consumer",
        "Basic Materials": "Energy",
        "Real Estate": "Financials",
        "Utilities": "Energy",
    }

    mapped = sector_map.get(sector, "Technology")
    return transactions_db.get(mapped, transactions_db["Technology"])


def _safe_get(df: pd.DataFrame, row_label: str, col_date) -> float | None:
    """Safely retrieve a value from a financial statement DataFrame."""
    try:
        # Try exact match first
        if row_label in df.index:
            val = df.loc[row_label, col_date]
            if pd.notna(val):
                return float(val)
        # Try partial match
        for idx in df.index:
            if row_label.lower() in str(idx).lower():
                val = df.loc[idx, col_date]
                if pd.notna(val):
                    return float(val)
    except (KeyError, TypeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Fetch financial data from Yahoo Finance")
    parser.add_argument("--ticker", required=True, help="Target company ticker symbol")
    parser.add_argument(
        "--peers", required=True, help="Comma-separated peer ticker symbols"
    )
    parser.add_argument(
        "--years", type=int, default=5, help="Number of historical years (default: 5)"
    )
    parser.add_argument(
        "--output", default="data/raw/financials.json", help="Output JSON file path"
    )
    args = parser.parse_args()

    peer_list = [p.strip().upper() for p in args.peers.split(",") if p.strip()]

    if len(peer_list) < 3:
        print(
            json.dumps(
                {"error": "At least 3 peer companies are required for CCA analysis."}
            )
        )
        sys.exit(1)

    print(f"Fetching data for {args.ticker} and peers: {', '.join(peer_list)}...")

    result = {
        "fetch_date": datetime.now().isoformat(),
        "target": None,
        "peers": [],
        "precedent_transactions": [],
    }

    # Fetch target company
    print(f"  Fetching {args.ticker}...")
    target_data = fetch_company_data(args.ticker, args.years)
    if "error" in target_data:
        print(f"ERROR: {target_data['error']}")
        sys.exit(1)
    result["target"] = target_data

    # Fetch peer companies
    for peer in peer_list:
        print(f"  Fetching {peer}...")
        peer_data = fetch_company_data(peer, args.years)
        if "error" in peer_data:
            print(f"  WARNING: {peer_data['error']} — skipping.")
            continue
        result["peers"].append(peer_data)

    if len(result["peers"]) < 3:
        print("ERROR: Fewer than 3 peers fetched successfully. Cannot proceed with CCA.")
        sys.exit(1)

    # Fetch precedent transactions
    sector = target_data.get("sector", "Technology")
    result["precedent_transactions"] = fetch_precedent_transactions(sector)
    print(f"  Loaded {len(result['precedent_transactions'])} precedent transactions for {sector}")

    # Write output
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\nData saved to {args.output}")
    print(f"  Target: {target_data['company_name']} ({args.ticker})")
    print(f"  Peers: {len(result['peers'])} companies")
    print(f"  Years: {len(target_data['records'])} fiscal years")
    print(f"  Transactions: {len(result['precedent_transactions'])}")


if __name__ == "__main__":
    main()
