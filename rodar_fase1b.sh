#!/usr/bin/env bash
# Fase 1B / retreino de uniform: GA e busca aleatoria com teto de fio, parametrizados por nivel de links (L)
# e por seeds de treino. Retomavel (pula execucoes com summary.json). Mesmo regime da Fase 1A
# (64 nos, 16 CUs Minor, BFS calibrado r=1, rho=0.5: spacing 6700 ns, janela 1700 us).
#
# 1) Fase 1B (niveis de orcamento; teto = M x L; um GA e uma RS por nivel):
#      nohup bash rodar_fase1b.sh > fase1b.log 2>&1 &
#    (padrao: LEVELS="84 98 124", MULTS="1.5", 3 padroes, 10 GA + 10 RS por celula; saida runs_fase1b)
# 2) Retreino de uniform com mais seeds de treino (conferir se o ganho pequeno e sobreajuste):
#      LEVELS=112 MULTS="1.5 2 3" PATTERNS=uniform TRAIN_SEEDS="1 2 3 4 5 6 7 8 9 10" OUT=runs_fase1_uni10 \
#        nohup bash rodar_fase1b.sh > fase1_uni10.log 2>&1 &
# 3) Teste curto:  LEVELS=84 PATTERNS=uniform RUNS=2 POP=12 GENS=4 OUT=runs_teste1b bash rodar_fase1b.sh
# Nomes: <padrao>_L<L>_m<M>_<ga|rs>_s<i>. Tempo: ~6 min por execucao com 3 seeds de treino (x3,3 com 10 seeds).
set -u
PY=${PY:-python3}
BIN=${BIN:-./main.exe}
MESH=${MESH:-configs/configs_ciclos/config_mesh_64.json}
SW=${SW:-configs/configs_ciclos/config_irregular_smallworld_64.json}
OUT=${OUT:-runs_fase1b}
WORKERS=${WORKERS:-12}
PATTERNS=${PATTERNS:-"bit_reversal butterfly uniform"}
LEVELS=${LEVELS:-"84 98 124"}
MULTS=${MULTS:-"1.5"}
RUNS=${RUNS:-10}
POP=${POP:-30}
GENS=${GENS:-40}
SPACING=${SPACING:-6700}
DUR=${DUR:-1700}
CUS=${CUS:-16}
TRAIN_SEEDS=${TRAIN_SEEDS:-"1 2 3"}
NP="--np routing_algorithm=bfs --np dijkstra_dispatch_cycles=129 --np dijkstra_init_cycles_per_node=1 --np dijkstra_pq_op_cycles=39 --np dijkstra_edge_check_cycles=1 --np control_clock_ratio=1 --np reserve_dst_port=true --np reserve_src_port=true --np dijkstra_early_exit=false"
mkdir -p "$OUT"
T0=$(date +%s)
for L in $LEVELS; do
 for M in $MULTS; do
  for PAT in $PATTERNS; do
   for ALGO in ga rs; do
    for I in $(seq 1 "$RUNS"); do
     NAME="${PAT}_L${L}_m${M}_${ALGO}_s${I}"
     if [ -f "$OUT/$NAME/summary.json" ]; then echo "[pula] $NAME"; continue; fi
     if [ "$ALGO" = "ga" ]; then A="--algo ga --init random"; else A="--algo random_search"; fi
     echo "=== $NAME ($(date +%H:%M:%S), decorrido $(( ($(date +%s)-T0)/60 )) min) ==="
     $PY ga_optimize.py --bin "$BIN" --template "$MESH" --workers "$WORKERS" \
       --traffic "$PAT" --cus "$CUS" --duration-us "$DUR" --spacing-ns "$SPACING" $NP \
       $A --refs "$MESH" "$SW" --pop "$POP" --gens "$GENS" --train-seeds $TRAIN_SEEDS \
       --links "$L" --wire-mult "$M" --ga-seed "$I" --name "$NAME" --out-root "$OUT" > "$OUT/${NAME}.log" 2>&1 \
       || echo "ERRO em $NAME (veja $OUT/${NAME}.log)"
     grep -E "best_fitness|best_wire" "$OUT/$NAME/summary.json" 2>/dev/null | tr -d '\n'; echo
    done
   done
  done
 done
done
echo "concluido em $(( ($(date +%s)-T0)/60 )) min"