import os
import json
import asyncio
import logging
import random
import requests
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji, ReactionCustomEmoji

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TGViewer")

# ==================== Device Info تصادفی ====================
DEVICES = [
    "Samsung Galaxy S24", "Samsung Galaxy S23", "Samsung Galaxy S22",
    "Xiaomi 14", "Xiaomi 13 Pro", "Xiaomi Redmi Note 13",
    "iPhone 15 Pro Max", "iPhone 14 Pro", "iPhone 13",
    "OnePlus 12", "OnePlus 11", "OPPO Find X7",
    "Google Pixel 8 Pro", "Google Pixel 7", "Huawei P60 Pro",
    "POCO X6", "Realme GT 5", "Vivo X100",
    "Nothing Phone 2", "Asus ROG Phone 8",
]

SYSTEM_VERSIONS = [
    "Android 14", "Android 13", "Android 12",
    "iOS 17.4", "iOS 17.3", "iOS 17.2", "iOS 17.1",
    "Android 14.0.1", "Android 13.0", "Android 12.0",
]

APP_VERSIONS = [
    "9.6.0", "9.5.0", "9.4.0", "9.3.0",
    "10.0.0", "10.1.0", "10.2.0", "10.3.0",
    "8.9.0", "8.8.0", "9.0.0",
]

LANG_CODES = ["en", "fa", "ar", "tr", "de", "fr", "es", "ru"]
# =========================================================

# ==================== لیست ریاکشن‌ها ====================
REACTIONS = [
    "👍",  # لایک
    "❤️",  # قلب
    "🔥",  # فایر
    "😍",  # چشم‌قلقه
    "😂",  # خنده
    "😮",  # شگفت‌زده
    "😢",  # غمگین
    "👎",  # دیسلایک
    "🎉",  # جشن
]

# هر اکانت با احتمال مشخص یه ریاکشن میزنه (نه همیشه - طبیعی باشه)
REACTION_PROBABILITY = 0.8  # 80% احتمال
# =========================================================

# ==================== متغیرهای محیطی ====================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNELS = [c.strip() for c in os.environ["CHANNELS"].split(",") if c.strip()]

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

ALL_ACCOUNTS = []
for i in range(1, 11):
    session = os.environ.get(f"SESSION_{i}")
    phone = os.environ.get(f"PHONE_{i}")
    if session and phone:
        ALL_ACCOUNTS.append({
            "index": i,
            "phone": phone,
            "session": session,
            "label": phone[-4:]
        })

logger.info(f"📱 {len(ALL_ACCOUNTS)} اکانت")
logger.info(f"📡 {len(CHANNELS)} کانال")
logger.info(f"🎭 {len(REACTIONS)} ریاکشن مختلف")
# =========================================================


# ==================== Gist ====================
def load_sessions_from_gist():
    if not GIST_TOKEN or not GIST_ID:
        return
    try:
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        resp = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers, timeout=15)
        if resp.status_code != 200:
            return
        files = resp.json().get("files", {})
        if "sessions.json" not in files:
            return
        saved = json.loads(files["sessions.json"]["content"])
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
            json={"files": {"sessions.json": {"content": json.dumps(data, indent=2)}}},
            timeout=15
        )
        if resp.status_code == 200:
            logger.info(f"✅ {len(data)} سشن در Gist ذخیره شد")
    except:
        pass
# =========================================================


# ==================== Helper ====================
def random_sleep(min_sec=8, max_sec=20):
    duration = random.uniform(min_sec, max_sec)
    return asyncio.sleep(duration)
# =========================================================


# ==================== پردازش کانال ====================
async def process_channel(client, phone_label, channel):
    try:
        entity = await client.get_entity(channel)
        channel_name = getattr(entity, 'title', str(channel))[:30]
        
        limit = random.randint(30, 150)
        msgs = await client.get_messages(entity, limit=limit)
        
        if not msgs:
            logger.info(f"  [{phone_label}] - {channel_name} → خالی")
            return True
        
        last_msg = msgs[0]
        last_id = last_msg.id
        
        # ===== ۱. سین کردن =====
        await client.send_read_acknowledge(entity, max_id=last_id)
        logger.info(f"  [{phone_label}] ✓ {channel_name} → {len(msgs)} پیام سین شد (تا {last_id})")
        
        await random_sleep(4, 12)
        
        # ===== ۲. کلیک / ویو =====
        try:
            views_result = await client(GetMessagesViewsRequest(
                peer=entity,
                id=[last_id],
                increment=True
            ))
            if views_result and views_result.views:
                logger.info(f"  [{phone_label}] 👁️ ویو روی پست {last_id}")
            
            await random_sleep(3, 8)
            
        except FloodWaitError as e:
            logger.warning(f"  [{phone_label}] ⏳ FloodWait: {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 60))
        except Exception as e:
            logger.debug(f"  [{phone_label}] ℹ️ کلیک: {str(e)[:40]}")
        
        # ===== ۳. ریاکشن (واکنش) =====
        try:
            # با احتمال مشخص شده ریاکشن میزنه
            if random.random() < REACTION_PROBABILITY:
                # یه ریاکشن تصادفی انتخاب کن
                chosen_reaction = random.choice(REACTIONS)
                
                # تأخیر تصادفی قبل از ریاکشن (شبیه انسان)
                await random_sleep(5, 15)
                
                # ارسال ریاکشن
                await client(SendReactionRequest(
                    peer=entity,
                    msg_id=last_id,
                    reaction=[ReactionEmoji(emoticon=chosen_reaction)]
                ))
                
                logger.info(f"  [{phone_label}] 🎭 ریاکشن {chosen_reaction} روی پست {last_id}")
                
                # گاهی بعد از ریاکشن یه ویو دیگه (طبیعی‌تر)
                if random.random() < 0.15:
                    await random_sleep(3, 7)
                    await client(GetMessagesViewsRequest(
                        peer=entity,
                        id=[last_id],
                        increment=True
                    ))
                    logger.info(f"  [{phone_label}] 👁️ ویو اضافی بعد از ریاکشن")
            else:
                logger.info(f"  [{phone_label}] ℹ️ اینبار ریاکشن نزد (تصادفی)")
                
        except FloodWaitError as e:
            logger.warning(f"  [{phone_label}] ⏳ FloodWait ریاکشن: {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 60))
        except Exception as e:
            error_text = str(e)
            # بعضی کانال‌ها ریاکشن نمی‌پذیرن - عادیست
            if "REACTION_INVALID" in error_text:
                logger.info(f"  [{phone_label}] ℹ️ این کانال ریاکشن نمی‌پذیرد")
            else:
                logger.debug(f"  [{phone_label}] ℹ️ ریاکشن ممکن نبود: {error_text[:50]}")
        
        # ===== ۴. بازدید رسانه (اگه عکس/ویدیو داره) =====
        if last_msg.media and random.random() < 0.5:
            await random_sleep(5, 12)
            try:
                await client.get_messages(entity, ids=last_id)
                logger.info(f"  [{phone_label}] 🖼️ رسانه بازدید شد")
            except:
                pass
        
        # ===== ۵. گاهی یه پست قدیمی =====
        if len(msgs) > 3 and random.random() < 0.1:
            random_old = random.choice(msgs[1:min(4, len(msgs))])
            await random_sleep(15, 30)
            try:
                await client(GetMessagesViewsRequest(
                    peer=entity,
                    id=[random_old.id],
                    increment=True
                ))
                logger.info(f"  [{phone_label}] 👁️ ویو روی پست قدیمی {random_old.id}")
            except:
                pass
        
        return True
        
    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.warning(f"  [{phone_label}] ❌ {channel[:30]} → جوین نیستید")
        else:
            logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:50]}")
        return False
    except FloodWaitError as e:
        wait = e.seconds
        real_wait = min(wait, 120) + random.randint(5, 15)
        logger.warning(f"  [{phone_label}] ⏳ FloodWait {wait}s → sleep {real_wait}s")
        await asyncio.sleep(real_wait)
        return False
    except Exception as e:
        logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:50]}")
        return False
# =========================================================


# ==================== اجرای اکانت ====================
async def run_account(acc):
    try:
        phone = acc["phone"]
        label = acc["label"]
        
        device = random.choice(DEVICES)
        system = random.choice(SYSTEM_VERSIONS)
        app = random.choice(APP_VERSIONS)
        lang = random.choice(LANG_CODES)
        
        logger.info(f"[{label}] 📱 {device} | {system} | v{app}")
        
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH,
            device_model=device,
            system_version=system,
            app_version=app,
            lang_code=lang
        )
        
        await client.start()
        me = await client.get_me()
        logger.info(f"[{label}] ✅ {me.first_name} (@{me.username or '---'})")
        
        await random_sleep(5, 15)
        
        for idx, channel in enumerate(CHANNELS):
            if idx > 0:
                await random_sleep(10, 30)
            
            await process_channel(client, label, channel)
        
        acc["session"] = client.session.save()
        await client.disconnect()
        logger.info(f"[{label}] 🏁 تکمیل ✅")
        return True
        
    except Exception as e:
        logger.error(f"[{label}] ❌ خطا: {str(e)[:80]}")
        return False
# =========================================================


# ==================== Main ====================
async def main():
    logger.info("=" * 60)
    logger.info(f"🚀 شروع - {len(ALL_ACCOUNTS)} اکانت × {len(CHANNELS)} کانال")
    logger.info(f"🎭 {len(REACTIONS)} ریاکشن | احتمال: {int(REACTION_PROBABILITY*100)}%")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    load_sessions_from_gist()
    
    shuffled = ALL_ACCOUNTS.copy()
    random.shuffle(shuffled)
    
    success = 0
    for idx, acc in enumerate(shuffled):
        logger.info(f"\n{'─'*40}")
        logger.info(f"📌 [{idx+1}/{len(shuffled)}] اکانت #{acc['index']} ({acc['label']})")
        logger.info(f"{'─'*40}")
        
        if await run_account(acc):
            success += 1
        
        if idx < len(shuffled) - 1:
            delay = random.randint(30, 90)
            logger.info(f"⏳ {delay} ثانیه تا بعدی...")
            await asyncio.sleep(delay)
    
    save_sessions_to_gist(ALL_ACCOUNTS)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"🏁 {success}/{len(ALL_ACCOUNTS)} موفق")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ متوقف شد")
    except Exception as e:
        logger.error(f"💥 {e}")
