
"""
inference_backend.py -- wraps llama-cpp-python for Qwen2.5-3B-Instruct.

llama_cpp is imported lazily so this file's non-model logic (thermal
thread-count adaptation) can be tested without the compiled library
being present.
"""

import os

try:
    import psutil
except ImportError:
    psutil = None

DEFAULT_MODEL_PATH = "models/qwen2.5-3b-instruct-q4_k_m.gguf"
DEFAULT_SEED = 42

THERMAL_WARM_C = 75.0
THERMAL_HOT_C = 85.0  # matches the framework's own throttling penalty threshold


def get_cpu_temperature() -> float | None:
    """Returns current CPU temperature in Celsius, or None if it can't
    be read (e.g. inside a VM -- a known, expected limitation)."""
    if psutil is None:
        return None
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        return None
    return None


def adaptive_thread_count(base_threads: int = 4) -> int:
    """Reduce thread count if the CPU is running hot. Returns
    base_threads unchanged if temperature can't be read."""
    temp = get_cpu_temperature()
    if temp is None:
        return base_threads
    if temp >= THERMAL_HOT_C:
        return max(1, base_threads // 2)
    if temp >= THERMAL_WARM_C:
        return max(2, base_threads - 1)
    return base_threads


class InferenceBackend:
    """Wraps a loaded Qwen2.5-3B-Instruct GGUF model. Instantiating
    this loads the model into memory -- don't create more than one per
    process."""

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, base_threads: int = 4):
        from llama_cpp import Llama

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file not found at {model_path}. Download it first."
            )

        self.base_threads = base_threads
        self._llama = Llama(
            model_path=model_path,
            n_threads=adaptive_thread_count(base_threads),
            seed=DEFAULT_SEED,
            n_ctx=2048,
            verbose=False,
        )

    def generate(self, prompt: str, grammar_path: str | None = None, max_tokens: int = 512) -> str:
        kwargs = {"max_tokens": max_tokens}
        if grammar_path:
            from llama_cpp import LlamaGrammar
            with open(grammar_path, "r") as f:
                grammar_text = f.read()
            kwargs["grammar"] = LlamaGrammar.from_string(grammar_text)

        result = self._llama(prompt, **kwargs)
        return result["choices"][0]["text"]

    def generate_json(self, prompt: str, grammar_path: str) -> dict:
        """Generate with a GBNF grammar constraining output to valid
        JSON, then parse it. Raises json.JSONDecodeError if the model
        somehow still produced invalid JSON -- callers should treat
        that as a Layer 3 failure and fall through to menu mode, not
        crash."""
        import json
        raw = self.generate(prompt, grammar_path=grammar_path)
        return json.loads(raw)


if __name__ == "__main__":
    print("=== inference_backend.py self-test (thermal logic only) ===")

    temp = get_cpu_temperature()
    print(f"Detected CPU temperature: {temp}")
    threads = adaptive_thread_count(base_threads=4)
    if temp is None:
        assert threads == 4
        print(f"OK: no thermal sensor, defaults to base ({threads} threads)")
    else:
        print(f"OK: real sensor read {temp}C, adapted -> {threads} threads")

    import unittest.mock as mock
    with mock.patch("__main__.get_cpu_temperature", return_value=90.0):
        assert adaptive_thread_count(4) == 2
        print("OK: simulated 90C (hot) -> 2 threads")
    with mock.patch("__main__.get_cpu_temperature", return_value=78.0):
        assert adaptive_thread_count(4) == 3
        print("OK: simulated 78C (warm) -> 3 threads")
    with mock.patch("__main__.get_cpu_temperature", return_value=45.0):
        assert adaptive_thread_count(4) == 4
        print("OK: simulated 45C (cool) -> 4 threads")

    print("\nThermal logic self-tests passed.")
    print("Now testing REAL model load -- this needs the compiled")
    print("llama_cpp library and the downloaded .gguf file.")

    try:
        backend = InferenceBackend()
        response = backend.generate("Say hello in one short sentence.", max_tokens=30)
        print(f"\nModel loaded successfully. Sample output:\n{response}")
    except FileNotFoundError as e:
        print(f"\nModel file not found yet -- expected until it's downloaded: {e}")
    except ImportError as e:
        print(f"\nllama_cpp not compiled yet -- expected until compile step runs: {e}")
