"""Temp-mail pakai API temp.ftstoresz.com (api-mail.ftstoresz.com).
Alamat ditentukan client-side: nama@domain dari daftar /domains. No signup needed."""
from __future__ import annotations

import random
import re
import string
import time

import httpx

BASE = "https://api-mail.ftstoresz.com"
NAMES = ["nexus", "dev", "mail", "inbox", "temp", "anon", "hello", "user",
         "quick", "fast", "cloud", "byte", "nova", "os", "sys"]


def _rand_word() -> str:
    n = random.choice(NAMES) + random.choice(string.ascii_lowercase) * 0 or random.choice(NAMES)
    n += str(random.randint(10, 999))
    n += random.choice(string.ascii_lowercase)
    return n


class FTMail:
    def __init__(self, proxy: str | None = None):
        self.client = httpx.Client(base_url=BASE, timeout=30, proxy=proxy or None,
                                   headers={"Accept": "application/json",
                                            "User-Agent": "Mozilla/5.0 Chrome/131"})
        self.address: str | None = None
        self.domains: list[str] = []

    def create(self, domain: str | None = None) -> str:
        r = self.client.get("/domains").json()
        self.domains = r.get("result") or []
        if not self.domains:
            raise RuntimeError("fts: no domains")
        d = domain if domain in self.domains else random.choice(self.domains)
        self.address = f"{_rand_word()}@{d}"
        return self.address

    def emails(self, limit: int = 20, offset: int = 0) -> list[dict]:
        r = self.client.get(f"/emails/{self.address}", params={"limit": limit, "offset": offset}).json()
        return r.get("result") or []

    def count(self) -> int:
        r = self.client.get(f"/emails/count/{self.address}").json()
        return (r.get("result") or {}).get("count", 0)

    def message(self, msg_id: str) -> dict:
        r = self.client.get(f"/inbox/{msg_id}").json()
        d = r.get("result") or {}
        # normalisasi nama field
        d.setdefault("text", d.get("text_content") or "")
        d.setdefault("html", d.get("html_content") or "")
        d.setdefault("subject", None)
        return d

    def wait_for_message(self, timeout: int = 240, poll: int = 6,
                         subject_contains: str | None = None) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for m in self.emails(limit=20):
                if subject_contains and subject_contains.lower() not in (m.get("subject") or "").lower():
                    continue
                return self.message(m["id"]) | {"list_subject": m.get("subject"),
                                                "from_address": m.get("from_address")}
            time.sleep(poll)
        raise TimeoutError(f"fts: no mail in {timeout}s -> {self.address}")

    @staticmethod
    def extract_links(msg: dict) -> list[str]:
        text = msg.get("text") or ""
        html = msg.get("html") or ""
        if isinstance(html, list):
            html = " ".join(html)
        return sorted(set(re.findall(r"https?://[^\s\"'<>]+", text + " " + html)))

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


if __name__ == "__main__":
    with FTMail() as m:
        print("addr:", m.create())
        print("count:", m.count())
        print("domains:", len(m.domains))
