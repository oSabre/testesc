#!/usr/bin/env bash
#
# run_routing_study.sh -- a vantagem das irregulares vem do CONTROLE ou da TOPOLOGIA?
#
# Reavalia as MESMAS topologias (mesh, small-world, melhores GAs ja treinados)
# sob tres modelos de controle, nos 3 padroes, em seeds novas:
#   dijkstra  : modelo original (heap, custo depende da topologia)
#   bfs       : BFS, custo fixo por operacao (quase independente da topologia)
#   bfs_free  : BFS com custo ZERO de computacao (controle ideal => so topologia)
# Sem retreinar os GAs. Requer o main.exe novo (routing_algorithm).
#
# USO (pasta com main.exe, configs/, runs/ e os scripts):
#   ./run_routing_study.sh
#   ALGS="bfs bfs_free" REPLICAS=10 EARLY_EXIT=false ./run_routing_study.sh
# Saidas: final_eval_route_<alg>.csv (+ _summary.csv), retries_route_<alg>_<padrao>.csv
set -euo pipefail
PYTHON_BIN=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PYTHON_BIN="$c"; break; }; done
[ -z "$PYTHON_BIN" ] && { echo "ERRO: Python nao encontrado." >&2; exit 1; }

BIN="${BIN:-./main.exe}"
CFG_DIR="${CFG_DIR:-configs/configs_ciclos}"
MESH="${MESH:-$CFG_DIR/config_mesh_64.json}"
SW="${SW:-$CFG_DIR/config_irregular_smallworld_64.json}"
ALGS="${ALGS:-dijkstra bfs bfs_free}"
CU="${CU:-16}"
DURATION_US="${DURATION_US:-150}"
SPACING_NS="${SPACING_NS:-800}"
EARLY_EXIT="${EARLY_EXIT:-false}"     # mesmo regime do passo 1 (sem saida antecipada)
REPLICAS="${REPLICAS:-10}"
WORKERS="${WORKERS:-4}"
SEED_START="${SEED_START:-1000}"
TAG="${TAG:-noee_}"                    # prefixo das runs treinadas (RUN_TAG da bateria)
RETRIES="${RETRIES:-1}"
EXTRA_NP="${EXTRA_NP:-}"     # ex.: EXTRA_NP="reserve_dst_port=true"
OUT_TAG="${OUT_TAG:-}"       # ex.: OUT_TAG="rdp_" (evita sobrescrever saidas anteriores)

EXTRAS=(--extra "mesh:$MESH" --extra "smallworld:$SW")
LABELED=("mesh:$MESH" "smallworld:$SW")
for pair in "gaBF:${TAG}butterfly_cu${CU}_ga_random" "gaBR:${TAG}bit_reversal_cu${CU}_ga_random" \
            "gaMIX:${TAG}mix_cu${CU}_ga_seeded" "rsMIX:${TAG}mix_cu${CU}_random_search"; do
  lab="${pair%%:*}"; dir="runs/${pair#*:}/best_config.json"
  if [ -f "$dir" ]; then EXTRAS+=(--extra "$lab:$dir"); LABELED+=("$lab:$dir"); else echo "[aviso] $dir nao existe; pulando $lab"; fi
done

for alg in $ALGS; do
  echo "=================== routing_algorithm=$alg ==================="
  NP=(--np "routing_algorithm=$alg" --np "dijkstra_early_exit=$EARLY_EXIT")
  for kv in $EXTRA_NP; do NP+=(--np "$kv"); done
  "$PYTHON_BIN" ga_final_eval.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
      --cus "$CU" --duration-us "$DURATION_US" --spacing-ns "$SPACING_NS" "${NP[@]}" \
      --replicas "$REPLICAS" --seed-start "$SEED_START" "${EXTRAS[@]}" --ref mesh \
      --cache-dir "runs/_final_cache_route_${OUT_TAG}${alg}" --out "final_eval_route_${OUT_TAG}${alg}"
  if [ "$RETRIES" = "1" ]; then
    for p in uniform bit_reversal butterfly; do
      "$PYTHON_BIN" ga_retries.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
          --cus "$CU" --duration-us "$DURATION_US" --spacing-ns "$SPACING_NS" "${NP[@]}" \
          --traffic "$p" --replicas 5 --tag "route_${OUT_TAG}${alg}_" "${LABELED[@]}" | tail -8
    done
  fi
done
echo "Pronto. Compare final_eval_route_*_summary.csv e final_eval_route_*.csv"