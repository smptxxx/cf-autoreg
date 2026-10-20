# cf-autoreg — Auto Register Cloudflare + Auto API Token

Tools auto-registrasi akun Cloudflare (solve Turnstile in-session + verifikasi email otomatis)
dilanjut **pembuatan API token full-otomatis** (Workers + AI Gateway + Workers AI).

## 1x Install

```bash
sudo bash install.sh
```

Installer mengurus: deps sistem (xvfb + browser libs), `cloakbrowser`/`playwright`/`httpx`,
Chromium, verifikasi solver captcha, dan smoke-test temp-mail API.

## Cara pakai

```bash
# 1. Daftar 1 akun CF (challenge otomatis + klik link verifikasi email)
xvfb-run -a python3 -u cf_register_cloak.py
# output: RESULT_OK <email> <password>

# 2. Buat API token (Workers + AI Gateway Edit + Workers AI Edit)
CF_EMAIL=akun@dom.com CF_PASSWORD='xxxx' python3 -u make_token_auto.py [nama-token] [file-out]
# default nama: nexus-automation | default file: /root/autoreg/.token-<nama>
# token tersimpan chmod 600 + terverifikasi via API. Exit 0 = sukses.

# 3. Hapus token yatim by nama
CF_EMAIL=akun@dom.com CF_PASSWORD='xxxx' CLEANUP_ONLY=1 CLEANUP_NAME=nama-token python3 -u make_token_auto.py
```

## Isi token

Template **Edit Cloudflare Workers** + policy tambahan:
- Workers Routes/Scripts/KV/R2/Tail/Pages/CI/Agents/Observability/Containers → Write
- **AI Gateway → Edit, Workers AI → Edit**
- Account Settings → Read · Expiry: No expiration

File token (JSON, chmod 600): `api_token`, `account_id`, R2 `access_key`/`secret_key`/`endpoint`.

## Tes AI (contoh)

```bash
TOK=$(python3 -c "import json;print(json.load(open('/root/autoreg/.token-nexus-automation'))['api_token'])")
AID=$(python3 -c "import json;print(json.load(open('/root/autoreg/.token-nexus-automation'))['account_id'])")
curl -s "https://api.cloudflare.com/client/v4/accounts/$AID/ai/run/@cf/meta/llama-3.1-8b-instruct" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Halo"}]}' | head -c 400
```

## File

| File | Fungsi |
|---|---|
| `install.sh` | installer 1x jalan (sistem + python + browser + cek captcha) |
| `cf_register_cloak.py` | daftar akun CF via CloakBrowser + temp-mail FT |
| `tempmail_ft.py` | client temp-mail (api-mail.ftstoresz.com) |
| `make_token_auto.py` | buat/hapus API token full-auto + verifikasi |

## Catatan

- Jangan commit file `.token-*` (secret). Sudah ada di `.gitignore`.
- `CF_EMAIL`/`CF_PASSWORD` via environment — jangan hardcode.
