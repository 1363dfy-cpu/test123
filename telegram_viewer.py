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
    ImportChatInviteRequest,
)
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import ReactionEmoji

# ================== Logging ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("TGViewer_Pro")

# ================== Constants ==================
MAX_OPERATIONS_PER_RUN = 200
MIN_DELAY_BETWEEN_CHANNELS = 10
MAX_DELAY_BETWEEN_CHANNELS = 30     

# تنظیمات Join/Leave Ads - فعال روی همه پست‌ها
JOIN_LEAVE_MIN_DELAY = 5   # حداقل ۵ ثانیه توی کانال بمونه
JOIN_LEAVE_MAX_DELAY = 15  # حداکثر ۱۵ ثانیه
JOIN_CLICK_DELAY = 1       # تأخیر قبل از کلیک
JOIN_LEAVE_PROBABILITY = 0.8  # 80% شانس Join/Leave روی هر پست

REACTIONS = ["👍", "❤️", "🔥", "🎉", "🤔"] 
REACTION_PROBABILITY = 1.0

DEVICE_MODELS = [
    "Samsung Galaxy S24 Ultra",
    "iPhone 15 Pro Max",
    "OnePlus 12R",
    "Xiaomi 14 Pro",
    "Google Pixel 8 Pro",
    "Samsung Galaxy S23",
    "iPhone 14",
    "Xiaomi 13T",
    "Huawei P60 Pro",
    "Oppo Find X7",
]
SYSTEM_VERSIONS = ["Android 14", "iOS 17.4.1", "Android 13", "iOS 17.2", "Android 12"]
APP_VERSIONS = ["10.5.x", "10.4.2", "10.3.1", "10.2.0"]

# ================== Env Variables ==================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNELS_RAW = os.getenv("CHANNELS", "")
CHANNELS = [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]

GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

# ================== Account Setup ==================
ALL_ACCOUNTS = []
MAX_ACCOUNTS = 10

for i in range(1, MAX_ACCOUNTS + 1):
    session = os.getenv(f"SESSION_{i}")
    phone = os.getenv(f"PHONE_{i}")
    
    if not session or not phone:
        continue
    
    proxy_str = os.getenv(f"PROXY_{i}", "")
    
    parsed_proxy = None
    if proxy_str:
        try:
            if "socks5://" in proxy_str:
                clean = proxy_str.replace("socks5://", "")
                if "@" in clean:
                    auth, hostport = clean.split("@")
                    user, password = auth.split(":", 1) if ":" in auth else (auth, "")
                    host, port = hostport.split(":")
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
        "proxy": parsed_proxy,
        "label": phone[-4:],
    })

log.info(f"📱 Loaded {len(ALL_ACCOUNTS)} accounts")

# ================== Helper Functions ==================

async def rand_delay_short():
    await asyncio.sleep(random.uniform(1, 3))

async def rand_delay_medium():
    await asyncio.sleep(random.uniform(3, 7))

def is_fresh(msg, hours=24):
    if not msg.date: return False
    now = datetime.now(msg.date.tzinfo) if msg.date.tzinfo else datetime.utcnow()
    delta = now - msg.date
    return delta.total_seconds() < (hours * 3600)

def extract_ad_links(text):
    """استخراج لینک‌های تبلیغاتی از متن پست"""
    if not text: return []
    
    patterns = [
        # لینک دعوت خصوصی
        r't\.me/joinchat/([a-zA-Z0-9_-]+)',
        # لینک دعوت عمومی
        r't\.me/\+([a-zA-Z0-9_-]+)',
        # لینک کانال عمومی
        r'https?://t\.me/[a-zA-Z0-9_]+',
        # لینک بدون https
        r't\.me/[a-zA-Z0-9_]+',
    ]
    
    links = []
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        links.extend(matches)
    
    # حذف تکراری‌ها
    unique_links = list(set(links))
    
    # فیلتر کردن لینک‌های معتبر
    valid_links = []
    for link in unique_links:
        # لینک‌های joinchat یا + را نگه میداریم
        if "joinchat" in str(link) or "+" in str(link) or "t.me" in str(link):
            valid_links.append(link)
    
    return valid_links

async def wait_flood_wait(client, error):
    wait_time = min(error.seconds, 60) + random.randint(5, 15)
    log.warning(f"⏳ FloodWait: {error.seconds}s → sleeping {wait_time}s")
    await asyncio.sleep(wait_time)

# ================== Core Flow ==================

async def process_channel(client, label, channel, op_cnt):
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        
        # دریافت ۵۰ پست آخر
        msgs = await client.get_messages(ent, limit=50)
        fresh = [m for m in msgs if is_fresh(m)]
        
        if not fresh:
            log.info(f"  [{label}] 📭 {title} → no new posts")
            return op_cnt

        log.info(f"  [{label}] 📬 {title} → {len(fresh)} new posts found")

        for msg in fresh:
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                log.info(f"  [{label}] ⚠️ Max ops reached")
                return op_cnt

            log.info(f"  [{label}] 🔄 Processing post #{msg.id}")

            # 1. Read
            await rand_delay_short()
            try:
                await client.send_read_acknowledge(ent, messages=[msg])
                op_cnt += 1
                log.info(f"  [{label}] ✓ Read post #{msg.id}")
            except Exception as e:
                log.debug(f"  [{label}] Read error: {e}")

            await rand_delay_medium()

            # 2. View
            try:
                await client(GetMessagesViewsRequest(peer=ent, id=[msg.id], increment=True))
                op_cnt += 1
                log.info(f"  [{label}] 👁️ View added to post #{msg.id}")
            except FloodWaitError as e:
                await wait_flood_wait(client, e)
                continue
            except Exception as e:
                log.debug(f"  [{label}] View error: {e}")

            await rand_delay_medium()

            # 3. Reaction
            react = random.choice(REACTIONS)
            try:
                await client(SendReactionRequest(
                    peer=ent, 
                    msg_id=msg.id, 
                    reaction=[ReactionEmoji(emoticon=react)]
                ))
                op_cnt += 1
                log.info(f"  [{label}] 🎭 Reaction {react} on post #{msg.id}")
            except FloodWaitError as e:
                await wait_flood_wait(client, e)
            except Exception as e:
                log.debug(f"  [{label}] Reaction error: {e}")

            await rand_delay_medium()

            # 4. ✅ Join/Leave Ads - فعال با 80% شانس
            if msg.text and random.random() < JOIN_LEAVE_PROBABILITY:
                ad_links = extract_ad_links(msg.text)
                
                log.info(f"  [{label}] 🔍 Found {len(ad_links)} ad links in post #{msg.id}")
                
                if ad_links:
                    # انتخاب یک لینک تصادفی
                    link = random.choice(ad_links)
                    
                    # استخراج hash
                    hash_part = None
                    link_str = str(link)
                    
                    if "joinchat/" in link_str:
                        hash_part = link_str.split("joinchat/")[1].split()[0]
                    elif "/+" in link_str:
                        hash_part = link_str.split("/+")[1].split()[0]
                    elif "t.me/" in link_str:
                        # لینک کانال عمومی - نیاز به username
                        username = link_str.split("t.me/")[1].split()[0]
                        hash_part = None  # برای کانال عمومی از روش دیگه استفاده میکنیم
                    
                    if hash_part:
                        await asyncio.sleep(JOIN_CLICK_DELAY)
                        try:
                            log.info(f"  [{label}] 🔗 Attempting to join {hash_part[:12]}...")
                            
                            # JOIN
                            result = await client(ImportChatInviteRequest(hash_part))
                            
                            if hasattr(result, 'chats') and result.chats:
                                joined = result.chats[0]
                                joined_title = getattr(joined, 'title', 'Unknown')[:20]
                                log.info(f"  [{label}] ✅ Joined channel: {joined_title}")
                                
                                # ماندن تصادفی در کانال
                                stay = random.randint(JOIN_LEAVE_MIN_DELAY, JOIN_LEAVE_MAX_DELAY)
                                log.info(f"  [{label}] ⏳ Staying {stay}s in {joined_title}")
                                await asyncio.sleep(stay)
                                
                                # LEAVE
                                try:
                                    await client(LeaveChannelRequest(joined))
                                    log.info(f"  [{label}] 🔙 Left channel: {joined_title}")
                                    op_cnt += 2  # Join + Leave = 2 operations
                                except Exception as e:
                                    log.warning(f"  [{label}] ⚠️ Leave error: {e}")
                            else:
                                log.warning(f"  [{label}] ⚠️ No chat returned from invite")
                                
                        except FloodWaitError as e:
                            await wait_flood_wait(client, e)
                        except Exception as e:
                            log.debug(f"  [{label}] Join error: {e}")
                    else:
                        # برای کانال‌های عمومی (بدون hash)
                        log.info(f"  [{label}] 📎 Found public channel link: {link_str[:30]}...")
                        # میتونیم از روش get_entity استفاده کنیم
                        try:
                            username = link_str.split("t.me/")[1].split()[0]
                            entity = await client.get_entity(username)
                            if entity:
                                log.info(f"  [{label}] ✅ Joined public channel: {username}")
                                stay = random.randint(JOIN_LEAVE_MIN_DELAY, JOIN_LEAVE_MAX_DELAY)
                                await asyncio.sleep(stay)
                                await client(LeaveChannelRequest(entity))
                                log.info(f"  [{label}] 🔙 Left public channel: {username}")
                                op_cnt += 2
                        except Exception as e:
                            log.debug(f"  [{label}] Public channel error: {e}")

            await rand_delay_medium()

        return op_cnt

    except FloodWaitError as e:
        await wait_flood_wait(client, e)
    except Exception as e:
        log.error(f"  [{label}] Channel error: {e}")
        
    return op_cnt

async def run_account(acc):
    try:
        device = random.choice(DEVICE_MODELS)
        system = random.choice(SYSTEM_VERSIONS)
        app = random.choice(APP_VERSIONS)
        
        log.info(f"[{acc['label']}] 📱 {device}")
        if acc["proxy"]:
            log.info(f"[{acc['label']}] 🔒 Proxy: {acc['proxy'][1]}:{acc['proxy'][2]}")
        else:
            log.info(f"[{acc['label']}] 🔓 No proxy")
        
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
                log.info(f"[{acc['label']}] ⚠️ Max ops reached")
                break
            
            if i > 0:
                delay = random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS)
                log.info(f"[{acc['label']}] ⏳ {delay}s wait before next channel...")
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
    log.info("🚀 TG Viewer Pro - Join/Leave Ads Active")
    log.info(f"📱 {len(ALL_ACCOUNTS)} accounts | 📡 {len(CHANNELS)} channels")
    log.info(f"🎯 Join/Leave Probability: {JOIN_LEAVE_PROBABILITY*100}%")
    log.info(f"⏱️ Stay duration: {JOIN_LEAVE_MIN_DELAY}-{JOIN_LEAVE_MAX_DELAY}s")
    log.info("=" * 60)

    random.shuffle(ALL_ACCOUNTS)
    success_count = 0

    for idx, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'='*40}")
        log.info(f"📌 Account {idx+1}/{len(ALL_ACCOUNTS)}: #{acc['index']} ({acc['label']})")
        log.info(f"{'='*40}")
        
        if await run_account(acc):
            success_count += 1
        
        if idx < len(ALL_ACCOUNTS) - 1:
            sleep_time = random.randint(90, 240)
            log.info(f"⏳ Sleeping {sleep_time}s before next account...")
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
