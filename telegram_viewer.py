import os
import json
import asyncio
import logging
import requests
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("TGViewer")

API_ID = int(os.environ["33821478"])
API_HASH = os.environ["9d81f8416d735de816b1ededcd51f9b8"]

# کانال‌ها با ویرگول جدا شدن
CHANNELS = [c.strip() for c in os.environ["https://t.me/Hesehkhoob1"].split(",") if c.strip()]

# Gist persistence
GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

# بارگذاری ۱۰ اکانت
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

logger.info(f"📱 تعداد اکانت‌های بارگذاری شده: {len(ALL_ACCOUNTS)}")
if len(ALL_ACCOUNTS) < 10:
    logger.warning(f"⚠️ فقط {len(ALL_ACCOUNTS)} اکانت از ۱۰ تنظیم شده")


def load_sessions_from_gist():
    """بارگذاری سشن‌های به‌روز از Gist"""
    if not GIST_TOKEN or not GIST_ID:
        logger.info("ℹ️ Gist persistence غیرفعال است (GIST_TOKEN یا GIST_ID تنظیم نشده)")
        return

    try:
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers,
            timeout=15
        )
        if resp.status_code != 200:
            logger.warning(f"Gist load failed: HTTP {resp.status_code}")
            return

        files = resp.json().get("files", {})
        if "sessions.json" not in files:
            logger.info("ℹ️ فایل sessions.json در Gist وجود ندارد")
            return

        saved = json.loads(files["sessions.json"]["content"])
        loaded_count = 0
        
        for acc in ALL_ACCOUNTS:
            phone = acc["phone"]
            if phone in saved and len(saved[phone]) > 50:
                acc["session"] = saved[phone]
                loaded_count += 1
        
        logger.info(f"✅ {loaded_count} سشن از Gist بارگذاری شد")
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ خطا در اتصال به Gist: {e}")
    except json.JSONDecodeError:
        logger.warning("⚠️ فرمت sessions.json در Gist نامعتبر است")
    except Exception as e:
        logger.warning(f"⚠️ خطای غیرمنتظره در Gist: {e}")


def save_sessions_to_gist(accounts):
    """ذخیره سشن‌های به‌روز در Gist"""
    if not GIST_TOKEN or not GIST_ID:
        return

    try:
        data = {acc["phone"]: acc["session"] for acc in accounts}
        headers = {"Authorization": f"token {GIST_TOKEN}"}
        
        payload = {
            "files": {
                "sessions.json": {
                    "content": json.dumps(data, indent=2, ensure_ascii=False)
                }
            }
        }
        
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers,
            json=payload,
            timeout=15
        )
        
        if resp.status_code == 200:
            logger.info(f"✅ {len(data)} سشن در Gist ذخیره شد")
        else:
            logger.warning(f"⚠️ ذخیره در Gist ناموفق: HTTP {resp.status_code}")
            
    except Exception as e:
        logger.warning(f"⚠️ خطا در ذخیره Gist: {e}")


async def mark_account_channels(client, phone_label):
    """یک اکانت تمام کانال‌ها رو سین می‌کنه"""
    success_count = 0
    fail_count = 0
    
    for idx, channel in enumerate(CHANNELS):
        try:
            entity = await client.get_entity(channel)
            messages = await client.get_messages(entity, limit=100)
            
            if messages:
                max_id = messages[0].id
                await client.send_read_acknowledge(entity, max_id=max_id)
                success_count += 1
                logger.info(f"  [{phone_label}] ✓ {channel[:40]}... → {len(messages)} msg (to {max_id})")
            else:
                logger.info(f"  [{phone_label}] - {channel[:40]}... → پیامی ندارد")
                success_count += 1
            
        except FloodWaitError as e:
            wait = e.seconds
            logger.warning(f"  [{phone_label}] ⏳ {channel[:30]}... rate limit → {wait}s sleep")
            await asyncio.sleep(min(wait, 60))
            fail_count += 1
            
        except ValueError as e:
            if "Cannot find any entity" in str(e):
                logger.warning(f"  [{phone_label}] ❌ {channel} → دسترسی ندارد (اکانت جوین نیست)")
                fail_count += 1
            else:
                logger.error(f"  [{phone_label}] ❌ {channel} → {e}")
                fail_count += 1
                
        except Exception as e:
            logger.error(f"  [{phone_label}] ❌ {channel[:30]}... → {str(e)[:80]}")
            fail_count += 1
        
        # تأخیر ۲-۵ ثانیه بین کانال‌ها (تصادفی برای طبیعی‌تر شدن)
        await asyncio.sleep(2 + (idx % 3))
    
    return success_count, fail_count


async def run_single_account(acc):
    """اجرای یک اکانت"""
    try:
        client = TelegramClient(
            StringSession(acc["session"]),
            API_ID,
            API_HASH
        )
        
        await client.start()
        me = await client.get_me()
        logger.info(f"[{acc['label']}] ✅ {me.first_name or me.username or 'Unknown'}")
        
        success, fail = await mark_account_channels(client, acc["label"])
        
        # ذخیره سشن به‌روز شده
        acc["session"] = client.session.save()
        
        await client.disconnect()
        
        logger.info(f"[{acc['label']}] 🏁 تمام شد: {success}✅ / {fail}❌")
        return True
        
    except Exception as e:
        error_msg = str(e)[:100]
        logger.error(f"[{acc['label']}] ❌ خطا: {error_msg}")
        
        # اگر خطای اعتبارسنجی بود سشن رو پاک می‌کنیم
        if "AUTH_KEY_UNREGISTERED" in error_msg or "SESSION_EXPIRED" in error_msg:
            logger.warning(f"[{acc['label']}] ⚠️ سشن منقضی شده - نیاز به لاگین مجدد")
        
        return False


async def main():
    logger.info("=" * 50)
    logger.info(f"🚀 شروع اجرا - {len(ALL_ACCOUNTS)} اکانت × {len(CHANNELS)} کانال")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    # بارگذاری سشن‌های ذخیره شده
    load_sessions_from_gist()
    
    total_success = 0
    total_fail = 0
    
    # اجرای ترتیبی اکانت‌ها (نه همزمان) برای کاهش ریسک بلاک
    for idx, acc in enumerate(ALL_ACCOUNTS):
        logger.info(f"\n--- اکانت {idx+1}/{len(ALL_ACCOUNTS)} [{acc['label']}] ---")
        
        result = await run_single_account(acc)
        
        if result:
            total_success += 1
        else:
            total_fail += 1
        
        # تأخیر ۵ ثانیه بین اکانت‌ها
        if idx < len(ALL_ACCOUNTS) - 1:
            logger.info(f"⏳ ۵ ثانیه صبر تا اکانت بعدی...")
            await asyncio.sleep(5)
    
    # ذخیره سشن‌ها در Gist
    save_sessions_to_gist(ALL_ACCOUNTS)
    
    logger.info("=" * 50)
    logger.info(f"🏁 پایان اجرا: {total_success} ✅ / {total_fail} ❌")
    logger.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
