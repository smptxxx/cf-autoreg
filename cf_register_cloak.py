"""CF signup via CloakBrowser — in-session turnstile click loop."""
from __future__ import annotations

import asyncio
import secrets
import string
import time

import cloakbrowser

from tempmail_ft import FTMail

SIGNUP = "https://dash.cloudflare.com/sign-up"


def gen_password() -> str:
    return "Xk9#" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(9)) + "!"


async def challenge_frame(page):
    for f in page.frames:
        if "challenges.cloudflare.com" in f.url:
            return f
    return None


async def attempt_click(page, frame):
    # 1) DOM click in-frame
    for sel in ["label.ctp-checkbox-label", "input[type=checkbox]", "body"]:
        try:
            await frame.click(sel, timeout=2500, force=True)
            return "frame-click:" + sel
        except Exception:
            continue
    # 2) coordinates click on frame element
    try:
        fr = frame.frame_element()
        fb = await fr.bounding_box()
        if fb:
            x = fb["x"] + 30
            y = fb["y"] + fb["height"] / 2
            await page.mouse.move(x - 70, y - 50)
            await asyncio.sleep(0.3)
            await page.mouse.move(x, y, steps=18)
            await asyncio.sleep(0.25)
            await page.mouse.down()
            await asyncio.sleep(0.08)
            await page.mouse.up()
            return "coord-click"
    except Exception as e:
        return "err:" + str(e)[:80]
    return None


async def run():
    with FTMail() as mail:
        addr = mail.create()
        pwd = gen_password()
        print(f"[mail] addr={addr} pwd={pwd}")

        browser = await cloakbrowser.launch_async(humanize=True, headless=False,
                                                  args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page()
        try:
            await page.goto(SIGNUP, timeout=90000, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector('input[name="email"]', timeout=60000)
                print("[form] siap")
            except Exception:
                print("[form] ga muncul:", page.url)
                await page.screenshot(path="/tmp/cb_cb2_loadfail.png")
                return
            await page.wait_for_timeout(4000)
            await page.fill('input[name="email"]', addr)
            await page.fill('input[name="password"]', pwd)
            try:
                await page.check('input[type="checkbox"]', force=True)
            except Exception:
                pass

            tok = None
            for i in range(45):
                await asyncio.sleep(3)
                try:
                    tok = await page.get_attribute('input[name="cf_challenge_response"]', "value")
                except Exception:
                    tok = None
                if tok:
                    print(f"[challenge] TOKEN OK ({len(tok)} ch) @poll {i+1}")
                    break
                fr = await challenge_frame(page)
                if fr and i % 2 == 0:
                    how = await attempt_click(page, fr)
                    print(f"[challenge] poll {i+1} click -> {how}")
            if not tok:
                print("[challenge] GAGAL")
                await page.screenshot(path="/tmp/cb_cb2_fail.png")
                return

            await page.click('button[type="submit"]:has-text("Sign up")')
            await page.wait_for_timeout(12000)
            print("[submit] URL:", page.url)
            try:
                body = await page.inner_text("body")
                print("[submit] body:", body[:250].replace("\n", " | "))
            except Exception:
                pass
            await page.screenshot(path="/tmp/cb_cb2_after.png")

            print("[verify] memantau inbox FT…")
            try:
                msg = await asyncio.to_thread(mail.wait_for_message, 300)
                print("[verify] SUBJEK:", msg.get("list_subject"))
                links = FTMail.extract_links(msg)
                cf = [l for l in links if "cloudflare" in l]
                for l in (cf or links)[:5]:
                    print("[verify] LINK:", l[:150])
                tgt = next((l for l in cf if "verify" in l or "email" in l), (cf or [None])[0])
                if tgt:
                    await page.goto(tgt, timeout=90000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(8000)
                    print("[verified] URL:", page.url)
                    try:
                        vb = await page.inner_text("body")
                        print("[verified] body:", vb[:250].replace("\n", " | "))
                    except Exception:
                        pass
                    await page.screenshot(path="/tmp/cb_cb2_verified.png")
                    print("RESULT_OK", addr, pwd)
            except TimeoutError as e:
                print("[verify]", e)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
