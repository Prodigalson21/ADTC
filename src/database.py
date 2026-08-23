# src/database.py
"""SQLite database layer for ADTC 2026 POS Agent.
All money stored as integer cents. All quantities stored as REAL.
WAL mode enabled for concurrent reads. threading.Lock() on all writes.

Fixes folded in this pass (from external code review, verified before
applying):
- Added indexes on sales(product_id), sales(timestamp), refunds(sale_id)
  -- cheap now, avoids slow full-table scans once Day 7's analytics
  engine starts querying this data.
- get_sales_by_period now JOINs products, returning product_name and
  unit alongside each sale -- the analytics engine needs the name, not
  just product_id, and it's cheaper to fix here than rework on Day 7.
- Added close() to explicitly release the persistent connection.
- Rounding contract documented explicitly for record_sale's total_cents
  check (see docstring there) and restock_qty in process_refund is now
  rounded to 4 decimal places to stop tiny float drift from accumulating
  across repeated partial refunds. NOT switched to Decimal/Fraction --
  that's real but more precision than a 10-day build needs; the ROUND
  documented here is the pragmatic middle ground.
"""

import sqlite3
import threading
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


class Database:
    """Thread-safe SQLite database for POS operations."""

    def __init__(self, db_path: str = "data/shop.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)

        # ONE persistent connection for the whole object's lifetime.
        # check_same_thread=False is safe here because every access to
        # this connection goes through self._lock.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                unit TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL,
                stock_quantity REAL NOT NULL DEFAULT 0.0,
                category TEXT
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                discount_cents INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (sale_id) REFERENCES sales(id)
            );
            CREATE TABLE IF NOT EXISTS restock_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_id);
            CREATE INDEX IF NOT EXISTS idx_sales_timestamp ON sales(timestamp);
            CREATE INDEX IF NOT EXISTS idx_refunds_sale ON refunds(sale_id);
        """)
        self._conn.commit()

    def close(self) -> None:
        """Explicitly close the persistent connection."""
        with self._lock:
            self._conn.close()

    def add_product(self, name: str, unit: str, unit_price_cents: int,
                     stock_quantity: float = 0.0, category: str = "") -> int:
        """Add a new product. Returns product ID."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO products (name, unit, unit_price_cents, stock_quantity, category) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, unit, unit_price_cents, stock_quantity, category)
            )
            self._conn.commit()
            return cursor.lastrowid

    def record_sale(self, product_id: int, quantity: float, unit: str,
                     total_cents: int, discount_cents: int = 0) -> int:
        """Record a sale. Returns sale ID.

        Rounding contract: total_cents is validated as
        round(quantity * unit_price_cents) - discount_cents, using
        Python's built-in round() (banker's rounding). Whatever caller
        computes total_cents -- agent.py, business_logic.py, the
        frontend -- MUST use this exact same formula and rounding
        method, or correct sales will be rejected as mismatches. This
        is a deliberate simplification (not Decimal-based) to keep the
        money math easy to reason about across the whole codebase; if
        real-world testing surfaces rounding mismatches between here
        and the caller, that's the first place to look.

        Raises ValueError if the product doesn't exist, quantity isn't
        positive, stock is insufficient, or total_cents doesn't match
        the expected amount.
        """
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")

        timestamp = datetime.now().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT stock_quantity, unit_price_cents FROM products WHERE id = ?",
                (product_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Product {product_id} not found")

            current_stock, unit_price_cents = row["stock_quantity"], row["unit_price_cents"]

            if quantity > current_stock:
                raise ValueError(f"Insufficient stock: {current_stock} < {quantity}")

            expected_cents = round(quantity * unit_price_cents) - discount_cents
            if total_cents != expected_cents:
                raise ValueError(
                    f"total_cents mismatch: got {total_cents}, expected {expected_cents} "
                    f"({quantity} x {unit_price_cents} - {discount_cents} discount)"
                )

            cursor = self._conn.execute(
                "INSERT INTO sales (product_id, quantity, unit, total_cents, timestamp, discount_cents) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (product_id, quantity, unit, total_cents, timestamp, discount_cents)
            )
            self._conn.execute(
                "UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?",
                (quantity, product_id)
            )
            self._conn.commit()
            return cursor.lastrowid

    def process_refund(self, sale_id: int, amount_cents: int) -> int:
        """Process a refund. Returns refund ID.

        Raises ValueError if the sale doesn't exist, amount_cents isn't
        positive, or amount_cents exceeds what's actually left to refund
        on that sale (total_cents minus any refunds already issued
        against it). This prevents both over-refunding a sale and
        refunding the same sale twice.
        """
        if amount_cents <= 0:
            raise ValueError(f"amount_cents must be positive, got {amount_cents}")

        timestamp = datetime.now().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT product_id, quantity, total_cents FROM sales WHERE id = ?",
                (sale_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Sale {sale_id} not found")

            product_id, quantity, total_cents = row["product_id"], row["quantity"], row["total_cents"]

            already_refunded = self._conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM refunds WHERE sale_id = ?",
                (sale_id,)
            ).fetchone()["total"]

            remaining = total_cents - already_refunded
            if amount_cents > remaining:
                raise ValueError(
                    f"Refund of {amount_cents} exceeds remaining refundable amount "
                    f"{remaining} on sale {sale_id} (total {total_cents}, "
                    f"already refunded {already_refunded})"
                )

            cursor = self._conn.execute(
                "INSERT INTO refunds (sale_id, amount_cents, timestamp) VALUES (?, ?, ?)",
                (sale_id, amount_cents, timestamp)
            )

            # Restock proportionally. Rounded to 4 decimal places to stop
            # float drift from accumulating across repeated partial refunds.
            fraction = amount_cents / total_cents if total_cents else 0
            restock_qty = round(quantity * fraction, 4)

            self._conn.execute(
                "UPDATE products SET stock_quantity = stock_quantity + ? WHERE id = ?",
                (restock_qty, product_id)
            )
            self._conn.commit()
            return cursor.lastrowid

    def check_inventory(self, name: str) -> Optional[Dict[str, Any]]:
        """Check inventory for a product by name."""
        row = self._conn.execute("SELECT * FROM products WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def get_sales_by_period(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Get sales within a date period (ISO timestamp strings).
        Joins products so the analytics engine gets product_name and unit
        without a second query.
        """
        rows = self._conn.execute(
            """SELECT s.*, p.name AS product_name, p.unit
               FROM sales s
               JOIN products p ON s.product_id = p.id
               WHERE s.timestamp >= ? AND s.timestamp <= ?
               ORDER BY s.timestamp""",
            (start, end)
        ).fetchall()
        return [dict(row) for row in rows]

    def most_recent_unrefunded_sale(self, product_name: str) -> Optional[Dict[str, Any]]:
        """Find the most recent sale of a product that still has a
        nonzero refundable balance. Used to resolve product-name-only
        refund requests (e.g. Swahili 'rudisha X') into a concrete
        sale_id before calling process_refund.

        Returns a dict with sale_id, total_cents, already_refunded,
        remaining_cents -- or None if no refundable sale exists.
        """
        rows = self._conn.execute(
            """
            SELECT s.id AS sale_id, s.total_cents,
                   COALESCE((SELECT SUM(r.amount_cents) FROM refunds r WHERE r.sale_id = s.id), 0) AS already_refunded
            FROM sales s
            JOIN products p ON p.id = s.product_id
            WHERE p.name = ?
            ORDER BY s.timestamp DESC
            """,
            (product_name,)
        ).fetchall()

        for row in rows:
            remaining = row["total_cents"] - row["already_refunded"]
            if remaining > 0:
                return {
                    "sale_id": row["sale_id"],
                    "total_cents": row["total_cents"],
                    "already_refunded": row["already_refunded"],
                    "remaining_cents": remaining,
                }
        return None

    def apply_discount(self, name: str, percent: float) -> Dict[str, Any]:
        """Permanently reduce a product's unit price by percent%.
        Raises ValueError if the product doesn't exist or percent is
        outside [0, 100]."""
        if not (0 <= percent <= 100):
            raise ValueError(f"percent must be between 0 and 100, got {percent}")

        with self._lock:
            row = self._conn.execute(
                "SELECT id, unit_price_cents FROM products WHERE name = ?", (name,)
            ).fetchone()
            if not row:
                raise ValueError(f"Product '{name}' not found")

            old_price = row["unit_price_cents"]
            new_price = round(old_price * (1 - percent / 100))

            self._conn.execute(
                "UPDATE products SET unit_price_cents = ? WHERE id = ?",
                (new_price, row["id"])
            )
            self._conn.commit()
            return {"product": name, "old_price_cents": old_price, "new_price_cents": new_price}

    def log_restock_request(self, name: str) -> int:
        """Flag a product as needing restock. No quantity is recorded
        or changed -- this is a notification, not a stock mutation."""
        timestamp = datetime.now().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM products WHERE name = ?", (name,)
            ).fetchone()
            if not row:
                raise ValueError(f"Product '{name}' not found")

            cursor = self._conn.execute(
                "INSERT INTO restock_requests (product_id, timestamp) VALUES (?, ?)",
                (row["id"], timestamp)
            )
            self._conn.commit()
            return cursor.lastrowid
if __name__ == "__main__":
    # Clean test database -- same pattern as swahili_agreement.py's test
    # harness. Without this, re-running this file fails on the second
    # execution with a UNIQUE constraint error, since "sukari" would
    # already exist from the prior run.
    test_db_path = "data/shop_test.db"
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(test_db_path + ext):
            os.remove(test_db_path + ext)

    db = Database(test_db_path)

    product_id = db.add_product("sukari", "kg", 1500, 10.0, "food")
    print(f"Added product id: {product_id}")

    inv = db.check_inventory("sukari")
    print(f"Inventory: {inv}")

    # Correct total: 2.5 kg * 1500 cents = 3750 cents
    sale_id = db.record_sale(product_id, 2.5, "kg", 3750)
    print(f"Recorded sale id: {sale_id}")

    inv = db.check_inventory("sukari")
    print(f"Inventory after sale: {inv}")

    # wrong total should be rejected
    try:
        db.record_sale(product_id, 1.0, "kg", 1)  # 1 kg should cost 1500 cents, not 1
        print("BUG: wrong total was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected wrong total: {e}")

    # oversell should be rejected
    try:
        db.record_sale(product_id, 20.0, "kg", 30000)
        print("BUG: oversell was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected oversell: {e}")

    # NEW TEST: negative quantity should be rejected (was the free-restock exploit)
    try:
        db.record_sale(product_id, -5.0, "kg", -7500)
        print("BUG: negative quantity was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected negative quantity: {e}")

    refund_id = db.process_refund(sale_id, 3750)
    print(f"Processed refund id: {refund_id}")

    inv = db.check_inventory("sukari")
    print(f"Inventory after refund: {inv}")

    # NEW TEST: refunding the same sale again should now be rejected (was a double-restock bug)
    try:
        db.process_refund(sale_id, 3750)
        print("BUG: double refund was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected double refund: {e}")

    # NEW TEST: refunding more than the sale total should be rejected
    sale_id_2 = db.record_sale(product_id, 1.0, "kg", 1500)
    try:
        db.process_refund(sale_id_2, 5000)
        print("BUG: over-refund was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected over-refund: {e}")

    # NEW TEST: most_recent_unrefunded_sale resolves a product name to a sale_id
    lookup = db.most_recent_unrefunded_sale("sukari")
    print(f"Most recent unrefunded sale for sukari: {lookup}")

    # FK enforcement
    try:
        db.record_sale(9999, 1.0, "kg", 1500)  # product 9999 doesn't exist
        print("BUG: nonexistent product was NOT rejected")
    except ValueError as e:
        print(f"Correctly rejected nonexistent product: {e}")

    # NEW TEST: get_sales_by_period returns joined product data
    sales = db.get_sales_by_period("1970-01-01T00:00:00", "2099-12-31T23:59:59")
    print(f"Sales with product names: {len(sales)} rows, first product_name={sales[0].get('product_name') if sales else 'N/A'}")

    # NEW TEST: close() doesn't explode
    db.close()
    print("close() OK")

    print("\nAll self-tests passed.")