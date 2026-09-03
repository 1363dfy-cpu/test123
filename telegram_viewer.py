#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Viewer Pro – نسخهٔ کامل و به‌روز‌شده
با پشتیبانی از پروکسی‌های داینامیک، مشاهده‌ی پیام‌ها، واکنش و join‑/leave
کانال‌ها.
"""

import os
import json
import random
import asyncio
import logging
import requests
import re
import math
import time
from datetime import datetime, timedelta

# ---------- Telethon ----------
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetMessagesViewsRequest,
    SendReactionRequest,
)
from telethon.tl.functions.channels import LeaveChannelRequest
# ← ImportChatInviteRequest ممکن است در نسخهٔ Telethon موجود نباشد
try:
    from telethon.tl.functions.channels import ImportChatInviteRequest
except ImportError:
    ImportChatInviteRequest = None
    logging.warning("ImportChatInviteRequest در نسخهٔ Telethon موجود نیست. "
                    "عملیات join/leave غیرفعال خواهد شد.")

from telethon.tl.types import ReactionEmoji

# ---------- Env ----------
from dotenv import load_dotenv
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNELS_RAW = os.getenv("CHANNELS", "")
CHANNELS = [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("TGViewer_Pro")

# ---------- Constants ----------
MAX_OPERATIONS_PER_RUN = 25
MIN_DELAY_BETWEEN_CHANNELS = 20
MAX_DELAY_BETWEEN_CHANNELS = 120

JOIN_LEAVE_MIN_DELAY = 15
JOIN_LEAVE_MAX_DELAY = 60
JOIN_CLICK_DELAY = 2

REACTIONS = ["👍", "❤️", "🔥", "🎉", "🤔"]
REACTION_PROBABILITY = 0.6

DEVICE_MODELS = [
    "Samsung Galaxy S24 Ultra",
    "iPhone 15 Pro Max",
    "OnePlus 12R",
    "Xiaomi 14 Pro",
    "Google Pixel 8 Pro",
]
SYSTEM_VERSIONS = ["Android 14", "iOS 17.4.1", "Android 13"]
APP_VERSIONS = ["10.5.x", "10.4.2"]

# ---------- Proxy ----------
PROXY_API_URLS = [
    "https://proxy-list.org/english/api.php?demon=t",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5",
]

INITIAL_PROXIES = [
    "socks5://user:pass@1.2.3.4:1080",
]

class ProxyManager:
    def __init__(self):
        self.proxies = []          # لیست نهایی و تست‌شده
        self.active_proxy = None
        self.lock = asyncio.Lock()

    async def fetch_proxies(self, url: str):
        """دریافت پروکسی‌ها از یک URL"""
        try:
            log.info(f"🌐 Fetching proxies from {url}…")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []

            content = resp.text.strip()
            if "json" in url or "{" in content:
                try:
                    data = json.loads(content)
                    proxies = [p for p in data if isinstance(p, str)]
                except Exception:
                    proxies = []
            else:
                proxies = content.splitlines()

            log.info(f"✅ Found {len(proxies)} raw proxies.")
            return proxies
        except Exception as e:
            log.warning(f"❌ Error fetching from {url}: {e}")
            return []

    @staticmethod
    def parse(proxy_str: str):
        """تبدیل رشته‌ی پروکسی به قالب Telethon"""
        try:
            clean = proxy_str.replace("socks5://", "").replace("http://", "")
            if "@" in clean:
                auth, host_port = clean.rsplit("@", 1)
                user, pwd = auth.split(":", 1) if ":" in auth else ("", "")
                host, port = host_port.split(":")
                return ("socks5", host, int(port), user, pwd)
            else:
                host, port = clean.split(":")
                return ("socks5", host, int(port))
        except Exception:
            return None

    async def test_proxy(self, proxy_str: str):
        """تست سرعت و دسترسی‌پذیری پروکسی"""
        try:
            parsed = self.parse(proxy_str)
            if not parsed:
                return False

            url = "https://api.ipify.org?format=json"
            session = requests.Session()
            proxy_dict = {
                "http": f"{proxy_str.replace('socks5://', '')}",
                "https": f"{proxy_str.replace('socks5://', '')}",
            }

            start = time.time()
            resp = await asyncio.to_thread(
                session.get, url, proxies=proxy_dict, timeout=5
            )
            elapsed = time.time() - start

            if resp.status_code == 200 and elapsed < 3.0:
                log.debug(f"🟢 Proxy {proxy_str[:20]}… FAST ({elapsed:.2f}s)")
                return True
            else:
                log.debug(f"🟡 Proxy {proxy_str[:20]}… SLOW ({elapsed:.2f}s)")
                return True
        except Exception:
            return False

    async def update_proxies(self):
        """به‌روزرسانی لیست پروکسی‌ها"""
        async with self.lock:
            log.info("🔄 Updating Proxy List…")
            raw = []
            for url in PROXY_API_URLS:
                raw.extend(await self.fetch_proxies(url))

            if not raw:
                log.warning("⚠️ No proxies fetched; using initial list.")
                raw = INITIAL_PROXIES

            valid = []
            for p in raw[:50]:
                if await self.test_proxy(p):
                    valid.append(p)

            if not valid:
                log.warning("⚠️ No valid proxies; falling back to initial.")
                valid = INITIAL_PROXIES

            self.proxies = valid
            log.info(f"✅ Active Proxy List Size: {len(self.proxies)}")

    def get_next_proxy(self):
        """انتخاب تصادفی پروکسی"""
        return random.choice(self.proxies) if self.proxies else None

proxy_manager = ProxyManager()

# ---------- Accounts ----------
ALL_ACCOUNTS = []
for i in range(1, 6):
    session = os.getenv(f"SESSION_{i}")
    phone = os.getenv(f"PHONE_{i}")

    if not session or not phone:
        continue

    acc_proxy_str = proxy_manager.get_next_proxy()
    acc_proxy = proxy_manager.parse(acc_proxy_str) if acc_proxy_str else None

    ALL_ACCOUNTS.append(
        {
            "index": i,
            "phone": phone,
            "session": session,
            "proxy": acc_proxy,
            "label": phone[-4:],
        }
    )

log.info(f"📱 Loaded {len(ALL_ACCOUNTS)} accounts | 🌐 Active Proxies: {len(proxy_manager.proxies)}")

# ---------- Helpers ----------
async def rand_delay_short():
    await asyncio.sleep(random.uniform(1, 4))

def is_fresh(msg, hours=24):
    if not getattr(msg, "date", None):
        return False
    now = datetime.utcnow()
    return (now - msg.date).total_seconds() < hours * 3600

def extract_ad_links(text):
    if not text:
        return []
    patterns = [
        r"t\.me/joinchat/([a-zA-Z0-9_\-]+)",
        r"t\.me/\+([a-zA-Z0-9_\-]+)",
        r"https?://t\.me/[a-zA-Z0-9_\-]+",
    ]
    links = []
    for p in patterns:
        links.extend(re.findall(p, text))
    return list(set(links))

async def wait_flood_wait(client, error):
    log.warning(f"FloodWait detected: {error.seconds}s. Sleeping…")
    await asyncio.sleep(error.seconds + 5)

# ---------- Core Flow ----------
async def process_channel(client, label, channel, op_cnt):
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        msgs = await client.get_messages(ent, limit=30)
        fresh = [m for m in msgs if is_fresh(m)]

        if not fresh:
            return op_cnt

        select_count = max(1, int(len(fresh) * random.uniform(0.3, 0.7)))
        selected_msgs = random.sample(
            fresh, k=min(select_count, len(fresh))
        )

        log.info(f"  [{label}] 📬 {title} → Processing {len(selected_msgs)} posts")

        for msg in selected_msgs:
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                return op_cnt

            # 1. Read
            if random.random() < 0.9:
                await rand_delay_short()
                try:
                    await client.send_read_acknowledge(ent, messages=[msg])
                    op_cnt += 1
                except Exception:
                    pass

            await rand_delay_short()

            # 2. View
            if random.random() < 0.4:
                try:
                    await client(GetMessagesViewsRequest(peer=ent, id=[msg.id], increment=True))
                    op_cnt += 1
                except FloodWaitError as e:
                    await wait_flood_wait(client, e)
                    continue

            await rand_delay_short()

            # 3. Reaction
            if random.random() < REACTION_PROBABILITY:
                react = random.choice(REACTIONS)
                try:
                    await client(
                        SendReactionRequest(
                            peer=ent,
                            msg_id=msg.id,
                            reaction=[ReactionEmoji(emoticon=react)],
                        )
                    )
                    op_cnt += 1
                except Exception:
                    pass

            await rand_delay_short()

            # 4. Join/Leave Ads
            if msg.text and ImportChatInviteRequest:
                ad_links = extract_ad_links(msg.text)
                all_links = list(set(ad_links))
                if all_links and random.random() < 0.3:
                    link = all_links[0]
                    await asyncio.sleep(JOIN_CLICK_DELAY)

                    try:
                        if "joinchat/" in link or "/+" in link:
                            hash_part = (
                                link.split("joinchat/")[1]
                                if "joinchat/" in link
                                else link.split("/+")[1]
                            ).split()[0]

                            invite = await client(ImportChatInviteRequest(hash_part))
                            joined_chat = invite.chat

                            stay_duration = random.randint(
                                JOIN_LEAVE_MIN_DELAY, JOIN_LEAVE_MAX_DELAY
                            )
                            log.debug(
                                f"  [{label}] 🔗 Joined {hash_part[:10]}… waiting {stay_duration}s"
                            )
                            await asyncio.sleep(stay_duration)

                            try:
                                await client(LeaveChannelRequest(joined_chat))
                                op_cnt += 1
                                log.debug(f"  [{label}] 🔙 Left channel")
                            except Exception as e:
                                log.debug(f"  [{label}] Leave error: {e}")

                    except Exception as e:
                        log.debug(f"  [{label}] Join/Leave error: {e}")

            await rand_delay_short()

        return op_cnt

    except FloodWaitError as e:
        await wait_flood_wait(client, e)
    except Exception as e:
        log.error(f"  [{label}] Error: {e}")

    return op_cnt

async def run_account(acc):
    try:
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH,
            device_model=random.choice(DEVICE_MODELS),
            system_version=random.choice(SYSTEM_VERSIONS),
            app_version=random.choice(APP_VERSIONS),
            proxy=acc["proxy"],
            connection_retries=5,
            timeout=30,
        )

        await client.start()
        me = await client.get_me()
        log.info(f"[{acc['label']}] ✅ Logged in as {me.first_name}")

        op_cnt = 0
        await asyncio.sleep(random.uniform(5, 15))

        for i, ch in enumerate(CHANNELS):
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                break

            if i > 0:
                delay = random.randint(
                    MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS
                )
                log.info(f"  [{acc['label']}] ⏳ Waiting {delay}s…")
                await asyncio.sleep(delay)

            op_cnt = await process_channel(client, acc["label"], ch, op_cnt)

        if client.session.changed:
            acc["session"] = client.session.save()

        await client.disconnect()
        log.info(f"[{acc['label']}] 🏁 Finished. Ops: {op_cnt}")
        return True

    except FloodWaitError as e:
        log.error(f"[{acc['label']}] Heavy Flood Wait: {e.seconds}s")
        await asyncio.sleep(e.seconds + 10)
        return False
    except AuthKeyDuplicatedError:
        log.error(f"[{acc['label']}] Auth Key Duplicated")
        return False
    except Exception as e:
        log.error(f"[{acc['label']}] Fatal: {e}")
        return False

async def main():
    log.info("=" * 60)
    log.info("🚀 TG Viewer Pro (Auto Proxy Discovery)")
    log.info("=" * 60)

    await proxy_manager.update_proxies()

    random.shuffle(ALL_ACCOUNTS)
    success_count = 0

    for i, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'=' * 40}\n📌 Account {i+1}/{len(ALL_ACCOUNTS)}: #{acc['index']}")

        if await run_account(acc):
            success_count += 1

        sleep_time = random.randint(90, 240)
        log.info(f"⏳ Sleeping {sleep_time}s before next account…")
        await asyncio.sleep(sleep_time)

    log.info("\n" + "=" * 60)
    log.info(f"🏁 Done. Success: {success_count}/{len(ALL_ACCOUNTS)}")
    log.info("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Stopped by user")
