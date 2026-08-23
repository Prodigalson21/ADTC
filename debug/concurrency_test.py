"""
concurrency_test.py -- Day 5 validation: scale + barcode + NL agent
queries running simultaneously against the same shared Database.
"""
import sys, os, threading, time
sys.path.insert(0, ".")
from src.database import Database
from src.agent import Agent
from src.scale_reader import get_scale
from src.barcode_scanner import BarcodeScanner
import src.business_logic as business_logic


def setup_db(path):
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(path + ext):
            os.remove(path + ext)
    db = Database(path)
    business_logic.register_product(db, "mchele", "kg", 2000, 1000.0, "food")
    return db


def scale_worker(scale, iterations, errors):
    try:
        for _ in range(iterations):
            scale.read()
            time.sleep(0.01)
    except Exception as e:
        errors.append(f"scale_worker: {e}")


def barcode_worker(scanner, iterations, errors):
    try:
        for _ in range(iterations):
            scanner.get_latest()
            time.sleep(0.01)
    except Exception as e:
        errors.append(f"barcode_worker: {e}")


def agent_worker(agent, iterations, errors, results):
    try:
        for i in range(iterations):
            result = agent.process_message("uza 1 kg ya mchele")
            results.append(result["success"])
            time.sleep(0.01)
    except Exception as e:
        errors.append(f"agent_worker: {e}")


if __name__ == "__main__":
    print("=== Day 5: concurrency test ===\n")

    db = setup_db("data/shop_concurrency.db")
    agent = Agent(db)
    scale = get_scale()
    scanner = BarcodeScanner()
    scanner.start()

    errors = []
    results = []
    ITERATIONS = 30

    threads = [
        threading.Thread(target=scale_worker, args=(scale, ITERATIONS, errors)),
        threading.Thread(target=barcode_worker, args=(scanner, ITERATIONS, errors)),
        threading.Thread(target=agent_worker, args=(agent, ITERATIONS, errors, results)),
    ]

    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.monotonic() - start

    print(f"Ran for {elapsed:.2f}s with 3 concurrent workers, {ITERATIONS} iterations each")
    print(f"Errors encountered: {len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}")

    successful_sales = sum(1 for r in results if r)
    print(f"Agent sales completed successfully during concurrent load: {successful_sales}/{len(results)}")

    db.close()

    if errors:
        print("\nFAIL: concurrency test found real errors")
        sys.exit(1)
    else:
        print("\nPASS: no errors under concurrent scale + barcode + agent load")
