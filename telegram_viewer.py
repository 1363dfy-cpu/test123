#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, random, asyncio, logging, requests, re, math, time
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetMessagesViewsRequest,
    SendReactionRequest,
)
from telethon.tl.functions.channels import LeaveChannelRequest, ImportChatInviteRequest
from telethon.tl.types import ReactionEmoji

# ================== نصب پیش‌نیاز ==================
# pip install aio_socks   یا    pip install socks-py
# pip install requests aiohttp

# ================== Logging ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("TGViewer_Pro")

# ================== Constants ==================
MAX_OPERATIONS_PER_RUN = 25          
MIN_DELAY_BETWEEN_CHANNELS = 20
MAX_DELAY_BETWEEN_CHANNELS = 120     

# تنظیمات Join/Leave Ads
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

# ================== Env Variables ==================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNELS_RAW = os.getenv("CHANNELS", "")
CHANNELS = [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]

GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

# ================== Account Setup ==================
ALL_ACCOUNTS = []
for i in range(1, 6): 
    session = os.getenv(f"SESSION_{i}")
    phone = os.getenv(f"PHONE_{i}")
    
    if not session or not phone:
        continue
    
    # گرفتن پروکسی از متغیر محیطی (اگر خالی بود None)
    proxy_str = os.getenv(f"PROXY_{i}", "")
    
    # پارس کردن پروکسی
    parsed_proxy = None
    if proxy_str:
        try:
            # فرمت: socks5://user:pass@host:port  یا  socks5://host:port
            if "socks5://" in proxy_str:
                clean = proxy_str.replace("socks5://", "")
                if "@" in clean:
                    auth, hostport = clean.split("@")
                    user, password = auth.split(":", 1) if ":" in auth else (auth, "")
                    host, port = hostport.split(":")
                    # فرمت صحیح Telethon برای socks5 با احراز هویت
                    parsed_proxy = ("socks5", host, int(port), True, user, password)
                else:
                    host, port = clean.split(":")
                    parsed_proxy = ("socks5", host, int(port), True, "", "")
        except Exception as e:
            log.warning(f"⚠️ Invalid proxy format for account {i}: {proxy_str}")
    
    ALL_ACCOUNTS.append({
        "index": i,
        "phone": phone,
        "session": session,
        "proxy": parsed_proxy,  # None or tuple
        "label": phone[-4:],
    })

log.info(f"📱 Loaded {len(ALL_ACCOUNTS)} accounts")

# ================== Helper Functions ==================

async def rand_delay_short():
    await asyncio.sleep(random.uniform(2, 6))

def is_fresh(msg, hours=24):
    if not msg.date: return False
    # اصلاح: استفاده از تاریخ UTC
    now = datetime.now(msg.date.tzinfo) if msg.date.tzinfo else datetime.utcnow()
    delta = now - msg.date
    return delta.total_seconds() < (hours * 3600)

def extract_ad_links(text):
    if not text: return []
    patterns = [r't\.me/joinchat/([a-zA-Z0-9_-]+)', r't\.me/\+([a-zA-Z0-9_-]+)', r'https?://t\.me/[a-zA-Z0-9_]+']
    links = []
    for p in patterns:
        links.extend(re.findall(p, text))
    return list(set(links))

async def wait_flood_wait(client, error):
    wait_time = min(error.seconds, 60) + random.randint(5, 15)
    log.warning(f"⏳ FloodWait: {error.seconds}s → sleeping {wait_time}s")
    await asyncio.sleep(wait_time)

# ================== Core Flow ==================

async def process_channel(client, label, channel, op_cnt):
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        
        msgs = await client.get_messages(ent, limit=30)
        fresh = [m for m in msgs if is_fresh(m)]
        
        if not fresh:
            log.info(f"  [{label}] 📭 {title} → no new posts")
            return op_cnt

        select_count = max(1, int(len(fresh) * random.uniform(0.3, 0.7)))
        selected_msgs = random.sample(fresh, k=min(select_count, len(fresh)))
        
        log.info(f"  [{label}] 📬 {title} → Processing {len(selected_msgs)} posts")

        for msg in selected_msgs:
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                log.info(f"  [{label}] ⚠️ Max ops reached")
                return op_cnt

            # 1. Read
            if random.random() < 0.9:
                await rand_delay_short()
                try:
                    await client.send_read_acknowledge(ent, messages=[msg])
                    op_cnt += 1
                except Exception as e:
                    log.debug(f"  [{label}] Read error: {e}")

            await rand_delay_short()

            # 2. View
            if random.random() < 0.4:
                try:
                    await client(GetMessagesViewsRequest(peer=ent, id=[msg.id], increment=True))
                    op_cnt += 1
                except FloodWaitError as e:
                    await wait_flood_wait(client, e)
                    continue
                except Exception as e:
                    log.debug(f"  [{label}] View error: {e}")

            await rand_delay_short()

            # 3. Reaction
            if random.random() < REACTION_PROBABILITY:
                react = random.choice(REACTIONS)
                try:
                    await client(SendReactionRequest(peer=ent, msg_id=msg.id, reaction=[ReactionEmoji(emoticon=react)]))
                    op_cnt += 1
                except FloodWaitError as e:
                    await wait_flood_wait(client, e)
                except Exception as e:
                    log.debug(f"  [{label}] Reaction error: {e}")

            await rand_delay_short()

            # 4. Join/Leave Ads
            if msg.text and random.random() < 0.3:
                ad_links = extract_ad_links(msg.text)
                
                if ad_links:
                    link = ad_links[0]
                    
                    # استخراج hash برای join
                    hash_part = None
                    if "joinchat/" in link:
                        hash_part = link.split("joinchat/")[1].split()[0]
                    elif "/+" in link:
                        hash_part = link.split("/+")[1].split()[0]
                    
                    if hash_part:
                        await asyncio.sleep(JOIN_CLICK_DELAY)
                        try:
                            # Join channel
                            result = await client(ImportChatInviteRequest(hash_part))
                            if hasattr(result, 'chats') and result.chats:
                                joined = result.chats[0]
                                log.info(f"  [{label}] 🔗 Joined {hash_part[:8]}...")
                                
                                # Stay then leave
                                stay = random.randint(JOIN_LEAVE_MIN_DELAY, JOIN_LEAVE_MAX_DELAY)
                                await asyncio.sleep(stay)
                                
                                try:
                                    await client(LeaveChannelRequest(joined))
                                    log.info(f"  [{label}] 🔙 Left channel")
                                    op_cnt += 2  # Join + Leave
                                except Exception as e:
                                    log.debug(f"  [{label}] Leave error: {e}")
                        except FloodWaitError as e:
                            await wait_flood_wait(client, e)
                        except Exception as e:
                            log.debug(f"  [{label}] Join error: {e}")

            await rand_delay_short()

        return op_cnt

    except FloodWaitError as e:
        await wait_flood_wait(client, e)
    except Exception as e:
        log.error(f"  [{label}] Channel error: {e}")
        
    return op_cnt

async def run_account(acc):
    try:
        # تنظیمات تصادفی device
        device = random.choice(DEVICE_MODELS)
        system = random.choice(SYSTEM_VERSIONS)
        app = random.choice(APP_VERSIONS)
        
        log.info(f"[{acc['label']}] 📱 {device}")
        if acc["proxy"]:
            log.info(f"[{acc['label']}] 🔒 Proxy: {acc['proxy'][1]}:{acc['proxy'][2]}")
        else:
            log.info(f"[{acc['label']}] 🔓 No proxy")
        
        # ایجاد کلاینت
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH,
            device_model=device,
            system_version=system,
            app_version=app,
            proxy=acc["proxy"],
            connection_retries=3,
            timeout=30,
        )
        
        await client.start()
        me = await client.get_me()
        log.info(f"[{acc['label']}] ✅ {me.first_name} (@{me.username or '---'})")

        op_cnt = 0
        await asyncio.sleep(random.uniform(5, 15))

        for i, ch in enumerate(CHANNELS):
            if op_cnt >= MAX_OPERATIONS_PER_RUN: 
                log.info(f"[{acc['label']}] ⚠️ Max ops ({MAX_OPERATIONS_PER_RUN}) reached")
                break
            
            if i > 0:
                delay = random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS)
                log.info(f"[{acc['label']}] ⏳ {delay}s wait...")
                await asyncio.sleep(delay)
                
            op_cnt = await process_channel(client, acc["label"], ch, op_cnt)

        if client.session and hasattr(client.session, 'changed') and client.session.changed:
            acc["session"] = client.session.save()
            log.info(f"[{acc['label']}] 💾 Session saved")

        await client.disconnect()
        log.info(f"[{acc['label']}] 🏁 Done. {op_cnt} operations")
        return True

    except FloodWaitError as e:
        log.error(f"[{acc['label']}] ⛔ Heavy Flood: {e.seconds}s")
        await asyncio.sleep(min(e.seconds, 120) + 10)
        return False
    except AuthKeyDuplicatedError:
        log.error(f"[{acc['label']}] ⛔ Auth key duplicated (banned?)")
        return False
    except Exception as e:
        log.error(f"[{acc['label']}] ❌ Fatal: {e}")
        return False

async def main():
    log.info("=" * 60)
    log.info("🚀 TG Viewer Pro - Version Fix")
    log.info(f"📱 {len(ALL_ACCOUNTS)} accounts | 📡 {len(CHANNELS)} channels")
    log.info(f"🛡️ Max ops/run: {MAX_OPERATIONS_PER_RUN}")
    log.info("=" * 60)

    random.shuffle(ALL_ACCOUNTS)
    success_count = 0

    for idx, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'='*40}")
        log.info(f"📌 Account {idx+1}/{len(ALL_ACCOUNTS)}: #{acc['index']} ({acc['label']})")
        log.info(f"{'='*40}")
        
        if await run_account(acc):
            success_count += 1
        
        # خواب بین اکانت‌ها
        if idx < len(ALL_ACCOUNTS) - 1:
            sleep_time = random.randint(90, 240)
            log.info(f"⏳ Sleeping {sleep_time}s...")
            await asyncio.sleep(sleep_time)

    log.info("\n" + "=" * 60)
    log.info(f"🏁 Done: {success_count}/{len(ALL_ACCOUNTS)} successful")
    log.info("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Stopped by user")
    except Exception as e:
        log.error(f"💥 Fatal: {e}")
