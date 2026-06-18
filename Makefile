SC_ROOT = /d/Codigos/systemc-3.0.2/systemc-3.0.2
SC_SRC = $(SC_ROOT)/src
SC_OBJ = $(SC_ROOT)/objdir/src
SC_SRC2 = $(SC_ROOT)/srcs
CXX = g++
CXXFLAGS = -I./include -I./srcs -I./tests_plano_rede -I./test_plano_control -I$(SC_SRC) -I$(SC_OBJ) -Wall -O2
LDFLAGS = -L$(SC_OBJ)/.libs -lsystemc
MAIN_SOURCES = main.cpp \
               srcs/Stats.cpp \
               srcs/TrafficInjector.cpp \
               srcs/arbitro.cpp \
               srcs/sdn_controller.cpp \
			   srcs/ControlUnit.cpp

all: con.exe back.exe reset.exe burst.exe integrity.exe testevec.exe main.exe conpl.exe

conpl.exe: test_plano_control/TestControlPlane.cpp
	$(CXX) $(CXXFLAGS) test_plano_control/TestControlPlane.cpp  test_plano_control/Stats.cpp -o test_plano_control/conpl.exe $(LDFLAGS)

main.exe: main.cpp
	$(CXX) $(CXXFLAGS) $(MAIN_SOURCES) -o main.exe $(LDFLAGS)

testvec.exe: teste_vector.cpp
	$(CXX) $(CXXFLAGS) teste_vector.cpp -o testevec.exe $(LDFLAGS)

con.exe: src_plano_rede/mainCon.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainCon.cpp -o tests_plano_rede/con.exe $(LDFLAGS)

back.exe: src_plano_rede/mainBack.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainBack.cpp -o tests_plano_rede/back.exe $(LDFLAGS)

reset.exe: src_plano_rede/mainRst.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainRst.cpp -o tests_plano_rede/reset.exe $(LDFLAGS)

burst.exe: src_plano_rede/mainBurst.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainBurst.cpp -o tests_plano_rede/burst.exe $(LDFLAGS)

integrity.exe: src_plano_rede/mainIntegrity.cpp
	$(CXX) $(CXXFLAGS) src_plano_rede/mainIntegrity.cpp -o tests_plano_rede/integrity.exe $(LDFLAGS)

cleanmain:
	rm -f main.exe

clean:
	rm -f main.exe tests_plano_rede/con.exe tests_plano_rede/back.exe tests_plano_rede/reset.exe tests_plano_rede/burst.exe tests_plano_rede/integrity.exe test_plano_control/conpl.exe