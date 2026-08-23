"""
thermal_bench.py -- Day 5 validation: sustained-load thermal check.
Honest about WSL2/VM sensor limitations rather than faking a number.
"""
import sys, os, argparse, time, csv
sys.path.insert(0, ".")
from src.inference_backend import get_cpu_temperature, adaptive_thread_count

try:
    import psutil
except ImportError:
    psutil = None


def run_thermal_bench(duration_seconds, log_path, sample_interval=5.0):
    samples = []
    start = time.monotonic()
    sensor_available = get_cpu_temperature() is not None

    print(f"Sensor data available on this machine: {sensor_available}")
    if not sensor_available:
        print("No CPU temperature sensor readable here -- expected on WSL2/VMs.")
        print("Real thermal validation needs native target hardware (Day 8).")

    while time.monotonic() - start < duration_seconds:
        temp = get_cpu_temperature()
        threads = adaptive_thread_count(base_threads=4)
        elapsed = time.monotonic() - start
        cpu_percent = psutil.cpu_percent(interval=None) if psutil else None
        samples.append({"elapsed_s": round(elapsed, 1), "temp_c": temp, "threads": threads, "cpu_percent": cpu_percent})
        time.sleep(sample_interval)

    os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else ".", exist_ok=True)
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["elapsed_s", "temp_c", "threads", "cpu_percent"])
        writer.writeheader()
        writer.writerows(samples)

    return samples, sensor_available


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--log", default="logs/thermal_bench.csv")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    print(f"=== Day 5: thermal benchmark, {args.duration}s, sampling every {args.interval}s ===\n")
    samples, sensor_available = run_thermal_bench(args.duration, args.log, args.interval)

    print(f"\n{len(samples)} samples collected, logged to {args.log}")

    if sensor_available:
        temps = [s["temp_c"] for s in samples if s["temp_c"] is not None]
        if temps:
            print(f"Temp range: {min(temps):.1f}C - {max(temps):.1f}C")
            throttle_events = sum(1 for s in samples if s["threads"] < 4)
            print(f"Thermal-adaptive throttle events: {throttle_events}/{len(samples)}")
            if max(temps) >= 85.0:
                print("WARNING: reached/exceeded 85C -- the framework's own throttling threshold.")
    else:
        print("No real sensor data -- log this honestly in REPORT.md/CHANGELOG.md:")
        print("'thermal-adaptive logic implemented and unit-tested, but not")
        print("validated under sustained load on target silicon.'")
