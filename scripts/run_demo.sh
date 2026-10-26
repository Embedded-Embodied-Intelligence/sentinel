#!/usr/bin/env bash
# The public course demo (WP9c, ADR-0026; docs/deploy.md): `sentinel ui --demo` on 127.0.0.1,
# kept running in tmux (or as a user systemd service), published over HTTPS by Tailscale Funnel.
# Every visitor gets an anonymous sandbox with the Polish showcase project (ADR-0024).
#
#     scripts/run_demo.sh start             # the app in the tmux session "sentinel-demo"
#     scripts/run_demo.sh start --systemd   # ... or as the user service sentinel-demo.service
#     scripts/run_demo.sh check             # health, and the client address the app sees
#     scripts/run_demo.sh funnel            # publish it: https://<machine>.<tailnet>.ts.net/
#     scripts/run_demo.sh unfunnel          # stop publishing it (tailscale funnel reset)
#     scripts/run_demo.sh stop              # stop the app
#     scripts/run_demo.sh status
#
# SENTINEL_DEMO_PORT (default 8000) and SENTINEL_DEMO_DATA (default
# ~/.local/share/sentinel-demo, apart from the data of `sentinel ui`) change the defaults.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${SENTINEL_DEMO_PORT:-8000}"
data="${SENTINEL_DEMO_DATA:-$HOME/.local/share/sentinel-demo}"
session="sentinel-demo"
unit="sentinel-demo.service"
base="http://127.0.0.1:$port"

usage() {
    sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
}

healthy() {
    curl -fsS --max-time 3 "$base/api/health" >/dev/null 2>&1
}

wait_healthy() {
    for _ in $(seq 1 120); do
        if healthy; then
            echo "The demo answers on $base (data in $data)."
            return 0
        fi
        sleep 0.5
    done
    echo "The demo did not answer on $base within 60 s; see: scripts/run_demo.sh status" >&2
    return 1
}

running_where() {
    if command -v tmux >/dev/null && tmux has-session -t "$session" 2>/dev/null; then
        echo tmux
    elif command -v systemctl >/dev/null && systemctl --user is-active --quiet "$unit" 2>/dev/null; then
        echo systemd
    fi
}

start() {
    if [ -n "$(running_where)" ] || healthy; then
        echo "Something already answers on $base; scripts/run_demo.sh status" >&2
        exit 1
    fi
    mkdir -p "$data"
    uv="$(command -v uv)"
    if [ "${1:-}" = "--systemd" ]; then
        mkdir -p "$HOME/.config/systemd/user"
        cat >"$HOME/.config/systemd/user/$unit" <<EOF
[Unit]
Description=Sentinel public demo (sentinel ui --demo on 127.0.0.1:$port)
After=network-online.target

[Service]
WorkingDirectory=$repo
ExecStart=$uv run --frozen sentinel ui --demo --host 127.0.0.1 --port $port --data-dir $data
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable --now "$unit"
        echo "Started the user service $unit (logs: journalctl --user -u $unit -f)."
        echo "To keep it after you log out: loginctl enable-linger $USER (needs root once)."
    else
        tmux new-session -d -s "$session" \
            "cd '$repo' && '$uv' run --frozen sentinel ui --demo --host 127.0.0.1 --port $port --data-dir '$data'"
        echo "Started in the tmux session $session (attach: tmux attach -t $session)."
    fi
    wait_healthy
}

stop() {
    case "$(running_where)" in
        tmux) tmux kill-session -t "$session" && echo "Stopped the tmux session $session." ;;
        systemd) systemctl --user disable --now "$unit" && echo "Stopped the user service $unit." ;;
        *) echo "The demo is not running under tmux or systemd." ;;
    esac
    if command -v tailscale >/dev/null && tailscale funnel status 2>/dev/null | grep -q "Funnel on"; then
        echo "Tailscale Funnel is still on: scripts/run_demo.sh unfunnel"
    fi
}

check() {
    healthy || { echo "No answer on $base; scripts/run_demo.sh start" >&2; exit 1; }
    echo "Health: $(curl -fsS "$base/api/health")"
    seen="$(curl -fsS -H "X-Forwarded-For: 203.0.113.7" "$base/api/client-address")"
    echo "A request from the local proxy for 203.0.113.7: $seen"
    case "$seen" in
        *'"address":"203.0.113.7"'*'"limited":true'*)
            echo "OK: the limits count the visitor's address from the local proxy." ;;
        *)
            echo "Not as expected: the demo should trust X-Forwarded-For from 127.0.0.1." >&2
            exit 1 ;;
    esac
    if command -v tailscale >/dev/null; then
        name="$(tailscale status --json 2>/dev/null | python3 -c \
            'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' \
            2>/dev/null || true)"
        if [ -n "$name" ]; then
            echo "With the funnel on, open https://$name/api/client-address from a phone on"
            echo "mobile data (outside the tailnet): it must show the phone's public address."
        fi
    fi
}

funnel() {
    healthy || { echo "Start the demo first: scripts/run_demo.sh start" >&2; exit 1; }
    tailscale funnel --bg "$port"
    tailscale funnel status
}

unfunnel() {
    tailscale funnel reset
    tailscale funnel status || true
}

status() {
    where="$(running_where)"
    echo "App: ${where:-not running under tmux or systemd} ($base)"
    if healthy; then
        echo "Health: $(curl -fsS "$base/api/health")"
    else
        echo "Health: no answer"
    fi
    if command -v tailscale >/dev/null; then
        echo "Tailscale Funnel:"
        tailscale funnel status 2>&1 | sed 's/^/  /'
    fi
}

command="${1:-}"
shift || true
case "$command" in
    start) start "$@" ;;
    stop) stop ;;
    check) check ;;
    funnel) funnel ;;
    unfunnel) unfunnel ;;
    status) status ;;
    *) usage ;;
esac
