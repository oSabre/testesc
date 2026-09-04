#!/usr/bin/env bash
#
# run_replicas.sh
#
# Roda N réplicas independentes da simulação, cada uma com uma seed
# diferente, e agrega a latência média + taxa de conclusão de cada réplica
# num resumo final (média entre réplicas + desvio padrão).
#
# POR QUE ISSO É UM SCRIPT EXTERNO E NÃO UM LOOP DENTRO DO sc_main:
# O SystemC não permite reiniciar o kernel de simulação (elaboração +
# sc_start) mais de uma vez dentro do mesmo processo. Cada réplica precisa
# ser uma execução nova do binário. Isso é o padrão usual em simulação
# baseada em SystemC/TLM: o "driver" de réplicas vive fora do modelo.
#
# PRÉ-REQUISITO: o binário do simulador (ajuste BIN abaixo) deve ler
# "simulation.seed" e "simulation.output_file" de config.json (implementado
# em main.cpp). Este script gera um config.json temporário por réplica a
# partir de um config.json "base", sobrescrevendo apenas esses dois campos.
#
# USO:
#   ./run_replicas.sh <config_base.json> <num_replicas> [seed_inicial]
#
# Requer: python3 (usado tanto para editar o JSON de cada réplica quanto
# para agregar os resultados no final). Não depende mais de jq.

set -euo pipefail

# Detecta qual comando de Python existe neste ambiente. Em shells
# MSYS2/MinGW64, o PATH do Windows nem sempre é herdado, então "python3"
# pode não ser encontrado mesmo com o Python instalado -- este bloco tenta
# alternativas comuns antes de desistir.
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
    echo "Ou adicione seu Python do Windows ao PATH deste shell." >&2
    exit 1
fi

echo "Usando interpretador Python: $PYTHON_BIN ($(command -v "$PYTHON_BIN"))"

BIN="./main.exe"                 # ajuste para o nome/caminho do seu executável
BASE_CONFIG="${1:?uso: run_replicas.sh <config_base.json> <num_replicas> [seed_inicial]}"
NUM_REPLICAS="${2:?informe o numero de replicas}"
SEED_START="${3:-1}"

OUT_DIR="replicas_out"
mkdir -p "$OUT_DIR"

echo "Rodando $NUM_REPLICAS replicas a partir de seed $SEED_START..."

for i in $(seq 0 $((NUM_REPLICAS - 1))); do
    seed=$((SEED_START + i))
    run_config="$OUT_DIR/config_seed${seed}.json"
    run_output="$OUT_DIR/results_seed${seed}.csv"

    # Sobrescreve/injeta simulation.seed e simulation.output_file no config
    # base usando o interpretador Python detectado (sem depender de jq).
    "$PYTHON_BIN" - "$BASE_CONFIG" "$run_config" "$seed" "$run_output" <<'PYEOF'
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

    # O binário le "config.json" com nome fixo no diretorio atual (main.cpp
    # nao aceita caminho por argv hoje); copiamos o config gerado por cima.
    cp "$run_config" config.json
    "$BIN"
done

echo ""
echo "Agregando resultados..."
"$PYTHON_BIN" - "$OUT_DIR" <<'PYEOF'
import csv, glob, sys, statistics as st

out_dir = sys.argv[1]
latencies = []
completion_rates = []

for path in sorted(glob.glob(f"{out_dir}/results_seed*.csv")):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if row[0].startswith("Latencia media regime permanente"):
                try:
                    latencies.append(float(row[1]))
                except ValueError:
                    pass
            if row[0].startswith("Taxa de conclusao"):
                try:
                    completion_rates.append(float(row[1]))
                except ValueError:
                    pass

def summarize(name, values):
    if not values:
        print(f"{name}: nenhuma replica com dado valido")
        return
    mean = st.mean(values)
    stdev = st.stdev(values) if len(values) > 1 else 0.0
    print(f"{name}: media={mean:.3f}  desvio_padrao={stdev:.3f}  n={len(values)}  valores={values}")

print(f"--- Agregado de {len(latencies)} replica(s) ---")
summarize("Latencia media (regime permanente, ciclos)", latencies)
summarize("Taxa de conclusao (%)", completion_rates)
PYEOF