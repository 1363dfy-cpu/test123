#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, random, asyncio, logging, requests, re, math
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetMessagesViewsRequest,
    SendReactionRequest,
    ImportChatInviteRequest,
)
from telethon.tl.functions.channels import LeaveChannelRequest, GetFullChannelRequest
from telethon.tl.types import ReactionEmoji, MessageEntityTextUrl, MessageEntityUrl

# ================== Logging ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("TGViewer_AntiBan")

# ================== Constants ==================
# کاهش تعداد عملیات برای هر ران برای جلوگیری از الگوی تکراری
MAX_OPERATIONS_PER_RUN = 20          
MIN_DELAY_BETWEEN_CHANNELS = 15
MAX_DELAY_BETWEEN_CHANNELS = 90      # افزایش فاصله بین کانال‌ها
MIN_DELAY_BETWEEN_ACTIONS = 3
MAX_DELAY_BETWEEN_ACTIONS = 45       # افزایش زمان بین اکشن‌ها (شبیه‌سازی خواندن)

# ری‌اکشن‌های متنوع‌تر
REACTIONS = ["👍", "❤️", "🔥", "🎉", "🤔", "👀"] 
REACTION_PROBABILITY = 0.6           # کاهش احتمال ری‌اکشن به 60%

# مدل‌های دستگاهی متنوع برای جلوگیری از تشخیص یکسان
DEVICE_MODELS = [
    "Samsung Galaxy S24 Ultra",
    "iPhone 15 Pro Max",
    "OnePlus 12R",
    "Xiaomi 14 Pro",
    "Google Pixel 8 Pro",
    "Huawei Mate 60 Pro",
    "Sony Xperia 1 V",
    "Asus Zenfone 10",
    "Nothing Phone (2)",
    "Motorola Edge 40 Pro",
]
SYSTEM_VERSIONS = ["Android 14", "iOS 17.4.1", "Android 13", "HarmonyOS 4.0", "iOS 16.7"]
APP_VERSIONS = ["10.5.x", "10.4.2", "10.3.1", "10.2.1"]

# ================== Env ==================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
# فرمت: channel1,channel2,... یا @username, id
CHANNELS_RAW = os.getenv("CHANNELS", "")
CHANNELS = [c.strip() for c in CHANNELS_RAW.split(",") if c.strip()]

GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")

# ================== Accounts ==================
ALL_ACCOUNTS = []
for i in range(1, 6): # فرض بر 5 اکانت برای تست بهتر
    session = os.getenv(f"SESSION_{i}")
    phone = os.getenv(f"PHONE_{i}")
    proxy = os.getenv(f"PROXY_{i}")  
    if not session or not phone:
        continue
    
    # پارس کردن پروکسی
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
        except Exception as e:
            log.warning(f"Proxy parse error for #{i}: {e}")
            
    ALL_ACCOUNTS.append({
        "index": i,
        "phone": phone,
        "session": session,
        "proxy": proxy_conf,
        "label": phone[-4:],
    })

log.info(f"📱 Loaded {len(ALL_ACCOUNTS)} accounts | 📡 {len(CHANNELS)} channels")

# ================== Helpers ==================

def get_human_delay(min_s=MIN_DELAY_BETWEEN_ACTIONS, max_s=MAX_DELAY_BETWEEN_ACTIONS):
    """
    ایجاد تاخیر تصادفی با توزیع کمی غیرخطی برای شبیه‌سازی انسان.
    گاهی اوقات سریع (اسکرول) و گاهی کند (خواندن عمیق).
    """
    delay = random.uniform(min_s, max_s)
    # 10% شانس تاخیر طولانی‌تر (مثلاً کاربر در حال فکر کردن است)
    if random.random() < 0.1:
        delay += random.randint(10, 30)
    return delay

def is_fresh(msg, hours=24):
    if not msg.date:
        return False
    # تطبیق تایم‌زون اگر لازم باشد، اما معمولاً UTC است
    now = datetime.utcnow()
    delta = now - msg.date
    return delta.total_seconds() < (hours * 3600)

def extract_ad_links(text):
    if not text:
        return []
    patterns = [
        r't\.me/joinchat/([a-zA-Z0-9_-]+)',
        r't\.me/\+([a-zA-Z0-9_-]+)',
        r'https?://t\.me/[a-zA-Z0-9_]+',
    ]
    links = []
    for p in patterns:
        links.extend(re.findall(p, text))
    return list(set(links))

def extract_entities_links(msg):
    links = []
    if msg.entities:
        for e in msg.entities:
            if isinstance(e, (MessageEntityTextUrl, MessageEntityUrl)):
                url = e.url if isinstance(e, MessageEntityTextUrl) else msg.text[e.offset:e.offset+e.length]
                if 't.me' in url:
                    links.append(url)
    return list(set(links))

async def wait_flood_wait(client, error):
    """مدیریت هوشمند FloodWait"""
    log.warning(f"FloodWait detected: {error.seconds} seconds. Sleeping...")
    await asyncio.sleep(error.seconds + 5) # اضافه کردن کمی حاشیه امنیت

# ================== Core Flow ==================

async def process_channel(client, label, channel, op_cnt):
    try:
        # دریافت اطلاعات کانال
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        
        # دریافت پیام‌های اخیر (محدود برای سرعت)
        msgs = await client.get_messages(ent, limit=30)
        fresh = [m for m in msgs if is_fresh(m)]
        
        if not fresh:
            log.debug(f"  [{label}] No fresh posts in {title}")
            return op_cnt

        # انتخاب تصادفی پیام‌ها (نه همه، نه کمترین)
        # انتخاب بین 30% تا 70% از پیام‌های تازه
        select_count = max(1, int(len(fresh) * random.uniform(0.3, 0.7)))
        selected_msgs = random.sample(fresh, k=min(select_count, len(fresh)))
        
        log.info(f"  [{label}] 📬 {title} → Selected {len(selected_msgs)} posts")

        for msg in selected_msgs:
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                return op_cnt

            # 1. خواندن پیام (Mark as Read)
            # احتمال خواندن 90% است
            if random.random() < 0.9:
                await rand_delay_short()
                try:
                    await client.send_read_acknowledge(ent, messages=[msg])
                    op_cnt += 1
                    log.debug(f"  [{label}] ✓ Read {msg.id}")
                except Exception as e:
                    pass # اگر خطا داد، ادامه بده (گاهی تکراری خواندن مشکلی ندارد)

            await rand_delay_short()

            # 2. ویو (View)
            # احتمال ویو 40% است (چون خواندن لزوماً ویو نمی‌خورد مگر اینکه اسکرول کند)
            if random.random() < 0.4:
                try:
                    await client(GetMessagesViewsRequest(peer=ent, id=[msg.id], increment=True))
                    op_cnt += 1
                    log.debug(f"  [{label}] 👁️ Viewed {msg.id}")
                except FloodWaitError as e:
                    await wait_flood_wait(client, e)
                    continue

            await rand_delay_short()

            # 3. ری‌اکشن (Reaction)
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
                    log.debug(f"  [{label}] 🎭 Reacted {react} on {msg.id}")
                except Exception:
                    pass

            await rand_delay_short()

            # 4. Join/Leave Logic
            if msg.text:
                ad_links = extract_ad_links(msg.text)
                ent_links = extract_entities_links(msg)
                all_links = list(set(ad_links + ent_links))
                
                # فقط اگر لینک وجود دارد و شانس رخ داد (50%)
                if all_links and random.random() < 0.5:
                    for link in all_links[:2]: # حداکثر 2 لینک در هر پیام
                        if op_cnt >= MAX_OPERATIONS_PER_RUN:
                            break
                        
                        # تاخیر بیشتر برای Join کردن (انسان‌وارتر)
                        await asyncio.sleep(random.uniform(2, 5))
                        
                        try:
                            if "joinchat" in link or "/+" in link:
                                hash_part = (
                                    link.split("joinchat/")[1]
                                    if "joinchat/" in link
                                    else link.split("/+")[1]
                                ).split()[0]
                                
                                # Join
                                invite = await client(ImportChatInviteRequest(hash_part))
                                joined_chat = invite.chat
                                
                                # تاخیر کوتاه قبل از لِیو کردن (شبیه‌سازی چک کردن کانال)
                                await asyncio.sleep(random.uniform(3, 8))
                                
                                try:
                                    await client(LeaveChannelRequest(joined_chat))
                                    op_cnt += 1
                                except Exception:
                                    pass
                            else:
                                # لینک ساده، فقط ویو یا ری‌اکشن روی خود پیام کافی است
                                pass 
                        except Exception as e:
                            log.debug(f"  [{label}] Link action error: {e}")

            await rand_delay_short()

        return op_cnt

    except FloodWaitError as e:
        await wait_flood_wait(client, e)
    except Exception as e:
        log.error(f"  [{label}] Error in channel: {e}")
        
    return op_cnt

async def run_account(acc):
    try:
        # ایجاد کلاینت با پراکسی و مشخصات دستگاهی تصادفی
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
        
        # تاخیر اولیه قبل از شروع کار
        await asyncio.sleep(random.uniform(5, 15))

        for i, ch in enumerate(CHANNELS):
            if op_cnt >= MAX_OPERATIONS_PER_RUN:
                break
            
            # تاخیر بین کانال‌ها (بیشتر و تصادفی‌تر)
            if i > 0:
                delay = random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS)
                log.info(f"  [{acc['label']}] ⏳ Waiting {delay}s before next channel...")
                await asyncio.sleep(delay)
                
            op_cnt = await process_channel(client, acc["label"], ch, op_cnt)

        # ذخیره سشن به‌روز شده
        if client.session.changed:
            acc["session"] = client.session.save()

        await client.disconnect()
        log.info(f"[{acc['label']}] 🏁 Finished. Total Ops: {op_cnt}")
        return True

    except FloodWaitError as e:
        log.error(f"[{acc['label']}] Heavy Flood Wait: {e.seconds}s")
        await asyncio.sleep(e.seconds + 10)
        return False
    except AuthKeyDuplicatedError:
        log.error(f"[{acc['label']}] Auth Key Duplicated (Session used elsewhere?)")
        return False
    except Exception as e:
        log.error(f"[{acc['label']}] Fatal Error: {e}")
        return False

async def main():
    log.info("=" * 60)
    log.info("🚀 TG Viewer Anti-Ban Mode Started")
    log.info("=" * 60)

    # اگر از Gist استفاده می‌کنید، لود کنید (اختیاری)
    if GIST_TOKEN and GIST_ID:
        load_gist() 

    random.shuffle(ALL_ACCOUNTS)
    success_count = 0

    for i, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'='*40}\n📌 Account {i+1}/{len(ALL_ACCOUNTS)}: #{acc['index']} ({acc['label']})")
        
        if await run_account(acc):
            success_count += 1
        
        # تاخیر بین اکانت‌ها برای جلوگیری از همزمانی زیاد (Concurrency Limit)
        # این خیلی مهم است! اگر همه اکانت‌ها همزمان عمل کنند، بن می‌شوید.
        sleep_time = random.randint(60, 180) 
        log.info(f"⏳ Sleeping {sleep_time}s before next account...")
        await asyncio.sleep(sleep_time)

    if GIST_TOKEN and GIST_ID:
        save_gist()

    log.info("\n" + "=" * 60)
    log.info(f"🏁 Done. Success: {success_count}/{len(ALL_ACCOUNTS)}")
    log.info("=" * 60)

# Helper functions for delays to keep code clean
async def rand_delay_short():
    await asyncio.sleep(random.uniform(1, 3))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Stopped by user")
