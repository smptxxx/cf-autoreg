#!/usr/bin/env bash
# cf-autoreg installer — 1x jalan: deps sistem + python + browser + captcha deps.
# Usage: sudo bash install.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Jalankan sebagai root: sudo bash install.sh"; exit 1; fi
export DEBIAN_FRONTEND=noninteractive
PY=${PY:-python3}

echo "[1/5] deps sistem (xvfb, browser libs, git)..."
apt-get update -qq
apt-get install -y -qq git xvfb libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2 python3-pip >/dev/null
echo "      ok"

echo "[2/5] deps python (cloakbrowser, playwright, httpx)..."
$PY -m pip install -q cloakbrowser httpx playwright
echo "      ok"

echo "[3/5] browser chromium (playwright)..."
$PY -m playwright install chromium --with-deps 2>&1 | tail -1 || $PY -m playwright install chromium 2>&1 | tail -1
echo "      ok"

echo "[4/5] verifikasi captcha/challenge solver..."
$PY -c "import cloakbrowser, playwright, httpx; print('      deps ok')"
which xvfb-run Xvfb
echo "      display ok"

echo "[5/5] smoke test temp-mail API..."
curl -s -m 15 https://api-mail.ftstoresz.com/domains -o /dev/null -w "      temp-mail HTTP %{http_code}\n"

echo ""
echo "SELESAI. Cara pakai:"
echo "  # 1. daftar akun CF (auto challenge + verifikasi email):"
echo "  xvfb-run -a python3 -u cf_register_cloak.py"
echo ""
echo "  # 2. buat API token (Workers + AI Gateway + Workers AI):"
echo "  CF_EMAIL=akun@dom.com CF_PASSWORD='xxxx' python3 -u make_token_auto.py [nama-token] [file-out]"
echo ""
echo "  # 3. hapus token yatim:"
echo "  CF_EMAIL=akun@dom.com CF_PASSWORD='xxxx' CLEANUP_ONLY=1 CLEANUP_NAME=nama-token python3 -u make_token_auto.py"
