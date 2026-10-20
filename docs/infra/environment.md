# Experiment environment

Recorded 2026-10-20 (WP−1). Update when versions change; every run manifest also records
versions automatically.

| Component | Value |
| --- | --- |
| Host | Windows 10 22H2, Intel Core i5-6600K (4 cores / 4 threads, 3.5 GHz), 32 GB DDR4-2133 |
| GPU | NVIDIA GeForce GTX 1060 6 GB (Pascal, compute 6.1), driver 582.66 |
| Linux | Ubuntu 24.04.5 LTS on WSL2, kernel 6.18 |
| WSL2 limits | 20 GB RAM, 4 processors, 60 GB virtual disk (SSD), 8 GB swap (HDD) |
| Access | Tailscale (host `sentinel`), SSH key-only, ufw allows `tailscale0` only |
| Toolchain | git 2.43.0, uv 0.13.2, CPython 3.12 (uv-managed) |
| Agents | Claude Code 2.1.304 (stable channel) |
| Local LLM | Ollama 0.40.6 (pinned, do not auto-update), `qwen2.5:7b` (Q4, ~84% GPU offload, 16.6 tok/s) |
| Cloud LLM | Groq API (planned, WP6) |
