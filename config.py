import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "6369714149").split(",")
    if value.strip().isdigit()
}

if not BOT_TOKEN:
    raise RuntimeError("Chua cau hinh BOT_TOKEN trong Railway Variables.")
