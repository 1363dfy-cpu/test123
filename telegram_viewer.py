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

# ================== Proxy Configuration (Auto-Discovery) ==================
# URL برای دریافت لیست پروکسی‌ها (می‌توانید تغییر دهید)
PROXY_API_URLS = [
    "https://proxy-list.org/english/api.php?demon=t", # رایگان
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5", # نمونه دیگر
]

# لیست اولیه پروکسی‌ها (اگر API کار نکرد)
INITIAL_PROXIES = [
    "socks5://user:pass@1.2.3.4:1080",
]

class ProxyManager:
    def __init__(self):
        self.proxies = [] # لیست نهایی و تست شده
        self.active_proxy = None
        self.lock = asyncio.Lock()
        
    async def fetch_proxies(self, url):
        """دریافت پروکسی از یک URL"""
        try:
            log.info(f"🌐 Fetching proxies from {url}...")
            # برخی API ها نیاز به User-Agent دارند
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.text.strip()
                # برخی API ها فرمت خط به خط دارند، برخی JSON
                if "json" in url or "{" in content:
                    try:
                        data = json.loads(content)
                        # فرض بر این است که آرایه‌ای از پروکسی‌هاست
                        proxies_found = [p for p in data if isinstance(p, str)]
                    except:
                        proxies_found = []
                else:
                    # فرمت متنی ساده (هر خط یک پروکسی)
                    proxies_found = content.split('\n')
                
                log.info(f"✅ Found {len(proxies_found)} raw proxies from API.")
                return proxies_found
            return []
        except Exception as e:
            log.warning(f"❌ Error fetching from {url}: {e}")
            return []

    async def test_proxy(self, proxy_str):
        """تست سرعت و دسترسی‌پذیری یک پروکسی"""
        try:
            # تبدیل به فرمت Telethon برای تست
            parsed = self.parse(proxy_str)
            if not parsed: return False
            
            # تست با درخواست به API خارجی (مثلاً httpbin یا ipify)
            # توجه: این تست باید سریع باشد
            url = "https://api.ipify.org?format=json"
            
            # استفاده از requests معمولی برای تست سریع
            session = requests.Session()
            proxy_dict = {
                "socks5": f"{proxy_str.replace('socks5://', '')}",
                "http": f"{proxy_str.replace('socks5://', '')}"
            }
            
            # شروع تایمر
            start_time = time.time()
            
            # انجام یک درخواست کوچک
            resp = await asyncio.to_thread(session.get, url, proxies={"http": proxy_dict["http"]}, timeout=5)
            
            elapsed = time.time() - start_time
            
            if resp.status_code == 200 and elapsed < 3.0: # اگر زیر 3 ثانیه بود قبول است
                log.debug(f"🟢 Proxy {proxy_str[:20]}... is FAST ({elapsed:.2f}s)")
                return True
            else:
                log.debug(f"🟡 Proxy {proxy_str[:20]}... is SLOW ({elapsed:.2f}s)")
                return True # هنوز هم قابل استفاده است ولی کندتر
                
        except Exception as e:
            # log.debug(f"🔴 Proxy {proxy_str[:20]}... FAILED: {e}")
            return False

    async def update_proxies(self):
        """به‌روزرسانی لیست پروکسی‌ها"""
        async with self.lock:
            log.info("🔄 Updating Proxy List...")
            
            # 1. دریافت از API
            new_raw_proxies = []
            for url in PROXY_API_URLS:
                found = await self.fetch_proxies(url)
                new_raw_proxies.extend(found)
            
            if not new_raw_proxies:
                log.warning("⚠️ No proxies fetched from API, using initial list.")
                new_raw_proxies = INITIAL_PROXIES

            # 2. تست و فیلتر کردن
            valid_proxies = []
            for p in new_raw_proxies[:50]: # تست حداکثر 50 تای اول برای سرعت
                if await self.test_proxy(p):
                    valid_proxies.append(p)
            
            # اگر لیست خالی بود، از اولیه استفاده کن
            if not valid_proxies:
                log.warning("⚠️ No fast proxies found, falling back to initial list.")
                valid_proxies = INITIAL_PROXIES
            
            self.proxies = valid_proxies
            log.info(f"✅ Active Proxy List Size: {len(self.proxies)}")

    def get_next_proxy(self):
        """انتخاب چرخشی پروکسی"""
        if not self.proxies:
            return None
        
        # انتخاب تصادفی برای جلوگیری از الگوی ثابت
        return random.choice(self.proxies)

    @staticmethod
    def parse(proxy_str):
        """پارس کردن رشته پروکسی"""
        try:
            clean_url = proxy_str.replace("socks5://", "").replace("http://", "")
            if "@" in clean_url:
                auth_part, host_port = clean_url.rsplit("@", 1)
                user_pass, ip_port = auth_part.split(":", 1) if ":" in auth_part else ("", "")
                ip, port = host_port.rsplit(":", 1)
                return ("socks5", ip, int(port), user_pass, "") # Telethon format: proto, host, port, user, password
            else:
                ip, port = clean_url.rsplit(":", 1)
                return ("socks5", ip, int(port))
        except Exception as e:
            return None

# ایجاد مدیریت پروکسی
proxy_manager = ProxyManager()

# ================== Accounts ==================
ALL_ACCOUNTS = []
for i in range(1, 6): 
    session = os.getenv(f"SESSION_{i}")
    phone = os.getenv(f"PHONE_{i}")
    
    # استفاده از پروکسی مدیریت شده
    acc_proxy_str = proxy_manager.get_next_proxy()
    acc_proxy = proxy_manager.parse(acc_proxy_str) if acc_proxy_str else None

    if not session or not phone:
        continue
            
    ALL_ACCOUNTS.append({
        "index": i,
        "phone": phone,
        "session": session,
        "proxy": acc_proxy,
        "label": phone[-4:],
    })

log.info(f"📱 Loaded {len(ALL_ACCOUNTS)} accounts | 🌐 Active Proxies: {len(proxy_manager.proxies)}")

# ================== Helpers ==================

async def rand_delay_short():
    await asyncio.sleep(random.uniform(1, 4))

def is_fresh(msg, hours=24):
    if not msg.date: return False
    now = datetime.utcnow()
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
    log.warning(f"FloodWait detected: {error.seconds}s. Sleeping...")
    await asyncio.sleep(error.seconds + 5)

# ================== Core Flow ==================

async def process_channel(client, label, channel, op_cnt):
    try:
        ent = await client.get_entity(channel)
        title = getattr(ent, "title", str(channel))[:30]
        
        msgs = await client.get_messages(ent, limit=30)
        fresh = [m for m in msgs if is_fresh(m)]
        
        if not fresh:
            return op_cnt

        select_count = max(1, int(len(fresh) * random.uniform(0.3, 0.7)))
        selected_msgs = random.sample(fresh, k=min(select_count, len(fresh)))
        
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
                except Exception: pass

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
                    await client(SendReactionRequest(peer=ent, msg_id=msg.id, reaction=[ReactionEmoji(emoticon=react)]))
                    op_cnt += 1
                except Exception: pass

            await rand_delay_short()

            # 4. Join/Leave Ads
            if msg.text:
                ad_links = extract_ad_links(msg.text)
                all_links = list(set(ad_links)) 
                
                if all_links and random.random() < 0.3:
                    link = all_links[0]
                    
                    await asyncio.sleep(JOIN_CLICK_DELAY) 
                    
                    try:
                        if "joinchat/" in link or "/+" in link:
                            hash_part = (
                                link.split("joinchat/")[1] if "joinchat/" in link
                                else link.split("/+")[1]
                            ).split()[0]
                            
                            invite = await client(ImportChatInviteRequest(hash_part))
                            joined_chat = invite.chat
                            
                            stay_duration = random.randint(JOIN_LEAVE_MIN_DELAY, JOIN_LEAVE_MAX_DELAY)
                            log.debug(f"  [{label}] 🔗 Joined {hash_part[:10]}... waiting {stay_duration}s")
                            
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
            if op_cnt >= MAX_OPERATIONS_PER_RUN: break
            
            if i > 0:
                delay = random.randint(MIN_DELAY_BETWEEN_CHANNELS, MAX_DELAY_BETWEEN_CHANNELS)
                log.info(f"  [{acc['label']}] ⏳ Waiting {delay}s...")
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

    # 1. کشف اولیه پروکسی‌ها
    await proxy_manager.update_proxies()

    random.shuffle(ALL_ACCOUNTS)
    success_count = 0

    for i, acc in enumerate(ALL_ACCOUNTS):
        log.info(f"\n{'='*40}\n📌 Account {i+1}/{len(ALL_ACCOUNTS)}: #{acc['index']}")
        
        if await run_account(acc):
            success_count += 1
        
        # خواب بین اکانت‌ها
        sleep_time = random.randint(90, 240) 
        log.info(f"⏳ Sleeping {sleep_time}s before next account...")
        await asyncio.sleep(sleep_time)

    log.info("\n" + "=" * 60)
    log.info(f"🏁 Done. Success: {success_count}/{len(ALL_ACCOUNTS)}")
    log.info("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("⛔ Stopped by user")
