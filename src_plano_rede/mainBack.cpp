#include <systemc.h>
#include "TestBackpressure.h"

int sc_main(int argc, char* argv[]) {
    TestBackpressure test("Backpressure_Bateria_2");
    sc_start();
    return 0;
}

//O que faz: Força o roteador a processar dados enquanto o receptor mantém o sinal ready_in baixo (pausado). 
//Verifica se o roteador consegue "segurar" o dado no buffer sem perdê-lo ou corrompê-lo.

// Por que é importante: É o coração da confiabilidade. 
// Sem backpressure, a rede perderia dados sempre que houvesse um congestionamento temporário. 
// Valida que o buffer está fazendo o papel de fila corretamente.

//O que esperar: O roteador deve atrasar a entrega do dado enquanto o ready_in estiver desativado, 
// mas o dado deve ser entregue corretamente e na ordem certa assim que o sinal voltar a ficar ativo, sem perda de flits.
