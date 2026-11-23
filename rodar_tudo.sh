#!/usr/bin/env bash
# Sequencia completa. Rode na pasta do simulador (onde estao main.exe, ga_*.py, run_cu_sweep.sh, ...).
#   nohup bash rodar_tudo.sh > rodar_tudo.log 2>&1 &      # roda em segundo plano
#   tail -f rodar_tudo.log                                 # acompanhar
# Para escolher etapas:  STAGES="1 2" bash rodar_tudo.sh   (1 retries, 2 rho 0.25/0.75 BFS, 3 Dijkstra, 4 pareado/resumos)
# Etapas 2 e 3 sao longas (janelas grandes com poucos CUs). CUS_LONGOS controla se 2 e 1 CUs entram.
export PATH="$PATH"
PY=${PY:-python3}
STAGES=${STAGES:-"1 2 3 4"}
CUS_LISTA=${CUS_LISTA:-"16 8 4 2 1"}   # use CUS_LISTA="16 8 4" para pular os mais demorados
MESH=configs/configs_ciclos/config_mesh_64.json
SW=configs/configs_ciclos/config_irregular_smallworld_64.json
COEF_BFS="--np routing_algorithm=bfs --np dijkstra_dispatch_cycles=129 --np dijkstra_init_cycles_per_node=1 --np dijkstra_pq_op_cycles=39 --np dijkstra_edge_check_cycles=1"
t0=$(date +%s); stamp() { echo; echo "##### $1  (+$(( $(date +%s) - t0 )) s, $(date +%H:%M:%S))"; }

has() { for s in $STAGES; do [ "$s" = "$1" ] && return 0; done; return 1; }

# ---------------------------------------------------------------- 1) retries em 16 CUs (rho 0,5; janela corrigida)
if has 1; then
  stamp "ETAPA 1: retries por fluxo, 16 CUs, spacing 6700 ns, janela 1700 us"
  for PAT in uniform bit_reversal butterfly; do
    CAND=runs/bfs_${PAT}_cu16_ga_random/best_config.json
    [ -f "$CAND" ] || { echo "aviso: $CAND nao existe; usando so mesh e small-world"; CAND=""; }
    $PY ga_retries.py --bin ./main.exe --traffic $PAT --cus 16 \
      --duration-us 1700 --spacing-ns 6700 \
      $COEF_BFS --np dijkstra_early_exit=false --np reserve_dst_port=true --np reserve_src_port=true \
      --np control_clock_ratio=1 --replicas 10 --tag r16_ \
      mesh:$MESH smallworld:$SW ${CAND:+cand_$PAT:$CAND}
  done
fi

# ---------------------------------------------------------------- 2) BFS com rho 0,25 e 0,75
if has 2; then
  for RHO in 0.75 0.25; do
    stamp "ETAPA 2: BFS r=1 rho=$RHO CUs=$CUS_LISTA"
    ALGO=bfs R=1 RHO=$RHO CUS="$CUS_LISTA" bash run_cu_sweep.sh
  done
fi

# ---------------------------------------------------------------- 3) Dijkstra (r=1, rho 0,5)
if has 3; then
  stamp "ETAPA 3: Dijkstra r=1 rho=0.5 CUs=$CUS_LISTA"
  ALGO=dij R=1 RHO=0.5 CUS="$CUS_LISTA" bash run_cu_sweep.sh
fi

# ---------------------------------------------------------------- 4) teste pareado + resumos
if has 4; then
  stamp "ETAPA 4: pareado por seed e resumos"
  for TAG in bfs_r1_rho0.5 bfs_r1_rho0.75 bfs_r1_rho0.25 dij_r1_rho0.5; do
    ls -d cache_${TAG}_cu* >/dev/null 2>&1 || { echo "sem cache para $TAG (pulando)"; continue; }
    echo; echo "=== $TAG: resumo (Welch) ==="
    $PY resumo_cus.py final_eval_$TAG
    echo; echo "=== $TAG: pareado por seed ==="
    $PY compare_paired.py --cache-glob "cache_${TAG}_cu*" \
      --run-dirs "runs/bfs_*_cu16_*" --extra mesh:$MESH --extra smallworld:$SW \
      --out paired_$TAG
  done
fi
stamp "FIM"