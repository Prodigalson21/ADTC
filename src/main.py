"""
main.py -- Flask API surface for the ADTC POS agent.

Sync, threaded Flask app. All writes go through business_logic.py,
which itself wraps database.py's own precondition validation --
main.py never touches the database directly. No /phone route -- the
phone-client concept was dropped from this build's scope.
"""

from flask import Flask, request, jsonify, send_from_directory
import os

from src.database import Database
from src.agent import Agent
from src.scale_reader import get_scale
from src.barcode_scanner import BarcodeScanner
import src.business_logic as business_logic


def create_app(db_path: str = "data/shop.db", inference_backend=None,
               grammar_path=None, system_prompt=""):
    """Factory function -- lets tests create an app against an isolated
    test database instead of the real one."""
    app = Flask(__name__, static_folder="static", static_url_path="")

    db = Database(db_path)
    agent = Agent(db, inference_backend=inference_backend,
                  grammar_path=grammar_path, system_prompt=system_prompt)
    scale = get_scale()
    scanner = BarcodeScanner()
    scanner.start()

    app.config["DB"] = db
    app.config["AGENT"] = agent
    app.config["SCALE"] = scale
    app.config["SCANNER"] = scanner

    @app.route("/api/query", methods=["POST"])
    def query():
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        if not text:
            return jsonify({"success": False, "error": "Missing 'text' field"}), 400
        result = app.config["AGENT"].process_message(text)
        status_code = 200 if result["success"] else 422
        return jsonify(result), status_code

    @app.route("/api/sale", methods=["POST"])
    def sale():
        data = request.get_json(silent=True) or {}
        required = ["product", "quantity", "unit"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400
        result = business_logic.record_sale(
            app.config["DB"],
            product_name=data["product"],
            quantity=float(data["quantity"]),
            unit=data["unit"],
            discount_cents=int(data.get("discount_cents", 0)),
        )
        status_code = 200 if result["success"] else 422
        return jsonify(result), status_code

    @app.route("/api/refund", methods=["POST"])
    def refund():
        data = request.get_json(silent=True) or {}
        result = business_logic.process_refund(
            app.config["DB"],
            product_name=data.get("product"),
            sale_id=data.get("sale_id"),
            amount_cents=data.get("amount_cents"),
        )
        status_code = 200 if result["success"] else 422
        return jsonify(result), status_code

    @app.route("/api/discount", methods=["POST"])
    def discount():
        data = request.get_json(silent=True) or {}
        if "product" not in data or "percent" not in data:
            return jsonify({"success": False, "error": "Missing 'product' or 'percent'"}), 400
        result = business_logic.apply_discount(
            app.config["DB"], product_name=data["product"], percent=float(data["percent"])
        )
        status_code = 200 if result["success"] else 422
        return jsonify(result), status_code

    @app.route("/api/inventory/<product_name>", methods=["GET"])
    def inventory(product_name):
        result = business_logic.check_inventory(app.config["DB"], product_name)
        status_code = 200 if result["success"] else 404
        return jsonify(result), status_code

    @app.route("/api/register", methods=["POST"])
    def register():
        data = request.get_json(silent=True) or {}
        required = ["name", "unit", "unit_price_cents"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400
        result = business_logic.register_product(
            app.config["DB"],
            name=data["name"],
            unit=data["unit"],
            unit_price_cents=int(data["unit_price_cents"]),
            stock_quantity=float(data.get("stock_quantity", 0.0)),
            category=data.get("category", ""),
        )
        status_code = 200 if result["success"] else 422
        return jsonify(result), status_code

    @app.route("/api/scale", methods=["GET"])
    def scale_reading():
        try:
            quantity, unit = app.config["SCALE"].read()
            return jsonify({"success": True, "quantity": quantity, "unit": unit})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 503

    @app.route("/api/barcode", methods=["GET"])
    def barcode_reading():
        scanner = app.config["SCANNER"]
        value = scanner.get_latest(clear=True)
        return jsonify({
            "success": True,
            "value": value,
            "scanner_available": scanner.is_available(),
        })

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/", methods=["GET"])
    def index():
        """Serve the frontend's index.html at the root URL."""
        return send_from_directory(app.static_folder, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, threaded=True)
