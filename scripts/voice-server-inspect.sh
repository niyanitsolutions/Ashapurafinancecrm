#!/usr/bin/env bash
# Read-only inventory. Run on the actual CRM host; never source its .env files.
set -u
section() { printf '\n== %s ==\n' "$1"; }
section 'Operating system'
uname -srm
if [ -r /etc/os-release ]; then
  grep -E '^(NAME|VERSION|ID|VERSION_ID)=' /etc/os-release
fi
section 'CPU and virtualization'
if command -v lscpu >/dev/null 2>&1; then
  lscpu | grep -E '^(Architecture|CPU\(s\)|On-line CPU|Model name|Thread|Core|Socket|Hypervisor|Virtualization)'
fi
section 'Memory and swap'
free -h
section 'Filesystem capacity'
df -h / /opt/afs-crm /var/lib 2>/dev/null || true
section 'GPU and VRAM'
if command -v nvidia-smi >/dev/null 2>&1; then
  timeout 10 nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader
elif command -v lspci >/dev/null 2>&1; then
  lspci | grep -Ei 'VGA|3D|Display' || true
  printf 'NVIDIA runtime not available; GPU usability and VRAM remain unverified.\n'
else
  printf 'No GPU inventory utility available; no GPU capability inferred.\n'
fi
section 'Docker availability (no container environment or logs)'
if command -v docker >/dev/null 2>&1; then
  docker --version
  timeout 10 docker info --format 'Server={{.ServerVersion}} CPUs={{.NCPU}} MemoryBytes={{.MemTotal}}' 2>/dev/null || printf 'Docker daemon unavailable or permission denied.\n'
  timeout 10 docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null || true
else
  printf 'Docker client absent.\n'
fi
section 'Known CRM and optional voice service state'
if command -v systemctl >/dev/null 2>&1; then
  for unit in afs-crm-backend afs-crm-worker afs-crm-arq-worker mongod redis-server nginx asterisk ollama; do
    systemctl show "$unit.service" --no-pager \
      --property=Id,LoadState,ActiveState,SubState,MemoryCurrent,CPUUsageNSec,TasksCurrent,NRestarts 2>/dev/null || true
  done
fi
section 'Current aggregate workload'
uptime
vmstat 1 3 2>/dev/null || true
printf '\nInventory only: no restart, installation, model pull, call, secret read or configuration change performed.\n'
