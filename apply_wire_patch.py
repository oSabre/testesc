#!/usr/bin/env python3
"""
apply_wire_patch.py -- teto de FIO TOTAL (orcamento = nº de links + fio) no GA.

Fio de um link = distancia de Manhattan entre os extremos numa planta fixa W x W
(W = sqrt(n), id = y*W + x). Fio total = soma sobre os links. A mesh 8x8 tem 112.

Novos argumentos (ga_optimize.py; qualquer script que use common_args os aceita):
    --wire-mult M   teto = M * links     (ex.: --links 112 --wire-mult 1.5  -> 168)
    --wire-cap  C   teto absoluto (tiles); tem prioridade sobre --wire-mult
Sem nenhum dos dois: SEM teto (comportamento anterior, identico).

Com teto: is_valid exige fio <= teto; repair troca links longos por pares livres mais
curtos; random_topology sorteia pares com vies para os curtos; mutate so propoe
trocas que cabem no orcamento restante; sementes que violam o teto sao descartadas.
summary.json ganha wire_cap e best_wire.

Uso:  py apply_wire_patch.py --src . [--check]
Cria .bak; se qualquer ancora falhar (nao achada exatamente 1x), nada e escrito.
"""
import argparse, os, sys

WIRE_BLOCK = '''FAIL_PENALTY = 1e6   # fitness de uma simulacao que falhou/travou

# ----------------------------------------------------------------------------
# Orcamento de FIO (teto no fio total). None = sem teto.
# Planta fixa W x W (id = y*W + x); comprimento = distancia de Manhattan.
# ----------------------------------------------------------------------------
WIRE_CAP = None      # fio total maximo (tiles)
WIRE_BIAS = 1.0      # vies de random_topology para pares curtos (0 = uniforme)


def set_wire_cap(cap):
    global WIRE_CAP
    WIRE_CAP = None if cap is None else int(cap)


def grid_w(n):
    w = int(round(n ** 0.5))
    if w * w != n:
        raise ValueError(f"n={n} nao e quadrado perfeito (planta W x W)")
    return w


def elen(e, W):
    u, v = e
    return abs(u % W - v % W) + abs(u // W - v // W)


def wire_total(edges, n):
    W = grid_w(n)
    return sum(elen(e, W) for e in edges)


def apply_wire_args(a, n, m):
    """Define o teto a partir de --wire-cap / --wire-mult (usar apos o parse)."""
    cap = getattr(a, "wire_cap", None)
    mult = getattr(a, "wire_mult", None)
    if cap is None and mult is not None:
        cap = int(round(mult * m))
    set_wire_cap(cap)
    if cap is not None:
        print(f"[fio] teto = {cap} tiles (mesh {n}x: {2 * grid_w(n) * (grid_w(n) - 1)}; "
              f"{cap / m:.2f} por link)")
    return cap


def _shuffled_pairs(n, rng):
    """Todos os pares (u,v), em ordem aleatoria. Com teto, amostra SEM reposicao
    ponderada por 1/comprimento**WIRE_BIAS (Efraimidis-Spirakis), favorecendo curtos."""
    pairs = [(u, v) for u in range(n) for v in range(u + 1, n)]
    if WIRE_CAP is None or WIRE_BIAS <= 0:
        rng.shuffle(pairs)
        return pairs
    W = grid_w(n)
    keyed = [(rng.random() ** (elen(p, W) ** WIRE_BIAS), p) for p in pairs]
    keyed.sort(key=lambda t: -t[0])
    return [p for _, p in keyed]


def _wire_fix(es, n, rng):
    """Reduz o fio de `es` (set, modificado no lugar) ate o teto, trocando links
    longos por pares livres mais curtos sem desconectar nem violar grau.
    Mantem o numero de links. True se atingiu o teto."""
    if WIRE_CAP is None:
        return True
    W = grid_w(n)
    for _ in range(3000):
        tot = sum(elen(e, W) for e in es)
        if tot <= WIRE_CAP:
            return True
        order = sorted(es, key=lambda e: (-elen(e, W), rng.random()))
        moved = False
        for e in order[:16]:
            L = elen(e, W)
            if L <= 1:
                break
            rest = set(es)
            rest.discard(e)
            if len(components(rest, n)) != 1:
                continue
            deg = degrees(rest, n)
            cand = [(u, v) for u in range(n) for v in range(u + 1, n)
                    if deg[u] < MAX_DEG and deg[v] < MAX_DEG
                    and (u, v) not in rest and elen((u, v), W) < L]
            if not cand:
                continue
            half = [c for c in cand if elen(c, W) <= (L + 1) // 2]
            rest.add(rng.choice(half or cand))
            es.clear()
            es.update(rest)
            moved = True
            break
        if not moved:
            return False
    return sum(elen(e, W) for e in es) <= WIRE_CAP
'''

EDITS = [
    # ---- ga_common.py ----
    ("ga_common.py",
     "FAIL_PENALTY = 1e6   # fitness de uma simulacao que falhou/travou\n",
     WIRE_BLOCK),
    ("ga_common.py",
     "    if max(degrees(edges, n)) > MAX_DEG:\n        return False\n    return len(components(edges, n)) == 1\n",
     "    if max(degrees(edges, n)) > MAX_DEG:\n        return False\n"
     "    if WIRE_CAP is not None and wire_total(edges, n) > WIRE_CAP:\n        return False\n"
     "    return len(components(edges, n)) == 1\n"),
    ("ga_common.py",
     "    while len(es) < m:\n        deg = degrees(es, n)\n        cand = _free_pairs(es, n, deg)\n"
     "        if not cand:\n            return None\n        es.add(rng.choice(cand))\n"
     "    out = canon(es)\n    return out if is_valid(out, n, m) else None\n",
     "    while len(es) < m:\n        deg = degrees(es, n)\n        cand = _free_pairs(es, n, deg)\n"
     "        if WIRE_CAP is not None:             # so pares que cabem no fio restante\n"
     "            W = grid_w(n)\n"
     "            left = WIRE_CAP - sum(elen(e, W) for e in es)\n"
     "            cand = [c for c in cand if elen(c, W) <= left] or cand\n"
     "        if not cand:\n            return None\n        es.add(rng.choice(cand))\n"
     "    if not _wire_fix(es, n, rng):\n        return None\n"
     "    out = canon(es)\n    return out if is_valid(out, n, m) else None\n"),
    ("ga_common.py",
     "        pairs = [(u, v) for u in range(n) for v in range(u + 1, n)]\n        rng.shuffle(pairs)\n        deg = [0] * n\n        es = []\n",
     "        pairs = _shuffled_pairs(n, rng)\n        deg = [0] * n\n        es = []\n"),
    ("ga_common.py",
     "        cand = [c for c in cand if c != (u, v)] or [(u, v)]\n",
     "        cand = [c for c in cand if c != (u, v)] or [(u, v)]\n"
     "        if WIRE_CAP is not None:                     # so trocas que cabem no teto\n"
     "            W = grid_w(n)\n"
     "            left = WIRE_CAP - sum(elen(e, W) for e in es)\n"
     "            cand = [c for c in cand if elen(c, W) <= left] or [(u, v)]\n"),
    ("ga_common.py",
     '    ap.add_argument("--workers", type=int, default=4)\n',
     '    ap.add_argument("--wire-mult", type=float, default=None,\n'
     '                    help="teto de fio total = wire_mult * links (so ga_optimize); sem teto se ausente")\n'
     '    ap.add_argument("--wire-cap", type=int, default=None,\n'
     '                    help="teto absoluto de fio total (tiles); prioridade sobre --wire-mult")\n'
     '    ap.add_argument("--workers", type=int, default=4)\n'),
    # ---- ga_optimize.py ----
    ("ga_optimize.py",
     "    n, m = a.nodes, a.links\n",
     "    n, m = a.nodes, a.links\n    gc.apply_wire_args(a, n, m)\n"),
    ("ga_optimize.py",
     "        init = list(dict.fromkeys(init))\n",
     "        init = list(dict.fromkeys(init))\n"
     "        if gc.WIRE_CAP is not None:\n"
     "            _ok = [e for e in init if gc.wire_total(e, n) <= gc.WIRE_CAP]\n"
     "            if len(_ok) < len(init):\n"
     "                print(f\"[fio] {len(init) - len(_ok)} semente(s) acima do teto {gc.WIRE_CAP} descartada(s)\")\n"
     "            init = _ok\n"),
    ("ga_optimize.py",
     '               "best_avg_path": avg, "best_diameter": dia,\n',
     '               "best_avg_path": avg, "best_diameter": dia,\n'
     '               "wire_cap": gc.WIRE_CAP, "best_wire": gc.wire_total(best_edges, n),\n'),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    names = sorted({e[0] for e in EDITS})
    paths, texts, crlf = {}, {}, {}
    for nme in names:
        hits = []
        for root, _, files in os.walk(a.src):
            if any(p in root for p in ("/.git", "/runs", "/__pycache__")):
                continue
            if nme in files:
                hits.append(os.path.join(root, nme))
        if len(hits) != 1:
            sys.exit(f"ERRO: esperava 1 arquivo '{nme}' sob {a.src}, achei {len(hits)}: {hits}")
        raw = open(hits[0], "rb").read().decode("utf-8")
        paths[nme], crlf[nme] = hits[0], "\r\n" in raw
        texts[nme] = raw.replace("\r\n", "\n")
        if "WIRE_CAP" in texts[nme]:
            sys.exit(f"{nme} ja contem WIRE_CAP. Nada feito.")
    errors = []
    for nme, old, new in EDITS:
        c = texts[nme].count(old)
        if c != 1:
            errors.append(f"  {nme}: ancora aparece {c}x (esperado 1): {old[:70]!r}")
            continue
        texts[nme] = texts[nme].replace(old, new, 1)
    if errors:
        sys.exit("ERRO: ancoras nao encontradas (nada foi escrito):\n" + "\n".join(errors) +
                 "\nMande os arquivos citados para eu ajustar o patch.")
    if a.check:
        print("OK: todas as ancoras foram encontradas 1x. Nada escrito (--check).")
        return
    for nme in names:
        p = paths[nme]
        if not os.path.exists(p + ".bak"):
            open(p + ".bak", "wb").write(open(p, "rb").read())
        out = texts[nme].replace("\n", "\r\n") if crlf[nme] else texts[nme]
        open(p, "wb").write(out.encode("utf-8"))
        print("patch aplicado:", p)
    print("\nFeito. Teste: py -c \"import ga_common as g; print(g.wire_total(g.mesh_edges(8), 64))\"  (esperado 112)")

if __name__ == "__main__":
    main()