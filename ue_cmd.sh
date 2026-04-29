#!/bin/bash
cd ~/openairinterface5g/cmake_targets/ran_build/build && echo "Widar@4321" | sudo -S RFSIMULATOR=127.0.0.1 ./nr-uesoftmodem -O ~/openairinterface5g/targets/PROJECTS/GENERIC-NR-5GC/CONF/ue.conf --rfsim --noS1 -C 3334620000 -r 189 --numerology 1 --band 78 --ssb 516 --telnetsrv --telnetsrv.listenport 9091
