#!/usr/bin/env bash
# Roda o kernel no gem5 para todas as topologias e 3 niveis de ocupacao.
# Uso: GEM5=/home/gabriel/gem5/gem5 [CPU=MINOR|TIMING|O3] bash run_experiments.sh [K=100] [semente=1]
# Resultados: results (MINOR, como antes), results_timing, results_o3
set -e
GEM5=${GEM5:?defina GEM5, ex.: export GEM5=/home/gabriel/gem5/gem5}
K=${1:-100}; SEED=${2:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
CPU=${CPU:-MINOR}; export CPU
case "$CPU" in MINOR) OUT=$HERE/results;; *) OUT=$HERE/results_$(echo "$CPU" | tr A-Z a-z);; esac
mkdir -p "$OUT"; echo "core: $CPU -> $OUT"
PY=${PY:-python3}
[ -d "$HERE/topos" ] || $PY "$HERE/make_topologies.py" --out "$HERE/topos"
riscv64-linux-gnu-g++ -O2 -static -DUSE_M5 -I"$GEM5/include" "$HERE/kernel_routing.cpp" \
    "$GEM5/util/m5/build/riscv/out/libm5.a" -o "$HERE/kernel_rv"
for topo in "$HERE"/topos/*.txt; do
  name=$(basename "$topo" .txt)
  for busy in 0 25 50; do
    run="$OUT/${name}_busy${busy}"
    [ -f "$run/stats.txt" ] && { echo "pula $run"; continue; }
    mkdir -p "$run"
    echo "== $name busy=$busy"
    "$GEM5/build/RISCV/gem5.opt" --outdir="$run" "$HERE/run.py" "$HERE/kernel_rv" \
        "$topo" "$run/calls.csv" "$K" "$SEED" "$busy" > "$run/stdout.txt" 2>&1
  done
done
echo "pronto. Rode: python3 calibrate.py $(basename "$OUT")"