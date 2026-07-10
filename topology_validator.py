#!/usr/bin/env python3
"""
topology_validator.py

Valida um config.json do simulador ANTES de rodar a simulacao, e reporta
metricas estruturais da topologia (uteis para correlacionar com os
resultados de desempenho: diametro menor tende a significar latencia media
menor, por exemplo).

O QUE ELE CHECA (a razao de existir):
- O simulador NAO valida graus de porta em tempo de execucao. Se um no
  tiver mais vizinhos do que NUM_PORTS-1 (default 4, ja que a porta 0 e
  reservada para PORT_LOCAL), o TopologyManager simplesmente atribui numeros
  de porta crescentes sem checar o limite -- e o roteador (NUM_PORTS fixo)
  vai ter portas invalidas/sobrepostas silenciosamente. Isso NAO da erro na
  hora, so comportamento errado (pacotes perdidos, rotas erradas). Rodar
  este script antes de simular pega esse problema de graca.

USO:
    python3 topology_validator.py config.json [max_grau]

    max_grau (opcional) = NUM_PORTS - 1 no seu definitions.h (default 4).
"""

import json
import sys
from collections import defaultdict, deque


def load_topology(path):
    with open(path) as f:
        cfg = json.load(f)

    if "topology" not in cfg:
        print(f"ERRO: '{path}' nao tem campo 'topology'.")
        sys.exit(1)

    return cfg["topology"]


def build_graph(topology):
    adj = defaultdict(set)
    max_node = -1
    for link in topology:
        u, v = link["u"], link["v"]
        adj[u].add(v)
        adj[v].add(u)
        max_node = max(max_node, u, v)

    num_nodes = max_node + 1
    # Garante que todo no de 0..num_nodes-1 aparece no dict, mesmo sem vizinhos
    for n in range(num_nodes):
        adj[n]  # defaultdict cria entrada vazia se nao existir
    return adj, num_nodes


def bfs_distances(adj, source, num_nodes):
    dist = {source: 0}
    q = deque([source])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def main():
    if len(sys.argv) < 2:
        print("uso: python3 topology_validator.py config.json [max_grau]")
        sys.exit(1)

    config_path = sys.argv[1]
    max_degree = int(sys.argv[2]) if len(sys.argv) > 2 else 4

    topology = load_topology(config_path)
    adj, num_nodes = build_graph(topology)
    num_links = len(topology)

    print(f"=== Validando: {config_path} ===")
    print(f"Nos: {num_nodes}")
    print(f"Links: {num_links}")
    print(f"Limite de grau (NUM_PORTS - 1): {max_degree}")
    print()

    # --- 1. Checagem de grau ---
    degree_ok = True
    degree_dist = defaultdict(int)
    for node in range(num_nodes):
        deg = len(adj[node])
        degree_dist[deg] += 1
        if deg > max_degree:
            print(f"  [FALHA] No {node} tem grau {deg} > {max_degree} "
                  f"-- vai estourar NUM_PORTS silenciosamente!")
            degree_ok = False
        if deg == 0:
            print(f"  [FALHA] No {node} esta ISOLADO (grau 0, nenhum link).")
            degree_ok = False

    print("Distribuicao de grau:")
    for deg in sorted(degree_dist):
        print(f"  grau {deg}: {degree_dist[deg]} no(s)")
    print()

    # --- 2. Conectividade ---
    dist_from_0 = bfs_distances(adj, 0, num_nodes)
    connected = len(dist_from_0) == num_nodes
    if not connected:
        unreachable = set(range(num_nodes)) - set(dist_from_0.keys())
        print(f"  [FALHA] Grafo DESCONEXO. Nos inalcancaveis a partir do 0: "
              f"{sorted(unreachable)}")
    else:
        print("  [OK] Grafo conexo (todos os nos alcancaveis).")
    print()

    # --- 3. Diametro e caminho medio (so faz sentido se conexo) ---
    if connected:
        all_dists = []
        diameter = 0
        for src in range(num_nodes):
            dist = bfs_distances(adj, src, num_nodes)
            for dst, d in dist.items():
                if dst != src:
                    all_dists.append(d)
                    diameter = max(diameter, d)

        avg_path_len = sum(all_dists) / len(all_dists)
        print(f"Diametro da rede (maior menor-caminho): {diameter} hops")
        print(f"Caminho medio entre pares: {avg_path_len:.3f} hops")
    else:
        print("Diametro/caminho medio nao calculados (grafo desconexo).")

    print()
    if degree_ok and connected:
        print("=== RESULTADO: topologia VALIDA para simular. ===")
        sys.exit(0)
    else:
        print("=== RESULTADO: topologia INVALIDA -- corrija antes de simular. ===")
        sys.exit(1)


if __name__ == "__main__":
    main()