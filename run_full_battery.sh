#!/usr/bin/env bash
#
# run_full_battery.sh
#
# Roda a bateria completa: 8 topologias (mesh/fewlinks/morelinks/
# smallworld x 16/64 nos) x 3 padroes de trafego (uniform/bit_reversal/
# butterfly) = 24 combinacoes, cada uma com N replicas (seeds diferentes).
#
# No final, agrega tudo e gera os graficos de barra via
# battery_aggregate_and_plot.py.
#
# PRE-REQUISITOS:
#   1. Rodar antes (uma vez): 
#        python3 topology_generator.py
#        python3 battery_config_generator.py
#      Isso gera os 8 config_*.json base + os 24 config_battery_*.json +
#      o battery_manifest.txt que este script consome.
#   2. matplotlib instalado (para os graficos): 
#        pip install matplotlib --break-system-packages
#      (ou no MSYS2/MinGW64: pacman -S mingw-w64-x86_64-python-matplotlib)
#
# USO:
#   ./run_full_battery.sh <num_replicas> [seed_inicial]
#
# EXEMPLO:
#   ./run_full_battery.sh 5 1
#
# Isso roda 24 x 5 = 120 execucoes do simulador. Ajuste num_replicas para
# baixo (ex: 2-3) numa primeira rodada de teste, e para cima (10+) na
# rodada final que vai virar grafico/tabela do trabalho.

set -euo pipefail

# --- Deteccao do interpretador Python (mesmo mecanismo dos scripts anteriores) ---
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
MANIFEST="battery_manifest.txt"

NUM_REPLICAS="${1:?uso: run_full_battery.sh <num_replicas> [seed_inicial]}"
SEED_START="${2:-1}"

if [ ! -f "$MANIFEST" ]; then
    echo "ERRO: '$MANIFEST' nao encontrado." >&2
    echo "Rode antes: python3 topology_generator.py && python3 battery_config_generator.py" >&2
    exit 1
fi

OUT_DIR="battery_out"
mkdir -p "$OUT_DIR"

# Conta quantas combinacoes existem (menos a linha de cabecalho) so para
# mostrar progresso "combinacao X/24".
TOTAL_COMBOS=$(($(wc -l < "$MANIFEST") - 1))
COMBO_IDX=0

echo "Bateria completa: $TOTAL_COMBOS combinacoes x $NUM_REPLICAS replicas " \
     "= $((TOTAL_COMBOS * NUM_REPLICAS)) execucoes."
echo ""

# Le o manifest (pulando o cabecalho) e itera linha a linha.
tail -n +2 "$MANIFEST" | while IFS=$'\t' read -r config_file topology size traffic; do
    # Remove um eventual "\r" residual no final do ultimo campo (arquivo
    # de manifest salvo com fim de linha CRLF, comum no Windows). Inofensivo
    # se nao houver "\r" nenhum.
    config_file="${config_file%$'\r'}"
    topology="${topology%$'\r'}"
    size="${size%$'\r'}"
    traffic="${traffic%$'\r'}"

    COMBO_IDX=$((COMBO_IDX + 1))
    combo_dir="$OUT_DIR/${topology}_${size}_${traffic}"
    mkdir -p "$combo_dir"

    echo "--- [$COMBO_IDX/$TOTAL_COMBOS] $topology (${size} nos) / $traffic ---"

    if [ ! -f "$config_file" ]; then
        echo "  AVISO: '$config_file' nao encontrado, pulando esta combinacao." >&2
        continue
    fi

    for i in $(seq 0 $((NUM_REPLICAS - 1))); do
        seed=$((SEED_START + i))
        run_config="$combo_dir/config_seed${seed}.json"
        run_output="$combo_dir/results_seed${seed}.csv"

        "$PYTHON_BIN" - "$config_file" "$run_config" "$seed" "$run_output" <<'PYEOF'
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

        cp "$run_config" config.json
        "$BIN" > "$combo_dir/log_seed${seed}.txt" 2>&1 || {
            echo "  ERRO: simulacao falhou (seed=$seed). Veja $combo_dir/log_seed${seed}.txt" >&2
        }
    done
    echo ""
done

echo "Todas as combinacoes rodadas. Agregando resultados e gerando graficos..."
echo ""

"$PYTHON_BIN" battery_aggregate_and_plot.py "$OUT_DIR"