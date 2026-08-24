"""
analytics_engine/handler.py
Parameterized analytical queries over shop.db. No free-text SQL.
Returns Chart.js-ready JSON: {"labels": [...], "datasets": [{"label": "...", "data": [...]}]}
"""
import duckdb
import json
import os
from datetime import datetime
from typing import Any, Dict

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "manifest.json")
with open(MANIFEST_PATH, "r") as f:
    MANIFEST = json.load(f)

VALID_TEMPLATES = set(MANIFEST["templates"].keys())

class AnalyticsError(Exception):
    pass

def _validate_params(template_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if template_name not in VALID_TEMPLATES:
        raise AnalyticsError(f"Unknown template: {template_name}. Valid: {sorted(VALID_TEMPLATES)}")

    spec = MANIFEST["templates"][template_name]["params"]
    cleaned = {}

    for pname, pspec in spec.items():
        required = pspec.get("required", False)
        ptype = pspec["type"]

        if pname not in params:
            if required:
                raise AnalyticsError(f"Missing required parameter: {pname}")
            continue

        value = params[pname]

        if ptype == "enum":
            if value not in pspec["values"]:
                raise AnalyticsError(f"Parameter '{pname}' must be one of {pspec['values']}, got {value!r}")
            cleaned[pname] = value
        elif ptype == "int":
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                raise AnalyticsError(f"Parameter '{pname}' must be an integer, got {value!r}")
            if "min" in pspec and ivalue < pspec["min"]:
                raise AnalyticsError(f"Parameter '{pname}' must be >= {pspec['min']}, got {ivalue}")
            if "max" in pspec and ivalue > pspec["max"]:
                raise AnalyticsError(f"Parameter '{pname}' must be <= {pspec['max']}, got {ivalue}")
            cleaned[pname] = ivalue
        elif ptype == "date":
            if not isinstance(value, str):
                raise AnalyticsError(f"Parameter '{pname}' must be a date string (YYYY-MM-DD)")
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                raise AnalyticsError(f"Parameter '{pname}' must be YYYY-MM-DD, got {value!r}")
            cleaned[pname] = value
        else:
            raise AnalyticsError(f"Unknown param type {ptype} in manifest")

    return cleaned

def _sales_by_period(conn, params: Dict) -> Dict:
    period = params["period"]
    unit_map = {"hour": "hour", "day": "day", "week": "week", "month": "month"}
    unit = unit_map[period]
    where_clauses, bind_values = [], []
    if "start_date" in params:
        where_clauses.append("timestamp::TIMESTAMP >= ?::date")
        bind_values.append(params["start_date"])
    if "end_date" in params:
        where_clauses.append("timestamp::TIMESTAMP <= ?::date")
        bind_values.append(params["end_date"])
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    query = f"""
        SELECT date_trunc('{unit}', timestamp::TIMESTAMP) AS period_start, SUM(total_cents) AS revenue_cents, COUNT(*) AS sale_count
        FROM sales WHERE {where_sql} GROUP BY period_start ORDER BY period_start
    """
    rows = conn.execute(query, bind_values).fetchall()
    return {
        "labels": [str(r[0]) for r in rows],
        "datasets": [
            {"label": f"Revenue ({period})", "data": [r[1] / 100.0 for r in rows]},
            {"label": "Sale count", "data": [r[2] for r in rows]},
        ],
    }

def _top_n_products(conn, params: Dict) -> Dict:
    n, metric = params["n"], params["metric"]
    if metric == "revenue":
        order_expr, value_expr, value_label = "SUM(total_cents) DESC", "SUM(total_cents) / 100.0", "Revenue"
    else:
        order_expr, value_expr, value_label = "SUM(quantity) DESC", "SUM(quantity)", "Quantity sold"
    query = f"SELECT p.name, {value_expr} AS value FROM sales s JOIN products p ON s.product_id = p.id GROUP BY p.name ORDER BY {order_expr} LIMIT ?"
    rows = conn.execute(query, [n]).fetchall()
    return {"labels": [r[0] for r in rows], "datasets": [{"label": value_label, "data": [r[1] for r in rows]}]}

def _margin_by_category(conn, params: Dict) -> Dict:
    period = params.get("period", "all")
    if period == "all":
        where_sql, bind_values = "1=1", []
    else:
        unit_map = {"day": "day", "week": "week", "month": "month"}
        unit = unit_map[period]
        where_sql, bind_values = "date_trunc(?, s.timestamp::TIMESTAMP) = date_trunc(?, CURRENT_DATE)", [unit, unit]
    query = f"""
        SELECT p.category, SUM(s.total_cents) AS revenue_cents, SUM(s.quantity * p.unit_price_cents * 0.3) AS cost_cents_approx
        FROM sales s JOIN products p ON s.product_id = p.id WHERE {where_sql} GROUP BY p.category ORDER BY revenue_cents DESC
    """
    rows = conn.execute(query, bind_values).fetchall()
    margins = [round(((r[1] - r[2]) / r[1] * 100) if r[1] > 0 else 0.0, 2) for r in rows]
    return {"labels": [r[0] for r in rows], "datasets": [{"label": f"Margin % ({period})", "data": margins}]}

def _stock_turnover(conn, params: Dict) -> Dict:
    days = params.get("days", 30)
    query = """
        SELECT p.name, COALESCE(SUM(s.quantity), 0) AS units_sold, p.stock_quantity AS current_stock,
               CASE WHEN p.stock_quantity > 0 THEN COALESCE(SUM(s.quantity), 0) / p.stock_quantity ELSE 0 END AS turnover_ratio
        FROM products p LEFT JOIN sales s ON s.product_id = p.id AND s.timestamp::TIMESTAMP >= CURRENT_DATE - ?::int
        GROUP BY p.name, p.stock_quantity ORDER BY turnover_ratio DESC
    """
    rows = conn.execute(query, [days]).fetchall()
    return {
        "labels": [r[0] for r in rows],
        "datasets": [
            {"label": f"Turnover (last {days} days)", "data": [round(r[3], 2) for r in rows]},
            {"label": "Units sold", "data": [r[1] for r in rows]},
        ],
    }

TEMPLATE_FUNCS = {
    "sales_by_period": _sales_by_period,
    "top_n_products": _top_n_products,
    "margin_by_category": _margin_by_category,
    "stock_turnover": _stock_turnover,
}

def run_analytics(db_path: str, template: str, params: Dict[str, Any]) -> Dict:
    cleaned = _validate_params(template, params)
    if not os.path.exists(db_path):
        raise AnalyticsError(f"Database not found: {db_path}")
    conn = duckdb.connect(db_path, read_only=True)
    try:
        return TEMPLATE_FUNCS[template](conn, cleaned)
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print(f"Usage: python handler.py <template> <json_params> [db_path]\nTemplates: {sorted(VALID_TEMPLATES)}")
        sys.exit(1)
    try:
        params = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(f"Invalid JSON params: {e}")
        sys.exit(1)
    db_path = sys.argv[3] if len(sys.argv) > 3 else "data/shop.db"
    try:
        print(json.dumps(run_analytics(db_path, sys.argv[1], params), indent=2))
    except AnalyticsError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
