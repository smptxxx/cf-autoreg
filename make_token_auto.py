"""Full-auto: login akun CF -> buat API token (Workers + AI Gateway + Workers AI)
-> simpan token ke file (chmod 600) -> verifikasi via API.

Usage:
    CF_EMAIL=... CF_PASSWORD=... python3 -u make_token_auto.py [nama-token] [file-output]
Default nama: nexus-automation | default file: /root/autoreg/.token-<nama>
Exit 0 = token tersimpan & terverifikasi. Exit != 0 = gagal (lihat log).
"""
import asyncio
import json
import os
import sys

import cloakbrowser
import httpx

EMAIL = os.environ.get("CF_EMAIL", "")
PWD = os.environ.get("CF_PASSWORD", "")
if not EMAIL or not PWD:
    print("ERROR: set CF_EMAIL dan CF_PASSWORD dulu. Contoh:")
    print('  CF_EMAIL=akun@domain.com CF_PASSWORD="xxxx" python3 -u make_token_auto.py')
    sys.exit(2)
TOKEN_NAME = sys.argv[1] if len(sys.argv) > 1 else "nexus-automation"
OUT_FILE = sys.argv[2] if len(sys.argv) > 2 else f"/root/autoreg/.token-{TOKEN_NAME}"
PERMS = ["AI Gateway", "Workers AI"]


def log(msg):
    print(msg, flush=True)


async def has_challenge(page) -> bool:
    try:
        html = await page.content()
    except Exception:
        return False
    return ("cf-turnstile" in html) or ("challenges.cloudflare.com" in html)


async def solve_challenge(page, label="challenge", max_poll=25):
    from cf_register_cloak import challenge_frame, attempt_click
    if not await has_challenge(page):
        log(f"[{label}] tidak ada challenge (lanjut)")
        return True
    for i in range(max_poll):
        if not await has_challenge(page):
            log(f"[{label}] challenge hilang @poll {i+1} (lanjut)")
            return True
        await asyncio.sleep(3)
        try:
            tok = await page.get_attribute(
                'input[name="cf-turnstile-response"], input[name="cf_challenge_response"]', "value")
        except Exception:
            tok = None
        if tok:
            log(f"[{label}] TOKEN OK @poll {i+1}")
            return True
        fr = await challenge_frame(page)
        if fr and i % 2 == 0:
            how = await attempt_click(page, fr)
            log(f"[{label}] poll {i+1} click -> {how}")
    if not await has_challenge(page):
        log(f"[{label}] challenge hilang di akhir (lanjut)")
        return True
    log(f"[{label}] GAGAL")
    return False


async def extract_token(page) -> dict | None:
    """Ambil semua kredensial dari modal sukses. Tunggu nilai stabil. Return dict atau None."""
    last = None
    stable = 0
    for _ in range(12):
        data = await page.evaluate("""() => {
            const out = {account_id: null, api_token: null, access_key: null,
                         secret_key: null, endpoint: null};
            const rows = [...document.querySelectorAll('div, li')];
            const val_near = (label) => {
                const el = rows.find(e => e.childElementCount > 0 &&
                    (e.innerText || '').split('\\n')[0].trim() === label);
                if (!el) return null;
                const inp = el.querySelector('input');
                if (inp && inp.value) return inp.value.trim();
                const t = (el.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
                return t.length > 1 ? t[1] : null;
            };
            out.account_id = val_near('Account ID');
            out.api_token = val_near('Your API Token');
            out.access_key = val_near('Access Key ID');
            out.secret_key = val_near('Secret Access Key');
            out.endpoint = val_near('S3 API endpoint');
            return out;
        }""")
        tok = (data or {}).get("api_token") or ""
        # token valid: panjang >= 40 & stabil 2x baca berurutan (render selesai)
        if len(tok) >= 40 and tok == last:
            stable += 1
            if stable >= 1:
                return data
        else:
            stable = 0
        last = tok
        await asyncio.sleep(3)
    return None


def save_and_verify(data: dict) -> bool:
    payload = {"email": EMAIL, "account_id": data.get("account_id"),
               "token_name": TOKEN_NAME, **data}
    with open(OUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    os.chmod(OUT_FILE, 0o600)
    log(f"[simpan] token tersimpan di {OUT_FILE} (chmod 600)")
    # verifikasi via API: /zones (butuh Zone:Read — selalu ada via template? tidak.
    # pakai endpoint yg sesuai izin token: Workers + AI). Coba bertingkat.
    try:
        h = {"Authorization": f"Bearer {data['api_token']}"}
        ok = False
        r = httpx.get("https://api.cloudflare.com/client/v4/accounts/"
                      f"{data.get('account_id')}/workers/scripts?per_page=1", headers=h, timeout=30)
        if r.json().get("success"):
            log("[verify] API OK — Workers Scripts list sukses")
            ok = True
        else:
            r2 = httpx.get("https://api.cloudflare.com/client/v4/zones?per_page=1",
                           headers=h, timeout=30)
            if r2.json().get("success"):
                log("[verify] API OK — Zones list sukses")
                ok = True
            else:
                log(f"[verify] API GAGAL: {r.text[:150]}")
        return ok
    except Exception as e:
        log(f"[verify] error: {e}")
    return False


async def delete_token_by_name(page, name: str) -> bool:
    """Hapus token by nama via menu '...' per baris. Return True jika terhapus."""
    try:
        await page.wait_for_timeout(4000)
        # scroll tabel ke bawah biar baris ke-render
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        found = await page.evaluate("""(nm) => {
            const rows = [...document.querySelectorAll('tr, [role=row]')];
            const row = rows.find(r => (r.innerText || '').includes(nm));
            if (!row) return 'baris-tidak-ketemu';
            // klik menu ... di baris tsb
            const menu = [...row.querySelectorAll('button')].find(b =>
                /\\.\\.\\.|more|menu|action/i.test(b.innerText + b.getAttribute('aria-label')));
            const anyBtn = [...row.querySelectorAll('button')].pop();
            (menu || anyBtn)?.click();
            return 'menu-clicked:' + ((menu || anyBtn)?.innerText || '').slice(0,20);
        }""", name)
        log(f"[cleanup] {found}")
        if "tidak-ketemu" in found:
            return False
        await page.wait_for_timeout(2000)
        await page.screenshot(path="/tmp/cb_menu.png")
        # klik Delete di menu dropdown
        dele = await page.evaluate("""() => {
            const items = [...document.querySelectorAll('[role=menuitem], [role=option], button, li')].filter(e =>
                /^delete$/i.test((e.innerText||'').trim()) && e.offsetParent !== null);
            if (items.length) { items[0].click(); return 'delete-clicked'; }
            return 'no-delete-item';
        }""")
        log(f"[cleanup] {dele}")
        await page.wait_for_timeout(2000)
        conf = await page.evaluate("""() => {
            const b = [...document.querySelectorAll('button')].filter(x =>
                /confirm|delete|revoke/i.test(x.innerText) && x.offsetParent !== null);
            if (b.length) { b[b.length-1].click(); return 'confirmed:' + b[b.length-1].innerText.trim(); }
            return 'no-confirm';
        }""")
        log(f"[cleanup] {conf}")
        await page.wait_for_timeout(3000)
        body = await page.inner_text("body")
        log(f"[cleanup] masih ada: {'YA' if name in body else 'TIDAK (terhapus)'}")
        return name not in body
    except Exception as e:
        log(f"[cleanup] gagal: {e}")
        return False


async def main() -> int:
    cleanup_only = os.environ.get("CLEANUP_ONLY") == "1"
    cleanup_name = os.environ.get("CLEANUP_NAME", "")
    browser = await cloakbrowser.launch_async(
        humanize=False, headless=False, args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = await browser.new_page()
    try:
        # --- login ---
        await page.goto("https://dash.cloudflare.com/login", timeout=90000,
                        wait_until="domcontentloaded")
        await page.wait_for_selector('input[name="email"], input[type="email"]', timeout=60000)
        await page.fill('input[name="email"], input[type="email"]', EMAIL)
        await page.fill('input[type="password"]', PWD)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(4000)
        await solve_challenge(page, "login-post")
        try:
            btn = await page.query_selector('button[type="submit"]')
            if btn and await btn.is_visible():
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(5000)
        except Exception:
            pass
        for _ in range(10):
            if "/login" not in page.url:
                break
            await page.wait_for_timeout(3000)
        if "/login" in page.url:
            log("[login] GAGAL — masih di halaman login")
            return 1
        log(f"[login] OK — {page.url[:80]}")

        # --- daftar token ---
        await page.goto("https://dash.cloudflare.com/?to=/:account/api-tokens", timeout=90000,
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(10000)

        if cleanup_only and cleanup_name:
            ok = await delete_token_by_name(page, cleanup_name)
            log(f"[cleanup] {'SELESAI' if ok else 'GAGAL/SKIP'}")
            # screenshot daftar biar bisa cek manual
            await page.screenshot(path="/tmp/cb_list.png", full_page=True)
            body2 = await page.inner_text("body")
            log(f"[cleanup] daftar: {body2[:800].replace(chr(10), ' | ')}")
            return 0 if ok else 2

        body = await page.inner_text("body")
        if TOKEN_NAME in body[:4000]:
            log(f"[cek] token {TOKEN_NAME} SUDAH ADA -> stop (hapus dulu via CLEANUP_NAME / dashboard)")
            return 3

        # --- create ---
        try:
            await page.click('text=Create Token', timeout=15000)
        except Exception:
            await page.click('a:has-text("Create Token"), button:has-text("Create Token")', timeout=15000)
        await page.wait_for_timeout(6000)
        await page.click('text=Edit Cloudflare Workers', timeout=15000)
        await page.wait_for_timeout(4000)
        try:
            await page.fill('input[placeholder*="oken name"], input[type="text"]', TOKEN_NAME)
        except Exception as e:
            log(f"[name] fill gagal: {str(e)[:80]}")

        # --- tambah policy AI ---
        await page.get_by_role("button", name="Add policy").click(timeout=10000)
        await page.wait_for_timeout(3000)
        await page.get_by_text("AI & Machine Learning").click(timeout=10000)
        await page.wait_for_timeout(2500)
        res = await page.evaluate("""(perms) => {
            const out = [];
            const panel = [...document.querySelectorAll('*')].find(e =>
                e.innerText && e.innerText.includes('Edit policy') && e.querySelector('li'));
            const root = panel || document;
            for (const perm of perms) {
                const t = [...root.querySelectorAll('li span')].find(e =>
                    e.childElementCount === 0 && e.innerText.trim() === perm &&
                    !e.closest('nav') && !e.closest('[data-sidebar]'));
                if (!t) { out.push(perm + ':label-tidak-ketemu'); continue; }
                const li = t.closest('li');
                const edit = [...li.querySelectorAll('[role=checkbox]')]
                    .find(b => b.getAttribute('aria-label') === 'Edit');
                if (!edit) { out.push(perm + ':ga-ada-edit'); continue; }
                edit.click();
                out.push(perm + ':clicked');
            }
            return out.join(' | ');
        }""", PERMS)
        log(f"[ai] {res}")
        await page.wait_for_timeout(2000)
        ver = await page.evaluate("""() => {
            const out = [];
            for (const cb of document.querySelectorAll('[role=checkbox][aria-checked=true]')) {
                const li = cb.closest('li');
                out.push((li ? li.innerText.split('\\n')[0].slice(0,30) : '?') + ':' + cb.getAttribute('aria-label'));
            }
            return out.join(' | ') || 'KOSONG';
        }""")
        log(f"[ai] terpilih: {ver}")
        if "AI Gateway:Edit" not in ver or "Workers AI:Edit" not in ver:
            log("[ai] GAGAL — permission AI tidak kepilih semua, stop (tidak create)")
            return 4

        # --- review + create ---
        await page.get_by_role("button", name="Review token").click(timeout=10000)
        await page.wait_for_timeout(5000)
        await page.get_by_role("button", name="Create Token").click(timeout=10000)
        await page.wait_for_timeout(6000)
        if "created successfully" not in (await page.inner_text("body")):
            log("[create] GAGAL — modal sukses tidak muncul")
            await page.screenshot(path="/tmp/cb_create_fail.png")
            return 5

        # --- ambil + simpan + verifikasi (klik tombol copy biar nilai dari clipboard, bukan DOM) ---
        data = None
        try:
            await page.evaluate("window.__clip = ''")
            # grant clipboard permission via context
            try:
                await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
            except Exception:
                pass
            data = await page.evaluate("""async () => {
                const out = {account_id: null, api_token: null, access_key: null,
                             secret_key: null, endpoint: null};
                const labels = ['Account ID', 'Your API Token', 'Access Key ID',
                                'Secret Access Key', 'S3 API endpoint'];
                const keys = ['account_id', 'api_token', 'access_key', 'secret_key', 'endpoint'];
                // cari modal (dialog) dulu, fallback ke document
                const modal = document.querySelector('[role=dialog]') || document;
                for (let i = 0; i < labels.length; i++) {
                    const t = [...modal.querySelectorAll('*')].find(e =>
                        e.childElementCount === 0 && (e.innerText||'').trim() === labels[i]);
                    if (!t) continue;
                    let scope = t;
                    for (let k = 0; k < 6 && scope; k++) {
                        scope = scope.parentElement;
                        if (!scope) break;
                        const copyBtn = [...scope.querySelectorAll('button')].find(b =>
                            /copy/i.test(b.getAttribute('aria-label')||'') || /copy/i.test(b.innerText||''));
                        if (copyBtn) {
                            copyBtn.click();
                            await new Promise(r => setTimeout(r, 800));
                            try {
                                const txt = await navigator.clipboard.readText();
                                if (txt && txt.length > 5) { out[keys[i]] = txt.trim(); break; }
                            } catch(e) {}
                        }
                    }
                    // fallback: input di dekat label
                    if (!out[keys[i]]) {
                        let s2 = t;
                        for (let k = 0; k < 6 && s2; k++) {
                            s2 = s2.parentElement;
                            if (!s2) break;
                            const inp = s2.querySelector('input');
                            if (inp && inp.value && inp.value.length > 5) { out[keys[i]] = inp.value.trim(); break; }
                        }
                    }
                }
                return out;
            }""")
            log(f"[token] via-copy: account={(data.get('account_id') or '')[:8]} "
                f"api_token={(data.get('api_token') or '')[:12]} len={len(data.get('api_token') or '')} "
                f"r2={'ya' if data.get('access_key') else 'tidak'}")
        except Exception as e:
            log(f"[token] via-copy gagal: {e}")
        if not data or not data.get("api_token"):
            data = await extract_token(page)
        if not data:
            log("[token] GAGAL ambil nilai token dari modal")
            await page.screenshot(path="/tmp/cb_token_fail.png")
            return 6
        log(f"[token] dapat: account={data.get('account_id')} api_token={data['api_token'][:10]}... "
            f"r2={'ya' if data.get('access_key') else 'tidak'}")
        if not save_and_verify(data):
            log("[verify] token tersimpan tapi verifikasi API gagal — cek manual")
            return 7
        log("RESULT_OK token tersimpan & terverifikasi")
        return 0
    finally:
        await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
