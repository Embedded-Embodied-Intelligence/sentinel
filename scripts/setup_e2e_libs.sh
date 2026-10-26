#!/usr/bin/env bash
# Chromium's system libraries for the end-to-end tests, without root (WP9c).
#
# Playwright's Chromium needs libnss3, libnspr4 and libasound2t64 (libasound2 before Ubuntu
# 24.04). Installing them needs sudo; this script downloads the Ubuntu packages with
# `apt-get download` (no root) and extracts them with `dpkg -x` into
# ~/.local/share/sentinel-e2e-libs (or $SENTINEL_E2E_LIBS). The e2e tests (tests/e2e_env.py)
# and scripts/ui_screenshots.py add its library folder to LD_LIBRARY_PATH when it exists.
#
#     scripts/setup_e2e_libs.sh        # once, about 2 MB to download
#     uv run playwright install chromium
#     uv run pytest -q -m e2e
#
# Running it again replaces the files with the current package versions. The .deb files stay in
# the folder's debs/ subfolder.
set -euo pipefail

target="${SENTINEL_E2E_LIBS:-$HOME/.local/share/sentinel-e2e-libs}"
debs="$target/debs"
mkdir -p "$debs"
cd "$debs"

sound=libasound2t64
if ! apt-cache show "$sound" >/dev/null 2>&1; then
    sound=libasound2  # Debian 12, Ubuntu 22.04
fi
echo "Downloading libnss3 libnspr4 $sound into $debs"
apt-get download libnss3 libnspr4 "$sound"

for deb in ./*.deb; do
    dpkg -x "$deb" "$target"
done

arch="$(dpkg-architecture -qDEB_HOST_MULTIARCH 2>/dev/null || echo x86_64-linux-gnu)"
lib="$target/usr/lib/$arch"
echo "Libraries in $lib"

# Check Playwright's Chromium, if it is installed (uv run playwright install chromium).
shopt -s nullglob
shells=("$HOME"/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell)
if [ ${#shells[@]} -gt 0 ]; then
    shell="${shells[-1]}"
    missing="$(LD_LIBRARY_PATH="$lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$shell" | grep 'not found' || true)"
    if [ -n "$missing" ]; then
        echo "Chromium still misses:"
        echo "$missing"
        exit 1
    fi
    echo "Chromium finds every library it needs."
else
    echo "Chromium for Playwright is not installed yet: uv run playwright install chromium"
fi
