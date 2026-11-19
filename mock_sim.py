#!/usr/bin/env python3
"""
mock_sim.py -- SIMULADOR FALSO so para testar o pipeline GA sem o SystemC.
Le config.json do diretorio atual e escreve o CSV de resultados no mesmo
formato do main.exe. A latencia e apenas um modelo simples (caminho medio do
padrao de trafego + fila por CU + ruido da seed). NAO usar para conclusoes.

Uso: --bin "python3 /caminho/mock_sim.py"
"""
import json
import random
from collections import deque, defaultdict

cfg = json.load(open("config.json"))
adj = defaultdict(set)
for l in cfg["topology"]:
    adj[l["u"]].add(l["v"])
    adj[l["v"]].add(l["u"])
n = max(adj) + 1
seed = cfg["simulation"]["seed"]
rng = random.Random(seed)


def bfs(s):
    d = {s: 0}
    q = deque([s])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in d:
                d[v] = d[u] + 1
                q.append(v)
    return d


D = {s: bfs(s) for s in range(n)}
mode = cfg["traffic"]["mode"]
k = n.bit_length() - 1
if mode == "bit_reversal":
    pairs = [(i, int(format(i, "0%db" % k)[::-1], 2)) for i in range(n)]
elif mode == "butterfly":
    pairs = [(i, ((i << 1) & (n - 1)) | (i >> (k - 1))) for i in range(n)]
else:
    pairs = [(rng.randrange(n), rng.randrange(n)) for _ in range(200)]
pairs = [(a, b) for a, b in pairs if a != b and b in D[a]]
hops = sum(D[a][b] for a, b in pairs) / len(pairs)
cus = cfg["network_params"].get("num_control_units", 2)
lat = 40 + 6 * hops + 120 / cus + rng.gauss(0, 3)
dur = cfg["simulation"].get("duration_us", 15.0) * 100
comp = 100.0 if lat < dur else 60.0
out = cfg["simulation"].get("output_file", "results.csv")
with open(out, "w") as f:
    f.write("flow_id,status,in_warmup,control_latency_cycles,data_latency_cycles,total_latency_cycles\n")
    for i in range(20):
        f.write("%d,CONCLUIDO,0,%d,%d,%d\n" % (i, round(lat), round(2*hops), round(lat + 2*hops)))
    f.write("\n--- Resumo ---\n")
    f.write("Taxa de conclusao (%%),%s\n" % comp)
    f.write("Latencia media regime permanente exclui warmup ciclos,%d\n" % round(lat))
    f.write("Latencia media exata sem arredondar ciclos,%.6f\n" % lat)
    f.write("Fluxos nao concluidos penalizados,0\n")
    f.write("Penalidade por fluxo (ciclos),%d\n" % dur)
    f.write("Latencia media penalizada ciclos,%.6f\n" % lat)