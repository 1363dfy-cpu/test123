# bulk_sessions.py
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 123456  # عدد واقعی
API_HASH = "your_api_hash"

phones = [
    "+989127555787"
    "+989358724559",
    "+916392174223",
    "+15802586529",
  "+15803246727", 
    "+19183243567",
    "+17868476191",
    "+919622377209",
  "+919622580730",
    "+9647772201125"
]

for i, phone in enumerate(phones, 1):
    print(f"\n=== اکانت {i} - {phone} ===")
    client = TelegramClient(StringSession(), 33821478, 9d81f8416d735de816b1ededcd51f9b8)
    
    async def login():
        await client.start(phone=phone)
        me = await client.get_me()
        ss = client.session.save()
        print(f"SESSION_{i}={ss}")
        print(f"PHONE_{i}={phone}")
        await client.disconnect()
    
    with client:
        client.loop.run_until_complete(login())
    
    input("Enter بزنید برای اکانت بعدی...")
