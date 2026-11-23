#!/usr/bin/env python3
"""Cria links de compatibilidade para #include "..." com maiusculas diferentes do arquivo real (Windows -> Linux).
Nao altera o codigo-fonte: os links ficam em ./compat_linux (o Makefile.linux inclui essa pasta com -I).
Uso (na pasta do projeto): python3 fix_case_includes.py
"""
import os, re, sys
DIRS = ['include', 'srcs', 'tests_plano_rede', 'test_plano_control', 'src_plano_rede', '.']
OUT = 'compat_linux'
INC = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)

def files_in(d):
    return [os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))] if os.path.isdir(d) else []

def main():
    sources = [f for d in DIRS for f in files_in(d) if f.endswith(('.h', '.hpp', '.cpp'))]
    headers = {}
    for d in DIRS:
        for f in files_in(d):
            if f.endswith(('.h', '.hpp')):
                headers.setdefault(os.path.basename(f).lower(), []).append(f)
    os.makedirs(OUT, exist_ok=True)
    made, bad = {}, []
    for s in sources:
        for name in INC.findall(open(s, errors='replace').read()):
            base = os.path.basename(name)
            cands = [os.path.join(os.path.dirname(s), name)] + [os.path.join(d, name) for d in DIRS]
            if any(os.path.isfile(c) for c in cands):
                continue                                   # ja resolve com a grafia exata
            hits = headers.get(base.lower(), [])
            if len(hits) == 1:
                link = os.path.join(OUT, name)
                os.makedirs(os.path.dirname(link) or OUT, exist_ok=True)
                target = os.path.relpath(hits[0], os.path.dirname(link))
                if not os.path.lexists(link):
                    os.symlink(target, link)
                made[name] = hits[0]
            elif base not in made and not base.startswith(('sysc', 'nlohmann')):
                bad.append((s, name, hits))
    for k, v in sorted(made.items()): print(f"link: {k} -> {v}")
    for s, n, h in bad: print(f"AVISO: {s} inclui \"{n}\": sem arquivo correspondente ({h or 'nenhum candidato'})")
    if not made and not bad: print("nenhum include precisou de correcao")

if __name__ == '__main__': main()