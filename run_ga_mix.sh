#!/usr/bin/env bash
#
# run_ga_mix.sh -- GA GENERALISTA: otimiza uma unica topologia para os 3 padroes
# ao mesmo tempo (fitness = media das razoes latencia/latencia_da_mesh).
# Testa se existe topologia irregular melhor que a mesh EM GERAL.
#
# Executa, para cada nº de CUs:
#   1) GA mix semeado (best_edges das execucoes por padrao + mesh + small-world)
#   2) GA mix so com populacao aleatoria
#   3) busca aleatoria mix (mesmo orcamento)
#   4) avaliacao final (seeds novas) com TODAS as candidatas nos 3 padroes
#
# Use as MESMAS variaveis do run_ga_battery.sh para o cenario desejado, ex.:
#   RUN_TAG="noee_" NP_OVERRIDES="dijkstra_early_exit=false" CUS="16" \
#     DURATION_US=150 SPACING_NS=800 POP=20 GENS=30 ./run_ga_mix.sh
# (RUN_TAG deve ser o mesmo usado nas execucoes por padrao, para semear o GA.)
# Custo: 3 padroes x seeds de treino simulacoes por topologia avaliada.
set -euo pipefail

PYTHON_BIN=""
for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1; then PYTHON_BIN="$c"; break; fi
done
[ -z "$PYTHON_BIN" ] && { echo "ERRO: Python nao encontrado." >&2; exit 1; }

BIN="${BIN:-./main.exe}"
CFG_DIR="${CFG_DIR:-configs/configs_ciclos}"
CUS="${CUS:-16}"
POP="${POP:-20}"
GENS="${GENS:-30}"
WORKERS="${WORKERS:-4}"
TRAIN_SEEDS="${TRAIN_SEEDS:-1 2 3}"
REPLICAS="${REPLICAS:-10}"
PATTERNS="${PATTERNS:-uniform bit_reversal butterfly}"   # padroes do objetivo mix
MESH="${MESH:-$CFG_DIR/config_mesh_64.json}"
SW="${SW:-$CFG_DIR/config_irregular_smallworld_64.json}"
RUN_TAG="${RUN_TAG:-}"
EXTRA=()
[ -n "${DURATION_US:-}" ] && EXTRA+=(--duration-us "$DURATION_US")
[ -n "${NUM_PACKETS:-}" ] && EXTRA+=(--num-packets "$NUM_PACKETS")
[ -n "${SPACING_NS:-}" ] && EXTRA+=(--spacing-ns "$SPACING_NS")
for kv in ${NP_OVERRIDES:-}; do EXTRA+=(--np "$kv"); done
COMMON=(--bin "$BIN" --template "$MESH" --workers "$WORKERS" "${EXTRA[@]}")

for cu in $CUS; do
  tag="${RUN_TAG}mix_cu${cu}"
  echo "=================== $tag ==================="
  SEED_DIRS=()
  for p in $PATTERNS; do SEED_DIRS+=("runs/${RUN_TAG}${p}_cu${cu}_ga_*"); done
  "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic mix --mix-patterns $PATTERNS --cus "$cu" \
      --algo ga --init seeded --seed-dirs "${SEED_DIRS[@]}" --refs "$MESH" "$SW" \
      --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS --name "${tag}_ga_seeded"
  "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic mix --mix-patterns $PATTERNS --cus "$cu" \
      --algo ga --init random --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
      --name "${tag}_ga_random"
  "$PYTHON_BIN" ga_optimize.py "${COMMON[@]}" --traffic mix --mix-patterns $PATTERNS --cus "$cu" \
      --algo random_search --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
      --name "${tag}_random_search"

  echo "=================== AVALIACAO FINAL GENERALISTA (cu=$cu) ==================="
  DIRS=("runs/${tag}_*")
  for p in $PATTERNS; do DIRS+=("runs/${RUN_TAG}${p}_cu${cu}_*"); done
  "$PYTHON_BIN" ga_final_eval.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
      --cus "$cu" "${EXTRA[@]}" --replicas "$REPLICAS" --seed-start 1000 \
      --run-dirs "${DIRS[@]}" \
      --extra "mesh:$MESH" --extra "smallworld:$SW" --ref mesh \
      --cache-dir "runs/_final_cache_${RUN_TAG}mix" \
      --out "final_eval_${RUN_TAG}mix_cu${cu}"
done
echo "Pronto. Veja final_eval_*mix_cu*.csv e *_summary.csv (media dos padroes)."