#include <systemc.h>
#include "TestReset.h"

int sc_main(int argc, char* argv[]) {
    TestReset test("Reset_Bateria_1");
    sc_start();
    return 0;
}

//O que faz: Verifica se, ao ativar o sinal de rst, 
//todos os buffers internos são limpos, os sinais de ready voltam ao estado inicial e o roteador ignora dados pendentes.

//Por que é importante: Em sistemas críticos, o estado de inicialização é vital. 
//Garante que o roteador não comece processando "lixo" de memória de uma simulação anterior.

//O que esperar: Após o pulso de reset, todos os sinais de ready_in devem ser lidos como true (ou o estado inicial definido) 
// e qualquer flit "pendurado" no buffer deve ser ignorado ou descartado.