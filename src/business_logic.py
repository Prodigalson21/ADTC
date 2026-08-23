"""
business_logic.py -- the six core POS tools.

Every function here wraps a Database call and returns a consistent
{"success": bool, ...} shape. Database.py's own validation (product
exists, sufficient stock, valid refund amount, etc.) IS the
precondition check -- this layer's job is to resolve product names to
IDs, compute derived values (total_cents), and turn ValueError into a
structured result instead of an exception agent.py would need to catch
everywhere.
"""

from typing import Optional, Dict, Any

VALID_UNITS = {"kg", "g", "l", "ml", "count"}


def _err(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def record_sale(db, product_name: str, quantity: float, unit: str,
                 discount_cents: int = 0) -> Dict[str, Any]:
    """Sell `quantity` of `product_name`. Computes total_cents from the
    product's current price -- the caller never supplies total_cents
    directly."""
    if unit not in VALID_UNITS:
        return _err(f"Unsupported unit: '{unit}'. Valid units: {sorted(VALID_UNITS)}")

    product = db.check_inventory(product_name)
    if product is None:
        return _err(f"Product '{product_name}' not found")

    total_cents = round(quantity * product["unit_price_cents"]) - discount_cents

    try:
        sale_id = db.record_sale(product["id"], quantity, unit, total_cents, discount_cents)
        return {
            "success": True,
            "sale_id": sale_id,
            "product": product_name,
            "quantity": quantity,
            "unit": unit,
            "total_cents": total_cents,
        }
    except ValueError as e:
        return _err(str(e))


def process_refund(db, product_name: Optional[str] = None,
                    sale_id: Optional[int] = None,
                    amount_cents: Optional[int] = None) -> Dict[str, Any]:
    """Refund a sale. If sale_id isn't given, resolve it from
    product_name via the most recent sale with a refundable balance --
    this is how 'rudisha X' (a product name, no sale ID) becomes an
    actual operation."""
    if sale_id is None:
        if product_name is None:
            return _err("Must provide either sale_id or product_name")
        lookup = db.most_recent_unrefunded_sale(product_name)
        if lookup is None:
            return _err(f"No refundable sale found for '{product_name}'")
        sale_id = lookup["sale_id"]
        if amount_cents is None:
            amount_cents = lookup["remaining_cents"]

    if amount_cents is None:
        return _err("Could not determine refund amount")

    try:
        refund_id = db.process_refund(sale_id, amount_cents)
        return {"success": True, "refund_id": refund_id, "sale_id": sale_id, "amount_cents": amount_cents}
    except ValueError as e:
        return _err(str(e))


def apply_discount(db, product_name: str, percent: float) -> Dict[str, Any]:
    """Permanently reduce a product's price by percent%."""
    try:
        result = db.apply_discount(product_name, percent)
        return {"success": True, **result}
    except ValueError as e:
        return _err(str(e))


def check_inventory(db, product_name: str) -> Dict[str, Any]:
    """Look up a product's current stock and price."""
    product = db.check_inventory(product_name)
    if product is None:
        return _err(f"Product '{product_name}' not found")
    return {"success": True, **product}


def register_product(db, name: str, unit: str, unit_price_cents: int,
                      stock_quantity: float = 0.0, category: str = "") -> Dict[str, Any]:
    """Register a new product, first-scan style -- no assumed catalog."""
    if unit not in VALID_UNITS:
        return _err(f"Unsupported unit: '{unit}'. Valid units: {sorted(VALID_UNITS)}")
    if unit_price_cents < 0:
        return _err(f"unit_price_cents must be non-negative, got {unit_price_cents}")

    existing = db.check_inventory(name)
    if existing is not None:
        return _err(f"Product '{name}' already exists")

    try:
        product_id = db.add_product(name, unit, unit_price_cents, stock_quantity, category)
        return {"success": True, "product_id": product_id, "name": name}
    except Exception as e:
        return _err(f"Could not register product '{name}': {e}")


def restock_alert(db, product_name: str) -> Dict[str, Any]:
    """Flag a product as needing restock. No quantity involved -- see
    database.py's log_restock_request docstring."""
    try:
        request_id = db.log_restock_request(product_name)
        return {"success": True, "request_id": request_id, "product": product_name}
    except ValueError as e:
        return _err(str(e))
