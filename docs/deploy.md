# Deploying Sentinel

Sentinel's application (`sentinel ui`, spec section 11) runs in three ways. This guide is for
the person who installs it; the people who use it read the user guide
([Polish](user-guide-pl.md), [English](user-guide-en.md)). Decisions: ADR-0022 (web stack),
ADR-0024 (demo security), ADR-0026 (image and public demo).

| Way | For | Start | Data |
| --- | --- | --- | --- |
| [Laptop](#1-on-a-laptop-uv) | one project manager | `uv run sentinel ui` | `~/.local/share/sentinel` |
| [Company server](#2-on-a-company-server-docker) | a team; IT runs it | `docker compose up -d` | the `sentinel-data` volume |
| [Public demo](#3-the-public-course-demo-tailscale-funnel) | anyone with the link | `scripts/run_demo.sh start` + `funnel` | `~/.local/share/sentinel-demo`, sandboxes deleted after 24 h |

**There are no user accounts.** Outside the demo, everybody who can open the address sees and
changes every project. Serve it on a laptop for yourself, or inside the company network (VPN)
or behind a proxy that signs people in; never publish the non-demo mode on the internet.

## 1. On a laptop (uv)

```bash
git clone https://github.com/Embedded-Embodied-Intelligence/sentinel.git && cd sentinel
uv sync                       # Python 3.12 and the locked dependencies, about 300 MB
uv run sentinel ui            # http://127.0.0.1:8000, Polish (EN at the top right)
```

Optional: `uv run python scripts/fetch_psplib.py --sets j30 j60` for the simulator's example
projects (about 2 minutes; without them the simulator page says it is unavailable).

## 2. On a company server (Docker)

The image (`Dockerfile`): two stages, uv installs the locked dependencies and the app on
`python:3.12-slim`; it runs as an unprivileged user, keeps everything in the `/data` volume and
reports its health on `/api/health` (Docker's `HEALTHCHECK`). The app listens on port 8000;
`docker-compose.yml` publishes it on `127.0.0.1:8000` of the host, for the company's HTTPS
reverse proxy.

```bash
docker compose up -d --build                    # build and start (the first build takes minutes)
docker compose ps                               # STATUS shows "(healthy)" after the first check, ~30 s
curl -s http://127.0.0.1:8000/api/health        # {"status":"ok","version":"1.2.1","demo":false}
docker compose logs -f sentinel                 # the log
docker compose down                             # stop; the data stay in the volume
```

- **Simulator data** (optional, once, into the volume):
  `docker compose run --rm sentinel python /app/scripts/fetch_psplib.py --sets j30 j60 --root /data/psplib`
- **Backup**: `docker compose stop sentinel`, then
  `docker run --rm -v sentinel_sentinel-data:/data -v "$PWD":/backup python:3.12-slim tar czf /backup/sentinel-data.tgz -C /data .`,
  then `docker compose start sentinel`. The volume holds `sentinel.db` (projects and their
  history), `settings.json` (the AI provider and key, readable only by the app), `secret.key`
  and `llm_cache/`.
- **Upgrade**: `git pull && docker compose up -d --build`; the volume is kept and the database
  migrates itself.
- **Another port or address**: change `ports:` in `docker-compose.yml`, e.g.
  `"0.0.0.0:8080:8000"` for a closed internal network.

### AI options

The AI only reads messages and explains; everything works without it (the check-in form and
the spreadsheet import replace it). Choose the provider on the app's **Settings** page; the key
is stored server-side and never shown again.

| Option | Cost | Data leaves the company? | Set up |
| --- | --- | --- | --- |
| None | free | no | nothing |
| Local Ollama | free; a GPU with 6 GB or more, or a slow CPU | no | `docker compose --profile ollama up -d`, then `docker compose --profile ollama exec ollama ollama pull qwen2.5:7b`; in Settings choose Ollama, model `qwen2.5:7b` (the address `http://ollama:11434` is preset) |
| Groq | free tier with daily limits | yes, to Groq (US) | a key from console.groq.com; in Settings choose Groq |
| OpenRouter | pay per use (prices on openrouter.ai; small for a team's messages) | yes, to OpenRouter and the model's host | a key from openrouter.ai; in Settings choose OpenRouter |

For a GPU in the `ollama` container, uncomment the `deploy:` block in `docker-compose.yml`
(needs the NVIDIA Container Toolkit).

### Docker in WP9c

Docker was not installed on the build server, so the image was not built in the work package.
Its recipe was checked by replaying the build without Docker: a non-editable install from
exactly the build context into a fresh environment (270 MB), started with
`configs/app_server.toml`: healthy after 3.7 s, a project created and planned through the API,
the Polish start page served. To build and measure it:

```bash
docker build -t sentinel:1.2.1 .                          # time it
docker image ls sentinel:1.2.1                            # SIZE: about 400 MB expected
docker run -d --name sentinel-smoke -p 127.0.0.1:8000:8000 sentinel:1.2.1
time sh -c 'until curl -fs http://127.0.0.1:8000/api/health; do sleep 0.5; done'
curl -s -c /tmp/jar http://127.0.0.1:8000/api/session     # note csrf_token
curl -s -b /tmp/jar -H "X-CSRF-Token: <csrf_token>" -H "content-type: application/json" \
  -d '{"name":"Smoke","start":"2026-11-02","team":[{"key":"a","name":"Ada","role":"Developer"}],"tasks":[{"key":"T1","name":"Build","duration":3,"crew":{"Developer":1}}]}' \
  http://127.0.0.1:8000/api/projects                        # 201 and the project
docker rm -f sentinel-smoke
```

## 3. The public course demo (Tailscale Funnel)

`sentinel ui --demo` gives every visitor an anonymous sandbox with the Polish showcase project
(English if the visitor chose English first), limits from `configs/app_demo.toml` and deletion
after 24 hours (ADR-0024). It listens on 127.0.0.1 only; Tailscale Funnel publishes it over
HTTPS at `https://<machine>.<tailnet>.ts.net/`.

### Once

1. In the Tailscale admin console: **DNS → HTTPS Certificates** on, and Funnel allowed for the
   machine (the first `tailscale funnel` prints a link that enables it).
2. Your user must be allowed to change Tailscale's serve settings. If `tailscale funnel` says
   *Access denied*, run once `sudo tailscale set --operator=$USER`. Without sudo on WSL2, open a
   root shell from Windows (`wsl -u root`) and run `tailscale set --operator=<your user name>`.
3. Optional, an AI model for the demo (the demo has no settings page): run the app once in the
   normal mode on the demo's data, choose the provider on Settings, then stop it:
   `uv run sentinel ui --data-dir ~/.local/share/sentinel-demo --port 8001`. The demo then uses
   it with the daily cap of `configs/app_demo.toml` (200 calls).

### Every time

```bash
scripts/run_demo.sh start        # the app in tmux session "sentinel-demo" on 127.0.0.1:8000
scripts/run_demo.sh check        # health, and the address the per-visitor limits count
scripts/run_demo.sh funnel       # = tailscale funnel --bg 8000: the public HTTPS address
scripts/run_demo.sh status       # the app, its health, the funnel
```

Instead of tmux, `scripts/run_demo.sh start --systemd` installs and starts the user service
`sentinel-demo.service` (restarts on failure; `journalctl --user -u sentinel-demo -f`). It keeps
running after you log out only with `loginctl enable-linger $USER` (root, once).

**Check the visitor addresses.** The limits (120 requests a minute per address) must see each
visitor, not the proxy. The app trusts `X-Forwarded-For` only from 127.0.0.1, the funnel's
local proxy, and takes the last address the proxy added, so a visitor cannot pick an address;
uvicorn's own proxy handling is off. `scripts/run_demo.sh check` sends a request as the proxy
would and expects that address back. With the funnel on, open
`https://<machine>.<tailnet>.ts.net/api/client-address` on a phone on mobile data (outside the
tailnet): `"address"` must be the phone's public address and `"trusted": true`. The endpoint
answers only requests that reach the app from 127.0.0.1 (a request from elsewhere gets 404) and
shows nothing but the requester's own address.

### Stop

```bash
scripts/run_demo.sh unfunnel     # = tailscale funnel reset: nothing is public any more
tailscale funnel status          # "No serve config"
scripts/run_demo.sh stop         # stop the app (it warns if the funnel is still on)
```

`tailscale funnel reset` also removes `tailscale serve` settings, if you have any; to stop only
this one: `tailscale funnel --https=443 off`. The funnel's `--bg` setting survives reboots until
it is reset. To wipe the demo's data: stop it and delete `~/.local/share/sentinel-demo`.

## 4. End-to-end tests and screenshots without root

The browser tests (`uv run pytest -q -m e2e`), the task-timing run and
`scripts/ui_screenshots.py` use Playwright's Chromium, which needs the system libraries
`libnss3`, `libnspr4` and `libasound2t64`. Without sudo:

```bash
uv run playwright install chromium   # once: the browser, into ~/.cache/ms-playwright
scripts/setup_e2e_libs.sh            # once: apt-get download + dpkg -x into
                                     #   ~/.local/share/sentinel-e2e-libs (about 2 MB)
uv run pytest -q -m e2e              # about a minute; the tests add the folder to Chromium's
                                     #   LD_LIBRARY_PATH (tests/e2e_env.py)
```

`SENTINEL_E2E_LIBS` moves the folder. With root, `sudo apt-get install -y libnss3 libnspr4
libasound2t64` does the same system-wide.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `scripts/run_demo.sh start`: "Something already answers" | Another app on the port: `SENTINEL_DEMO_PORT=8002 scripts/run_demo.sh start` (and `funnel` with the same variable) |
| Visitors get "Too many requests" together | The limits see one address: run `check`; is `trust_proxy = true` in `configs/app_demo.toml`? |
| `tailscale funnel`: Access denied | See *Once*, step 2 |
| The simulator page says it is unavailable | The PSPLIB data are missing: `uv run python scripts/fetch_psplib.py --sets j30 j60` (Docker: see section 2) |
| The container is "unhealthy" | `docker compose logs sentinel`; the volume must be writable by the container's user (uid 10001) |
| The e2e tests skip: "Chromium … cannot start" | Section 4 |
