#!/usr/bin/env python3
"""
topology_generator.py

Gera as topologias de comparacao (mesh, irregular small-world, irregular
com menos links) para tamanhos de rede arbitrarios, de forma sistematica e
reproduzivel (sem aleatoriedade -- as mesmas regras sempre produzem a
mesma topologia, para dar para explicar/reproduzir no texto do trabalho).

Uso: python3 topology_generator.py
(gera todos os arquivos de configuracao direto no diretorio atual)
"""

import json
from collections import defaultdict, deque


# ---------------------------------------------------------------------
# Blocos de config compartilhados entre todas as topologias (so a
# "topology" muda entre elas -- mantem a comparacao justa).
# ---------------------------------------------------------------------
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


def mesh_edges(rows, cols):
    """Gera os links de uma mesh regular rows x cols (grau max 4)."""
    edges = []
    for r in range(rows):
        for c in range(cols):
            node = r * cols + c
            if c + 1 < cols:
                edges.append((node, node + 1))          # horizontal
            if r + 1 < rows:
                edges.append((node, node + cols))        # vertical
    return edges


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


def max_degree(adj, num_nodes):
    return max(len(adj[n]) for n in range(num_nodes))


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


def validate_and_report(name, edges, num_nodes, max_deg_limit=4):
    adj = build_adj(edges, num_nodes)
    deg = max_degree(adj, num_nodes)
    conn = is_connected(adj, num_nodes)
    ok = conn and deg <= max_deg_limit
    diam, avg = (None, None)
    if conn:
        diam, avg = diameter_and_avg(adj, num_nodes)

    print(f"--- {name} ---")
    print(f"  nos={num_nodes} links={len(edges)} grau_max={deg} "
          f"conexo={conn} diametro={diam} caminho_medio={avg:.3f}"
          if conn else f"  nos={num_nodes} links={len(edges)} grau_max={deg} "
                        f"conexo={conn} (DESCONEXO!)")
    if not ok:
        print("  [FALHA DE VALIDACAO -- corrigir antes de usar]")
    print()
    return ok


def saturate_with_shortcuts(edges, num_nodes, rows, cols, max_degree=4):
    """Adiciona o maior numero possivel de atalhos de longo alcance,
    respeitando max_degree, priorizando sempre o par valido MAIS DISTANTE
    (distancia Manhattan na grade original) primeiro -- uma versao "mais
    links" so faz sentido se os links extras forem uteis (atalhos), não
    redundancia local arbitraria.
    """
    edge_set = set(tuple(sorted(e)) for e in edges)
    adj = defaultdict(set)
    for u, v in edge_set:
        adj[u].add(v)
        adj[v].add(u)

    def manhattan(a, b):
        ra, ca = divmod(a, cols)
        rb, cb = divmod(b, cols)
        return abs(ra - rb) + abs(ca - cb)

    capacity = {n: max_degree - len(adj[n]) for n in range(num_nodes)}

    candidates = []
    for u in range(num_nodes):
        if capacity[u] <= 0:
            continue
        for v in range(u + 1, num_nodes):
            if capacity[v] <= 0 or v in adj[u]:
                continue
            candidates.append((manhattan(u, v), u, v))
    candidates.sort(reverse=True)  # maior distancia primeiro

    added = []
    for _, u, v in candidates:
        if capacity[u] > 0 and capacity[v] > 0 and v not in adj[u]:
            adj[u].add(v)
            adj[v].add(u)
            capacity[u] -= 1
            capacity[v] -= 1
            edge_set.add(tuple(sorted((u, v))))
            added.append((u, v))

    return sorted(edge_set), added


def remove_links_keep_connected(edges, num_nodes, num_to_remove,
                                 protect_edges=None, seed=42):
    """Remove num_to_remove arestas de uma copia de `edges`, sem nunca
    desconectar o grafo (verificado a cada remocao) e sem tocar em
    protect_edges (os atalhos de longo alcance, que devem sobreviver para
    a topologia continuar "irregular" no mesmo sentido da small-world).

    Duas passadas, ambas deterministicas dado `seed`:
      1) Tenta espalhar a reducao por nos AINDA NAO tocados (evita
         concentrar a perda de grau sempre nos mesmos nos).
      2) Se ainda faltar remover, permite repetir nos ja tocados,
         continuando a verificar conectividade em toda remocao.
    """
    import random
    rng = random.Random(seed)
    protect = set(tuple(sorted(e)) for e in (protect_edges or []))

    edge_set = set(tuple(sorted(e)) for e in edges)
    candidates = [e for e in edge_set if e not in protect]
    rng.shuffle(candidates)

    removed = []
    touched = set()

    for e in candidates:
        if len(removed) >= num_to_remove:
            break
        u, v = e
        if u in touched or v in touched:
            continue
        trial = edge_set - {e}
        if is_connected(build_adj(trial, num_nodes), num_nodes):
            edge_set = trial
            removed.append(e)
            touched.add(u)
            touched.add(v)

    if len(removed) < num_to_remove:
        for e in candidates:
            if len(removed) >= num_to_remove:
                break
            if e in removed or e not in edge_set:
                continue
            trial = edge_set - {e}
            if is_connected(build_adj(trial, num_nodes), num_nodes):
                edge_set = trial
                removed.append(e)

    if len(removed) < num_to_remove:
        raise RuntimeError(
            f"So consegui remover {len(removed)}/{num_to_remove} arestas "
            "sem desconectar o grafo -- peca um alvo menos agressivo.")

    return sorted(edge_set), removed


def small_world_rewire(edges, remove, add):
    """Remove uma lista de arestas e adiciona outra, preservando a
    contagem total de links (rewiring 1-para-1)."""
    edge_set = set(tuple(sorted(e)) for e in edges)
    for e in remove:
        key = tuple(sorted(e))
        if key not in edge_set:
            raise ValueError(f"Link a remover nao existe: {e}")
        edge_set.discard(key)
    for e in add:
        edge_set.add(tuple(sorted(e)))
    return sorted(edge_set)


def to_config(edges, description):
    topology = [{"id": i, "u": u, "v": v} for i, (u, v) in enumerate(edges)]
    return {
        "network_params": NETWORK_PARAMS,
        "topology_description": description,
        "topology": topology,
        "traffic": TRAFFIC,
        "simulation": SIMULATION,
    }


def save(cfg, path):
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  -> escrito: {path}")


def main():
    # =====================================================================
    # 16 NOS (4x4) -- ja tinhamos mesh e small-world; adicionando a de
    # menos links: um anel (16 links) + 4 acordes diametrais (small-world
    # classico), totalizando 20 links (~83% do orcamento da mesh/24).
    # =====================================================================
    mesh16 = mesh_edges(4, 4)
    validate_and_report("mesh 4x4 (16 nos, referencia)", mesh16, 16)

    smallworld16 = small_world_rewire(
        mesh16,
        remove=[(5, 6), (9, 10)],
        add=[(0, 15), (3, 12)],
    )
    validate_and_report("irregular small-world 4x4 (16 nos, mesmo orcamento)",
                         smallworld16, 16)

    # "Menos links": parte da PRÓPRIA small-world (não de um anel -- assim
    # toda a família mesh/small-world/menos-links/mais-links vem da mesma
    # base, e qualquer diferença de desempenho é atribuível só à
    # quantidade de links, não a uma estrutura fundamentalmente diferente).
    # Remove 4 links locais (~16.7%, mesma proporção usada abaixo pro caso
    # de 64 nós), protegendo os 2 atalhos de longo alcance -- eles
    # continuam intactos, só a redundância local diminui.
    fewlinks16, removed16 = remove_links_keep_connected(
        smallworld16, 16, num_to_remove=4,
        protect_edges=[(0, 15), (3, 12)])
    ok = validate_and_report(
        f"irregular MENOS links (small-world - {len(removed16)} links, "
        f"16 nos, {len(fewlinks16)} links)",
        fewlinks16, 16)

    save(to_config(mesh16,
                    "Mesh 4x4 regular: 16 nos, 24 links, grau 2-4."),
         "config_mesh.json")
    save(to_config(smallworld16,
                    "Small-world irregular: mesh 4x4 com 2 links centrais "
                    "removidos e 2 links de longo alcance adicionados. "
                    "Mesmo orcamento da mesh (24 links), grau uniforme 3."),
         "config_irregular_smallworld.json")
    save(to_config(fewlinks16,
                    "Irregular com MENOS links: deriva da small-world "
                    f"(24 links) removendo {len(removed16)} links locais "
                    "(protegendo os 2 atalhos de longo alcance), chegando "
                    f"a {len(fewlinks16)} links. Mesma familia da mesh/"
                    "small-world/mais-links, so o orcamento muda."),
         "config_irregular_fewlinks_16.json")

    # --- Irregular com MAIS links (16 nos) ---
    # Parte da small-world (todo no com grau 3, 1 unidade de folga cada) e
    # satura o grau restante com atalhos adicionais de longo alcance,
    # escolhidos gulosamente pelo par valido mais distante primeiro. Com
    # 16 nos e folga uniforme de 1, isso tende a formar um emparelhamento
    # perfeito (8 arestas novas), atingindo o maximo teorico de 2*16=32
    # links para grau maximo 4 -- o maior orcamento possivel sem violar
    # NUM_PORTS.
    morelinks16, added16 = saturate_with_shortcuts(smallworld16, 16, 4, 4)
    ok = validate_and_report(
        f"irregular MAIS links (16 nos, {len(morelinks16)} links, "
        f"+{len(added16)} atalhos sobre a small-world)",
        morelinks16, 16)
    assert ok, "more-links 16 falhou na validacao"
    save(to_config(morelinks16,
                    "Irregular com MAIS links: parte da small-world (24 "
                    "links) e satura o grau restante de todo no com "
                    f"{len(added16)} atalhos adicionais de longo alcance, "
                    f"chegando a {len(morelinks16)} links (maximo teorico "
                    "para grau <= 4 com 16 nos: 32)."),
         "config_irregular_morelinks_16.json")

    print()

    # =====================================================================
    # 64 NOS (8x8)
    # =====================================================================
    mesh64 = mesh_edges(8, 8)
    validate_and_report("mesh 8x8 (64 nos, referencia)", mesh64, 64)

    def node(r, c):
        return r * 8 + c

    # Small-world 8x8: usa SOMENTE nos que já têm capacidade de grau livre
    # de verdade (cantos do grid inteiro: grau 2, folga 2; bordas não-canto:
    # grau 3, folga 1) para os novos links de longo alcance -- SEM precisar
    # de nenhuma remoção correspondente para "abrir espaço" nesses nós
    # específicos. As remoções (para manter o orçamento total idêntico ao
    # da mesh) são feitas em nós interiores completamente diferentes,
    # escolhidos só para não estourar o orçamento de links, não para
    # liberar grau em lugar nenhum -- exatamente a mesma lógica usada no
    # caso de 16 nós (lá, os links removidos do núcleo 2x2 não têm
    # nenhuma relação direta com os cantos que ganharam os atalhos).
    #
    # (Uma tentativa anterior conectava "cantos de quadrante" que na
    # verdade são nós INTERIORES do grid 8x8 inteiro (grau 4, sem folga
    # nenhuma) -- por isso a validação abaixo existe: ela pega esse tipo
    # de erro automaticamente em vez de depender de conta de cabeça.)
    add_64 = [
        (0, 63), (0, 56),      # canto TL usado 2x (grau 2 -> 4)
        (7, 56), (7, 63),      # canto TR usado 2x (grau 2 -> 4)
        (node(3, 0), node(4, 7)),   # bordas esq/dir, grau 3 -> 4
        (node(0, 3), node(7, 4)),   # bordas topo/baixo, grau 3 -> 4
    ]

    # 6 remoções em nós interiores DISTINTOS e espalhados, sem nenhuma
    # relação com os nós usados acima -- só para manter o total de links
    # igual ao da mesh (112).
    remove_64 = [
        (node(2, 2), node(2, 3)),
        (node(2, 5), node(2, 6)),
        (node(5, 1), node(5, 2)),
        (node(5, 5), node(5, 6)),
        (node(3, 3), node(4, 3)),
        (node(3, 4), node(4, 4)),
    ]

    smallworld64 = small_world_rewire(mesh64, remove=remove_64, add=add_64)
    ok_sw64 = validate_and_report(
        "irregular small-world 8x8 (64 nos, mesmo orcamento)",
        smallworld64, 64)
    assert ok_sw64, "small-world 8x8 falhou na validacao -- ver mensagem acima"

    # "Menos links" (64 nos): mesma logica do caso 16 nos -- deriva da
    # PROPRIA small-world 64, removendo ~16.7% dos links locais (mesma
    # proporcao do caso 16 nos: 4/24 = 16.7%), protegendo os 6 atalhos de
    # longo alcance (add_64) que definem o carater "small-world" da
    # topologia.
    num_remove_64 = round(0.167 * len(smallworld64))  # ~19 de 112
    fewlinks64, removed64 = remove_links_keep_connected(
        smallworld64, 64, num_to_remove=num_remove_64,
        protect_edges=add_64)
    validate_and_report(
        f"irregular MENOS links (small-world - {len(removed64)} links, "
        f"64 nos, {len(fewlinks64)} links)",
        fewlinks64, 64)

    # --- Irregular com MAIS links (64 nos) ---
    # Mesma ideia: satura o grau restante da small-world 64 (que hoje NAO
    # tem folga uniforme -- so os nos usados nos atalhos/remocoes tem grau
    # 4, o resto ainda tem folga variada) com atalhos adicionais de longo
    # alcance, gulosamente do par mais distante para o mais proximo.
    morelinks64, added64 = saturate_with_shortcuts(smallworld64, 64, 8, 8)
    ok = validate_and_report(
        f"irregular MAIS links (64 nos, {len(morelinks64)} links, "
        f"+{len(added64)} atalhos sobre a small-world)",
        morelinks64, 64)
    assert ok, "more-links 64 falhou na validacao"

    save(to_config(mesh64,
                    "Mesh 8x8 regular: 64 nos, 112 links, grau 2-4."),
         "config_mesh_64.json")
    save(to_config(smallworld64,
                    "Small-world irregular 8x8: rewiring local por "
                    "quadrante (igual ao caso 16 nos) + 2 expressos "
                    "inter-quadrante ligando cantos opostos do grid "
                    "inteiro. Mesmo orcamento da mesh (112 links)."),
         "config_irregular_smallworld_64.json")
    save(to_config(fewlinks64,
                    "Irregular com MENOS links 8x8: deriva da small-world "
                    f"(112 links) removendo {len(removed64)} links locais "
                    "(protegendo os 6 atalhos de longo alcance), chegando "
                    f"a {len(fewlinks64)} links. Mesma familia da mesh/"
                    "small-world/mais-links, so o orcamento muda."),
         "config_irregular_fewlinks_64.json")
    save(to_config(morelinks64,
                    "Irregular com MAIS links 8x8: parte da small-world "
                    "(112 links) e satura o grau restante de todo no com "
                    f"{len(added64)} atalhos adicionais de longo alcance, "
                    f"chegando a {len(morelinks64)} links (maximo teorico "
                    "para grau <= 4 com 64 nos: 128)."),
         "config_irregular_morelinks_64.json")


if __name__ == "__main__":
    main()