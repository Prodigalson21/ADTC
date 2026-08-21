"""
profiler.py -- measures real RAM usage (RSS) of this process over time.
Used to check inference_backend.py's actual memory footprint against
the Master Framework's §4.1 budget targets (~4.54 GB corrected total).

Usage: python debug/profiler.py --component <name>
"""

import argparse
import time
import psutil
import os


def measure_current_process(duration_seconds: float = 5.0, interval: float = 0.5):
    process = psutil.Process(os.getpid())
    samples = []
    start = time.monotonic()
    while time.monotonic() - start < duration_seconds:
        rss_mb = process.memory_info().rss / (1024 * 1024)
        samples.append(rss_mb)
        time.sleep(interval)
    return {
        "peak_mb": round(max(samples), 1) if samples else 0.0,
        "final_mb": round(samples[-1], 1) if samples else 0.0,
        "samples": len(samples),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", default="unknown")
    parser.add_argument("--duration", type=float, default=5.0)
    args = parser.parse_args()

    print(f"=== profiling '{args.component}' for {args.duration}s ===")
    result = measure_current_process(duration_seconds=args.duration)
    print(f"Peak RSS: {result['peak_mb']} MB")
    print(f"Final RSS: {result['final_mb']} MB")
    print("\nCompare against the Master Framework's §4.1 corrected targets (~4.54 GB total).")
    print("Log this number in CHANGELOG.md -- measured, not estimated.")
