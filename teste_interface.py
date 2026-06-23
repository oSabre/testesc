import json
import numpy as np
import subprocess
import os
import matplotlib.pyplot as plt
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

def verificar_conectividade(u_originais, v_propostos, n_nodes=16):
    """
    Verifica se todos os nós estão interligados globalmente na topologia.
    Trata as conexões como bidirecionais para refletir o comportamento real da NoC,
    evitando que o filtro barre topologias válidas baseadas na Mesh.
    """
    # Monta a lista de adjacência do grafo como NÃO-DIRECIONADO (bidirecional)
    adj = {i: [] for i in range(n_nodes)}
    for u, v in zip(u_originais, v_propostos):
        adj[u].append(v)
        adj[v].append(u)  # Garante o fluxo de ida e volta no teste estrutural
    
    # Em grafos não-direcionados, basta rodar a BFS uma única vez a partir do nó 0
    visitados = set()
    fila = [0]
    while fila:
        no = fila.pop(0)
        if no not in visitados:
            visitados.add(no)
            fila.extend(adj[no])
            
    # Se a busca visitou todos os 16 nós, o grafo é estruturalmente conexo
    return len(visitados) == n_nodes


class SystemCProblem(ElementwiseProblem):
    def __init__(self, caminho_executavel, caminho_trafego, arquivo_modelo):
        with open(arquivo_modelo, "r") as f:
            config_template = json.load(f)
        
        self.u_originais = [link["u"] for link in config_template["topology"]]
        
        n_vars = len(self.u_originais)  # 24 links
        xl = 0                          
        xu = 15                         # IDs dos roteadores de 0 a 15
        
        super().__init__(n_var=n_vars, n_obj=2, n_ieq_constr=n_vars, xl=xl, xu=xu)
        
        self.caminho_executavel = caminho_executavel
        self.caminho_trafego = caminho_trafego
        self.arquivo_modelo = arquivo_modelo

    def _evaluate(self, x, out, *args, **kwargs):
        valores_v = [int(np.round(val)) for val in x]
        
        # 1. Aplicar restrições básicas (u == v)
        restricoes = []
        for i in range(len(valores_v)):
            if valores_v[i] == self.u_originais[i]:
                restricoes.append(1.0)  # Força a violação
            else:
                restricoes.append(-1.0)
        out["G"] = restricoes

        if any(g > 0 for g in restricoes):
            out["F"] = [1e9, 1e9]
            return

        # 2. Filtro de Segurança: Validar conectividade estrutural do grafo
        if not verificar_conectividade(self.u_originais, valores_v, n_nodes=16):
            out["F"] = [1e9, 1e9] 
            return

        # 3. CÁLCULO DA ÁREA (Ligações físicas únicas compartilhadas)
        ligacoes_fisicas = set()
        for i in range(len(valores_v)):
            u = self.u_originais[i]
            v = valores_v[i]
            ligacoes_fisicas.add(tuple(sorted([u, v])))
        area = len(ligacoes_fisicas)

        # 4. Montar o JSON temporário
        with open(self.arquivo_modelo, "r") as f:
            config = json.load(f)
        
        for i in range(len(valores_v)):
            config["topology"][i]["v"] = valores_v[i]
        
        arquivo_temp = "config_atual.json"
        with open(arquivo_temp, "w") as f:
            json.dump(config, f, indent=2)
        
        # 5. Executar o simulador controlando códigos de saída do sistema
        try:
            subprocess.run(
                [self.caminho_executavel, arquivo_temp, self.caminho_trafego],
                check=False,  # Permite que o Python leia o CSV mesmo se o executável retornar código != 0
                capture_output=True,
                text=True
            )
            
            latency = 1e9  
            nome_arquivo_res = "results.csv"
            
            if os.path.exists(nome_arquivo_res):
                with open(nome_arquivo_res, "r") as f:
                    conteudo = f.read()
                
                if "INCOMPLETO" in conteudo:
                    latency = 1e9  
                else:
                    achou_latencia = False
                    for linha in conteudo.splitlines():
                        if "Average Total Latency:" in linha:
                            valor_str = linha.split(":")[1].replace("ns", "").strip()
                            latency = float(valor_str)
                            achou_latencia = True
                            break
                    
                    if not achou_latencia:
                        print("[Aviso] Arquivo de resultados existe, mas a linha 'Average Total Latency:' não foi encontrada.")
                        latency = 1e9
            else:
                print(f"[Aviso] O arquivo '{nome_arquivo_res}' não foi encontrado após a execução.")
                latency = 1e9

            out["F"] = [latency, area]
            
        except Exception as e:
            print(f"[Erro Crítico] Falha na execução ou leitura dos dados: {e}")
            out["F"] = [1e9, 1e9]


# --- Configuração do Otimizador ---
if __name__ == "__main__":
    
    arquivo_base = "config.json"
    
    problem = SystemCProblem(
        caminho_executavel="./main.exe",
        caminho_trafego="traces/trace_01.csv", 
        arquivo_modelo=arquivo_base
    )
    
    # Mapeamento exato dos destinos 'v' da sua topologia base funcional (Mesh estável)
    v_mesh_original = [
        1, 2, 3,       # Linha 0
        5, 6, 7,       # Linha 1
        9, 10, 11,     # Linha 2
        13, 14, 15,    # Linha 3
        4, 8, 12,      # Coluna 0
        5, 9, 13,      # Coluna 1
        6, 10, 14,     # Coluna 2
        7, 11, 15      # Coluna 3
    ]
    
    # População inicial inteligente baseada na Mesh funcional
    tamanho_pop = 40
    pop_inicial = np.tile(v_mesh_original, (tamanho_pop, 1)).astype(float)
    
    # Adicionamos pequenas perturbações aleatórias nas outras cópias para dar diversidade
    for i in range(1, tamanho_pop):
        mutacoes = np.random.randint(1, 4) 
        for _ in range(mutacoes):
            idx_aleatorio = np.random.randint(0, 24)
            pop_inicial[i, idx_aleatorio] = float(np.random.randint(0, 16))

    # Inicializa o NSGA-II alimentado com a nossa população inicial guiada
    algorithm = NSGA2(pop_size=tamanho_pop, sampling=pop_inicial)
    
    termination = get_termination("n_gen", 10)
    
    print("Iniciando otimização guiada da Mesh 16 nós (Blindado contra quedas)...")
    
    res = minimize(
        problem,
        algorithm,
        termination,
        seed=1,
        save_history=True,
        verbose=True
    )
    
    print("\n--- Otimização Concluída ---")
    print("Fronteira de Pareto - Melhores combinações de destinos 'v' encontradas:")
    melhores_topologias = np.round(res.X).astype(int)
    print(melhores_topologias)
    
    valores_objetivos = res.F
    
    # Filtra soluções penalizadas com 1e9 para não distorcer a escala do gráfico
    indices_validos = valores_objetivos[:, 0] < 1e8
    objetivos_filtrados = valores_objetivos[indices_validos]

    if len(objetivos_filtrados) > 0:
        plt.figure(figsize=(10, 6))
        
        # Plota os pontos [Latência, Área]
        plt.scatter(
            objetivos_filtrados[:, 0], 
            objetivos_filtrados[:, 1], 
            color="red", 
            edgecolors="black", 
            s=80, 
            zorder=3,
            label="Topologias da Fronteira"
        )
        
        plt.title("Fronteira de Pareto - Otimização de Topologia NoC", fontsize=14, fontweight='bold')
        plt.xlabel("Latência Média (ns)", fontsize=12)
        plt.ylabel("Área (Total de Ligações Físicas Únicas)", fontsize=12)
        
        # Garante que o eixo Y exiba apenas números inteiros
        plt.gca().yaxis.get_major_locator().set_params(integer=True)
        
        plt.grid(True, linestyle="--", alpha=0.5, zorder=1)
        plt.legend(loc="upper right")
        
        print("\n[Gráfico] Renderizando a Fronteira de Pareto... Feche a janela para encerrar.")
        plt.show()
    else:
        print("\n[Aviso] Nenhuma solução válida filtrada para plotar o gráfico.")

    print("\nResultados [Latência Média (ns), Área (Ligações Únicas)]:")
    print(res.F)