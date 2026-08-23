"""
scenario_runner.py -- Day 5 validation: run agent.py against a set of
realistic scenarios, English and Swahili, happy paths and precondition
failures.
"""
import sys, os
sys.path.insert(0, ".")
from src.database import Database
from src.agent import Agent
import src.business_logic as business_logic


def setup_db(path):
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(path + ext):
            os.remove(path + ext)
    db = Database(path)
    business_logic.register_product(db, "mchele", "kg", 2000, 10.0, "food")
    business_logic.register_product(db, "sukari", "kg", 1500, 10.0, "food")
    business_logic.register_product(db, "mafuta", "l", 3000, 5.0, "food")
    business_logic.register_product(db, "chumvi", "kg", 500, 20.0, "food")
    return db


SCENARIOS = [
    ("uza 2.5 kg ya mchele", True, "record_sale"),
    ("uza 1 kg ya sukari", True, "record_sale"),
    ("nipe chumvi kg 1", True, "record_sale"),
    ("bei gani ya sukari", True, "check_inventory"),
    ("baki ngapi ya mchele", True, "check_inventory"),
    ("punguzo la 10% kwa sukari", True, "apply_discount"),
    ("ongezea mafuta", True, "restock_alert"),
    ("uza 999 kg ya mchele", False, None),
    ("uza 2 kg ya nonexistentproduct", False, None),
    ("bei gani ya nonexistentproduct", False, None),
    ("rudisha mchele", True, "resolve_refund_by_product"),
    ("rudisha mafuta", False, None),
    ("sukari ni nzuri", False, None),
    ("habari za asubuhi", False, None),
    ("asante sana", False, None),
]


if __name__ == "__main__":
    print("=== Day 5: agent.py scenario runner ===\n")
    db = setup_db("data/shop_scenarios.db")
    agent = Agent(db)

    passed = 0
    fast_path_count = 0
    results_log = []

    for text, expected_success, expected_action in SCENARIOS:
        result = agent.process_message(text)
        ok = result["success"] == expected_success
        if expected_action is not None:
            ok = ok and result.get("action") == expected_action
        if result.get("layer") == "fast-path":
            fast_path_count += 1

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"{status}: '{text}' -> success={result['success']}, layer={result.get('layer')}, "
              f"action={result.get('action')}, error={result.get('error', '')[:60]}")
        results_log.append({"input": text, "ok": ok, "result": result})

    total = len(SCENARIOS)
    print(f"\n{passed}/{total} scenarios behaved as expected = {passed/total*100:.1f}%")
    print(f"Fast-path bypass rate: {fast_path_count}/{total} = {fast_path_count/total*100:.1f}%")

    db.close()

    if passed < total:
        print("\n--- Scenarios that did NOT behave as expected: ---")
        for r in results_log:
            if not r["ok"]:
                print(f"  '{r['input']}' -> {r['result']}")
        sys.exit(1)
