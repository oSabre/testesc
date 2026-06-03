#ifndef TESTBENCH_H
#define TESTBENCH_H

#include <systemc.h>
#include "TopologyManager.h"
#include <iostream>

SC_MODULE(Testbench) {
    TopologyManager* tm;

    SC_CTOR(Testbench) {
        tm = new TopologyManager(4);
        SC_THREAD(run_test); 
    }

    void run_test(){
        tm->add_link(0, 0, 1);
        tm->add_link(1, 1, 2);
        tm->add_link(2, 2, 3);

        std::vector<int> path = {0, 1, 2}; // Caminho de 0 para 2
        std::vector<int> path2 = {0, 1, 3};
        std::vector<int> pathCycle = {0, 1, 0};
        std::vector<int> pathImp = {0, 99};
        
        /*
        sc_spawn([&]() {
            if (tm->try_allocate_path(path)) std::cout << "Thread 1 venceu!" << std::endl;
        });
        sc_spawn([&]() {
            wait(1, SC_NS); // Pequeno atraso para simular concorrência
            if (!tm->try_allocate_path(path2)) std::cout << "Thread 2 bloqueada (correto)!" << std::endl;
        });

        tm->release_path(path);
        tm->release_path(path2);
        */

        //Caminho Impossível
        if (tm->try_allocate_path(path2)) std::cout << "Tentando alocar 0,1,3" << std::endl;
        //Caminho Cíclico
        if (tm->try_allocate_path(pathCycle)) std::cout << "Ciclo Alocado 0,1,0" << std::endl;
        tm->release_path(pathCycle);
        // Id inexistente
        if (tm->try_allocate_path(pathImp)) std::cout << "Caminho impossível" << std::endl;
        // Teste 1: Alocação
        /*
        if (tm->try_allocate_path(path)) {
            std::cout << "Caminho alocado com sucesso!" << std::endl;
        } else {
            std::cout << "Falha na alocação!" << std::endl;
        }
        */

        // Teste 2: Tentar alocar o mesmo caminho (deve falhar)
        /*
        if (!tm->try_allocate_path(path)) {
            std::cout << "Teste de bloqueio passou (link ocupado)." << std::endl;
        }
        */

        // Teste 3: Liberar e tentar novamente
        /*
        tm->release_path(path);
        if (tm->try_allocate_path(path)) {
            std::cout << "Teste de liberacao passou." << std::endl;
        }
        */
    }

};

#endif