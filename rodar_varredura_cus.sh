#!/usr/bin/env bash
# Varredura de CUs e sensibilidades da Fase 1 por REAVALIACAO das topologias ja treinadas (runs_fase1).
# Uso (pasta do simulador): nohup bash rodar_varredura_cus.sh > varredura.log 2>&1 &
#   CENARIOS="cus" (so CUs, BFS) | "ctrl" (Dijkstra, 16 CUs) | "reach" (alcance do fio) | "cus ctrl reach" (padrao)
set -u
PY=${PY:-python3}; BIN=${BIN:-./main.exe}; RUNS=${RUNS:-runs_fase1}; WORKERS=${WORKERS:-12}
SW=${SW:-configs/configs_ciclos/config_irregular_smallworld_64.json}
TPL=${TPL:-configs/configs_ciclos/config_mesh_64.json}
CENARIOS=${CENARIOS:-"cus ctrl reach"}
run() { $PY fase1_reavaliacao.py --runs "$RUNS" --bin "$BIN" --template "$TPL" --sw "$SW" --workers "$WORKERS" "$@" || echo "ERRO em: $*"; }
for C in $CENARIOS; do
  case $C in
    cus)   for N in 1 2 4 8; do run --cus $N --ctrl bfs; done ;;                       # 16 CUs ja foi feito na avaliacao final
    ctrl)  run --cus 16 --ctrl dij; run --cus 4 --ctrl dij ;;
    reach) for K in 4 2 1; do run --cus 16 --ctrl bfs --np link_reach_tiles_per_cycle=$K --tag cu16_bfs_reach$K; done ;;
  esac
done
echo "varredura concluida"