#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ====================  Imports  ====================
import os
import json
import asyncio
import logging
import random
import requests
import re
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.tl.functions.messages import (
    GetMessagesViewsRequest,
    SendReactionRequest,
    ImportChatInviteRequest,
    LeaveChatRequest          # ← اضافه شده
)
from telethon.tl.types import ReactionEmoji, MessageEntityTextUrl, MessageEntityUrl

# ====================  Logging  ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TGViewerPRO")

# ==================== Anti‑Ban Configuration ====================
MAX_OPERATIONS_PER_RUN = 50      # حداکثر عملیات در هر اجرا
MIN_DELAY_BETWEEN_CHANNELS = 15
MAX_DELAY_BETWEEN_CHANNELS = 45
MIN_DELAY_BETWEEN_ACTIONS = 3
MAX_DELAY_BETWEEN_ACTIONS = 12

# لیست پروکسی‌های تصادفی (می‌توانید پروکسی واقعی اضافه کنید)
PROXIES = [
    None,  # بدون پروکسی برای برخی اکانت‌ها
]

# Device Info متغیر (هر بار تغییر می‌کنه)
DEVICE_MODELS = [
    "Samsung Galaxy S24 Ultra", "Samsung Galaxy S23 FE", "Samsung Galaxy A54",
    "Xiaomi 14 Pro", "Xiaomi 13T Pro", "Xiaomi Redmi Note 12 Pro+",
    "iPhone 15 Pro Max", "iPhone 14 Plus", "iPhone SE (3rd gen)",
    "OnePlus 12R", "OnePlus Open", "OPPO Find N3 Flip",
    "Google Pixel 8 Pro", "Google Pixel 7a", "Huawei Mate 60 Pro",
    "POCO F5 Pro", "Realme GT 5 Pro", "Vivo X100 Pro",
    "Nothing Phone 2a", "Asus Zenfone 10", "Sony Xperia 1 V",
]
SYSTEM_VERSIONS = [
    "Android 14.0.1", "Android 14", "Android 13.0",
    "iOS 17.4.1", "iOS 17.3.1", "iOS 17.2.1",
    "Android 13.1", "Android 12.0", "HarmonyOS 4.0",
]
APP_VERSIONS = [
    "10.4.0", "10.3.1", "10.2.1",
    "10.0.1", "9.7.0", "9.6.1",
    "11.0.0", "10.5.0", "9.8.0"
]

# ==================== Reactions ====================
REACTIONS = ["👍", "❤️", "🔥", "😍", "😂", "😮", "😢", "👎", "🎉"]
REACTION_PROBABILITY = 0.95

# ==================== Environment Variables ====================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNELS = [c.strip() for c in os.environ["CHANNELS"].split(",") if c.strip()]
GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

# ==================== Account List ====================
ALL_ACCOUNTS = []
for i in range(1, 11):
    session = os.environ.get(f"SESSION_{i}")
    phone = os.environ.get(f"PHONE_{i}")
    proxy = os.environ.get(f"PROXY_{i}")  # فرمت: socks5://user:pass@host:port یا خالی
    if session and phone:
        proxy_config = None
        if proxy:
            try:
                parts = proxy.replace("socks5://", "").split("@")
                if len(parts) == 2:
                    auth, hostport = parts
                    user, passw = auth.split(":")
                    host, port = hostport.split(":")
                    proxy_config = ("socks5", host, int(port), user, passw)
                else:
                    host, port = parts[0].split(":")
                    proxy_config = ("socks5", host, int(port))
            except:
                pass

        ALL_ACCOUNTS.append({
            "index": i,
            "phone": phone,
            "session": session,
            "proxy": proxy_config or random.choice(PROXIES),
            "label": phone[-4:]
        })

logger.info(f"📱 {len(ALL_ACCOUNTS)} اکانت")
logger.info(f"📡 {len(CHANNELS)} کانال")
logger.info(f"🎭 {len(REACTIONS)} ریاکشن")
logger.info(f"🛡️ ضد بن فعال - حداکثر {MAX_OPERATIONS_PER_RUN} عملیات")

# ==================== Gist Functions ====================
def load_sessions_from_gist():
    if not GIST_TOKEN or not GIST_ID:
        return
    try:
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers, timeout=15)
        if resp.status_code != 200:
            return
        files = resp.json().get("files", {})
        if "sessions_pro.json" not in files:
            return
        saved = json.loads(files["sessions_pro.json"]["content"])
        count = 0
        for acc in ALL_ACCOUNTS:
            if acc["phone"] in saved and len(saved[acc["phone"]]) > 50:
                acc["session"] = saved[acc["phone"]]
                count += 1
        logger.info(f"✅ {count} سشن از Gist بارگذاری شد")
    except:
        pass

def save_sessions_to_gist(accounts):
    if not GIST_TOKEN or not GIST_ID:
        return
    try:
        data = {acc["phone"]: acc["session"] for acc in accounts}
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers,
            json={"files": {"sessions_pro.json": {"content": json.dumps(data, indent=2)}}},
            timeout=15
        )
        if resp.status_code == 200:
            logger.info(f"✅ {len(data)} سشن ذخیره شد")
    except:
        pass

# ==================== Helper Functions ====================
def smart_delay(min_s=3, max_s=12):
    base = random.uniform(min_s, max_s)
    noise = random.uniform(-1, 2)
    return asyncio.sleep(max(1, base + noise))

def is_fresh_post(msg, hours=24):
    if not msg.date:
        return False
    now = datetime.now(msg.date.tzinfo)
    return (now - msg.date) < timedelta(hours=hours)

def extract_ad_links(message_text):
    if not message_text:
        return []
    patterns = [
        r't\.me/joinchat/([a-zA-Z0-9_-]+)',
        r't\.me/\+([a-zA-Z0-9_-]+)',
        r't\.me/([a-zA-Z][a-zA-Z0-9_]{3,30})',
        r'https?://t\.me/[a-zA-Z0-9_]+',
    ]
    found_links = []
    for pattern in patterns:
        matches = re.findall(pattern, message_text)
        found_links.extend(matches)
    return found_links

def extract_entities_links(msg):
    links = []
    if msg.entities:
        for entity in msg.entities:
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                url = entity.url if isinstance(entity, MessageEntityTextUrl) else msg.text[entity.offset:entity.offset+entity.length]
                if 't.me' in url:
                    links.append(url)
    return links

# ==================== Channel Processing ====================
async def process_channel(client, phone_label, channel, operations_count):
    try:
        entity = await client.get_entity(channel)
        channel_name = getattr(entity, 'title', str(channel))[:30]
        limit = 50
        msgs = await client.get_messages(entity, limit=limit)

        if not msgs:
            logger.info(f"  [{phone_label}] - {channel_name} → خالی")
            return operations_count

        fresh_posts = [msg for msg in msgs if is_fresh_post(msg)]
        logger.info(f"  [{phone_label}] 📬 {channel_name} → {len(fresh_posts)} پست جدید از {len(msgs)} کل")

        if not fresh_posts:
            logger.info(f"  [{phone_label}] ℹ️ {channel_name} → پست جدیدی نیست")
            return operations_count

        for msg in fresh_posts[:10]:
            if operations_count >= MAX_OPERATIONS_PER_RUN:
                logger.info(f"  [{phone_label}] ⚠️ به حد نصاب عملیات رسیدیم")
                return operations_count

            await smart_delay(5, 15)

            # 1. سین کردن
            await client.send_read_acknowledge(entity, max_id=msg.id)
            operations_count += 1
            logger.info(f"  [{phone_label}] ✓ سین شد: پست {msg.id}")

            await smart_delay(3, 8)

            # 2. ویو
            try:
                await client(GetMessagesViewsRequest(peer=entity, id=[msg.id], increment=True))
                operations_count += 1
                logger.info(f"  [{phone_label}] 👁️ ویو: پست {msg.id}")
            except FloodWaitError as e:
                logger.warning(f"  [{phone_label}] ⏳ FloodWait: {e.seconds}s")
                await asyncio.sleep(min(e.seconds, 30))
                continue

            await smart_delay(4, 10)

            # 3. ریاکشن
            if random.random() < REACTION_PROBABILITY:
                chosen_reaction = random.choice(REACTIONS)
                try:
                    await client(SendReactionRequest(
                        peer=entity,
                        msg_id=msg.id,
                        reaction=[ReactionEmoji(emoticon=chosen_reaction)]
                    ))
                    operations_count += 1
                    logger.info(f"  [{phone_label}] 🎭 ریاکشن {chosen_reaction} روی پست {msg.id}")
                except FloodWaitError as e:
                    logger.warning(f"  [{phone_label}] ⏳ FloodWait ریاکشن: {e.seconds}s")
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception as e:
                    if "REACTION_INVALID" in str(e):
                        pass
                    else:
                        logger.debug(f"  [{phone_label}] ℹ️ ریاکشن: {str(e)[:40]}")

            # 4. کلیک روی اد تلگرام
            if msg.text:
                ad_links = extract_ad_links(msg.text)
                entity_links = extract_entities_links(msg)
                all_links = list(set(ad_links + entity_links))

                if all_links and random.random() < 0.6:
                    for link in all_links[:2]:
                        if operations_count >= MAX_OPERATIONS_PER_RUN:
                            break

                        await smart_delay(10, 25)
                        try:
                            if 'joinchat' in link or '/+' in link:
                                if 'joinchat/' in link:
                                    hash_part = link.split('joinchat/')[1].split()[0]
                                else:
                                    hash_part = link.split('/+')[1].split()[0]

                                try:
                                    # عضویت در کانال
                                    invite_res = await client(ImportChatInviteRequest(hash_part))
                                    joined_chat = invite_res.chat
                                    logger.info(f"  [{phone_label}] ✅ عضو شد: {hash_part[:10]}...")
                                    operations_count += 1

                                    # --------- خروج فوری پس از join ----------
                                    await smart_delay(0.5, 1.5)            # تاخیر کوتاه
                                    try:
                                        await client(LeaveChatRequest(joined_chat))
                                        operations_count += 1
                                        title = joined_chat.title if hasattr(joined_chat, "title") else joined_chat.id
                                        logger.info(f"  [{phone_label}] 🔙 ترک شد: {title}")
                                    except Exception as leave_err:
                                        logger.debug(f"  [{phone_label}] ⚠️ خروج ناموفق: {leave_err}")

                                except Exception as join_err:
                                    logger.info(f"  [{phone_label}] ℹ️ عضویت ممکن نبود: {str(join_err)[:40]}")
                            elif link.startswith('http') or link.startswith('@'):
                                await smart_delay(5, 12)
                                logger.info(f"  [{phone_label}] 🔗 کلیک روی لینک: {link[:30]}...")
                                operations_count += 1
                        except Exception as click_err:
                            logger.debug(f"  [{phone_label}] ℹ️ خطای کلیک: {str(click_err)[:40]}")

            await smart_delay(8, 18)

        return operations_count

    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.warning(f"  [{phone_label}] ❌ {channel[:30]} → جوین نیستید")
        else:
            logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:50]}")
        return operations_count
    except FloodWaitError as e:
        wait = min(e.seconds, 60) + random.randint(5, 10)
        logger.warning(f"  [{phone_label}] ⏳ FloodWait {e.seconds}s → sleep {wait}s")
        await asyncio.sleep(wait)
        return operations_count
    except Exception as e:
        logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:50]}")
        return operations_count

# ==================== Account Runner ====================
async def run_account(acc):
    try:
        phone = acc["phone"]
        label = acc["label"]
        proxy = acc.get("proxy")

        device = random.choice(DEVICE_MODELS)
        system = random.choice(SYSTEM_VERSIONS)
        app = random.choice(APP_VERSIONS)
        lang = random.choice(["en", "fa", "ar", "tr", "de"])

        logger.info(f"[{label}] 📱 {device} | {system} | v{app}")
        if proxy:
            logger.info(f"[{label}] 🔒 پروکسی فعال: {proxy[1]}:{proxy[2]}")

        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH,
            device_model=device,
            system_version=system,
            app_version=app,
            lang_code=lang,
            proxy=proxy,
            connection_retries=3,
            timeout=30
        )

        await client.start()
        me = await client.get_me()
        logger.info(f"[{label}] ✅ {me.first_name} (@{me.username or '---'})")

        operations_count = 0

        try:
            await me.phone
        except AuthKeyDuplicatedError:
            logger.warning(f"[{label}] ⛔ کلید احراز هویت تکراری - احتمال بن!")
            await client.disconnect()
            return False

        await smart_delay(10, 20)

        for idx, channel in enumerate(CHANNELS):
            if operations_count >= MAX_OPERATIONS_PER_RUN:
                logger.info(f"[{label}] ⚠️ به حد نصاب {MAX_OPERATIONS_PER_RUN} عملیات رسیدیم")
                break

            if idx > 0:
                delay = random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS)
                logger.info(f"[{label}] ⏳ {delay}s تا کانال بعدی...")
                await asyncio.sleep(delay)

            operations_count = await process_channel(client, label, channel, operations_count)

        acc["session"] = client.session.save()
        await client.disconnect()
        logger.info(f"[{label}] 🏁 تکمیل ({operations_count} عملیات)")
        return True

    except Exception as e:
        logger.error(f"[{label}] ❌ خطا: {str(e)[:80]}")
        if "key" in str(e).lower() or "auth" in str(e).lower():
            logger.warning(f"[{label}] ⛔ احتمال بن شدن اکانت!")
        return False

# ==================== Main ====================
async def main():
    logger.info("=" * 70)
    logger.info(f"🚀 شروع نسخه حرفه‌ای با ضد بن")
    logger.info(f"📱 {len(ALL_ACCOUNTS)} اکانت × {len(CHANNELS)} کانال")
    logger.info(f"🎭 {len(REACTIONS)} ریاکشن | احتمال: {int(REACTION_PROBABILITY*100)}%")
    logger.info(f"🛡️ حداکثر {MAX_OPERATIONS_PER_RUN} عملیات در هر اکانت")
    logger.info(f"⏱️ تأخیر بین کانال‌ها: {MIN_DELAY_BETWEEN_CHANNELS}-{MAX_DELAY_BETWEEN_CHANNELS}s")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    load_sessions_from_gist()

    shuffled = ALL_ACCOUNTS.copy()
    random.shuffle(shuffled)

    success = 0
    for idx, acc in enumerate(shuffled):
        logger.info(f"\n{'─'*50}")
        logger.info(f"📌 [{idx+1}/{len(shuffled)}] اکانت #{acc['index']} ({acc['label']})")
        logger.info(f"{'─'*50}")

        if await run_account(acc):
            success += 1

        if idx < len(shuffled) - 1:
            delay = random.randint(45, 120)
            logger.info(f"⏳ {delay}s تا اکانت بعدی...")
            await asyncio.sleep(delay)

    save_sessions_to_gist(ALL_ACCOUNTS)

    logger.info("\n" + "=" * 70)
    logger.info(f"🏁 {success}/{len(ALL_ACCOUNTS)} موفق")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ متوقف شد")
    except Exception as e:
        logger.error(f"💥 خطای بحرانی: {e}")
