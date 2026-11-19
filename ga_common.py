#!/usr/bin/env python3
"""
ga_common.py -- utilitarios compartilhados pelo pipeline GA (pymoo):

  * representacao canonica de topologias (tupla ordenada de arestas (u,v), u<v)
  * validade (grau <= 4, conexa, exatamente m links) + reparo
  * operadores geneticos (crossover, mutacao, topologia aleatoria)
  * Evaluator: roda o simulador (main.exe) em diretorio temporario e devolve
    a latencia media PENALIZADA (fitness), com cache em disco.

Por que ordem canonica: as portas dos roteadores seguem a ORDEM DOS LINKS no
JSON (TopologyManager::add_link) e o Dijkstra desempata pela ordem das portas.
Se a mesma topologia fosse escrita com ordens diferentes, a latencia mudaria.
Aqui toda topologia e SEMPRE escrita ordenada por (u,v).
"""

import csv
import hashlib
import json
import os
import random
import shlex
import shutil
import statistics as st
import subprocess
import tempfile
import threading
import completion_alarm as _ca  # alarme de conclusao (<100%)
from collections import deque

MAX_DEG = 4          # NUM_PORTS - 1 (porta 0 = local)
FAIL_PENALTY = 1e6   # fitness de uma simulacao que falhou/travou


# ----------------------------------------------------------------------------
# Topologia
# ----------------------------------------------------------------------------
def canon(edges):
    return tuple(sorted((min(u, v), max(u, v)) for u, v in edges if u != v))


def edges_hash(edges):
    return hashlib.md5(str(canon(edges)).encode()).hexdigest()[:16]


def edges_from_config(path):
    with open(path) as f:
        cfg = json.load(f)
    return canon((l["u"], l["v"]) for l in cfg["topology"])


def mesh_edges(side=8):
    e = []
    for r in range(side):
        for c in range(side):
            i = r * side + c
            if c < side - 1:
                e.append((i, i + 1))
            if r < side - 1:
                e.append((i, i + side))
    return canon(e)


def _adj(edges, n):
    a = [[] for _ in range(n)]
    for u, v in edges:
        a[u].append(v)
        a[v].append(u)
    return a


def degrees(edges, n):
    d = [0] * n
    for u, v in edges:
        d[u] += 1
        d[v] += 1
    return d


def components(edges, n):
    a = _adj(edges, n)
    seen = [-1] * n
    comps = []
    for s in range(n):
        if seen[s] >= 0:
            continue
        cid = len(comps)
        seen[s] = cid
        q = deque([s])
        comp = [s]
        while q:
            u = q.popleft()
            for v in a[u]:
                if seen[v] < 0:
                    seen[v] = cid
                    q.append(v)
                    comp.append(v)
        comps.append(comp)
    return comps


def is_valid(edges, n, m):
    edges = canon(edges)
    if len(edges) != m or len(set(edges)) != m:
        return False
    if max(degrees(edges, n)) > MAX_DEG:
        return False
    return len(components(edges, n)) == 1


def avg_path_and_diameter(edges, n):
    a = _adj(edges, n)
    tot = cnt = dia = 0
    for s in range(n):
        d = {s: 0}
        q = deque([s])
        while q:
            u = q.popleft()
            for v in a[u]:
                if v not in d:
                    d[v] = d[u] + 1
                    q.append(v)
        for t, x in d.items():
            if t != s:
                tot += x
                cnt += 1
                dia = max(dia, x)
    return tot / max(cnt, 1), dia


def _removable(edges, n):
    """Arestas cuja remocao NAO aumenta o numero de componentes."""
    base = len(components(edges, n))
    out = []
    for e in edges:
        rest = [x for x in edges if x != e]
        if len(components(rest, n)) == base:
            out.append(e)
    return out


def _free_pairs(es, n, deg):
    return [(u, v) for u in range(n) for v in range(u + 1, n)
            if deg[u] < MAX_DEG and deg[v] < MAX_DEG and (u, v) not in es]


def repair(edges, n, m, rng):
    """Leva um conjunto qualquer de arestas a uma topologia VALIDA
    (grau<=4, conexa, exatamente m links). Devolve tupla canonica ou None."""
    es = set(canon(edges))
    # 1) respeita o grau maximo
    deg = [0] * n
    kept = set()
    lst = list(es)
    rng.shuffle(lst)
    for u, v in lst:
        if deg[u] < MAX_DEG and deg[v] < MAX_DEG:
            kept.add((u, v))
            deg[u] += 1
            deg[v] += 1
    es = kept
    # 2) conecta (adiciona ponte entre componentes; se nao houver grau livre,
    #    libera grau removendo uma aresta nao-ponte)
    for _ in range(400):
        comps = components(es, n)
        if len(comps) == 1:
            break
        comps.sort(key=len)
        S, R = comps[0], [x for c in comps[1:] for x in c]
        deg = degrees(es, n)
        sa = [x for x in S if deg[x] < MAX_DEG]
        rb = [x for x in R if deg[x] < MAX_DEG]
        if sa and rb:
            es.add(canon([(rng.choice(sa), rng.choice(rb))])[0])
        else:
            rem = _removable(es, n)
            Sset = set(S)
            pref = [e for e in rem if (e[0] in Sset) == (not sa) or (e[1] in Sset) == (not sa)] or rem
            if not pref:
                return None
            es.discard(rng.choice(pref))
    else:
        return None
    # 3) ajusta para exatamente m links mantendo conexao
    while len(es) > m:
        rem = _removable(es, n)
        if not rem:
            return None
        es.discard(rng.choice(rem))
    while len(es) < m:
        deg = degrees(es, n)
        cand = _free_pairs(es, n, deg)
        if not cand:
            return None
        es.add(rng.choice(cand))
    out = canon(es)
    return out if is_valid(out, n, m) else None


def random_topology(n, m, rng):
    for _ in range(100):
        pairs = [(u, v) for u in range(n) for v in range(u + 1, n)]
        rng.shuffle(pairs)
        deg = [0] * n
        es = []
        for u, v in pairs:
            if len(es) >= m:
                break
            if deg[u] < MAX_DEG and deg[v] < MAX_DEG:
                es.append((u, v))
                deg[u] += 1
                deg[v] += 1
        r = repair(es, n, m, rng)
        if r is not None:
            return r
    raise RuntimeError("nao consegui gerar topologia aleatoria valida")


def crossover(a, b, n, m, rng):
    """Mantem as arestas comuns e sorteia o restante da diferenca simetrica."""
    sa, sb = set(a), set(b)
    child = set(sa & sb)
    diff = list(sa ^ sb)
    rng.shuffle(diff)
    deg = degrees(child, n)
    for u, v in diff:
        if len(child) >= m:
            break
        if deg[u] < MAX_DEG and deg[v] < MAX_DEG:
            child.add((u, v))
            deg[u] += 1
            deg[v] += 1
    r = repair(child, n, m, rng)
    return r if r is not None else canon(a)


def mutate(edges, n, m, rng, max_ops=3):
    """1..max_ops operacoes: troca de aresta (remove uma, adiciona outra) ou
    reencaixe de uma ponta de aresta. Sempre devolve topologia valida."""
    es = set(canon(edges))
    ops = rng.randint(1, max_ops)
    for _ in range(ops):
        rem = _removable(es, n) or list(es)
        u, v = rng.choice(rem)
        es.discard((u, v))
        deg = degrees(es, n)
        if rng.random() < 0.5:                       # reencaixe de uma ponta
            keep = rng.choice((u, v))
            cand = [(min(keep, w), max(keep, w)) for w in range(n)
                    if w != keep and deg[w] < MAX_DEG and deg[keep] < MAX_DEG
                    and (min(keep, w), max(keep, w)) not in es]
        else:                                        # troca livre
            cand = _free_pairs(es, n, deg)
        cand = [c for c in cand if c != (u, v)] or [(u, v)]
        es.add(rng.choice(cand))
    r = repair(es, n, m, rng)
    return r if r is not None else canon(edges)


# ----------------------------------------------------------------------------
# Configuracao e avaliacao
# ----------------------------------------------------------------------------
def build_config(template, edges, traffic, seed, cus, duration_us,
                 num_packets, injection, np_overrides):
    cfg = json.loads(json.dumps(template))
    cfg["topology"] = [{"id": i, "u": u, "v": v} for i, (u, v) in enumerate(canon(edges))]
    cfg.pop("topology_description", None)
    np_ = cfg.setdefault("network_params", {})
    if cus is not None:
        np_["num_control_units"] = cus
    np_.update(np_overrides or {})
    t = cfg.setdefault("traffic", {})
    t["mode"] = traffic
    if num_packets is not None:
        t["num_packets"] = num_packets
    t["seed"] = seed                      # trafego DIFERENTE por replica
    inj = dict(injection or {})
    inj["seed"] = seed
    t["injection"] = inj
    s = cfg.setdefault("simulation", {})
    s["seed"] = seed
    s["output_file"] = "results.csv"
    if duration_us is not None:
        s["duration_us"] = duration_us
    return cfg


def parse_results(path):
    vals = {}
    with open(path, newline="") as f:
        for r in csv.reader(f):
            if len(r) >= 2:
                vals[r[0].strip()] = r[1].strip()

    flows_data, flows_ctrl = [], []
    with open(path, newline="") as f:
        for r in csv.reader(f):
            if len(r) >= 6 and r[2].strip() == "0":
                try:
                    flows_ctrl.append(float(r[3]))
                    flows_data.append(float(r[4]))
                except ValueError:
                    pass          # N/A (nao concluido) ou linha de resumo

    def num(key):
        try:
            return float(vals[key])
        except (KeyError, ValueError):
            return None
    return {
        "pen": num("Latencia media penalizada ciclos"),
        "exact": num("Latencia media exata sem arredondar ciclos"),
        "completion": num("Taxa de conclusao (%)"),
        "penalized_flows": num("Fluxos nao concluidos penalizados"),
        "penalty": num("Penalidade por fluxo (ciclos)"),
        "stuck_tx": num("Presos em transmissao (rota alocada mas sem confirmacao)"),
        "stuck_route": num("Presos em roteamento (aguardando alocacao de rota)"),
        "timeouts": num("Descartados por timeout de roteamento"),
        "not_started": num("Nao iniciados (fora da janela de simulacao)"),
        "data": st.mean(flows_data) if flows_data else None,
        "control": st.mean(flows_ctrl) if flows_ctrl else None,
    }


def _file_md5(path):
    """Hash do binario: entra na chave do cache (rebuild => cache antigo ignorado)."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except OSError:
        return ""


class Evaluator:
    """Fitness = media (entre as seeds de treino) da latencia media
    penalizada, em ciclos. Menor = melhor. Seeds FIXAS => fitness
    deterministica e comparavel entre geracoes. Resultados em cache."""

    def __init__(self, bin_cmd, template, traffic, seeds, cus=None,
                 duration_us=None, num_packets=None, injection=None,
                 np_overrides=None, timeout=300, cache_path=None, quiet=True,
                 objective="total"):
        parts = shlex.split(bin_cmd)
        if parts and os.path.exists(parts[0]):
            parts[0] = os.path.abspath(parts[0])
        self.cmd = parts
        self.bin_id = "".join(_file_md5(x) for x in parts if os.path.isfile(x))
        self.objective = objective
        self.template = template
        self.traffic = traffic
        self.seeds = list(seeds)
        self.cus = cus
        self.duration_us = duration_us
        self.num_packets = num_packets
        self.injection = injection or {"mode": "burst", "burst_max": 4}
        self.np_overrides = np_overrides or {}
        self.timeout = timeout
        self.quiet = quiet
        self.cache_path = cache_path
        self.lock = threading.Lock()
        self.cache = {}
        self.n_sim_evals = 0
        self.settings_key = hashlib.md5(json.dumps(
            [traffic, self.seeds, cus, duration_us, num_packets, self.injection,
             self.np_overrides, template.get("network_params", {}), objective, self.bin_id],
            sort_keys=True, default=str).encode()).hexdigest()[:10]
        if cache_path and os.path.exists(cache_path):
            with open(cache_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if rec.get("settings") == self.settings_key and rec.get("fitness", 0) < FAIL_PENALTY:
                        self.cache[rec["hash"]] = rec

    def _alarm_ctx(self, edges):
        return f"{self.traffic} cus={self.cus} topo={edges_hash(canon(edges))[:8]}"

    def run_one(self, edges, seed):
        cfg = build_config(self.template, edges, self.traffic, seed, self.cus,
                           self.duration_us, self.num_packets, self.injection,
                           self.np_overrides)
        tmp = tempfile.mkdtemp(prefix="ga_")
        try:
            os.makedirs(os.path.join(tmp, "log"), exist_ok=True)
            with open(os.path.join(tmp, "config.json"), "w") as f:
                json.dump(cfg, f)
            try:
                subprocess.run(self.cmd, cwd=tmp, timeout=self.timeout,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False)
                res = parse_results(os.path.join(tmp, "results.csv"))
                _ca.record(self._alarm_ctx(edges), seed, res)
                if res["pen"] is None:
                    raise ValueError("resultado sem latencia penalizada")
                res["fit"] = res["pen"]
                if self.objective == "data":
                    # latencia de DADOS dos concluidos + penalidade p/ nao concluidos
                    c = (res["completion"] or 0.0) / 100.0
                    pen = res["penalty"] if res["penalty"] is not None else res["pen"]
                    res["fit"] = c * (res["data"] or 0.0) + (1 - c) * pen
                return res
            except Exception as exc:  # falha => penalidade grande, nao derruba o GA
                if not self.quiet:
                    print(f"[aviso] simulacao falhou (seed {seed}): {exc}")
                return {"pen": FAIL_PENALTY, "fit": FAIL_PENALTY, "exact": None,
                        "completion": 0.0, "penalized_flows": None, "data": None,
                        "control": None}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def evaluate(self, edges):
        edges = canon(edges)
        h = edges_hash(edges)
        with self.lock:
            if h in self.cache:
                return self.cache[h]
        runs = [self.run_one(edges, s) for s in self.seeds]
        pens = [r["fit"] for r in runs]
        n_fail = sum(1 for p in pens if p >= FAIL_PENALTY)
        comps = [r["completion"] for r in runs if r["completion"] is not None]
        rec = {"hash": h, "settings": self.settings_key,
               "fitness": st.mean(pens),
               "std": st.stdev(pens) if len(pens) > 1 else 0.0,
               "per_seed": pens,
               "completion": st.mean(comps) if comps else 0.0,
               "data": (st.mean([r["data"] for r in runs if r["data"] is not None])
                        if any(r["data"] is not None for r in runs) else None),
               "control": (st.mean([r["control"] for r in runs if r["control"] is not None])
                           if any(r["control"] is not None for r in runs) else None),
               "exact": (st.mean([r["exact"] for r in runs if r["exact"] is not None])
                         if any(r["exact"] is not None for r in runs) else None),
               "edges": [list(e) for e in edges]}
        rec["n_fail"] = n_fail
        if n_fail:
            # NUNCA cacheia falhas: uma falha transitoria (timeout, antivirus,
            # disco) ficaria gravada para sempre e envenenaria as proximas execucoes.
            self.n_failed_evals = getattr(self, "n_failed_evals", 0) + 1
            print(f"[ALERTA] {n_fail}/{len(pens)} simulacoes falharam para a topologia "
                  f"{h} (seeds {self.seeds}); resultado NAO foi para o cache. "
                  f"Rode o main.exe manualmente numa pasta com esse config para ver o erro.",
                  flush=True)
            return rec
        with self.lock:
            self.cache[h] = rec
            self.n_sim_evals += 1
            if self.cache_path:
                with open(self.cache_path, "a") as f:
                    f.write(json.dumps(rec) + "\n")
        return rec


def load_template(path):
    with open(path) as f:
        return json.load(f)


def parse_kv(items):
    """['chave=valor', ...] -> dict com numeros convertidos."""
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        if v.lower() in ("true", "false"):
            out[k] = (v.lower() == "true")
            continue
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        out[k] = v
    return out


def common_args(ap):
    """Argumentos de avaliacao compartilhados por todos os scripts."""
    ap.add_argument("--bin", default="./main.exe", help="executavel do simulador (ou comando)")
    ap.add_argument("--template", default="configs/configs_ciclos/config_mesh_64.json",
                    help="config base (network_params, traffic, simulation)")
    ap.add_argument("--traffic", default="uniform",
                    choices=["uniform", "bit_reversal", "butterfly", "mix"],
                    help="mix = GA generalista (media normalizada dos padroes de --mix-patterns)")
    ap.add_argument("--mix-patterns", nargs="+", default=["uniform", "bit_reversal", "butterfly"],
                    help="padroes do objetivo mix")
    ap.add_argument("--cus", type=int, default=None, help="num_control_units")
    ap.add_argument("--duration-us", type=float, default=None)
    ap.add_argument("--num-packets", type=int, default=None)
    ap.add_argument("--injection-mode", default="burst",
                    choices=["burst", "poisson", "simultaneous", "fixed"])
    ap.add_argument("--burst-max", type=int, default=4)
    ap.add_argument("--spacing-ns", type=int, default=100,
                    help="espacamento medio entre fluxos (carga). Maior = rede menos carregada")
    ap.add_argument("--objective", default="total", choices=["total", "data"],
                    help="total = latencia total penalizada; data = latencia de dados dos "
                         "concluidos (+penalidade p/ nao concluidos)")
    ap.add_argument("--np", action="append", default=[],
                    help="override de network_params: chave=valor (repetivel)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=300)
    return ap


def evaluator_from_args(a, seeds, cache_path=None):
    return Evaluator(
        a.bin, load_template(a.template), a.traffic, seeds, cus=a.cus,
        duration_us=a.duration_us, num_packets=a.num_packets,
        injection={"mode": a.injection_mode, "burst_max": a.burst_max,
                   "spacing_ns": a.spacing_ns},
        np_overrides=parse_kv(a.np), timeout=a.timeout, cache_path=cache_path,
        objective=a.objective)


class MixEvaluator:
    """Objetivo GENERALISTA: media, entre padroes de trafego, da razao
    fitness_padrao(topologia) / fitness_padrao(mesh). Valor < 1 => melhor que a
    mesh em media; a normalizacao impede que um padrao de latencia alta domine.
    Mesma interface do Evaluator (evaluate/cache/template/injection/np_overrides)."""

    def __init__(self, evaluators, mesh_edges_, weights=None):
        self.evs = evaluators                     # dict padrao -> Evaluator
        self.patterns = list(evaluators)
        self.weights = weights or {p: 1.0 for p in self.patterns}
        first = evaluators[self.patterns[0]]
        self.template, self.injection = first.template, first.injection
        self.np_overrides, self.traffic = first.np_overrides, "mix"
        self.cache, self.lock = {}, threading.Lock()
        self.base = {p: self.evs[p].evaluate(mesh_edges_)["fitness"] for p in self.patterns}
        bad = [p for p, v in self.base.items() if v >= FAIL_PENALTY]
        if bad:
            raise SystemExit(f"[ERRO] simulacao da mesh falhou nos padroes {bad}; corrija antes de rodar o GA.")

    def evaluate(self, edges):
        edges = canon(edges)
        h = edges_hash(edges)
        with self.lock:
            if h in self.cache:
                return self.cache[h]
        per = {p: self.evs[p].evaluate(edges) for p in self.patterns}
        if any(r["fitness"] >= FAIL_PENALTY for r in per.values()):
            return {"hash": h, "fitness": FAIL_PENALTY, "std": 0.0, "completion": 0.0,
                    "per_pattern": {p: None for p in per}}
        wsum = sum(self.weights.values())
        ratio = {p: per[p]["fitness"] / self.base[p] for p in per}
        fit = sum(self.weights[p] * ratio[p] for p in per) / wsum
        n = min(len(r["per_seed"]) for r in per.values())
        seedwise = [sum(self.weights[p] * per[p]["per_seed"][i] / self.base[p] for p in per) / wsum
                    for i in range(n)]
        rec = {"hash": h, "fitness": fit,
               "std": st.stdev(seedwise) if len(seedwise) > 1 else 0.0,
               "completion": st.mean(r["completion"] for r in per.values()),
               "per_pattern": {p: ratio[p] for p in per}}
        with self.lock:
            self.cache[h] = rec
        return rec