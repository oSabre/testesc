#!/usr/bin/env bash
#
# run_random_battery.sh
#
# Roda as topologias aleatorias geradas por random_topology_generator.py
# (cada uma ja vem com traffic.mode="uniform" pronto no config), com N
# replicas cada, e no final chama o script de comparacao contra as
# topologias desenhadas a mao.
#
# PRE-REQUISITO: rodar antes (uma vez):
#   python3 random_topology_generator.py 50 64 112 1000
#
# USO:
#   ./run_random_battery.sh <num_replicas> [seed_inicial_das_replicas]
#
# EXEMPLO (recomendado para a primeira rodada exploratoria):
#   ./run_random_battery.sh 3 1
#
# Nota: "seed_inicial_das_replicas" aqui é a seed do JITTER de retry (via
# simulation.seed), diferente da seed que identifica CADA topologia
# aleatoria (essa ja esta fixada por topologia no proprio config, via
# random_topology_generator.py). Ou seja: para cada uma das 50 topologias,
# rodamos N replicas variando so o jitter, exatamente como fizemos antes
# para mesh/small-world/etc.

set -euo pipefail

PYTHON_BIN=""
for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "ERRO: nenhum interpretador Python encontrado (tentei: python3, python, py)." >&2
    exit 1
fi

echo "Usando interpretador Python: $PYTHON_BIN ($(command -v "$PYTHON_BIN"))"

BIN="./main.exe"   # AJUSTE para o nome/caminho do seu executavel
MANIFEST="${3:-random_manifest_112.txt}"
OUT_DIR="${4:-random_out_112}"

NUM_REPLICAS="${1:?uso: run_random_battery.sh <num_replicas> [seed_inicial] [manifest] [out_dir]}"
SEED_START="${2:-1}"

if [ ! -f "$MANIFEST" ]; then
    echo "ERRO: '$MANIFEST' nao encontrado." >&2
    echo "Rode antes: python3 random_topology_generator.py 50 64 <links> <seed_inicial_topologias>" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

TOTAL_TOPOS=$(($(wc -l < "$MANIFEST") - 1))
IDX=0

echo "Bateria aleatoria: $TOTAL_TOPOS topologias x $NUM_REPLICAS replicas " \
     "= $((TOTAL_TOPOS * NUM_REPLICAS)) execucoes."
echo ""

tail -n +2 "$MANIFEST" | while IFS=$'\t' read -r config_file label num_nodes; do
    # Defesa contra CRLF residual (ver historico: manifest gerado no
    # Windows pode trazer "\r" grudado no ultimo campo).
    config_file="${config_file%$'\r'}"
    label="${label%$'\r'}"
    num_nodes="${num_nodes%$'\r'}"

    IDX=$((IDX + 1))
    combo_dir="$OUT_DIR/$label"
    mkdir -p "$combo_dir"

    echo "--- [$IDX/$TOTAL_TOPOS] $label ($num_nodes nos) ---"

    if [ ! -f "$config_file" ]; then
        echo "  AVISO: '$config_file' nao encontrado, pulando." >&2
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

        cp "$run_config" config.json
        "$BIN" > "$combo_dir/log_seed${seed}.txt" 2>&1 || {
            echo "  ERRO: simulacao falhou (seed=$seed). Veja $combo_dir/log_seed${seed}.txt" >&2
        }
    done
    echo "  ${NUM_REPLICAS} replicas concluidas."
done

echo ""
echo "Bateria aleatoria concluida (resultados em $OUT_DIR/)."
echo ""
echo "Para comparar contra as topologias desenhadas, rode (ajustando o"
echo "orcamento de links certo para este lote):"
echo ""
echo "  $PYTHON_BIN compare_random_vs_designed.py $OUT_DIR \\"
echo "    mesh:battery_out/mesh_64_uniform:112 \\"
echo "    smallworld:battery_out/smallworld_64_uniform:112"
echo ""
echo "(ou fewlinks:battery_out/fewlinks_64_uniform:93 / "
echo " morelinks:battery_out/morelinks_64_uniform:128, dependendo do "
echo " orcamento deste lote)"