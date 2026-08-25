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

# ==================== تنظیمات لاگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TGViewer")

# ==================== Device Info تصادفی (ضد بن) ====================
DEVICES = [
    "Samsung Galaxy S24", "Samsung Galaxy S23", "Samsung Galaxy S22",
    "Xiaomi 14", "Xiaomi 13 Pro", "Xiaomi Redmi Note 13",
    "iPhone 15 Pro Max", "iPhone 14 Pro", "iPhone 13",
    "OnePlus 12", "OnePlus 11", "OPPO Find X7",
    "Google Pixel 8 Pro", "Google Pixel 7", "Huawei P60 Pro",
    "POCO X6", "Realme GT 5", "Vivo X100",
    "Nothing Phone 2", "Asus ROG Phone 8", "Sony Xperia 1 VI",
]

SYSTEM_VERSIONS = [
    "Android 14", "Android 13", "Android 12",
    "iOS 17.4", "iOS 17.3", "iOS 17.2", "iOS 17.1",
    "Android 14.0.1", "Android 13.0", "Android 12.0",
    "iOS 18.0", "iOS 18.1",
]

APP_VERSIONS = [
    "9.6.0", "9.5.0", "9.4.0", "9.3.0", "9.2.0",
    "10.0.0", "10.1.0", "10.2.0", "10.3.0",
    "8.9.0", "8.8.0", "9.0.0", "9.1.0",
    "11.0.0", "11.1.0",
]

LANG_CODES = ["en", "fa", "ar", "tr", "de", "fr", "es", "ru", "zh", "pt", "hi", "id"]
# ===============================================================

# ==================== خواندن Environment Variables ====================
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
            "label": phone[-4:],
            "last_processed_msg": {}  # ذخیره آخرین پیام پردازش شده برای هر کانال
        })

logger.info(f"📱 {len(ALL_ACCOUNTS)} اکانت بارگذاری شد")
logger.info(f"📡 {len(CHANNELS)} کانال برای سین کردن")
# =======================================================================


# ==================== مدیریت Gist (ذخیره سشن) ====================
def load_sessions_from_gist():
    if not GIST_TOKEN or not GIST_ID:
        logger.info("ℹ️ Gist persistence غیرفعال است")
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
            phone = acc["phone"]
            if phone in saved and len(saved[phone]) > 50:
                acc["session"] = saved[phone]
                count += 1
        logger.info(f"✅ {count} سشن از Gist بارگذاری شد")
    except Exception as e:
        logger.warning(f"⚠️ Gist load: {e}")


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
    except Exception as e:
        logger.warning(f"⚠️ Gist save: {e}")
# ===============================================================


# ==================== Helper: خواب تصادفی ====================
def random_sleep(min_sec=8, max_sec=20):
    duration = random.uniform(min_sec, max_sec)
    return asyncio.sleep(duration)
# ===============================================================


# ==================== عملیات اصلی روی یک کانال ====================
async def process_channel(client, phone_label, channel):
    """
    ۱. سین کردن (مارک به عنوان خوانده شده)
    ۲. کلیک روی آخرین پست (افزایش ویو)
    ۳. کلیک روی ادز (اگه باشه)
    """
    try:
        entity = await client.get_entity(channel)
        channel_name = getattr(entity, 'title', str(channel))[:30]
        
        # ========== دریافت پیام‌ها (تعداد تصادفی) ==========
        limit = random.randint(30, 150)
        msgs = await client.get_messages(entity, limit=limit)
        
        if not msgs:
            logger.info(f"  [{phone_label}] - {channel_name} → هیچ پیامی نیست")
            return True
        
        last_msg = msgs[0]
        last_id = last_msg.id
        
        # ========== ۱. سین کردن ==========
        await client.send_read_acknowledge(entity, max_id=last_id)
        logger.info(f"  [{phone_label}] ✓ {channel_name} → {len(msgs)} پیام سین شد (تا {last_id})")
        
        # تأخیر تصادفی قبل از کلیک
        await random_sleep(4, 12)
        
        # ========== ۲. کلیک روی آخرین پست (افزایش ویو) ==========
        try:
            views_result = await client(GetMessagesViewsRequest(
                peer=entity,
                id=[last_id],
                increment=True
            ))
            
            if views_result and views_result.views:
                new_views = views_result.views[0].views
                logger.info(f"  [{phone_label}] 👁️ ویو +1 روی پست {last_id} → {new_views} بازدید")
            
            # تأخیر بعد از کلیک
            await random_sleep(2, 6)
            
            # ========== ۳. کلیک دوباره (شبیه باز کردن و بستن) ==========
            # بعضی از الگوریتم‌های ادز کلیک دوم رو هم حساب می‌کنن
            if random.random() < 0.3:  # ۳۰٪ احتمال کلیک دوم
                await client(GetMessagesViewsRequest(
                    peer=entity,
                    id=[last_id],
                    increment=True
                ))
                logger.info(f"  [{phone_label}] 👁️ کلیک دوم روی پست {last_id}")
                await random_sleep(3, 8)
            
        except FloodWaitError as e:
            wait = e.seconds
            logger.warning(f"  [{phone_label}] ⏳ FloodWait: {wait}s")
            await asyncio.sleep(min(wait, 60))
        except Exception as e:
            logger.debug(f"  [{phone_label}] ℹ️ کلیک ممکن نبود: {str(e)[:50]}")
        
        # ========== ۴. پردازش پست‌های اد ==========
        # پست‌های اد (Sponsored Messages) معمولاً به عنوان پیام‌های معمولی
        # میان ولی گاهی با فلگ‌های خاص مشخص می‌شن.
        # ما همه پیام‌ها رو چک می‌کنیم و بهشون ویو میدیم
        
        # اگر پست رسانه داشت (عکس/ویدیو) - شبیه بازدید رسانه
        if last_msg.media:
            await random_sleep(5, 15)
            try:
                # فقط درخواست اطلاعات = شبیه باز کردن رسانه
                await client.get_messages(entity, ids=last_id)
                logger.info(f"  [{phone_label}] 🖼️ رسانه پست {last_id} بازدید شد")
            except:
                pass
        
        # ========== ۵. پردازش پیام‌های قدیمی‌تر (اختیاری) ==========
        # برای طبیعی‌تر شدن، گاهی یه پیام قدیمی‌تر رو هم میبینیم
        if len(msgs) > 3 and random.random() < 0.15:  # ۱۵٪ احتمال
            random_old_msg = random.choice(msgs[1:min(5, len(msgs))])
            await random_sleep(10, 25)
            try:
                await client(GetMessagesViewsRequest(
                    peer=entity,
                    id=[random_old_msg.id],
                    increment=True
                ))
                logger.info(f"  [{phone_label}] 👁️ ویو روی پست قدیمی‌تر {random_old_msg.id}")
            except:
                pass
        
        return True
        
    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.warning(f"  [{phone_label}] ❌ {channel[:30]} → جوین نیستید")
        else:
            logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:60]}")
        return False
    except FloodWaitError as e:
        wait = e.seconds
        real_wait = min(wait, 120) + random.randint(5, 15)
        logger.warning(f"  [{phone_label}] ⏳ FloodWait {wait}s → sleep {real_wait}s")
        await asyncio.sleep(real_wait)
        return False
    except Exception as e:
        logger.error(f"  [{phone_label}] ❌ {channel[:30]} → {str(e)[:60]}")
        return False
# ===============================================================


# ==================== اجرای یک اکانت ====================
async def run_account(acc):
    try:
        phone = acc["phone"]
        label = acc["label"]
        
        # انتخاب تصادفی Device Info
        device = random.choice(DEVICES)
        system = random.choice(SYSTEM_VERSIONS)
        app = random.choice(APP_VERSIONS)
        lang = random.choice(LANG_CODES)
        
        logger.info(f"[{label}] 📱 {device} | {system} | v{app}")
        
        # ساخت کلاینت
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH,
            device_model=device,
            system_version=system,
            app_version=app,
            lang_code=lang
        )
        
        # اتصال
        await client.start()
        me = await client.get_me()
        logger.info(f"[{label}] ✅ {me.first_name} (@{me.username or 'بدون یوزرنیم'})")
        
        # تأخیر تصادفی قبل از شروع
        await random_sleep(5, 20)
        
        # پردازش کانال‌ها
        for idx, channel in enumerate(CHANNELS):
            if idx > 0:
                # تأخیر تصادفی بین کانال‌ها (۱۰ تا ۳۰ ثانیه)
                await random_sleep(10, 30)
            
            await process_channel(client, label, channel)
        
        # ذخیره سشن به‌روز شده
        acc["session"] = client.session.save()
        
        # قطع اتصال
        await client.disconnect()
        
        logger.info(f"[{label}] 🏁 تکمیل شد ✅")
        return True
        
    except Exception as e:
        error_msg = str(e)[:100]
        logger.error(f"[{label}] ❌ خطا: {error_msg}")
        
        if any(x in error_msg for x in ["AUTH_KEY_UNREGISTERED", "SESSION_EXPIRED"]):
            logger.warning(f"[{label}] ⚠️ سشن منقضی شده - نیاز به لاگین مجدد")
        
        return False
# ===============================================================


# ==================== تابع اصلی ====================
async def main():
    logger.info("=" * 60)
    logger.info(f"🚀 شروع اجرا - {len(ALL_ACCOUNTS)} اکانت × {len(CHANNELS)} کانال")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # بارگذاری سشن‌های ذخیره شده
    load_sessions_from_gist()
    
    # ترتیب تصادفی اکانت‌ها (ضد بن)
    shuffled = ALL_ACCOUNTS.copy()
    random.shuffle(shuffled)
    order_str = " → ".join([f"#{a['index']}({a['label']})" for a in shuffled])
    logger.info(f"🔀 ترتیب اجرا: {order_str}")
    
    success = 0
    fail = 0
    
    for idx, acc in enumerate(shuffled):
        logger.info(f"\n{'─'*40}")
        logger.info(f"📌 اکانت {idx+1}/{len(shuffled)} [{acc['label']}]")
        logger.info(f"{'─'*40}")
        
        if await run_account(acc):
            success += 1
        else:
            fail += 1
        
        # تأخیر تصادفی بین اکانت‌ها (۳۰ تا ۹۰ ثانیه)
        if idx < len(shuffled) - 1:
            delay = random.randint(30, 90)
            logger.info(f"⏳ {delay} ثانیه تا اکانت بعدی...")
            await asyncio.sleep(delay)
    
    # ذخیره سشن‌ها
    save_sessions_to_gist(ALL_ACCOUNTS)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"🏁 پایان اجرا: ✅ {success} موفق | ❌ {fail} ناموفق")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
# ===============================================================


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ توقف توسط کاربر")
    except Exception as e:
        logger.error(f"💥 خطای بحرانی: {e}")
