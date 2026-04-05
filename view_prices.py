#!/usr/bin/env python3
"""
view_prices.py  --  CLI tool to inspect stored flight prices.

Usage:
    python3 view_prices.py
    python3 view_prices.py --route YYZ_SYD
    python3 view_prices.py --airline "Cathay Pacific"
    python3 view_prices.py --top 20
    python3 view_prices.py --route MEL_YYZ --top 5
"""

import argparse
import sqlite3
import sys

import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Section 1: All-time bests per airline per route
# ---------------------------------------------------------------------------

def print_all_time_bests(conn, route_filter=None, airline_filter=None) -> None:
    where, params = build_where(
        route_filter=route_filter,
        airline_filter=airline_filter,
        table="best_prices",
    )
    query = (
        "SELECT route, airline, best_price_cad, best_price_usd, "
        "travel_date, last_alert_at "
        "FROM best_prices"
        + where
        + " ORDER BY route, best_price_cad ASC"
    )
    rows = conn.execute(query, params).fetchall()

    print("\n=== All-Time Best Prices per Airline per Route ===\n")
    if not rows:
        print("  (no data -- run flight_tracker.py first)")
        return

    col_w = [12, 32, 12, 12, 12, 22]
    hdr = (
        f"{'Route':<{col_w[0]}} {'Airline':<{col_w[1]}} "
        f"{'Best CAD':>{col_w[2]}} {'Best USD':>{col_w[3]}} "
        f"{'Date':<{col_w[4]}} {'Last Alert':<{col_w[5]}}"
    )
    print(hdr)
    print("-" * len(hdr))

    for r in rows:
        alert_at = (r["last_alert_at"] or "never")[:20]
        print(
            f"{r['route']:<{col_w[0]}} {r['airline']:<{col_w[1]}} "
            f"${r['best_price_cad']:>{col_w[2]-1},.0f} "
            f"${r['best_price_usd']:>{col_w[3]-1},.0f} "
            f"{r['travel_date']:<{col_w[4]}} {alert_at:<{col_w[5]}}"
        )


# ---------------------------------------------------------------------------
# Section 2: Top N cheapest prices ever seen
# ---------------------------------------------------------------------------

def print_top_cheapest(conn, top_n=10, route_filter=None, airline_filter=None) -> None:
    where, params = build_where(
        route_filter=route_filter,
        airline_filter=airline_filter,
        table="price_history",
    )
    query = (
        "SELECT route, travel_date, airline, price_cad, price_usd, stops, duration "
        "FROM price_history"
        + where
        + f" ORDER BY price_cad ASC LIMIT {int(top_n)}"
    )
    rows = conn.execute(query, params).fetchall()

    print(f"\n=== Top {top_n} Cheapest Prices Ever Seen ===\n")
    if not rows:
        print("  (no data)")
        return

    col_w = [4, 12, 12, 32, 11, 11, 7, 12]
    hdr = (
        f"{'#':<{col_w[0]}} {'Route':<{col_w[1]}} {'Date':<{col_w[2]}} "
        f"{'Airline':<{col_w[3]}} {'CAD':>{col_w[4]}} {'USD':>{col_w[5]}} "
        f"{'Stops':>{col_w[6]}} {'Duration':<{col_w[7]}}"
    )
    print(hdr)
    print("-" * len(hdr))

    for i, r in enumerate(rows, 1):
        stops_val = r["stops"] if r["stops"] is not None else "?"
        print(
            f"{i:<{col_w[0]}} {r['route']:<{col_w[1]}} {r['travel_date']:<{col_w[2]}} "
            f"{r['airline']:<{col_w[3]}} ${r['price_cad']:>{col_w[4]-1},.0f} "
            f"${r['price_usd']:>{col_w[5]-1},.0f} "
            f"{str(stops_val):>{col_w[6]}} {r['duration'] or '':.<{col_w[7]}}"
        )


# ---------------------------------------------------------------------------
# Section 3: Price trend table + ASCII bar chart
# ---------------------------------------------------------------------------

def print_price_trend(conn, route_filter=None, airline_filter=None) -> None:
    """Cheapest price per travel date per route, with an ASCII bar chart."""
    bar_width = 32

    for route_cfg in config.ROUTES:
        route_id = route_cfg["id"]
        if route_filter and route_id != route_filter:
            continue

        where_parts = ["route = ?"]
        params: list = [route_id]
        if airline_filter:
            where_parts.append("airline LIKE ?")
            params.append(f"%{airline_filter}%")

        query = (
            "SELECT travel_date, MIN(price_cad) AS min_cad "
            "FROM price_history "
            "WHERE " + " AND ".join(where_parts) +
            " GROUP BY travel_date ORDER BY travel_date ASC"
        )
        rows = conn.execute(query, params).fetchall()
        if not rows:
            continue

        prices  = [r["min_cad"] for r in rows]
        min_p   = min(prices)
        max_p   = max(prices)
        p_range = max_p - min_p if max_p > min_p else 1.0

        print(f"\n=== Price Trend: {route_cfg['label']} ===")
        print(f"    Scale: ${min_p:,.0f} CAD (left) -- ${max_p:,.0f} CAD (right)\n")
        print(f"  {'Date':<12} {'Min CAD':>10}  {'Chart'}")
        print("  " + "-" * (12 + 10 + bar_width + 6))

        for r in rows:
            p      = r["min_cad"]
            filled = int((p - min_p) / p_range * bar_width)
            bar    = "#" * filled + "." * (bar_width - filled)
            print(f"  {r['travel_date']:<12} ${p:>9,.0f}  |{bar}|")


# ---------------------------------------------------------------------------
# Shared WHERE builder
# ---------------------------------------------------------------------------

def build_where(route_filter, airline_filter, table="price_history"):
    parts:  list = []
    params: list = []
    if route_filter:
        parts.append("route = ?")
        params.append(route_filter.upper())
    if airline_filter:
        parts.append("airline LIKE ?")
        params.append(f"%{airline_filter}%")
    where = (" WHERE " + " AND ".join(parts)) if parts else ""
    return where, params


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="View stored flight prices from prices.db"
    )
    parser.add_argument(
        "--route",
        help="Filter by route ID  (e.g. YYZ_SYD or MEL_YYZ)",
        default=None,
    )
    parser.add_argument(
        "--airline",
        help='Filter by airline name (partial match, e.g. "Cathay Pacific")',
        default=None,
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of cheapest rows to show  (default: 10)",
    )
    args = parser.parse_args()

    try:
        conn = get_conn()
    except Exception as exc:
        print(f"Cannot open {config.DB_PATH}: {exc}", file=sys.stderr)
        sys.exit(1)

    print_all_time_bests(conn, route_filter=args.route, airline_filter=args.airline)
    print_top_cheapest(
        conn,
        top_n=args.top,
        route_filter=args.route,
        airline_filter=args.airline,
    )
    print_price_trend(conn, route_filter=args.route, airline_filter=args.airline)
    print()
    conn.close()


if __name__ == "__main__":
    main()
