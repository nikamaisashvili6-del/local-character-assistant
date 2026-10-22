#!/bin/bash
# desc: PC health: disk space, RAM, GPU memory, load
# keywords: health, status, check, free, usage, how, much, eating, resources, disk, space, ram, memory, gpu, cpu, storage, left
# confirm: no
echo "Disk:"; df -h / /media/$USER/* 2>/dev/null | awk 'NR>1{print "  "$6": "$4" free ("$5" used)"}'
free -h | awk '/Mem:/{print "RAM: "$3" used of "$2", "$7" available"}'
nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu --format=csv,noheader 2>/dev/null | awk -F', ' '{print "GPU: "$1" of "$2" VRAM, "$3"C"}'
echo "Load (1/5/15 min): $(cut -d' ' -f1-3 /proc/loadavg)"
