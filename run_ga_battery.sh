#!/usr/bin/env bash
#
# run_ga_battery.sh -- bateria completa do estudo GA (latencia, mono-objetivo)
#
# Para cada padrao de trafego (uniform, bit_reversal, butterfly) e cada
# numero de CUs informado:
#   1) ga_select_topk.py   top-k aleatorias, reavaliadas em seeds novas
#   2) ga_optimize.py      GA semeado (top-k + mesh + small-world)
#   3) ga_optimize.py      GA so com populacao aleatoria (controle)
#   4) ga_optimize.py      busca aleatoria (mesmo orcamento de avaliacoes)
# Ao final, ga_final_eval.py reavalia tudo em seeds NOVAS nos 3 padroes
# (matriz de generalizacao) com testes de Welch vs mesh.
#
# USO (na pasta onde estao main.exe, configs/ e estes scripts):
#   ./run_ga_battery.sh                       # padrao: CUS="1 2"
#   CUS="2" POP=20 GENS=20 ./run_ga_battery.sh
#   BIN="python3 mock_sim.py" ./run_ga_battery.sh   # teste rapido sem SystemC
#
# Variaveis: NP_OVERRIDES, RUN_TAG, OBJECTIVE (total|data), SPACING_NS (carga), BIN, CFG_DIR, CUS, POP, GENS, WORKERS, TRAIN_SEEDS, REPLICAS,
#            PATTERNS, DURATION_US, NUM_PACKETS, MESH, SW, PRE, KEEP
set -euo pipefail

PYTHON_BIN=""
for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1; then PYTHON_BIN="$c"; break; fi
done
[ -z "$PYTHON_BIN" ] && { echo "ERRO: Python nao encontrado." >&2; exit 1; }

BIN="${BIN:-./main.exe}"
CFG_DIR="${CFG_DIR:-configs/configs_ciclos}"
CUS="${CUS:-1 2}"
POP="${POP:-30}"
GENS="${GENS:-40}"
WORKERS="${WORKERS:-4}"
TRAIN_SEEDS="${TRAIN_SEEDS:-1 2 3}"
REPLICAS="${REPLICAS:-10}"
PATTERNS="${PATTERNS:-uniform bit_reversal butterfly}"
MESH="${MESH:-$CFG_DIR/config_mesh_64.json}"
SW="${SW:-$CFG_DIR/config_irregular_smallworld_64.json}"
PRE="${PRE:-15}"
KEEP="${KEEP:-10}"
EXTRA=()
[ -n "${DURATION_US:-}" ] && EXTRA+=(--duration-us "$DURATION_US")
[ -n "${NUM_PACKETS:-}" ] && EXTRA+=(--num-packets "$NUM_PACKETS")
[ -n "${SPACING_NS:-}" ] && EXTRA+=(--spacing-ns "$SPACING_NS")
[ -n "${OBJECTIVE:-}" ] && EXTRA+=(--objective "$OBJECTIVE")
# NP_OVERRIDES="chave=valor chave2=valor2" -> --np (ex.: dijkstra_early_exit=false)
for kv in ${NP_OVERRIDES:-}; do EXTRA+=(--np "$kv"); done
RUN_TAG="${RUN_TAG:-}"   # prefixo dos nomes (evita sobrescrever execucoes anteriores)

COMMON=(--bin "$BIN" --template "$MESH" --workers "$WORKERS" "${EXTRA[@]}")

for cu in $CUS; do
  for pat in $PATTERNS; do
    tag="${RUN_TAG}${pat}_cu${cu}"
    echo "=================== $tag ==================="
    "$PYTHON_BIN" ga_select_topk.py "${COMMON[@]}" --traffic "$pat" --cus "$cu" \
        --config-dir "$CFG_DIR" --train-seeds $TRAIN_SEEDS --pre "$PRE" --keep "$KEEP" \
        --out "topk_${tag}.json"
    "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic "$pat" --cus "$cu" \
        --algo ga --init seeded --seeds-file "topk_${tag}.json" --n-seeds "$KEEP" \
        --refs "$MESH" "$SW" --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
        --name "${tag}_ga_seeded"
    "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic "$pat" --cus "$cu" \
        --algo ga --init random --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
        --name "${tag}_ga_random"
    "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic "$pat" --cus "$cu" \
        --algo random_search --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
        --name "${tag}_random_search"
  done

  echo "=================== AVALIACAO FINAL (cu=$cu) ==================="
  # candidatas = melhores de cada execucao deste numero de CUs + referencias
  DIRS=()
  for p in $PATTERNS; do DIRS+=("runs/${RUN_TAG}${p}_cu${cu}_*"); done
  "$PYTHON_BIN" ga_final_eval.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
      --cus "$cu" "${EXTRA[@]}" --replicas "$REPLICAS" --seed-start 1000 \
      --run-dirs "${DIRS[@]}" \
      --extra "mesh:$MESH" --extra "smallworld:$SW" --ref mesh \
      --out "final_eval_${RUN_TAG}cu${cu}"
done
echo "Pronto. Resultados: runs/*/, final_eval_cu*.csv/.png"