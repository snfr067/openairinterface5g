#!/bin/bash
cd ~/openairinterface5g/cmake_targets/ran_build/build && echo "Widar@4321" | sudo -S -E RFSIMULATOR=server ./nr-softmodem -O ~/openairinterface5g/targets/PROJECTS/GENERIC-NR-5GC/CONF/gnb.sa.band78.fr1.189PRB.rfsim.conf --rfsim --noS1 --telnetsrv --telnetsrv.listenport 9090 2>&1 | tee /tmp/gnb.log
