import json
import numpy as np
import subprocess
import os
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination

def verificar_conectividade(u_originais, v_propostos, n_nodes=16):
    """
    Verifica se todos os nós conseguem alcançar todos os outros nós na topologia.
    Evita enviar grafos desconectados/quebrados que causam SegFault no simulador.
    """
    # Monta a lista de adjacência do grafo direcionado
    adj = {i: [] for i in range(n_nodes)}
    for u, v in zip(u_originais, v_propostos):
        adj[u].append(v)
    
    # Executa uma busca (BFS) a partir de cada nó para garantir conectividade global
    for inicio in range(n_nodes):
        visitados = set()
        fila = [inicio]
        while fila:
            no = fila.pop(0)
            if no not in visitados:
                visitados.add(no)
                fila.extend(adj[no])
        # Se algum nó não conseguiu alcançar os outros 15, o grafo é inválido
        if len(visitados) < n_nodes:
            return False
    return True


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

        # 2. Filtro de Segurança: Validar conectividade do grafo
        if not verificar_conectividade(self.u_originais, valores_v, n_nodes=16):
            out["F"] = [1e9, 1e9] # Penaliza direto sem rodar o executável e evita o crash 3221225477
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
        
        # 5. Executar o simulador controlando a falha de execução catastrófica
        try:
            subprocess.run(
                [self.caminho_executavel, arquivo_temp, self.caminho_trafego],
                check=True,
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
                    for linha in conteudo.splitlines():
                        if "Average Total Latency:" in linha:
                            valor_str = linha.split(":")[1].replace("ns", "").strip()
                            latency = float(valor_str)
            else:
                latency = 1e9

            out["F"] = [latency, area]
            
        except subprocess.CalledProcessError:
            # Captura erros de sistema do executável (como o erro 3221225477) sem derrubar o script Python
            out["F"] = [1e9, 1e9]
        except Exception as e:
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
    
    # Criamos uma população inicial inteligente baseada na Mesh funcional
    # Isso evita que o algoritmo comece atirando no escuro
    tamanho_pop = 40
    pop_inicial = np.tile(v_mesh_original, (tamanho_pop, 1)).astype(float)
    
    # Adicionamos pequenas perturbações aleatórias nas outras cópias para dar diversidade
    for i in range(1, tamanho_pop):
        mutacoes = np.random.randint(1, 4) # Altera de 1 a 3 links aleatórios por indivíduo
        for _ in range(mutacoes):
            idx_aleatorio = np.random.randint(0, 24)
            pop_inicial[i, idx_aleatorio] = float(np.random.randint(0, 16))

    # Inicializa o NSGA-II alimentado com a nossa população inicial guiada
    algorithm = NSGA2(pop_size=tamanho_pop, sampling=pop_inicial)
    
    termination = get_termination("n_gen", 20)
    
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
    
    #print("\nResultados [Latência Média (ns), Área (Ligações Únicas)]:")
    #print(res.F)