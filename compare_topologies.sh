#!/usr/bin/env bash
#
# compare_topologies.sh
#
# Roda N replicas para CADA topologia informada (variando simulation.seed
# igual ao run_replicas.sh) e imprime uma comparacao lado a lado entre elas
# no final (taxa de conclusao e latencia media, com media + desvio padrao
# entre as replicas de cada topologia).
#
# Reaproveita a mesma logica do run_replicas.sh (patch de JSON via Python,
# deteccao automatica do interpretador Python disponivel), so generalizada
# para varias topologias em vez de uma so.
#
# USO:
#   ./compare_topologies.sh <num_replicas> [seed_inicial] rotulo1:config1.json rotulo2:config2.json ...
#
# EXEMPLO:
#   ./compare_topologies.sh 5 1 mesh:config_mesh.json irregular:config_irregular_smallworld.json
#
# PRE-REQUISITO: cada config*.json deve ja ter os mesmos network_params/
# traffic/simulation -- so a topologia deve diferir entre eles. Rode
# topology_validator.py em cada um antes, para garantir que sao
# comparaveis (mesmo numero de nos/links, grau dentro do limite).

set -euo pipefail

# --- Deteccao do interpretador Python (mesmo mecanismo do run_replicas.sh) ---
PYTHON_BIN=""
for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "ERRO: nenhum interpretador Python encontrado (tentei: python3, python, py)." >&2
    echo "No MSYS2/MinGW64, instale com: pacman -S mingw-w64-x86_64-python" >&2
    exit 1
fi

echo "Usando interpretador Python: $PYTHON_BIN ($(command -v "$PYTHON_BIN"))"

BIN="./main.exe"   # ajuste para o nome/caminho do seu executavel

NUM_REPLICAS="${1:?uso: compare_topologies.sh <num_replicas> [seed_inicial] rotulo1:config1.json rotulo2:config2.json ...}"
shift

# O segundo argumento so eh seed_inicial se NAO tiver ":" (ou seja, nao for
# um par rotulo:arquivo). Caso contrario, assume seed_inicial=1.
SEED_START=1
if [[ "${1:-}" != *:* ]]; then
    SEED_START="${1:?informe seed_inicial ou o primeiro rotulo:config.json}"
    shift
fi

if [ "$#" -eq 0 ]; then
    echo "ERRO: informe ao menos um par rotulo:config.json" >&2
    exit 1
fi

OUT_DIR="compare_out"
mkdir -p "$OUT_DIR"

echo "Rodando $NUM_REPLICAS replicas (seed inicial=$SEED_START) para $# topologia(s)..."
echo ""

# Guarda "rotulo:diretorio_de_resultados" para a agregacao final
declare -a LABEL_DIRS=()

for pair in "$@"; do
    label="${pair%%:*}"
    base_config="${pair#*:}"

    if [ ! -f "$base_config" ]; then
        echo "ERRO: config '$base_config' (topologia '$label') nao encontrado." >&2
        exit 1
    fi

    topo_dir="$OUT_DIR/$label"
    mkdir -p "$topo_dir"
    LABEL_DIRS+=("$label:$topo_dir")

    echo "--- Topologia: $label ($base_config) ---"

    for i in $(seq 0 $((NUM_REPLICAS - 1))); do
        seed=$((SEED_START + i))
        run_config="$topo_dir/config_seed${seed}.json"
        run_output="$topo_dir/results_seed${seed}.csv"

        "$PYTHON_BIN" - "$base_config" "$run_config" "$seed" "$run_output" <<'PYEOF'
import json, sys

base_path, out_path, seed, out_csv = sys.argv[1:5]

with open(base_path) as f:
    cfg = json.load(f)

cfg.setdefault("simulation", {})
cfg["simulation"]["seed"] = int(seed)
cfg["simulation"]["output_file"] = out_csv

with open(out_path, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF

        echo "  [replica $((i+1))/$NUM_REPLICAS] seed=$seed -> $run_output"

        # main.cpp le "config.json" com nome fixo no diretorio atual.
        cp "$run_config" config.json
        "$BIN"
    done
    echo ""
done

echo "Agregando e comparando topologias..."
echo ""

"$PYTHON_BIN" - "${LABEL_DIRS[@]}" <<'PYEOF'
import csv, glob, sys, statistics as st

label_dirs = sys.argv[1:]

results = {}  # label -> {"latency": [...], "completion": [...]}

for entry in label_dirs:
    label, topo_dir = entry.split(":", 1)
    latencies = []
    completion_rates = []

    for path in sorted(glob.glob(f"{topo_dir}/results_seed*.csv")):
        with open(path, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                if row[0].startswith("Latencia media regime permanente"):
                    try:
                        latencies.append(float(row[1]))
                    except ValueError:
                        pass
                if row[0].startswith("Taxa de conclusao"):
                    try:
                        completion_rates.append(float(row[1]))
                    except ValueError:
                        pass

    results[label] = {"latency": latencies, "completion": completion_rates}


def mean_std(values):
    if not values:
        return None, None
    mean = st.mean(values)
    stdev = st.stdev(values) if len(values) > 1 else 0.0
    return mean, stdev


print("=" * 72)
print(f"{'Topologia':<20} {'N':>3} {'Lat. media (ns)':>22} {'Taxa conclusao (%)':>22}")
print("-" * 72)
for label, data in results.items():
    n = len(data["latency"])
    lat_mean, lat_std = mean_std(data["latency"])
    comp_mean, comp_std = mean_std(data["completion"])

    lat_str = f"{lat_mean:.2f} +/- {lat_std:.2f}" if lat_mean is not None else "N/A"
    comp_str = f"{comp_mean:.2f} +/- {comp_std:.2f}" if comp_mean is not None else "N/A"

    print(f"{label:<20} {n:>3} {lat_str:>22} {comp_str:>22}")
print("=" * 72)
print()
print("Nota: valores sao media +/- desvio padrao entre as replicas de cada topologia.")
print("Confira tambem se a taxa de conclusao esta proxima de 100%% nas duas antes de")
print("comparar latencia -- taxas muito diferentes tornam a comparacao de latencia")
print("enviesada (topologia com mais descartes tende a mostrar latencia media MENOR,")
print("so porque os fluxos mais dificeis nunca completaram para entrar na media).")
PYEOF