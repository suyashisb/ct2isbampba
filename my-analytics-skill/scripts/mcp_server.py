#!/usr/bin/env python3
"""
mcp_server.py — MCP (Model Context Protocol) server for the Company Valuation Skill.

Exposes fetch_data.py functionality as MCP tools that an LLM agent can invoke
at runtime to fetch live financial data from Yahoo Finance.

Usage (stdio transport — standard for VS Code / Copilot skills):
    python scripts/mcp_server.py

The server exposes two tools:
  1. fetch_financials  — Fetch financial data for a target company and peers
  2. generate_synthetic — Generate synthetic data for testing

Protocol: JSON-RPC 2.0 over stdin/stdout (MCP stdio transport)
"""

import json
import sys
import os

# Add scripts dir to path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from fetch_data import fetch_company_data, fetch_precedent_transactions
from generate_synthetic_data import generate_dataset

# MCP tool definitions
TOOLS = [
    {
        "name": "fetch_financials",
        "description": (
            "Fetch live financial data (income statement, balance sheet, cash flow) "
            "from Yahoo Finance for a target company and its peer companies. "
            "Returns structured JSON with target financials, peer financials, "
            "and precedent M&A transactions for the sector. "
            "Requires: ticker (e.g. 'MSFT'), peers (e.g. 'AAPL,GOOGL,META,AMZN'), "
            "years (default 5)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Target company stock ticker symbol (e.g., 'MSFT', 'AAPL', 'NAUKRI.NS')",
                },
                "peers": {
                    "type": "string",
                    "description": "Comma-separated peer company tickers (minimum 3). E.g., 'AAPL,GOOGL,META,AMZN'",
                },
                "years": {
                    "type": "integer",
                    "description": "Number of historical fiscal years to fetch (default: 5)",
                    "default": 5,
                },
            },
            "required": ["ticker", "peers"],
        },
    },
    {
        "name": "generate_synthetic",
        "description": (
            "Generate synthetic but realistic financial data for testing the "
            "valuation pipeline without requiring network access. "
            "Returns structured JSON in the same format as fetch_financials."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_ticker": {
                    "type": "string",
                    "description": "Ticker symbol for the synthetic target company",
                    "default": "SYNTH",
                },
                "peers": {
                    "type": "string",
                    "description": "Comma-separated peer tickers (or auto-generated if omitted)",
                },
                "num_companies": {
                    "type": "integer",
                    "description": "Total number of companies (target + peers). Default: 5",
                    "default": 5,
                },
                "years": {
                    "type": "integer",
                    "description": "Years of history to generate. Default: 5",
                    "default": 5,
                },
                "sector": {
                    "type": "string",
                    "description": "Industry sector profile. Options: Technology, Healthcare, Consumer, Energy, Financials",
                    "default": "Technology",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility. Default: 42",
                    "default": 42,
                },
            },
            "required": [],
        },
    },
]


def handle_fetch_financials(params: dict) -> dict:
    """Handle the fetch_financials MCP tool call."""
    ticker = params.get("ticker", "").strip().upper()
    peers_str = params.get("peers", "")
    years = params.get("years", 5)

    if not ticker:
        return {"error": "ticker is required"}

    peer_list = [p.strip().upper() for p in peers_str.split(",") if p.strip()]
    if len(peer_list) < 3:
        return {"error": "At least 3 peer companies are required for CCA analysis."}

    from datetime import datetime

    result = {
        "fetch_date": datetime.now().isoformat(),
        "target": None,
        "peers": [],
        "precedent_transactions": [],
    }

    # Fetch target
    target_data = fetch_company_data(ticker, years)
    if "error" in target_data:
        return {"error": f"Failed to fetch target: {target_data['error']}"}
    result["target"] = target_data

    # Fetch peers
    for peer in peer_list:
        peer_data = fetch_company_data(peer, years)
        if "error" in peer_data:
            continue
        result["peers"].append(peer_data)

    if len(result["peers"]) < 3:
        return {"error": "Fewer than 3 peers fetched successfully. Cannot proceed with CCA."}

    # Fetch precedent transactions
    sector = target_data.get("sector", "Technology")
    result["precedent_transactions"] = fetch_precedent_transactions(sector)

    return result


def handle_generate_synthetic(params: dict) -> dict:
    """Handle the generate_synthetic MCP tool call."""
    target_ticker = params.get("target_ticker", "SYNTH")
    peers_str = params.get("peers")
    num_companies = params.get("num_companies", 5)
    years = params.get("years", 5)
    sector = params.get("sector", "Technology")
    seed = params.get("seed", 42)

    peer_list = None
    if peers_str:
        peer_list = [p.strip().upper() for p in peers_str.split(",") if p.strip()]

    dataset = generate_dataset(
        num_companies=num_companies,
        years=years,
        sector=sector,
        target_ticker=target_ticker,
        peer_tickers=peer_list,
        seed=seed,
    )
    return dataset


def send_response(id, result=None, error=None):
    """Send a JSON-RPC 2.0 response to stdout."""
    msg = {"jsonrpc": "2.0", "id": id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_notification(method, params=None):
    """Send a JSON-RPC 2.0 notification (no id)."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    """Main MCP server loop — reads JSON-RPC messages from stdin, responds on stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "initialize":
            send_response(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "company-valuation-skill",
                    "version": "2.0",
                },
            })

        elif method == "notifications/initialized":
            pass  # Client acknowledged init

        elif method == "tools/list":
            send_response(msg_id, {"tools": TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            if tool_name == "fetch_financials":
                result = handle_fetch_financials(tool_args)
            elif tool_name == "generate_synthetic":
                result = handle_generate_synthetic(tool_args)
            else:
                send_response(msg_id, error={"code": -32601, "message": f"Unknown tool: {tool_name}"})
                continue

            if "error" in result:
                send_response(msg_id, {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "isError": True,
                })
            else:
                send_response(msg_id, {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                })

        elif method == "ping":
            send_response(msg_id, {})

        else:
            send_response(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})


if __name__ == "__main__":
    main()
