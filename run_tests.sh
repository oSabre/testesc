#!/bin/bash

# Array com a lista de testes
TESTES=("tests_plano_rede/reset.exe" "tests_plano_rede/con.exe" "tests_plano_rede/back.exe" "tests_plano_rede/burst.exe" "tests_plano_rede/integrity.exe")

echo "========================================="
echo " Iniciando Bateria de Testes do Hardware "
echo "========================================="

for teste in "${TESTES[@]}"; do
    echo "-----------------------------------------"
    echo " Rodando: $teste"
    echo "-----------------------------------------"
    ./$teste
    echo -e "\n"
done

echo "Bateria de testes finalizada."