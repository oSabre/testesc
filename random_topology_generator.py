#!/usr/bin/env python3
"""
random_topology_generator.py

Gera um lote de topologias aleatorias, conexas, respeitando um limite de
grau (NUM_PORTS - 1), com um numero de links alvo -- para servir de
"linha de base" estatistica contra a qual comparar as topologias
desenhadas a mao (mesh, small-world, fewlinks, morelinks).

Algoritmo (por topologia, dada uma seed):
  1. Constroi uma ARVORE GERADORA aleatoria (garante conectividade),
     preferindo sempre conectar ao no ja-incluido com MENOR grau atual
     (espalha o grau, evita concentrar tudo em poucos nos).
  2. Adiciona arestas extras aleatorias (respeitando o limite de grau e
     sem duplicar arestas) ate atingir o numero de links alvo, ou até
     esgotar as tentativas (caso em que aceita um pouco menos que o alvo
     e AVISA -- nao falha silenciosamente).
  3. Valida grau maximo e conectividade antes de aceitar a topologia
     (mesma logica de validacao usada no topology_generator.py).

Uso:
    python3 random_topology_generator.py [num_topologias] [num_nodes] [num_links] [seed_inicial]

    Defaults: 50 topologias, 64 nos, 112 links (mesmo orcamento da mesh/
    small-world 8x8), seed inicial 1000 (para nao colidir com as seeds
    1..10 ja usadas nas replicas das topologias desenhadas a mao).
"""

import json
import random
import sys
from collections import defaultdict, deque

# Reaproveita os mesmos blocos de config do topology_generator.py, para
# que as topologias aleatorias sejam comparaveis (mesmos network_params/
# traffic/simulation -- só a "topology" muda).
NETWORK_PARAMS = {
    "num_control_units": 4,
    "link_transit_latency_cycles": 1,
    "max_retries": 10,
    "retry_wait_cycles": 100,
    "packets_per_flow": 1,
    "flits_per_packet": 1,
    "idle_cycles": 2,
    "buffer_size_flits": 16,
    "dijkstra_dispatch_cycles": 1,
    "dijkstra_init_cycles_per_node": 1,
    "dijkstra_pq_op_cycles": 1,
    "dijkstra_edge_check_cycles": 1,
    "control_plane_latency_cycles": 1,
    "retry_jitter_cycles": 25,
    "arbitro_latency_cycles": 1,
}

TRAFFIC = {
    "mode": "uniform",
    "num_packets": 100,
    "source_file": "traces/trace_01.csv",
    "seed": 1,
}

SIMULATION = {
    "seed": 1,
    "warmup_ns": 0,
    "duration_us": 15.0,
    "output_file": "results.csv",
}


def build_adj(edges, num_nodes):
    adj = defaultdict(set)
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    for n in range(num_nodes):
        adj[n]
    return adj


def is_connected(adj, num_nodes):
    if num_nodes == 0:
        return True
    seen = {0}
    q = deque([0])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return len(seen) == num_nodes


def diameter_and_avg(adj, num_nodes):
    all_d, diam = [], 0
    for src in range(num_nodes):
        dist = {src: 0}
        q = deque([src])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        for dst, d in dist.items():
            if dst != src:
                all_d.append(d)
                diam = max(diam, d)
    return diam, sum(all_d) / len(all_d)


def generate_random_topology(num_nodes, num_links, max_degree, seed):
    """Retorna (edges, achieved_links, warning_or_None)."""
    rng = random.Random(seed)
    nodes = list(range(num_nodes))
    degree = [0] * num_nodes
    edges = set()

    # 1) Arvore geradora aleatoria, preferindo sempre o no ja-incluido de
    #    MENOR grau atual (espalha a conectividade em vez de concentrar).
    order = nodes[:]
    rng.shuffle(order)
    connected = [order[0]]
    for node in order[1:]:
        candidates = [n for n in connected if degree[n] < max_degree]
        if not candidates:
            raise RuntimeError(
                f"[seed={seed}] Nao foi possivel construir arvore geradora "
                f"com limite de grau {max_degree} (ficou sem candidatos)."
            )
        min_deg = min(degree[n] for n in candidates)
        best = [n for n in candidates if degree[n] == min_deg]
        parent = rng.choice(best)
        edges.add(tuple(sorted((parent, node))))
        degree[parent] += 1
        degree[node] += 1
        connected.append(node)

    # 2) Arestas extras aleatorias ate atingir o alvo (ou esgotar tentativas)
    target_extra = num_links - len(edges)
    max_attempts = max(target_extra * 40, 2000)
    attempts = 0
    while len(edges) < num_links and attempts < max_attempts:
        attempts += 1
        u, v = rng.sample(nodes, 2)
        if degree[u] >= max_degree or degree[v] >= max_degree:
            continue
        key = tuple(sorted((u, v)))
        if key in edges:
            continue
        edges.add(key)
        degree[u] += 1
        degree[v] += 1

    # 2b) Arremate exaustivo: perto do maximo teorico (ex: 128 de 128 para
    # grau 4), a amostragem aleatoria pura frequentemente fica 1-2 arestas
    # aquem, porque sobra so um punhado de nos com capacidade e a chance de
    # SORTEAR exatamente um par valido entre eles fica baixa. Aqui,
    # verificamos EXAUSTIVAMENTE todos os pares entre os nos com folga
    # restante (populacao pequena a esta altura, entao e barato) em vez de
    # continuar so sorteando as cegas.
    if len(edges) < num_links:
        import itertools
        spare_nodes = [n for n in nodes if degree[n] < max_degree]
        for u, v in itertools.combinations(spare_nodes, 2):
            if len(edges) >= num_links:
                break
            if degree[u] >= max_degree or degree[v] >= max_degree:
                continue
            key = tuple(sorted((u, v)))
            if key in edges:
                continue
            edges.add(key)
            degree[u] += 1
            degree[v] += 1

    warning = None
    if len(edges) < num_links:
        warning = (f"so consegui {len(edges)}/{num_links} links "
                   f"(esgotei {attempts} tentativas de emparelhamento aleatorio)")

    return sorted(edges), len(edges), warning


def to_config(edges, description):
    topology = [{"id": i, "u": u, "v": v} for i, (u, v) in enumerate(edges)]
    return {
        "network_params": NETWORK_PARAMS,
        "topology_description": description,
        "topology": topology,
        "traffic": dict(TRAFFIC),
        "simulation": dict(SIMULATION),
    }


def main():
    num_topologies = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    num_nodes = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    num_links = int(sys.argv[3]) if len(sys.argv) > 3 else 112
    seed_start = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
    max_degree = 4  # NUM_PORTS - 1

    print(f"Gerando {num_topologies} topologias aleatorias: "
          f"{num_nodes} nos, alvo {num_links} links, grau max {max_degree}, "
          f"seeds {seed_start}..{seed_start + num_topologies - 1}\n")

    metrics_rows = []
    manifest_lines = []

    for i in range(num_topologies):
        seed = seed_start + i
        edges, achieved, warning = generate_random_topology(
            num_nodes, num_links, max_degree, seed)

        adj = build_adj(edges, num_nodes)
        deg_max = max(len(adj[n]) for n in range(num_nodes))
        connected = is_connected(adj, num_nodes)

        if not connected:
            print(f"  [seed={seed}] FALHA: grafo desconexo -- descartando esta amostra.")
            continue
        if deg_max > max_degree:
            print(f"  [seed={seed}] FALHA: grau maximo {deg_max} > {max_degree} -- descartando.")
            continue
        if warning:
            print(f"  [seed={seed}] AVISO: {warning}")

        diam, avg_path = diameter_and_avg(adj, num_nodes)

        label = f"random_{seed}"
        out_name = f"config_random_{seed}.json"
        desc = (f"Topologia aleatoria (seed={seed}): {num_nodes} nos, "
                f"{achieved} links, grau max {deg_max}, diametro {diam}, "
                f"caminho medio {avg_path:.3f}.")
        cfg = to_config(edges, desc)
        with open(out_name, "w") as f:
            json.dump(cfg, f, indent=2)

        metrics_rows.append({
            "seed": seed, "label": label, "num_nodes": num_nodes,
            "links": achieved, "max_degree": deg_max,
            "diameter": diam, "avg_path_length": round(avg_path, 4),
        })
        manifest_lines.append(f"{out_name}\t{label}\t{num_nodes}")

        print(f"  [{i+1}/{num_topologies}] seed={seed} -> {out_name} "
              f"({achieved} links, diam={diam}, avg={avg_path:.3f})")

    # --- CSV de metricas estruturais (para correlacionar com desempenho depois) ---
    with open("random_topologies_metrics.csv", "w", newline="") as f:
        import csv
        writer = csv.DictWriter(f, fieldnames=list(metrics_rows[0].keys()))
        writer.writeheader()
        writer.writerows(metrics_rows)

    # --- Manifest (mesmo formato do battery_manifest.txt, sem tradução CRLF) ---
    with open("random_manifest.txt", "w", newline="") as f:
        f.write("config_file\tlabel\tnum_nodes\n")
        f.write("\n".join(manifest_lines) + "\n")

    print(f"\n{len(metrics_rows)}/{num_topologies} topologias validas geradas.")
    print("Metricas: random_topologies_metrics.csv")
    print("Manifest: random_manifest.txt")


if __name__ == "__main__":
    main()