#!/bin/bash
pkill -9 -f "src.main"
pkill -9 -f "python.*main"
pkill -9 -f "multiprocessing"
sleep 1
killall -9 python 2>/dev/null
echo "O2Monitor stopped"
