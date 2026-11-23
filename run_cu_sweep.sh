#!/usr/bin/env bash
# Varredura de CUs com utilizacao-alvo fixa (rho), custo calibrado, r configuravel.
# Uso (na pasta do simulador, ex.: ~/tcc/testesc):
#   bash run_cu_sweep.sh                 # BFS, r=1, rho=0.5, CUs "16 8 4 2 1"
#   ALGO=dij bash run_cu_sweep.sh        # Dijkstra
#   CUS="16 8" RHO=0.25 R=1 bash run_cu_sweep.sh
# Cada CU gera: final_eval_<algo>_r<R>_rho<RHO>_cu<C>.{csv,_summary.csv,...} e saida_<...>.txt
# Observacao: spacing_ns = intervalo medio entre chegadas; rho = S/(CUs*spacing).
set -u
ALGO=${ALGO:-bfs}            # bfs | dij
R=${R:-1}
RHO=${RHO:-0.5}
CUS=${CUS:-"16 8 4 2 1"}
PY=${PY:-python3}
WORKERS=${WORKERS:-12}
BIN=${BIN:-./main.exe}
TPL=${TPL:-configs/configs_ciclos/config_mesh_64.json}
SW=${SW:-configs/configs_ciclos/config_irregular_smallworld_64.json}
RUNDIRS=${RUNDIRS:-"runs/bfs_*_cu16_*"}   # topologias treinadas (BFS, custo antigo, 16 CUs)
REPL=${REPL:-10}

if [ "$ALGO" = "bfs" ]; then
  S_US_R1=53.3      # mesh 8x8, 5330 ciclos do core a 10 ns
  COEF="--np routing_algorithm=bfs --np dijkstra_dispatch_cycles=129 --np dijkstra_init_cycles_per_node=1 --np dijkstra_pq_op_cycles=39 --np dijkstra_edge_check_cycles=1"
elif [ "$ALGO" = "dij" ]; then
  S_US_R1=109.6     # mesh 8x8, 10964 ciclos do core
  COEF="--np routing_algorithm=dijkstra --np dijkstra_dispatch_cycles=227 --np dijkstra_init_cycles_per_node=5 --np dijkstra_pq_op_cycles=11 --np dijkstra_edge_check_cycles=1 --np dijkstra_pq_base_cycles=45"
else
  echo "ALGO deve ser bfs ou dij"; exit 1
fi

# Sobrescritas opcionais (outros cores): COEF_OVERRIDE="--np ..." S_US_OVERRIDE=<us na mesh, r=1> TAGX=_timing
[ -n "${COEF_OVERRIDE:-}" ] && COEF="$COEF_OVERRIDE"
[ -n "${S_US_OVERRIDE:-}" ] && S_US_R1="$S_US_OVERRIDE"

for C in $CUS; do
  # spacing arredondado a 100 ns; janela = SPANF*spacing + 6*S (SPANF=200), arredondada para cima a 100 us.
  # O instante da ultima chegada e aleatorio (media ~98 spacings, p99 ~140, max ~181 em 2000 seeds): com a janela
  # curta (100*spacing+4*S) fluxos 'nao iniciados' eram contados como nao concluidos e penalizados pela janela inteira.
  read SP DUR < <($PY - "$S_US_R1" "$R" "$C" "$RHO" "${SPANF:-200}" <<'PYEOF'
import sys, math
s1, r, c, rho, spanf = map(float, sys.argv[1:6])
S = s1 / r                                   # us
sp_ns = max(100, int(round(S * 1000.0 / (c * rho) / 100.0)) * 100)
dur = math.ceil((spanf * sp_ns / 1000.0 + 6 * S) / 100.0) * 100
print(sp_ns, int(dur))
PYEOF
)
  TAG="${ALGO}${TAGX:-}_r${R}_rho${RHO}_cu${C}"
  echo "=== $TAG : spacing_ns=$SP duration_us=$DUR ($(date +%H:%M:%S)) ==="
  START=$(date +%s)
  $PY ga_final_eval.py --bin "$BIN" --template "$TPL" --workers "$WORKERS" \
    --cus "$C" --duration-us "$DUR" --spacing-ns "$SP" \
    $COEF \
    --np reserve_dst_port=true --np reserve_src_port=true --np dijkstra_early_exit=false \
    --np control_clock_ratio="$R" \
    --replicas "$REPL" --seed-start 1000 \
    --run-dirs "$RUNDIRS" \
    --extra "mesh:$TPL" --extra "smallworld:$SW" --ref mesh \
    --cache-dir "cache_${TAG}" --out "final_eval_${TAG}" 2>&1 | tee "saida_${TAG}.txt"
  echo "--- $TAG levou $(( $(date +%s) - START )) s"
done