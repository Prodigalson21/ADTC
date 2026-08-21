Day 3: inference_backend.py measured Peak RSS = 3430.5 MB (idle, model loaded, no generation yet)

## Day 3 correction (final)
Original compile included llama.cpp's REPACK optimization by default,
which converts q4_K weights to q4_K_8x8 (a CPU-SIMD-friendly layout)
at load time -- this added ~1 GB of RAM (measured Peak RSS 3430.5 MB).
Recompiled with CMAKE_ARGS="-DGGML_AVX2=on -DGGML_CPU_REPACK=OFF".
Confirmed via verbose load log: zero "repack:" lines present (vs.
dozens before). New measured Peak RSS: 2165.2 MB -- better than the
framework's original 2400 MB estimate. This is the final number for
REPORT.md, replacing both the original estimate and the earlier
(repacked) 3430.5 MB measurement.
