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
uv sync                       # Python 3.12 and the locked dependencies: 175 MB down, 550 MB on disk
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
docker compose up -d --build                    # build and start (the first build took 57 s)
docker compose ps                               # STATUS shows "(healthy)" after about 8 s
curl -s http://127.0.0.1:8000/api/health        # {"status":"ok","version":"1.7.0","demo":false}
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
- **Another port or address**: `SENTINEL_PORT=8001 docker compose up -d` publishes the app on
  `127.0.0.1:8001`; for another address change `ports:` in `docker-compose.yml`, e.g.
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
| Voice recordings (with any of the three above) | Groq's free tier; beyond it about 0.04 USD an hour of audio | yes, the audio to Groq (US), as a typed message goes to a cloud model | a Groq key: the provider's own if it is Groq, else **Groq key for recordings** in Settings; **Test recordings** checks it |

Recordings (WP14, ADR-0031): a microphone beside the message box of a check-in and of "describe
the project" records at most 90 s in the browser; the server has Groq's `whisper-large-v3-turbo`
write it out with the team's and the tasks' names as its vocabulary and sends the text back into
the box, where the manager reads and corrects it before processing it. The audio and the text are
kept nowhere (no cache, no log, no file); the demo's request log notes only that a recording was
written out, and its length, and its daily AI cap counts each recording. The button shows only
with a Groq key and only where the browser may use a microphone: an https page (the Funnel, a
proxy with TLS) or `localhost`; on plain http from another machine the box is for typing only.

For a GPU in the `ollama` container, uncomment the `deploy:` block in `docker-compose.yml`
(needs the NVIDIA Container Toolkit).

A person waits for these answers, so one AI call may take at most 600 s with Ollama and 90 s
(with two retries) with Groq or OpenRouter; `llm_timeout_s = 120` in the app's config file
(`sentinel ui --config …`) sets one limit for every provider. Measured in WP11 on the 4-core
server without a GPU (`docs/qa/ai/`): `qwen2.5:7b` loads in about 17 s on the first call, then
reads a 12-task description in about 50 s, a status message in about 7 s and writes an
explanation in about 8 s; `gpt-oss-120b` on Groq answers each in 1–5 s, and the three flows
cost well under 0.01 USD through OpenRouter. When a call fails, the page says why (the key, the
model's name, the address, a timeout, the provider's limit or a text too long) and the form
keeps what was written. The cloud model reads messages and writes explanations more accurately
than the local one; for messages about real people's absences, use the local model or a
provider that does not retain data.

### Measured in WP11

On the 4-core server without a GPU (Docker 29.1.3, Compose 2.40.3; `scripts/docker_check.py`,
its log in [`docs/qa/docker/`](qa/docker/)):

| Step | Result |
| --- | --- |
| First build (`docker build`; the base images and the dependencies downloaded) | 57 s |
| Build after a code change (`docker compose build`; the dependencies cached) | 26 s |
| The image `sentinel:1.3.0` | 653 MB on disk, 156 MB compressed |
| `docker compose up -d` until `/api/health` answers; until Docker calls it healthy | 4.3 s; 7.6 s |
| A project made through the pages (11 people, 30 tasks, a plan) | unchanged after `docker compose restart` (answering after 3.0 s) and after `down` and `up -d` (3.7 s) |
| `docker compose --profile ollama up -d` (the `ollama/ollama` image downloaded once) | 363 s |
| `ollama pull qwen2.5:7b` in its container (4.7 GB) | 420 s |
| The settings page's test of the local model (address and model left empty; it loads the model) | "Model qwen2.5:7b odpowiedział" after 13 s |
| Memory as `docker stats` shows it (with the cached model file): the `ollama` container after the pull and the test; the app | 9.6 GiB; 123 MiB |

To check it again, as its own compose project (`sentinel-check`, port 8002), so that a running
deployment keeps its containers and data: `uv run python scripts/docker_check.py [--ollama]`.

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
3. The demo's AI model (the demo has no settings page): the cloud model `gpt-oss-120b`, the
   more accurate one for messages and explanations. Run the app once in the normal mode on the
   demo's data, choose **OpenRouter** on Settings, paste the key, leave the model empty
   (`openai/gpt-oss-120b`), save, then stop it:
   `uv run sentinel ui --data-dir ~/.local/share/sentinel-demo --port 8001`. The demo then uses
   it with the daily cap of `configs/app_demo.toml` (200 calls; at about 0.0003–0.0006 USD a
   call in WP11, at most about 0.12 USD a day). For voice recordings (1.5.0) also paste a Groq
   key under **Groq key for recordings** and press **Test recordings** in the same run; the cap
   counts each recording (about 0.0002 USD for a short one).

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

### The request log for the usability test

With `request_log = true` in `configs/app_demo.toml` (the default there; ADR-0030) every sandbox
also keeps one row per request in the demo's database: the time, the method, the route's path
template (e.g. `/projects/{project_id}/checkin`: no real path, no query), the project if it is one
of the sandbox's own, whether it was an HTMX request, and the status answered. It never holds an
address, a cookie or what a form held, and it is deleted with the sandbox after 24 hours. Static
files, `/api/health` and requests without a sandbox are not logged. The owner exports one
tester's timeline and task durations with `scripts/usability_logs.py`
([docs/usability/README.md](usability/README.md)); the export reads the database read-only, so
the demo keeps running. After the test set `request_log = false` and restart the demo; outside
the demo the flag does nothing.

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
| "The AI did not answer in time" | A local model on a processor: the first call loads it, a description takes about a minute. Try again; on a slow machine raise `llm_timeout_s` |
| "The AI provider cannot be reached" | The address in **Settings**: empty for Ollama on the same machine, `http://ollama:11434` in Docker; is `ollama serve` (or the `ollama` container) running? |
| No **Record by voice** button | A Groq key on Settings (the provider's or the one for recordings); an https address or `localhost` (browsers allow the microphone nowhere else); a browser with MediaRecorder (Chrome, Edge, Firefox, Safari 14.1 or later) |
| "The browser did not allow the microphone" | Allow it beside the address bar (the lock or camera icon) and record again; the system's privacy settings may block it too |
| "The AI provider refused the API key" or "cannot serve this model" | A new key, or the model's exact name (`openai/gpt-oss-120b` on OpenRouter), in **Settings**; **Test the connection** checks both |
| The container is "unhealthy" | `docker compose logs sentinel`; the volume must be writable by the container's user (uid 10001) |
| The e2e tests skip: "Chromium … cannot start" | Section 4 |
