#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -------------  Imports  ---------------------------------
import os, json, random, asyncio, logging, requests, re
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetMessagesViewsRequest,
    SendReactionRequest,
    ImportChatInviteRequest,
)
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import ReactionEmoji, MessageEntityTextUrl, MessageEntityUrl

# -------------  Logging  ---------------------------------
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    handlers=[logging.StreamHandler()])
log = logging.getLogger("TGViewer")

# -------------  Constants  -------------------------------
MAX_OPERATIONS_PER_RUN = 50
MIN_DELAY_BETWEEN_CHANNELS = 15
MAX_DELAY_BETWEEN_CHANNELS = 45
MIN_DELAY_BETWEEN_ACTIONS = 3
MAX_DELAY_BETWEEN_ACTIONS = 12
REACTIONS = ["👍","❤️","🔥","😍","😂","😮","😢","👎","🎉"]
REACTION_PROBABILITY = 0.95

DEVICE_MODELS = [
    "Samsung Galaxy S24 Ultra", "iPhone 15 Pro Max", "OnePlus 12R",
    "Xiaomi 14 Pro", "Google Pixel 8 Pro", "Huawei Mate 60 Pro",
    "Sony Xperia 1 V", "Asus Zenfone 10", "Nothing Phone 2a",
]
SYSTEM_VERSIONS = ["Android 14", "iOS 17.4.1", "Android 13", "HarmonyOS 4.0"]
APP_VERSIONS = ["10.4.0", "10.3.1", "10.2.1"]

# -------------  Load env vars  ---------------------------
API_ID          = int(os.getenv("API_ID"))
API_HASH        = os.getenv("API_HASH")
CHANNELS        = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
GIST_TOKEN      = os.getenv("GIST_TOKEN")
GIST_ID         = os.getenv("GIST_ID")

# -------------  Account list  ----------------------------
ALL_ACCOUNTS = []
for i in range(1, 11):
    session = os.getenv(f"SESSION_{i}")
    phone   = os.getenv(f"PHONE_{i}")
    proxy   = os.getenv(f"PROXY_{i}")  # socks5://user:pass@host:port
    if session and phone:
        proxy_conf = None
        if proxy:
            try:
                p = proxy.replace("socks5://", "").split("@")
                if len(p) == 2:
                    auth, hostport = p
                    user, pw = auth.split(":")
                    host, port = hostport.split(":")
                    proxy_conf = ("socks5", host, int(port), user, pw)
                else:
                    host, port = p[0].split(":")
                    proxy_conf = ("socks5", host, int(port))
            except: proxy_conf = None
        ALL_ACCOUNTS.append({
            "index": i,
            "phone": phone,
            "session": session,
            "proxy": proxy_conf,
            "label": phone[-4:],
        })

log.info(f"📱 {len(ALL_ACCOUNTS)} account(s) | 📡 {len(CHANNELS)} channel(s)")

# -------------  Helper functions  -----------------------
def smart_delay(min_s=3, max_s=12):
    return asyncio.sleep(random.uniform(min_s, max_s))

def is_fresh(msg, hours=24):
    if not msg.date: return False
    return datetime.now(msg.date.tzinfo) - msg.date < timedelta(hours=hours)

def extract_ad_links(text):
    if not text: return []
    patterns = [
        r't\.me/joinchat/([a-zA-Z0-9_-]+)',
        r't\.me/\+([a-zA-Z0-9_-]+)',
        r't\.me/([a-zA-Z][a-zA-Z0-9_]{3,30})',
        r'https?://t\.me/[a-zA-Z0-9_]+',
    ]
    links = []
    for p in patterns:
        links.extend(re.findall(p, text))
    return links

def extract_entities_links(msg):
    links = []
    if msg.entities:
        for e in msg.entities:
            if isinstance(e, (MessageEntityTextUrl, MessageEntityUrl)):
                url = e.url if isinstance(e, MessageEntityTextUrl) else msg.text[e.offset:e.offset+e.length]
                if 't.me' in url: links.append(url)
    return links

# -------------  Gist helpers  --------------------------
def load_gist():
    if not GIST_TOKEN or not GIST_ID: return
    try:
        resp = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                            headers={"Authorization": f"token {GIST_TOKEN}"},
                            timeout=15)
        if resp.status_code != 200: return
        files = resp.json().get("files", {})
        if "sessions_pro.json" not in files: return
        data = json.loads(files["sessions_pro.json"]["content"])
        for a in ALL_ACCOUNTS:
            if a["phone"] in data and len(data[a["phone"]]) > 50:
                a["session"] = data[a["phone"]]
    except Exception as e:
        log.debug(f"Gist load error: {e}")

def save_gist():
    if not GIST_TOKEN or not GIST_ID: return
    try:
        data = {a["phone"]: a["session"] for a in ALL_ACCOUNTS}
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
            json={"files": {"sessions_pro.json": {"content": json.dumps(data, indent=2)}}},
            timeout=15)
        if resp.status_code == 200:
            log.info(f"✅ {len(data)} session(s) saved to Gist")
    except Exception as e:
        log.debug(f"Gist save error: {e}")

# -------------  Channel processing  --------------------
async def process_channel(client, label, channel, op_count):
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        msgs = await client.get_messages(ent, limit=50)

        fresh = [m for m in msgs if is_fresh(m)]
        log.info(f"  [{label}] 📬 {title} → {len(fresh)} new posts")

        for msg in fresh[:10]:
            if op_count >= MAX_OPERATIONS_PER_RUN: return op_count
            await smart_delay(5,15)

            # 1. سین
            await client.send_read_acknowledge(ent, max_id=msg.id)
            op_count += 1
            log.info(f"  [{label}] ✓ read {msg.id}")

            await smart_delay(3,8)

            # 2. ویو
            try:
                await client(GetMessagesViewsRequest(peer=ent, id=[msg.id], increment=True))
                op_count += 1
                log.info(f"  [{label}] 👁️ view {msg.id}")
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 30))
                continue

            await smart_delay(4,10)

            # 3. ریاکشن
            if random.random() < REACTION_PROBABILITY:
                react = random.choice(REACTIONS)
                try:
                    await client(SendReactionRequest(peer=ent, msg_id=msg.id,
                                                    reaction=[ReactionEmoji(emoticon=react)]))
                    op_count += 1
                    log.info(f"  [{label}] 🎭 react {react} on {msg.id}")
                except Exception:
                    pass

            # 4. اد/لینک
            if msg.text:
                ad_links = extract_ad_links(msg.text)
                ent_links = extract_entities_links(msg)
                all_links = list(set(ad_links + ent_links))
                if all_links and random.random() < 0.6:
                    for link in all_links[:2]:
                        if op_count >= MAX_OPERATIONS_PER_RUN: break
                        await smart_delay(10,25)
                        try:
                            if 'joinchat' in link or '/+' in link:
                                hash_part = (link.split('joinchat/')[1] if 'joinchat/' in link
                                             else link.split('/+')[1]).split()[0]
                                invite = await client(ImportChatInviteRequest(hash_part))
                                joined = invite.chat
                                log.info(f"  [{label}] ✅ joined {hash_part[:10]}...")
                                op_count += 1
                                await smart_delay(0.5,1.5)
                                try:
                                    await client(LeaveChannelRequest(joined))
                                    op_count += 1
                                    title_joined = getattr(joined, "title", str(joined))
                                    log.info(f"  [{label}] 🔙 left {title_joined}")
                                except Exception:
                                    pass
                            else:
                                log.info(f"  [{label}] 🔗 link {link[:30]}...")
                                op_count += 1
                        except Exception:
                            pass

            await smart_delay(8,18)

        return op_count

    except Exception as e:
        log.error(f"  [{label}] error: {e}")
        return op_count

# -------------  Account runner  -------------------------
async def run_account(acc):
    try:
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID, API_HASH,
            device_model=random.choice(DEVICE_MODELS),
            system_version=random.choice(SYSTEM_VERSIONS),
            app_version=random.choice(APP_VERSIONS),
            proxy=acc["proxy"],
            connection_retries=3,
            timeout=30
        )
        await client.start()
        me = await client.get_me()
        log.info(f"[{acc['label']}] ✅ {me.first_name} ({me.username or 'anon'})")

        op_cnt = 0
        await smart_delay(10,20)

        for i, ch in enumerate(CHANNELS):
            if op_cnt >= MAX_OPERATIONS_PER_RUN: break
            if i > 0:
                await asyncio.sleep(random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS))
            op_cnt = await process_channel(client, acc["label"], ch, op_cnt)

        acc["session"] = client.session.save()
        await client.disconnect()
        log.info(f"[{acc['label']}] 🏁 finished ({op_cnt} ops)")
        return True
    except Exception as e:
        log.error(f"[{acc['label']}] fatal: {e}")
        return False

# -------------  Main entry  ----------------------------
async def main():
    log.info("="*70)
    log.info("🚀 TG Viewer started")
    log.info("="*70)

    load_gist()
    random.shuffle(ALL_ACCOUNTS)
    success = 0

    for i, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'-'*50}\n📌 {i+1}/{len(ALL_ACCOUNTS)} – #{acc['index']} ({acc['label']})")
        if await run_account(acc):
            success += 1
        await asyncio.sleep(random.randint(45,120))

    save_gist()
    log.info("\n" + "="*70)
    log.info(f"🏁 {success}/{len(ALL_ACCOUNTS)} succeeded")
    log.info("="*70)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ stopped")
