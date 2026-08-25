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
from telethon.tl.functions.messages import GetMessagesViewsRequest
from telethon.tl.types import InputMessagePdu

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TGViewer")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
CHANNELS = [c.strip() for c in os.environ["CHANNELS"].split(",") if c.strip()]

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

# ========== Device Info تصادفی ==========
DEVICES = [
    "Samsung Galaxy S24", "Samsung Galaxy S23", "Samsung Galaxy S22",
    "Xiaomi 14", "Xiaomi 13 Pro", "Xiaomi Redmi Note 13",
    "iPhone 15 Pro Max", "iPhone 14 Pro", "iPhone 13",
    "OnePlus 12", "OnePlus 11", "OPPO Find X7",
    "Google Pixel 8 Pro", "Google Pixel 7", "Huawei P60 Pro",
    "POCO X6", "Realme GT 5", "Vivo X100",
]

SYSTEM_VERSIONS = [
    "Android 14", "Android 13", "Android 12",
    "iOS 17.4", "iOS 17.3", "iOS 17.2",
    "Android 14.0.1", "Android 13.0", "Android 12.0",
]

APP_VERSIONS = [
    "9.6.0", "9.5.0", "9.4.0", "9.3.0",
    "10.0.0", "10.1.0", "10.2.0",
    "8.9.0", "8.8.0", "9.0.0", "9.1.0",
]

LANG_CODES = ["en", "fa", "ar", "tr", "de", "fr", "es", "ru", "zh"]
# ========================================


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

logger.info(f"📱 {len(ALL_ACCOUNTS)} اکانت بارگذاری شد")


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


def random_sleep(min_sec=8, max_sec=20):
    duration = random.uniform(min_sec, max_sec)
    logger.debug(f"⏳ sleep {duration:.1f}s")
    return asyncio.sleep(duration)


async def mark_channel_messages(client, phone_label, channel):
    """سین کردن کانال و کلیک روی آخرین پست"""
    try:
        entity = await client.get_entity(channel)
        
        # ========== دریافت آخرین پیام‌ها ==========
        limit = random.randint(30, 150)
        msgs = await client.get_messages(entity, limit=limit)
        
        if not msgs:
            logger.info(f"  [{phone_label}] - {channel[:35]}... → هیچ پیامی نیست")
            return True
        
        last_msg = msgs[0]
        last_id = last_msg.id
        
        # ========== ۱. سین کردن (مارک به عنوان خوانده شده) ==========
        await client.send_read_acknowledge(entity, max_id=last_id)
        logger.info(f"  [{phone_label}] ✓ {channel[:35]}... → {len(msgs)} msg synced (to {last_id})")
        
        # ========== ۲. کلیک کردن روی آخرین پست (افزایش ویو) ==========
        try:
            # تأخیر تصادفی ۳ تا ۱۰ ثانیه قبل از کلیک (شبیه انسان)
            await random_sleep(3, 10)
            
            # روش ۱: افزایش ویو کانت با GetMessagesViewsRequest
            views_result = await client(GetMessagesViewsRequest(
                peer=entity,
                id=[last_id],
                increment=True
            ))
            
            # views_result لیستی از views_count برگردونده
            if views_result and len(views_result.views) > 0:
                new_views = views_result.views[0].views
                logger.info(f"  [{phone_label}] 👁️ کلیک روی پست {last_id} → ویو: {new_views}")
            
            # روش ۲: ارسال یک سیگنال "دیدم" اضافی (اختیاری)
            # این خط رو uncomment کنید اگه روش بالا کافی نیست:
            # await client.send_read_acknowledge(entity, max_id=last_id)
            
            # روش ۳: شبیه‌سازی باز کردن رسانه (اگه پست عکس/ویدیو داشت)
            if last_msg.media:
                # دانلود نمیکنیم، فقط درخواست اطلاعات رسانه میدیم = یه جورایی کلیک محسوب میشه
                try:
                    await client.get_messages(entity, ids=last_id)
                    logger.info(f"  [{phone_label}] 🖼️ رسانه پست {last_id} بازدید شد")
                except:
                    pass
            
        except FloodWaitError as e:
            logger.warning(f"  [{phone_label}] ⏳ FloodWait در کلیک: {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 60))
        except Exception as e:
            # بعضی کانال‌ها ممکنه اجازه ندن - نادیده میگیریم
            logger.debug(f"  [{phone_label}] ℹ️ کلیک ممکن نبود: {str(e)[:50]}")
        
        return True
        
    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.warning(f"  [{phone_label}] ❌ {channel[:30]} → دسترسی ندارد (جوین نیستید)")
        else:
            logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:60]}")
        return False
    except FloodWaitError as e:
        logger.warning(f"  [{phone_label}] ⏳ FloodWait: {e.seconds}s")
        await asyncio.sleep(min(e.seconds, 120))
        return False
    except Exception as e:
        logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:60]}")
        return False


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
        logger.info(f"[{label}] ✅ {me.first_name} (@{me.username or 'no username'})")
        
        await random_sleep(5, 15)
        
        for idx, channel in enumerate(CHANNELS):
            if idx > 0:
                await random_sleep(8, 25)
            
            await mark_channel_messages(client, label, channel)
        
        acc["session"] = client.session.save()
        await client.disconnect()
        
        logger.info(f"[{label}] 🏁 تمام شد ✅")
        return True
        
    except Exception as e:
        error_msg = str(e)[:100]
        logger.error(f"[{label}] ❌ خطا: {error_msg}")
        return False


async def main():
    logger.info("=" * 55)
    logger.info(f"🚀 شروع - {len(ALL_ACCOUNTS)} اکانت × {len(CHANNELS)} کانال")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 55)

    load_sessions_from_gist()

    shuffled = ALL_ACCOUNTS.copy()
    random.shuffle(shuffled)
    logger.info(f"🔀 ترتیب: {' - '.join([a['label'] for a in shuffled])}")

    success = 0
    for idx, acc in enumerate(shuffled):
        logger.info(f"\n--- {idx+1}/{len(shuffled)} [{acc['label']}] ---")
        
        if await run_account(acc):
            success += 1
        
        if idx < len(shuffled) - 1:
            delay = random.randint(20, 60)
            logger.info(f"⏳ {delay} ثانیه تا بعدی...")
            await asyncio.sleep(delay)

    save_sessions_to_gist(ALL_ACCOUNTS)
    
    logger.info("\n" + "=" * 55)
    logger.info(f"🏁 {success}/{len(ALL_ACCOUNTS)} موفق")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
