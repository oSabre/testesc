#!/usr/bin/env bash
# Fase 1A: GA e busca aleatoria (single-objective, latencia) com teto de fio, 64 nos, BFS calibrado r=1,
# 16 CUs, rho=0.5 (spacing 6700 ns, janela 1700 us). Retomavel (pula execucoes com summary.json).
# Uso (na pasta do simulador, ex.: ~/tcc/testesc):
#   nohup bash rodar_fase1a.sh > fase1a.log 2>&1 &        # tudo: 3 padroes x 3 tetos x (10 GA + 10 RS)
#   MULTS="1.5" bash rodar_fase1a.sh                      # so um teto
#   PATTERNS="bit_reversal" RUNS=3 bash rodar_fase1a.sh   # teste curto
# Tempo: ~6 min por execucao (12 nucleos) => ~2 h por celula (10 GA + 10 RS), ~18 h para as 9 celulas.
set -u
PY=${PY:-python3}
BIN=${BIN:-./main.exe}
MESH=${MESH:-configs/configs_ciclos/config_mesh_64.json}
SW=${SW:-configs/configs_ciclos/config_irregular_smallworld_64.json}
OUT=${OUT:-runs_fase1}
WORKERS=${WORKERS:-12}
PATTERNS=${PATTERNS:-"bit_reversal butterfly uniform"}
MULTS=${MULTS:-"1.5 2 3"}
RUNS=${RUNS:-10}
POP=${POP:-30}
GENS=${GENS:-40}
SPACING=${SPACING:-6700}
DUR=${DUR:-1700}
CUS=${CUS:-16}
NP="--np routing_algorithm=bfs --np dijkstra_dispatch_cycles=129 --np dijkstra_init_cycles_per_node=1 --np dijkstra_pq_op_cycles=39 --np dijkstra_edge_check_cycles=1 --np control_clock_ratio=1 --np reserve_dst_port=true --np reserve_src_port=true --np dijkstra_early_exit=false"
mkdir -p "$OUT"
T0=$(date +%s)
for M in $MULTS; do
 for PAT in $PATTERNS; do
  for ALGO in ga rs; do
   for I in $(seq 1 "$RUNS"); do
    NAME="${PAT}_m${M}_${ALGO}_s${I}"
    if [ -f "$OUT/$NAME/summary.json" ]; then echo "[pula] $NAME"; continue; fi
    if [ "$ALGO" = "ga" ]; then A="--algo ga --init random"; else A="--algo random_search"; fi
    echo "=== $NAME ($(date +%H:%M:%S), decorrido $(( ($(date +%s)-T0)/60 )) min) ==="
    $PY ga_optimize.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
      --traffic "$PAT" --cus "$CUS" --duration-us "$DUR" --spacing-ns "$SPACING" $NP \
      $A --refs "$MESH" "$SW" --pop "$POP" --gens "$GENS" --train-seeds 1 2 3 \
      --wire-mult "$M" --ga-seed "$I" --name "$NAME" --out-root "$OUT" > "$OUT/${NAME}.log" 2>&1 \
      || echo "ERRO em $NAME (veja $OUT/${NAME}.log)"
    grep -E "best_fitness|best_wire" "$OUT/$NAME/summary.json" 2>/dev/null | tr -d '\n'; echo
   done
  done
 done
done
echo "Fase 1A (treino) concluida em $(( ($(date +%s)-T0)/60 )) min"