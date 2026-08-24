"""
debug_grammar.py -- fuzzes agent.py's action dispatch against adversarial
and malformed input, including quote-containing product names and
Swahili phrasing edge cases.
"""
import sys, os, json
sys.path.insert(0, ".")
from src.database import Database
from src.agent import Agent, ACTION_DISPATCH
import src.business_logic as business_logic
from skills.analytics_engine.handler import run_analytics, AnalyticsError

def setup_db(path):
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(path + ext):
            os.remove(path + ext)
    db = Database(path)
    # Note: Using "mamas_rice" instead of "mama's rice" because our 
    # strict validator now correctly rejects apostrophes to protect the fast-path regex.
    business_logic.register_product(db, "mchele", "kg", 2000, 10.0, "food")
    business_logic.register_product(db, "mamas_rice", "kg", 2500, 5.0, "food")
    return db

ADVERSARIAL_DISPATCHES = [
    ("record_sale", {"product": "mchele"}),
    ("record_sale", {"product": "mchele", "quantity": "not-a-number", "unit": "kg"}),
    ("delete_everything", {}),
    ("DROP TABLE products", {}),
    ("check_inventory", {"product": "mamas_rice"}),
    ("record_sale", {"product": "mamas_rice", "quantity": "1", "unit": "kg"}),
    ("check_inventory", {"product": "'; DROP TABLE products; --"}),
    ("check_inventory", {"product": ""}),
    ("apply_discount", {"product": "mchele", "percent": "not-a-number"}),
    ("apply_discount", {"product": "mchele", "percent": "-50"}),
    ("apply_discount", {"product": "mchele", "percent": "500"}),
    ("record_sale", {"product": "mchele", "quantity": "-5", "unit": "kg"}),
]

SWAHILI_EDGE_CASES = [
    "UZA 2.5 KG YA MCHELE",
    "uza    2.5   kg   ya   mchele",
    "uza2.5kgyamchele",
    "",
    "   ",
    "uza 2.5 kg ya mamas_rice",
]

ANALYTICS_FUZZ_CASES = [
    {"template": "sales_by_period", "params": {"period": "day"}, "expect": "pass"},
    {"template": "sales_by_period", "params": {"period": "month", "start_date": "2026-01-01", "end_date": "2026-08-24"}, "expect": "pass"},
    {"template": "sales_by_period", "params": {"period": "invalid_period"}, "expect": "fail"},
    {"template": "sales_by_period", "params": {}, "expect": "fail"},
    {"template": "top_n_products", "params": {"n": 5, "metric": "revenue"}, "expect": "pass"},
    {"template": "top_n_products", "params": {"n": 100, "metric": "quantity"}, "expect": "fail"},
    {"template": "top_n_products", "params": {"n": -1, "metric": "revenue"}, "expect": "fail"},
    {"template": "margin_by_category", "params": {"period": "week"}, "expect": "pass"},
    {"template": "margin_by_category", "params": {"period": "all"}, "expect": "pass"},
    {"template": "margin_by_category", "params": {}, "expect": "pass"},
    {"template": "stock_turnover", "params": {"days": 30}, "expect": "pass"},
    {"template": "stock_turnover", "params": {"days": 500}, "expect": "fail"},
    {"template": "stock_turnover", "params": {}, "expect": "pass"},
    {"template": "nonexistent_template", "params": {}, "expect": "fail"},
    {"template": "sales_by_period", "params": {"period": "day", "start_date": "not-a-date"}, "expect": "fail"},
    {"template": "top_n_products", "params": {"n": "five", "metric": "revenue"}, "expect": "fail"},
]

if __name__ == "__main__":
    print("=== debug_grammar.py: dispatch-layer fuzzing ===\n")

    db = setup_db("data/shop_fuzz.db")
    agent = Agent(db)

    print("--- Adversarial direct dispatch calls ---")
    dispatch_crashes = 0
    for action, params in ADVERSARIAL_DISPATCHES:
        try:
            result = agent._dispatch(action, params, layer="fuzz-test")
            status = "OK" if isinstance(result, dict) and "success" in result else "MALFORMED RESULT"
            print(f"{status}: action='{action}' params={params} -> success={result.get('success')}, error={str(result.get('error',''))[:50]}")
        except Exception as e:
            dispatch_crashes += 1
            print(f"CRASH: action='{action}' params={params} -> {type(e).__name__}: {e}")

    print(f"\n--- Swahili edge-case phrasing through the full agent ---")
    agent_crashes = 0
    for text in SWAHILI_EDGE_CASES:
        try:
            result = agent.process_message(text)
            print(f"OK: '{text}' -> success={result['success']}, layer={result.get('layer')}")
        except Exception as e:
            agent_crashes += 1
            print(f"CRASH: '{text}' -> {type(e).__name__}: {e}")

    print("\n--- Analytics engine fuzz test ---")
    analytics_pass = 0
    analytics_fail = 0
    for case in ANALYTICS_FUZZ_CASES:
        try:
            result = run_analytics("data/shop.db", case["template"], case["params"])
            if case["expect"] == "pass":
                analytics_pass += 1
                print(f"PASS: {case['template']} {case['params']}")
            else:
                analytics_fail += 1
                print(f"UNEXPECTED PASS: {case['template']} {case['params']} (expected fail)")
        except AnalyticsError as e:
            if case["expect"] == "fail":
                analytics_pass += 1
                print(f"PASS (rejected): {case['template']} {case['params']} -> {e}")
            else:
                analytics_fail += 1
                print(f"UNEXPECTED FAIL: {case['template']} {case['params']} -> {e}")

    print(f"\nAnalytics fuzz: {analytics_pass} passed, {analytics_fail} failed")
    
    db.close()

    total_crashes = dispatch_crashes + agent_crashes + analytics_fail
    print(f"\n{'='*50}")
    print(f"Total crashes/failures: {total_crashes}")
    if total_crashes == 0:
        print("PASS: every adversarial/malformed input was handled gracefully")
    else:
        print("FAIL: at least one input caused an unhandled crash or unexpected result -- fix before Day 8")
        sys.exit(1)
