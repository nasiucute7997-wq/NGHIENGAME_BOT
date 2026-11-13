import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMINS = {int(x) for x in os.getenv("ADM_IDS", "").split(",") if x.strip().isdigit()}
ROOT_ADMINS = set(ADMINS)
DB = os.getenv("DB_PATH", "/data/bot.db")
if not TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
dp = Dispatcher()
pending = {}

GAMES = ["LLWIN", "XX8", "AD88", "U888", "ABC8", "MM88", "RR88", "XX88", "GG88"]

async def init_db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, balance INTEGER NOT NULL DEFAULT 0, blocked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, game TEXT DEFAULT '', name TEXT NOT NULL, price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, description TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER, category TEXT, product_name TEXT, game TEXT, account TEXT, price INTEGER, status TEXT DEFAULT 'processing', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS admin_staff(user_id INTEGER PRIMARY KEY, added_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        try:
            await db.execute("ALTER TABLE products ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass
        # Giá bán CODE GAME cố định 10.000đ cho tất cả site hiện tại và site tạo mới.
        await db.execute("UPDATE products SET price=10000 WHERE category='GAME'")
        # Xóa dữ liệu cũ trong MINIGAME LIVE đúng một lần; giữ nguyên thư mục chính.
        cur = await db.execute("SELECT value FROM settings WHERE key='migration:minigame_live_cleared_v1'")
        if not await cur.fetchone():
            await db.execute("DELETE FROM products WHERE category='MINIGAME LIVE'")
            await db.execute("DELETE FROM settings WHERE key='minigame_text' OR key LIKE 'folder_label:mini_%' OR key LIKE 'folder:mini_%'")
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('migration:minigame_live_cleared_v1','1')")
        cur = await db.execute("SELECT value FROM settings WHERE key='migration:minigame_live_products_v2'")
        if not await cur.fetchone():
            await db.execute("DELETE FROM products WHERE category='MINIGAME LIVE'")
            descriptions = {
                "XX8": "Nhận đủ 250 điểm theo combo.\n\n• Không nhận đủ điểm, liên hệ CSKH để kiểm tra và hoàn tiền.\n\n👤 NHẬP TÊN TÀI KHOẢN GAME CẦN MUA:\n• Mỗi dòng 01 tài khoản.\nVí dụ:\nabcxyz\nnguyenvana\ntaikhoan123\n\n⚠️ ĐIỀU KIỆN BẮT BUỘC:\n• Tài khoản phải có lịch sử nạp TRÊN 500.000Đ trong 07 ngày trước khi mua MINIGAME.\n• Trúng thưởng nhưng không đủ điều kiện nạp sẽ KHÔNG ĐƯỢC NHẬN THƯỞNG.\n\n❗ Vui lòng kiểm tra tài khoản và điều kiện trước khi đặt mua!",
                "88CLB": "Nhận đủ 174 điểm theo combo.\n\n• Không nhận đủ điểm, liên hệ CSKH để kiểm tra và hoàn tiền.\n\n👤 NHẬP TÊN TÀI KHOẢN GAME CẦN MUA:\n• Mỗi dòng 01 tài khoản.\nVí dụ:\nabcxyz\nnguyenvana\ntaikhoan123\n\n⚠️ ĐIỀU KIỆN BẮT BUỘC:\n• Tài khoản phải có lịch sử nạp TRÊN 500.000Đ trong 07 ngày trước khi mua MINIGAME.\n• Trúng thưởng nhưng không đủ điều kiện nạp sẽ KHÔNG ĐƯỢC NHẬN THƯỞNG.\n\n❗ Vui lòng kiểm tra tài khoản và điều kiện trước khi đặt mua!",
                "U888": "Nhận CODE ngẫu nhiên 118–288 điểm theo combo (khách hàng không được lựa chọn mức điểm).\n\n• Không nhận đủ điểm theo nội dung đơn hàng, liên hệ CSKH để kiểm tra và hoàn tiền.\n\n👤 NHẬP TÊN TÀI KHOẢN GAME CẦN MUA:\n• Mỗi dòng 01 tài khoản.\nVí dụ:\nabcxyz\nnguyenvana\ntaikhoan123\n\n⚠️ ĐIỀU KIỆN BẮT BUỘC:\n• Tài khoản phải có lịch sử nạp TRÊN 500.000Đ trong 07 ngày trước khi mua MINIGAME.\n• Trúng thưởng nhưng không đủ điều kiện nạp sẽ KHÔNG ĐƯỢC NHẬN THƯỞNG.\n\n❗ Vui lòng kiểm tra tài khoản và điều kiện trước khi đặt mua!"
            }
            for game_name, product_name, price in [
                ("XX8", "XX8 — GÓI 250 ĐIỂM", 65000),
                ("88CLB", "88CLB — GÓI 174 ĐIỂM", 60000),
                ("U888", "U888 — CODE NGẪU NHIÊN 118–288", 60000),
            ]:
                await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",
                                 ("MINIGAME LIVE", game_name, product_name, price, descriptions[game_name]))
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('migration:minigame_live_products_v2','1')")
        cur = await db.execute("SELECT value FROM settings WHERE key='migration:minigame_live_labels_v3'")
        if not await cur.fetchone():
            for game_name, label in [("XX8", "XX8 LIVE"), ("U888", "U888 LIVE"), ("88CLB", "88CLB LIVE")]:
                await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"folder_label:mini_{game_name}", label))
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('migration:minigame_live_labels_v3','1')")
        defaults = [
            ("SHARE","","SHARE QQ88",50000,"Chương trình CODE SHARE QQ88"),
            ("SHARE","","SHARE HI88",60000,"Chương trình CODE SHARE HI88"),
        ]
        for cat, game_name, name, price, desc in defaults:
            cur = await db.execute("SELECT id FROM products WHERE category=? AND game=? AND name=? LIMIT 1",(cat,game_name,name))
            if not await cur.fetchone():
                await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",(cat,game_name,name,price,desc))
        cur = await db.execute("SELECT key,value FROM settings WHERE key LIKE 'custom_site:%' ORDER BY key")
        for setting_key, site_name in await cur.fetchall():
            folder_key = setting_key.split(":", 1)[1]
            parent = "home_codegame" if folder_key.startswith("game_") else "home_mini" if folder_key.startswith("mini_") else None
            if not parent:
                continue
            if folder_key not in {item[0] for item in FOLDER_DEFS}:
                FOLDER_DEFS.append((folder_key, site_name, "Site game do Admin tạo"))
            if folder_key not in CHILD_FOLDER_KEYS.setdefault(parent, []):
                CHILD_FOLDER_KEYS[parent].append(folder_key)
        await db.commit()
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT user_id FROM admin_staff")
        ADMINS.update(int(row[0]) for row in await cur.fetchall())

def kb(rows):
    b = InlineKeyboardBuilder()
    for label, data in rows: b.button(text=label, callback_data=data)
    b.adjust(2)
    return b.as_markup()


def back():
    return kb([("⬅️ QUAY LẠI MENU", "m:home")])


FOLDER_DEFS = [
    ("home_code", "🚀 CODE", "Thư mục khách hàng"),
    ("home_codegame", "🎮 CODE GAME", "Danh mục CODE"),
    ("home_mini", "🎯 MINIGAME LIVE", "Danh mục CODE"),
    ("home_share", "🔗 CODE SHARE", "Danh mục CODE"),
    ("home_services", "🛠 DỊCH VỤ KHÁC", "Thư mục khách hàng"),
    ("home_account", "👤 TÀI KHOẢN", "Thư mục khách hàng"),
    ("home_deposit", "💳 NẠP TIỀN", "Thư mục khách hàng"),
    ("home_orders", "📋 LỊCH SỬ ĐƠN", "Thư mục khách hàng"),
    ("home_contact", "📞 LIÊN HỆ ADMIN", "Thư mục khách hàng"),
    ("home_houses", "🏦 HỆ THỐNG NHÀ CÁI", "Thư mục khách hàng"),
    ("mini_XX8", "XX8 LIVE", "Chi tiết Minigame"),
    ("mini_U888", "U888 LIVE", "Chi tiết Minigame"),
    ("mini_88CLB", "88CLB LIVE", "Chi tiết Minigame"),
    ("share_QQ88", "🔗 CODE SHARE QQ88", "Chi tiết CODE SHARE"),
    ("share_HI88", "🔗 CODE SHARE HI88", "Chi tiết CODE SHARE"),
    ("admin_add", "➕ THÊM SẢN PHẨM", "Thư mục quản trị"),
    ("admin_products", "📦 QUẢN LÝ SẢN PHẨM", "Thư mục quản trị"),
    ("admin_deposits", "💰 DUYỆT NẠP TIỀN", "Thư mục quản trị"),
    ("admin_orders", "🧾 QUẢN LÝ ĐƠN HÀNG", "Thư mục quản trị"),
    ("admin_payment", "🏦 CÀI ĐẶT THANH TOÁN", "Thư mục quản trị"),
    ("admin_notify", "📢 THÔNG BÁO THEO ID", "Thư mục quản trị"),
    ("admin_notifyall", "📣 THÔNG BÁO TẤT CẢ ID", "Thư mục quản trị"),
    ("admin_minitext", "✏️ NỘI DUNG MINIGAME", "Thư mục quản trị"),
    *[(f"game_{g}", f"🎮 GAME {g}", "Danh mục game") for g in GAMES],
    ("service_sms_receive", "📩 SMS NHẬN", "Danh mục dịch vụ"),
    ("service_sms_send", "📤 SMS GỬI", "Danh mục dịch vụ"),
    ("service_proxy", "🌐 PROXY / PRX", "Danh mục dịch vụ"),
]

async def folder_label(key, default):
    value = await setting(f"folder_label:{key}", "")
    return value or default

async def folder_is_on(key):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (f"folder:{key}",))
        row = await cur.fetchone()
    return row is None or row[0] != "0"

def kb2(rows):
    b = InlineKeyboardBuilder()
    for label, data in rows: b.button(text=label, callback_data=data)
    b.adjust(2)
    return b.as_markup()

async def home_kb(is_admin=False):
    b = InlineKeyboardBuilder()
    items = [
        ("home_code", "🚀 CODE", "m:code"),
        ("home_services", "🛠 DỊCH VỤ KHÁC", "m:services"),
        ("home_deposit", "💳 NẠP TIỀN", "m:deposit"),
        ("home_account", "👤 TÀI KHOẢN", "m:account"),
        ("home_orders", "📋 LỊCH SỬ ĐƠN", "m:orders"),
        ("home_contact", "📞 LIÊN HỆ ADMIN", "m:contact"),
    ]
    for key, label, data in items:
        if await folder_is_on(key):
            b.button(text=await folder_label(key, label), callback_data=data)
    b.button(text="🔄 LÀM MỚI MENU", callback_data="m:home")
    if is_admin:
        b.button(text="🛡 TRUNG TÂM QUẢN TRỊ", callback_data="m:admin")
    b.adjust(2)
    return b.as_markup()

async def admin_kb():
    b = InlineKeyboardBuilder()
    items = [
        ("admin_add","➕ THÊM SẢN PHẨM","a:add"),("admin_products","📦 QUẢN LÝ SẢN PHẨM","a:products"),
        ("admin_deposits","💰 DUYỆT NẠP TIỀN","a:deposits"),("admin_orders","🧾 QUẢN LÝ ĐƠN HÀNG","a:orders"),
        ("admin_payment","🏦 CÀI ĐẶT THANH TOÁN","a:payment"),("admin_notify","📢 THÔNG BÁO THEO ID","a:notify"),
        ("admin_notifyall","📣 THÔNG BÁO TẤT CẢ ID","a:notifyall"),("admin_minitext","✏️ NỘI DUNG MINIGAME","a:minitext")
    ]
    b.button(text="📊 TỔNG QUAN / DOANH THU", callback_data="am:stats")
    b.button(text="👥 QUẢN LÝ THÀNH VIÊN", callback_data="am:users")
    b.button(text="➕➖ CỘNG / TRỪ SỐ DƯ", callback_data="am:balance")
    b.button(text="🧑‍💼 NHÂN VIÊN / PHÂN QUYỀN", callback_data="am:staff")
    b.button(text="📜 LỊCH SỬ THAO TÁC", callback_data="am:logs")
    for key, label, data in items:
        if await folder_is_on(key):
            b.button(text=label, callback_data=data)
    b.button(text="⚙️ QUẢN LÝ THƯ MỤC / CÀI ĐẶT", callback_data="a:folders")
    b.button(text="🔄 LÀM MỚI MENU", callback_data="a:refresh")
    b.button(text="⬅️ MENU CHÍNH", callback_data="m:home")
    b.adjust(2)
    return b.as_markup()

CHILD_FOLDER_KEYS = {
    "home_code": ["home_codegame", "home_mini", "home_share"],
    "home_services": ["service_sms_receive", "service_sms_send", "service_proxy"],
    "home_codegame": [f"game_{g}" for g in GAMES],
    "home_mini": ["mini_XX8", "mini_U888", "mini_88CLB"],
    "home_share": ["share_QQ88", "share_HI88"],
}

async def folders_kb():
    # Menu gốc chỉ hiển thị đúng 2 nhóm lớn: CODE và DỊCH VỤ KHÁC.
    b = InlineKeyboardBuilder()
    for key, default_label in [
        ("home_code", "🚀 CODE"),
        ("home_services", "🛠 DỊCH VỤ KHÁC"),
    ]:
        if await folder_is_on(key):
            shown = await folder_label(key, default_label)
            b.button(text=shown[:64], callback_data=f"afchildren:{key}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:folders")
    b.button(text="⬅️ QUAY LẠI MENU ADMIN", callback_data="a:refresh")
    b.adjust(2)
    return b.as_markup()

async def child_folders_kb(parent):
    b = InlineKeyboardBuilder()
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    for key in CHILD_FOLDER_KEYS.get(parent, []):
        label = defs.get(key, key)
        enabled = await folder_is_on(key)
        shown = await folder_label(key, label)
        b.button(text=f"🎮 {shown}"[:64], callback_data=f"afselect:{key}")
    if parent == "home_codegame":
        b.button(text="➕ THÊM SITE GAME", callback_data="afaddcodesite")
    elif parent == "home_mini":
        b.button(text="➕ THÊM SITE GAME", callback_data="afaddminisite")
    b.button(text="🔄 TẢI LẠI", callback_data=f"afchildren:{parent}")
    b.button(text="⬅️ QUAY LẠI THƯ MỤC CHÍNH", callback_data="a:folders")
    b.adjust(1)
    return b.as_markup()

def admin_products_kb(rows):
    b = InlineKeyboardBuilder()
    for pid, category, game, name, price, active in rows:
        site = f"{category}/{game}" if game else category
        b.button(text=f"⚙️ THAO TÁC #{pid} · {site}"[:64], callback_data=f"apd:{pid}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:products")
    b.button(text="⬅️ MENU ADMIN", callback_data="a:refresh")
    b.adjust(2)
    return b.as_markup()

def product_detail_kb(pid, active):
    b = InlineKeyboardBuilder()
    b.button(text="✏️ SỬA TÊN", callback_data=f"apf:{pid}:name")
    b.button(text="📝 SỬA MÔ TẢ", callback_data=f"apf:{pid}:description")
    b.button(text="💵 SỬA GIÁ", callback_data=f"apf:{pid}:price")
    b.button(text=("🔴 TẮT SẢN PHẨM" if active else "🟢 BẬT SẢN PHẨM"), callback_data=f"at:{pid}")
    b.button(text="🗑 XÓA SẢN PHẨM", callback_data=f"apdel:{pid}")
    b.button(text="⬅️ DANH SÁCH SẢN PHẨM", callback_data="a:products")
    b.adjust(2,1,1,1,1)
    return b.as_markup()

async def show_product_detail(message, pid):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,category,game,name,description,price,active FROM products WHERE id=?",(pid,))
        row=await cur.fetchone()
    if not row:
        await message.edit_text("Không tìm thấy sản phẩm.",reply_markup=kb([("⬅️ DANH SÁCH SẢN PHẨM","a:products")]))
        return
    i,cat,game,name,description,price,active=row
    site=f"{cat}/{game}" if game else cat
    body=(f"📦 CHI TIẾT SẢN PHẨM #{i}\\nSite/danh mục: {site}\\nTên: {name}\\n"
          f"Mô tả: {description or 'Chưa có'}\\nGiá: {price:,}đ\\n"
          f"Trạng thái: {'BẬT' if active else 'TẮT'}\\nChọn thao tác:")
    await message.edit_text(body,reply_markup=product_detail_kb(i,active))

def admin_users_kb(rows):
    b = InlineKeyboardBuilder()
    for uid, name, balance, blocked in rows:
        label = f"{'🚫' if blocked else '👤'} {name or 'Thành viên'} · {balance:,}đ"[:60]
        b.button(text=label, callback_data=f"amu:{uid}")
    b.button(text="🔎 TÌM THÀNH VIÊN KHÁC", callback_data="am:users")
    b.button(text="⬅️ MENU QUẢN TRỊ", callback_data="a:refresh")
    b.adjust(2)
    return b.as_markup()

def admin_user_detail_kb(uid, blocked):
    b = InlineKeyboardBuilder()
    b.button(text="➕ CỘNG SỐ DƯ", callback_data=f"amb:{uid}:add")
    b.button(text="➖ TRỪ SỐ DƯ", callback_data=f"amb:{uid}:sub")
    b.button(text=("🔓 MỞ KHÓA TÀI KHOẢN" if blocked else "🚫 KHÓA TÀI KHOẢN"), callback_data=f"amlock:{uid}")
    b.button(text="⬅️ DANH SÁCH THÀNH VIÊN", callback_data="am:users")
    b.button(text="🏠 MENU QUẢN TRỊ", callback_data="a:refresh")
    b.adjust(2,1,1,1)
    return b.as_markup()

def admin_deposits_kb(rows):
    b = InlineKeyboardBuilder()
    for did, user_id, amount, status in rows:
        b.button(text=f"✅ DUYỆT NẠP #{did}", callback_data=f"adok:{did}")
        b.button(text=f"❌ TỪ CHỐI #{did}", callback_data=f"adno:{did}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:deposits")
    b.button(text="⬅️ MENU ADMIN", callback_data="a:refresh")
    b.adjust(2)
    return b.as_markup()

async def ensure_user(u):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(id,name) VALUES(?,?)",(u.id,u.full_name))
        await db.execute("UPDATE users SET name=? WHERE id=?",(u.full_name,u.id))
        await db.commit()

async def setting(key, default=""):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT value FROM settings WHERE key=?",(key,))
        row=await cur.fetchone()
        return row[0] if row else default

async def page_products(message, category, game=""):
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,name,price,description FROM products WHERE active=1 AND category=? AND (game=? OR game='') ORDER BY id",(category,game))
        rows=await cur.fetchall()
    back_to={"GAME":"m:codegame","MINIGAME LIVE":"m:mini","SHARE":"m:share","SMS":"m:services","PRX":"m:services"}.get(category,"m:home")
    if not rows:
        extra = ""
        if category == "MINIGAME LIVE":
            extra = "\\n\\n" + await setting("minigame_text","Admin chưa cập nhật chi tiết/thể lệ cho minigame này.")
        await message.edit_text("Hiện chưa có sản phẩm được mở bán hoặc Admin chưa cấu hình giá."+extra,reply_markup=kb([("⬅️ QUAY LẠI",back_to)])); return
    details = "\\n".join([f"• {name}: {desc}" for _,name,price,desc in rows if desc])
    body = "Chọn sản phẩm:" + (f"\\n\\n{details}" if details else "")
    await message.edit_text(body,reply_markup=kb2([(f"{n} — {p:,}đ",f"buy:{i}") for i,n,p,desc in rows]+[("⬅️ QUAY LẠI",back_to)]))

@dp.message(CommandStart())
async def start(m: Message):
    await ensure_user(m.from_user)
    if m.from_user.id not in ADMINS:
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT blocked FROM users WHERE id=?",(m.from_user.id,)); blocked=(await cur.fetchone())[0]
        if blocked:
            return await m.answer("🚫 Tài khoản của bạn hiện đang bị khóa. Vui lòng liên hệ Admin.")
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    weekdays = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    date_text = f"{weekdays[now.weekday()]}, ngày {now:%d/%m/%Y}"
    time_text = now.strftime("%H:%M:%S")
    welcome = (
        "🌟🎉 XIN CHÀO, 𖣸𝓑𝓮 𝓷𝓲 ༘ [ẩn]! 🎉🌟\n"
        "💎 CHÀO MỪNG ĐẾN VỚI NGHIỆN CODE 💎\n"
        f"📅 HÔM NAY: {date_text}\n"
        f"⏰ THỜI GIAN: {time_text} (GMT+7)\n\n"
        "🎮 CODE GAME HOT – MINIGAME LIVE\n"
        "⚡ GIAO DỊCH NHANH – TIỆN LỢI\n"
        "🤖 HỖ TRỢ TỰ ĐỘNG 24/7\n\n"
        "🚀 VUI LÒNG CHỌN DỊCH VỤ BÊN DƯỚI! 👇"
    )
    await m.answer(welcome,reply_markup=await home_kb(m.from_user.id in ADMINS))

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMINS: return await m.answer("Bạn không có quyền.")
    await m.answer("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=await admin_kb())

@dp.callback_query(F.data.startswith("m:"))
async def menus(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT blocked FROM users WHERE id=?",(c.from_user.id,)); row=await cur.fetchone()
        if row and row[0]:
            return await c.answer("Tài khoản đang bị khóa. Vui lòng liên hệ Admin.",show_alert=True)
    key=c.data.split(":")[1]
    if key=="home":
        return await c.message.edit_text("🏮 NGHIỆN CODE GAME 🏮\nChọn danh mục bên dưới:",reply_markup=await home_kb(c.from_user.id in ADMINS))
    if key=="admin":
        if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
        await c.message.edit_text("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=await admin_kb())
        return await c.answer()
    folder_map={"code":"home_code","services":"home_services","account":"home_account","deposit":"home_deposit","orders":"home_orders","contact":"home_contact","houses":"home_houses","codegame":"home_codegame","mini":"home_mini","share":"home_share"}
    if key in folder_map and not await folder_is_on(folder_map[key]):
        return await c.answer("Thư mục này hiện đang tắt.",show_alert=True)
    if key=="code":
        rows=[]
        if await folder_is_on("home_codegame"): rows.append((await folder_label("home_codegame","🎮 CODE GAME"),"m:codegame"))
        if await folder_is_on("home_mini"): rows.append((await folder_label("home_mini","🎯 MINIGAME LIVE"),"m:mini"))
        if await folder_is_on("home_share"): rows.append((await folder_label("home_share","🔗 CODE SHARE"),"m:share"))
        rows.append(("⬅️ MENU CHÍNH","m:home"))
        await c.message.edit_text((await folder_label("home_code","🚀 CODE"))+"\n\nChọn danh mục:",reply_markup=kb2(rows))
    elif key=="codegame":
        game_rows=[]
        for folder_key in CHILD_FOLDER_KEYS.get("home_codegame", []):
            if await folder_is_on(folder_key):
                game_name = folder_key[5:]
                game_rows.append((await folder_label(folder_key, game_name), f"game:{game_name}"))
        await c.message.edit_text((await folder_label("home_codegame","🎮 CODE GAME"))+"\\n\\nChọn game:",reply_markup=kb2(game_rows+[("⬅️ QUAY LẠI","m:code")]))
    elif key=="mini":
        mini_rows=[]
        for folder_key in CHILD_FOLDER_KEYS.get("home_mini", []):
            if await folder_is_on(folder_key):
                game_name = folder_key[5:]
                mini_rows.append((await folder_label(folder_key,f"{game_name} LIVE"),f"miniitem:{game_name}"))
        mini_rows.append(("⬅️ QUAY LẠI","m:code"))
        await c.message.edit_text(await folder_label("home_mini","🎯 MINIGAME LIVE"),reply_markup=kb2(mini_rows))
    elif key=="share":
        share_rows=[]
        if await folder_is_on("share_QQ88"):
            share_rows.append((await folder_label("share_QQ88","🔗 CODE SHARE QQ88"),"shareitem:QQ88"))
        if await folder_is_on("share_HI88"):
            share_rows.append((await folder_label("share_HI88","🔗 CODE SHARE HI88"),"shareitem:HI88"))
        share_rows.append(("⬅️ QUAY LẠI","m:code"))
        await c.message.edit_text((await folder_label("home_share","🔗 CODE SHARE"))+"\\n\\nChọn thư mục:",reply_markup=kb2(share_rows))
    elif key=="services":
        rows=[(await folder_label(folder,label),data) for folder,label,data in [("service_sms_receive","📩 SMS NHẬN","cat:SMS"),("service_sms_send","📤 SMS GỬI","cat:SMS"),("service_proxy","🌐 PROXY / PRX","cat:PRX")] if await folder_is_on(folder)]
        rows.append(("⬅️ QUAY LẠI","m:home"))
        await c.message.edit_text((await folder_label("home_services","🛠 DỊCH VỤ KHÁC"))+"\n\nChọn dịch vụ:",reply_markup=kb2(rows))
    elif key=="account":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT balance FROM users WHERE id=?",(c.from_user.id,)); row=await cur.fetchone()
        me=await c.bot.get_me()
        await c.message.edit_text(f"👤 TÀI KHOẢN\nTên: {c.from_user.full_name}\nID: {c.from_user.id}\nSố dư: {(row[0] if row else 0):,}đ\n\nLink chia sẻ: https://t.me/{me.username}?start=ref_{c.from_user.id}",reply_markup=kb([("🔄 LÀM MỚI","m:account"),("⬅️ MENU CHÍNH","m:home")]))
    elif key=="deposit":
        pending[c.from_user.id]="deposit"
        qr=await setting("qr_file_id")
        detail=await setting("payment_text","Admin chưa cài thông tin thanh toán.")
        text="💳 NẠP TIỀN\n"+detail+"\n\nNhập số tiền muốn nạp (VNĐ)."
        if qr:
            try: await c.message.answer_photo(qr,caption=text,reply_markup=kb([("⬅️ MENU CHÍNH","m:home")]))
            except Exception: await c.message.answer(text,reply_markup=kb([("⬅️ MENU CHÍNH","m:home")]))
        else: await c.message.answer(text,reply_markup=kb([("⬅️ MENU CHÍNH","m:home")]))
    elif key=="orders":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,product_name,price,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",(c.from_user.id,))
            rows=await cur.fetchall()
        text="📋 LỊCH SỬ ĐƠN\n"+("\n".join([f"#{i} | {n} | {p:,}đ | {s} | {t}" for i,n,p,s,t in rows]) if rows else "Chưa có đơn hàng.")
        await c.message.edit_text(text,reply_markup=kb([("🔄 LÀM MỚI","m:orders"),("⬅️ MENU CHÍNH","m:home")]))
    elif key=="contact":
        support=await setting("support_url","")
        b=InlineKeyboardBuilder()
        if support: b.button(text="💬 CSKH",url=support)
        b.button(text="⬅️ MENU CHÍNH",callback_data="m:home")
        b.adjust(1)
        await c.message.edit_text("📞 LIÊN HỆ ADMIN\\n\\n"+("Bấm CSKH để liên hệ hỗ trợ." if support else "Vui lòng liên hệ Admin để được hỗ trợ."),reply_markup=b.as_markup())
    elif key=="houses":
        b=InlineKeyboardBuilder()
        b.button(text="👥 NHÓM GIAO LƯU 1",url="https://t.me/xomkeofreegame")
        b.button(text="👥 NHÓM GIAO LƯU 2",url="https://t.me/Lienminhokvipnew")
        b.button(text="📚 TOÀN BỘ NHÓM",url="https://t.me/addlist/p53rAdejV1Q4MWJl")
        b.button(text="📢 TOÀN BỘ KÊNH",url="https://t.me/addlist/3hMdPUZtVvwyOTZl")
        b.button(text="⬅️ MENU CHÍNH",callback_data="m:home")
        b.adjust(2,2,1)
        await c.message.edit_text("🏦 HỆ THỐNG NHÀ CÁI\n\nCác liên kết cộng đồng:",reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("shareitem:"))
async def share_item(c: CallbackQuery):
    site = c.data.split(":",1)[1]
    if site not in {"QQ88","HI88"}:
        return await c.answer("Thư mục không hợp lệ.",show_alert=True)
    if not await folder_is_on(f"share_{site}"):
        return await c.answer("Thư mục CODE SHARE này hiện đang tắt.",show_alert=True)
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,name,price,description FROM products WHERE active=1 AND category='SHARE' AND (name LIKE ? OR game=?) ORDER BY id",(f"%{site}%",site))
        rows=await cur.fetchall()
    back_to="m:share"
    if not rows:
        await c.message.edit_text("Hiện chưa có sản phẩm đang mở bán cho "+site+".",reply_markup=kb2([("⬅️ QUAY LẠI",back_to)]))
    else:
        details = "\\n".join([f"• {name}: {desc}" for _,name,price,desc in rows if desc])
        body = "Chọn sản phẩm "+site+":" + (f"\\n\\n{details}" if details else "")
        await c.message.edit_text(body,reply_markup=kb2([(f"{name} — {price:,}đ",f"buy:{pid}") for pid,name,price,desc in rows]+[("⬅️ QUAY LẠI",back_to)]))
    await c.answer()

@dp.callback_query(F.data.startswith("miniitem:"))
async def minigame_item(c: CallbackQuery):
    game_name=c.data.split(":",1)[1]
    if f"mini_{game_name}" not in {item[0] for item in FOLDER_DEFS}:
        return await c.answer("Danh mục không hợp lệ.",show_alert=True)
    if not await folder_is_on(f"mini_{game_name}"):
        return await c.answer("Thư mục minigame này hiện đang tắt.",show_alert=True)
    await page_products(c.message,"MINIGAME LIVE",game_name)
    await c.answer()

@dp.callback_query(F.data.startswith("game:"))
async def game(c: CallbackQuery):
    selected=c.data.split(":")[1]
    if not await folder_is_on(f"game_{selected}"):
        return await c.answer("Danh mục game này hiện đang tắt.", show_alert=True)
    await page_products(c.message,"GAME",selected); await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def category(c: CallbackQuery):
    cat=c.data.split(":")[1]
    if cat=="SMS" and not (await folder_is_on("service_sms_receive") or await folder_is_on("service_sms_send")):
        return await c.answer("Danh mục SMS hiện đang tắt.", show_alert=True)
    if cat=="PRX" and not await folder_is_on("service_proxy"):
        return await c.answer("Danh mục PROXY hiện đang tắt.", show_alert=True)
    await page_products(c.message,cat); await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT blocked FROM users WHERE id=?",(c.from_user.id,)); row=await cur.fetchone()
        if row and row[0]:
            return await c.answer("Tài khoản đang bị khóa. Vui lòng liên hệ Admin.",show_alert=True)
    pid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT category,game,name,price FROM products WHERE id=? AND active=1",(pid,)); p=await cur.fetchone()
    if not p: return await c.answer("Sản phẩm không còn khả dụng.",show_alert=True)
    unit_price = 10000 if p[0] == "GAME" else p[3]
    pending[c.from_user.id]={"product_id":pid,"category":p[0],"game":p[1],"name":p[2],"unit_price":unit_price,"price":unit_price}
    prompt = "👤 NHẬP TÊN TÀI KHOẢN GAME CẦN MUA:"
    await c.message.answer(prompt,reply_markup=kb([("❌ HỦY ĐẶT HÀNG","buyact:cancel")]))
    await c.answer()


@dp.message(F.text)
async def capture_purchase_account(m: Message):
    task = pending.get(m.from_user.id)
    if m.from_user.id in ADMINS and isinstance(task, dict):
        raw = (m.text or "").strip()
        if task.get("admin_new_site_name"):
            if not raw or len(raw) > 40:
                return await m.answer("Tên SITE GAME không hợp lệ. Nhập từ 1–40 ký tự.")
            category = task.get("category")
            if category not in {"GAME", "MINIGAME LIVE"}:
                pending.pop(m.from_user.id, None)
                return await m.answer("Danh mục không hợp lệ. Vui lòng thao tác lại.")
            prefix = "game_" if category == "GAME" else "mini_"
            slug = hashlib.sha1(raw.casefold().encode("utf-8")).hexdigest()[:12]
            folder_key = prefix + slug
            if folder_key in {item[0] for item in FOLDER_DEFS}:
                pending.pop(m.from_user.id, None)
                return await m.answer("SITE GAME này đã tồn tại hoặc trùng tên.")
            task.update({"new_site_key": folder_key, "new_site_name": raw, "draft_kind": "new_site"})
            pending[m.from_user.id] = task
            return await m.answer(f"📋 XÁC NHẬN TẠO SITE GAME\\n\\nDanh mục: {category}\\nTên SITE: {raw}\\n\\nBạn xác nhận tạo thư mục này?", reply_markup=kb([("✅ XÁC NHẬN TẠO", "afsiteconfirm:yes"), ("❌ HỦY", "afsiteconfirm:no")]))
        if "folder_label_edit" in task:
            if not raw or len(raw) > 60:
                return await m.answer("Tên hiển thị không hợp lệ. Nhập tối đa 60 ký tự.")
            task["draft_value"] = raw
            task["draft_kind"] = "folder_label"
            pending[m.from_user.id] = task
            return await m.answer(
                f"📋 XÁC NHẬN ĐỔI TÊN THƯ MỤC\\n\\nTên mới: {raw}\\n\\nLưu thay đổi này?",
                reply_markup=kb([("✅ XÁC NHẬN LƯU", "cfgconfirm:yes"), ("❌ HỦY", "cfgconfirm:no")])
            )
        if task.get("admin_product_field") in {"name", "description", "price"} and task.get("config_return"):
            field = task["admin_product_field"]
            if field == "name":
                value = raw
                if not value or len(value) > 100:
                    return await m.answer("Tên sản phẩm không hợp lệ. Nhập từ 1–100 ký tự.")
                preview = value
            elif field == "price":
                digits = raw.replace(",", "").replace(".", "").replace("đ", "").replace(" ", "")
                if not digits.isdigit() or int(digits) <= 0:
                    return await m.answer("Giá không hợp lệ. Vui lòng nhập số tiền VNĐ lớn hơn 0.")
                value = int(digits)
                preview = f"{value:,}đ"
            else:
                value = "" if raw == "-" else raw
                if len(value) > 1000:
                    return await m.answer("Nội dung quá dài. Tối đa 1000 ký tự.")
                preview = value or "Đã xóa nội dung"
            task["draft_value"] = value
            task["draft_kind"] = "product_field"
            pending[m.from_user.id] = task
            return await m.answer(
                f"📋 XÁC NHẬN CẬP NHẬT {({'name':'TÊN SẢN PHẨM','price':'GIÁ','description':'NỘI DUNG'}[field])}\\n\\nGiá trị mới: {preview}\\n\\nBạn xác nhận lưu mục này?",
                reply_markup=kb([("✅ XÁC NHẬN LƯU", "cfgconfirm:yes"), ("❌ HỦY", "cfgconfirm:no")])
            )
    if not isinstance(task, dict) or "product_id" not in task or task.get("purchase_confirm"):
        return
    account = m.text.strip()
    if task.get("category") == "MINIGAME LIVE":
        accounts = [line.strip() for line in account.splitlines() if line.strip()]
        if not accounts or len(accounts) > 100 or any(len(x) > 100 for x in accounts):
            return await m.answer("Danh sách tài khoản không hợp lệ. Mỗi dòng nhập 01 tài khoản (tối đa 100 tài khoản).")
        account = "\\n".join(accounts)
        task["quantity"] = len(accounts)
        task["price"] = task["unit_price"] * len(accounts)
    elif not account or len(account) > 100:
        return await m.answer("Tên tài khoản không hợp lệ. Vui lòng nhập lại (tối đa 100 ký tự).")
    task["account"] = account
    task["purchase_confirm"] = True
    pending[m.from_user.id] = task
    site = task.get("game") or task.get("category") or "CODE GAME"
    await m.answer(
        "📋 XÁC NHẬN ĐƠN HÀNG\\n\\n"
        "━━━━━━━━━━━━━━━━━━\\n"
        f"🎮 SITE GAME: {site}\\n"
        f"📦 SẢN PHẨM: {task['name']}\\n"
        f"👤 TÊN TÀI KHOẢN: {account}\\n\\n"
        f"💰 TỔNG TIỀN CẦN THANH TOÁN: {task['price']:,}đ\\n"
        + (f"📦 SỐ TÀI KHOẢN: {task.get('quantity',1)}\\n💵 ĐƠN GIÁ: {task['unit_price']:,}đ\\n" if task.get("category")=="MINIGAME LIVE" else "")
        + "━━━━━━━━━━━━━━━━━━\\n\\n"
        "⚠️ VUI LÒNG KIỂM TRA KỸ THÔNG TIN ĐƠN HÀNG TRƯỚC KHI TIẾP TỤC.\\n\\n"
        "🔴 KHI NHẤN XÁC NHẬN THANH TOÁN:\\n"
        "✅ Hệ thống kiểm tra số dư ví bot. Chỉ khi đủ tiền mới trừ tiền và tạo đơn hàng.\\n"
        "✅ Sau khi thanh toán thành công, hệ thống thông báo mã đơn hàng.\\n\\n"
        "❗ Nếu thông tin chưa chính xác, vui lòng chọn QUAY LẠI để chỉnh sửa.\\n"
        "━━━━━━━━━━━━━━━━━━",
        reply_markup=kb([
            ("✅ XÁC NHẬN THANH TOÁN", "buyact:confirm"),
            ("✏️ QUAY LẠI CHỈNH SỬA", "buyact:back"),
            ("❌ HỦY ĐƠN HÀNG", "buyact:cancel")
        ])
    )


@dp.callback_query(F.data.startswith("buyact:"))
async def purchase_action(c: CallbackQuery):
    action=c.data.split(":",1)[1]
    task=pending.get(c.from_user.id)
    if action=="cancel":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("❌ Đã hủy thao tác mua hàng.",reply_markup=kb([("🏠 MENU CHÍNH","m:home")]))
        return await c.answer("Đã hủy.")
    if action=="back":
        if not isinstance(task,dict) or not task.get("product_id"):
            return await c.answer("Phiên mua hàng đã hết. Vui lòng chọn lại sản phẩm.",show_alert=True)
        task.pop("purchase_confirm",None)
        pending[c.from_user.id]=task
        await c.message.edit_text(
            "✏️ CHỈNH SỬA THÔNG TIN ĐƠN HÀNG\\nVui lòng nhập lại tên tài khoản cần mua. Nếu không yêu cầu tài khoản, nhập dấu -.",
            reply_markup=kb([("❌ HỦY ĐƠN HÀNG","buyact:cancel")])
        )
        return await c.answer("Vui lòng nhập lại thông tin.")
    if action!="confirm" or not isinstance(task,dict) or not task.get("purchase_confirm"):
        return await c.answer("Phiên mua hàng đã hết. Vui lòng chọn lại sản phẩm.",show_alert=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur=await db.execute("SELECT active FROM products WHERE id=?",(task["product_id"],))
        product=await cur.fetchone()
        cur=await db.execute("SELECT balance FROM users WHERE id=?",(c.from_user.id,))
        user=await cur.fetchone()
        balance=user[0] if user else 0
        if not product or not product[0]:
            await db.rollback()
            pending.pop(c.from_user.id,None)
            return await c.message.edit_text("Sản phẩm đã tắt hoặc không còn khả dụng.",reply_markup=kb([("⬅️ MENU CHÍNH","m:home")]))
        if balance<task["price"]:
            await db.rollback()
            return await c.answer(f"Số dư không đủ. Hiện có {balance:,}đ, cần {task['price']:,}đ.",show_alert=True)
        await db.execute("UPDATE users SET balance=balance-? WHERE id=?",(task["price"],c.from_user.id))
        cur=await db.execute("INSERT INTO orders(user_id,product_id,category,product_name,game,account,price) VALUES(?,?,?,?,?,?,?)",(c.from_user.id,task["product_id"],task["category"],task["name"],task["game"],task["account"],task["price"]))
        oid=cur.lastrowid
        await db.commit()
    pending.pop(c.from_user.id,None)
    await c.message.edit_text(f"✅ THANH TOÁN HOÀN TẤT\n\nMã đơn: #{oid}\nSản phẩm: {task['name']}\nTài khoản: {task['account']}\nĐã thanh toán: {task['price']:,}đ\nTrạng thái đơn: ĐANG XỬ LÝ",reply_markup=kb([("📋 LỊCH SỬ ĐƠN","m:orders"),("🏠 MENU CHÍNH","m:home")]))
    for aid in ADMINS:
        try: await c.bot.send_message(aid,f"ĐƠN #{oid}\nUser {c.from_user.id}\n{task['name']}\nTK: {task['account']}\n{task['price']:,}đ")
        except Exception: pass
    await c.answer("Thanh toán hoàn tất.")

async def folder_config_products(key):
    if key.startswith("game_"):
        return ("GAME", key[5:])
    if key.startswith("mini_"):
        return ("MINIGAME LIVE", key[5:])
    if key.startswith("share_"):
        return ("SHARE", key[6:])
    if key == "home_codegame":
        return ("GAME", None)
    if key == "home_mini":
        return ("MINIGAME LIVE", None)
    if key == "home_share":
        return ("SHARE", None)
    if key in {"service_sms_receive", "service_sms_send"}:
        return ("SMS", None)
    if key == "service_proxy":
        return ("PRX", None)
    return (None, None)

async def folder_config_kb(key):
    b = InlineKeyboardBuilder()
    category, game = await folder_config_products(key)
    if category:
        b.button(text="✏️ TÊN SITE / THƯ MỤC", callback_data=f"cfgsite:{key}")
        b.button(text="📦 TÊN SẢN PHẨM", callback_data=f"cfgfield:name:{key}")
        b.button(text="📝 NỘI DUNG / MÔ TẢ", callback_data=f"cfgfield:description:{key}")
        b.button(text="💵 GIÁ BÁN", callback_data=f"cfgfield:price:{key}")
    else:
        b.button(text="✏️ ĐỔI TÊN HIỂN THỊ", callback_data=f"cfgsite:{key}")
    parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), None)
    back_callback = f"afchildren:{parent}" if parent else "a:folders"
    b.button(text="⬅️ QUAY LẠI THƯ MỤC", callback_data=back_callback)
    b.adjust(2)
    return b.as_markup()

@dp.callback_query(F.data.startswith("afsiteconfirm:"))
async def admin_add_site_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    task = pending.get(c.from_user.id)
    action = c.data.split(":", 1)[1]
    if not isinstance(task, dict) or task.get("draft_kind") != "new_site" or action not in {"yes", "no"}:
        return await c.answer("Phiên tạo SITE GAME đã hết hạn.", show_alert=True)
    if action == "yes":
        key, name, category = task["new_site_key"], task["new_site_name"], task["category"]
        parent = "home_codegame" if category == "GAME" else "home_mini"
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"custom_site:{key}", name))
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"folder_label:{key}", name))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)", (c.from_user.id, f"create site {category}/{name}"))
            await db.commit()
        if key not in {item[0] for item in FOLDER_DEFS}:
            FOLDER_DEFS.append((key, name, "Site game do Admin tạo"))
        if key not in CHILD_FOLDER_KEYS.setdefault(parent, []):
            CHILD_FOLDER_KEYS[parent].append(key)
        result = f"✅ ĐÃ TẠO SITE GAME\\n\\nDanh mục: {category}\\nTên SITE: {name}\\n\\nBạn có thể vào Quản lý thư mục để bật/tắt, đổi tên và thêm sản phẩm."
    else:
        result = "❌ Đã hủy. Không tạo SITE GAME mới."
    pending.pop(c.from_user.id, None)
    await c.message.edit_text(result, reply_markup=kb([("⚙️ QUẢN LÝ THƯ MỤC", "a:folders"), ("⬅️ MENU QUẢN TRỊ", "a:refresh")]))
    await c.answer("Đã lưu." if action == "yes" else "Đã hủy.")

@dp.callback_query(F.data.startswith("afchildren:"))
async def admin_child_folders(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    parent = c.data.split(":",1)[1]
    if parent not in CHILD_FOLDER_KEYS:
        return await c.answer("Thư mục chính không hợp lệ.", show_alert=True)
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    title = await folder_label(parent, defs.get(parent, parent))
    await c.message.edit_text(f"⚙️ QUẢN LÝ THƯ MỤC\\n{title}\\n\\nChọn một mục trong danh sách:", reply_markup=await child_folders_kb(parent))
    await c.answer()

@dp.callback_query(F.data.startswith("afselect:"))
async def admin_select_folder_for_config(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    if key not in defs:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    category, game = await folder_config_products(key)
    title = await folder_label(key, defs[key])
    if key in {"home_codegame", "home_mini", "home_share"}:
        await c.message.edit_text(
            f"📂 {title}\\n\\nChọn một game/site trong danh sách. Sau khi chọn mới hiển thị các thao tác chỉnh sửa:",
            reply_markup=await child_folders_kb(key)
        )
        await c.answer()
        return
    if category:
        async with aiosqlite.connect(DB) as db:
            if key.startswith("game_") or key.startswith("mini_"):
                cur = await db.execute("SELECT id,name,price,active FROM products WHERE category=? AND game=? ORDER BY id", (category, game))
            elif key.startswith("share_"):
                cur = await db.execute("SELECT id,name,price,active FROM products WHERE category=? AND name LIKE ? ORDER BY id", (category, f"%{game}%"))
            else:
                cur = await db.execute("SELECT id,name,price,active FROM products WHERE category=? ORDER BY id", (category,))
            products = await cur.fetchall()
        buttons = [(f"📦 {name} · {price:,}đ {'🟢' if active else '🔴'}", f"afproduct:{pid}:{key}") for pid,name,price,active in products]
        if key.startswith("mini_") or key.startswith("game_"):
            buttons.append(("➕ THÊM SẢN PHẨM", f"afaddsiteproduct:{key}"))
        if not products:
            buttons.append(("⚙️ CÀI ĐẶT TÊN THƯ MỤC", f"afe:{key}"))
        parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), "home_code")
        buttons.append(("⬅️ DANH SÁCH THƯ MỤC", f"afchildren:{parent}"))
        await c.message.edit_text(f"📂 {title}\\n\\nDanh sách sản phẩm/site đã có. Chọn mục cần chỉnh sửa:", reply_markup=kb2(buttons))
    else:
        await c.message.edit_text(f"⚙️ CÀI ĐẶT {title}\\nChọn nội dung cần chỉnh sửa:", reply_markup=await folder_config_kb(key))
    await c.answer()

@dp.callback_query(F.data == "afaddcodesite")
async def admin_add_codegame_site_start(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    pending[c.from_user.id] = {"admin_new_site_name": True, "category": "GAME"}
    await c.message.edit_text(
        "➕ THÊM SITE GAME MỚI\\nDanh mục: 🎮 CODE GAME\\n\\nNhập tên SITE GAME mới:",
        reply_markup=kb([("⬅️ QUAY LẠI CODE GAME", "afchildren:home_codegame")])
    )
    await c.answer()

@dp.callback_query(F.data == "afaddminisite")
async def admin_add_minigame_site_start(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    pending[c.from_user.id] = {"admin_new_site_name": True, "category": "MINIGAME LIVE"}
    await c.message.edit_text(
        "➕ THÊM SITE GAME MỚI\nDanh mục: 🎯 MINIGAME LIVE\n\nNhập tên SITE GAME mới:",
        reply_markup=kb([("⬅️ QUAY LẠI MINIGAME LIVE", "afchildren:home_mini")])
    )
    await c.answer()

@dp.callback_query(F.data == "afaddsite")
async def admin_add_site_start(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    await c.message.edit_text("➕ THÊM SITE GAME MỚI\\n\\nChọn thư mục muốn tạo site:", reply_markup=kb([
        ("🎮 CODE GAME", "afsitecat:GAME"), ("🎯 MINIGAME LIVE", "afsitecat:MINIGAME LIVE"), ("⬅️ QUẢN LÝ THƯ MỤC", "a:folders")
    ]))
    await c.answer()

@dp.callback_query(F.data.startswith("afsitecat:"))
async def admin_add_site_choose_category(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    category = c.data.split(":", 1)[1]
    if category not in {"GAME", "MINIGAME LIVE"}:
        return await c.answer("Danh mục không hợp lệ.", show_alert=True)
    pending[c.from_user.id] = {"admin_new_site_name": True, "category": category}
    await c.message.edit_text(f"➕ THÊM SITE GAME\\nDanh mục: {category}\\n\\nNhập tên SITE GAME mới:", reply_markup=kb([("⬅️ HỦY", "a:folders")]))
    await c.answer()

@dp.callback_query(F.data.startswith("afaddsiteproduct:"))
async def admin_add_product_from_site(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":", 1)[1]
    if key not in {item[0] for item in FOLDER_DEFS} or not (key.startswith("game_") or key.startswith("mini_")):
        return await c.answer("SITE GAME không hợp lệ.", show_alert=True)
    category, game_name = await folder_config_products(key)
    if not category or not game_name:
        return await c.answer("Không xác định được SITE GAME.", show_alert=True)
    pending[c.from_user.id] = {"add_stage": "name", "category": category, "game": game_name}
    await c.message.edit_text(f"➕ THÊM SẢN PHẨM\\nDanh mục: {category}\\nGame/site: {game_name}\\nNhập tên sản phẩm:", reply_markup=kb([("⬅️ QUAY LẠI SITE", f"afselect:{key}")]))
    await c.answer()

@dp.callback_query(F.data.startswith("afproduct:"))
async def admin_select_folder_product(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    _, raw_pid, key = c.data.split(":",2)
    pid = int(raw_pid)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT name,description,price,active FROM products WHERE id=?", (pid,))
        row = await cur.fetchone()
    if not row:
        return await c.answer("Không tìm thấy sản phẩm.", show_alert=True)
    name, description, price, active = row
    buttons = [
        (f"✏️ SỬA TÊN: {name}"[:60], f"apf:{pid}:name"),
        ("📝 SỬA NỘI DUNG / MÔ TẢ", f"apf:{pid}:description"),
        (f"💵 SỬA GIÁ: {price:,}đ", f"apf:{pid}:price"),
        (("🔴 TẮT SẢN PHẨM" if active else "🟢 BẬT SẢN PHẨM"), f"at:{pid}"),
        ("⬅️ DANH SÁCH SITE / SẢN PHẨM", f"afselect:{key}")
    ]
    await c.message.edit_text(f"📦 CHI TIẾT SẢN PHẨM\\nTên: {name}\\nNội dung: {description or 'Chưa có'}\\nGiá: {price:,}đ\\nTrạng thái: {'ĐANG BẬT' if active else 'ĐANG TẮT'}\\n\\nChọn chi tiết cần chỉnh sửa:", reply_markup=kb2(buttons))
    await c.answer()

@dp.callback_query(F.data.startswith("afe:"))
async def admin_edit_folder_name(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    if key not in defs:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    await c.message.edit_text(
        f"⚙️ CÀI ĐẶT THƯ MỤC\\n{await folder_label(key, defs[key])}\\n\\nChọn nội dung cần chỉnh sửa:",
        reply_markup=await folder_config_kb(key)
    )
    await c.answer()

@dp.callback_query(F.data.startswith("cfgsite:"))
async def admin_config_site(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    if key not in defs:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    current = await folder_label(key, defs[key])
    pending[c.from_user.id] = {"folder_label_edit": key, "config_return": key}
    await c.message.edit_text(
        f"🎮 CÀI ĐẶT SITE GAME\\nTên hiện tại: {current}\\n\\nNhập tên SITE GAME mới:",
        reply_markup=kb([("⬅️ QUAY LẠI CÀI ĐẶT",f"cfgback:{key}")])
    )
    await c.answer()

@dp.callback_query(F.data.startswith("cfgback:"))
async def admin_config_back(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    if key not in defs:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    pending.pop(c.from_user.id, None)
    await c.message.edit_text(f"⚙️ CÀI ĐẶT THƯ MỤC\\n{await folder_label(key, defs[key])}\\n\\nChọn nội dung cần chỉnh sửa:", reply_markup=await folder_config_kb(key))
    await c.answer()

@dp.callback_query(F.data.startswith("cfgfield:"))
async def admin_config_product_field(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    _, field, key = c.data.split(":",2)
    if field not in {"name","description","price"}:
        return await c.answer("Mục chỉnh sửa không hợp lệ.", show_alert=True)
    category, game = await folder_config_products(key)
    if not category:
        return await c.answer("Thư mục này không có sản phẩm để chỉnh sửa.", show_alert=True)
    async with aiosqlite.connect(DB) as db:
        if key.startswith("share_"):
            site = key[6:]
            cur = await db.execute("SELECT id,name,price FROM products WHERE category=? AND name LIKE ? ORDER BY id", (category, f"%{site}%"))
        elif game:
            cur = await db.execute("SELECT id,name,price FROM products WHERE category=? AND game=? ORDER BY id", (category, game))
        else:
            cur = await db.execute("SELECT id,name,price FROM products WHERE category=? ORDER BY id", (category,))
        rows = await cur.fetchall()
    if not rows:
        return await c.answer("Chưa có sản phẩm trong thư mục này. Hãy thêm sản phẩm trước.", show_alert=True)
    label = "NỘI DUNG" if field == "description" else "GIÁ"
    buttons = [(f"{name} · {price:,}đ", f"cfgprod:{field}:{pid}:{key}") for pid,name,price in rows]
    buttons.append(("⬅️ QUAY LẠI CÀI ĐẶT", f"cfgback:{key}"))
    await c.message.edit_text(f"⚙️ CÀI ĐẶT {label}\\nChọn sản phẩm cần chỉnh sửa:", reply_markup=kb2(buttons))
    await c.answer()

@dp.callback_query(F.data.startswith("cfgprod:"))
async def admin_config_product_select(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    _, field, raw_pid, key = c.data.split(":",3)
    if field not in {"name","description","price"}:
        return await c.answer("Mục chỉnh sửa không hợp lệ.", show_alert=True)
    pid = int(raw_pid)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT name,description,price FROM products WHERE id=?", (pid,))
        row = await cur.fetchone()
    if not row:
        return await c.answer("Không tìm thấy sản phẩm.", show_alert=True)
    pending[c.from_user.id] = {"admin_product_field": field, "product_id": pid, "config_return": key}
    if field == "name":
        prompt = f"✏️ NHẬP TÊN MỚI CHO SẢN PHẨM\\nHiện tại: {row[0]}"
    elif field == "description":
        current_value = row[1] or "Chưa có"
        prompt = f"📝 NHẬP NỘI DUNG MỚI CHO {row[0]}\\nHiện tại: {current_value}\\n\\nGửi dấu - nếu muốn xóa nội dung."
    else:
        prompt = f"💵 NHẬP GIÁ MỚI CHO {row[0]}\\nHiện tại: {row[2]:,}đ\\n\\nNhập số tiền VNĐ."
    await c.message.edit_text(prompt, reply_markup=kb([("⬅️ QUAY LẠI CHỌN SẢN PHẨM", f"cfgfield:{field}:{key}"), ("⬅️ CÀI ĐẶT THƯ MỤC", f"cfgback:{key}")]))
    await c.answer()

@dp.callback_query(F.data.startswith("cfgconfirm:"))
async def admin_config_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    task = pending.get(c.from_user.id)
    action = c.data.split(":", 1)[1]
    if not isinstance(task, dict) or action not in {"yes", "no"} or "draft_kind" not in task:
        return await c.answer("Không còn thay đổi nào cần xác nhận.", show_alert=True)
    key = task.get("config_return") or task.get("folder_label_edit")
    if action == "no":
        pending.pop(c.from_user.id, None)
        return await c.message.edit_text("❌ Đã hủy cập nhật. Chưa có thay đổi nào được lưu.", reply_markup=kb([("⬅️ CÀI ĐẶT THƯ MỤC", f"afe:{key}")]))
    if task["draft_kind"] == "folder_label":
        await setting_write(f"folder_label:{task['folder_label_edit']}", task["draft_value"])
        pending.pop(c.from_user.id, None)
        await c.message.edit_text("✅ ĐÃ LƯU TÊN THƯ MỤC.", reply_markup=kb([("⚙️ CÀI ĐẶT LẠI", f"afe:{key}"), ("⬅️ QUẢN LÝ THƯ MỤC", "a:folders")]))
    elif task["draft_kind"] == "product_field":
        field, pid, value = task["admin_product_field"], task["product_id"], task["draft_value"]
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("SELECT category FROM products WHERE id=?", (pid,))
            product_row = await cur.fetchone()
            if field == "price" and product_row and product_row[0] == "GAME":
                value = 10000
            await db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, pid))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)", (c.from_user.id, f"folder config {field} product {pid}"))
            await db.commit()
        pending.pop(c.from_user.id, None)
        await c.message.edit_text("✅ ĐÃ LƯU THAY ĐỔI SẢN PHẨM.", reply_markup=kb([("⚙️ CÀI ĐẶT THƯ MỤC", f"afe:{key}"), ("⬅️ QUẢN LÝ THƯ MỤC", "a:folders")]))
    await c.answer("Đã xác nhận lưu.")

@dp.callback_query(F.data.startswith("afconfirm:"))
async def admin_folder_toggle_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    task = pending.get(c.from_user.id)
    action = c.data.split(":", 1)[1]
    if not isinstance(task, dict) or "folder_toggle_confirm" not in task or action not in {"yes", "no"}:
        return await c.answer("Phiên xác nhận đã hết.", show_alert=True)
    key = task["folder_toggle_confirm"]
    parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), None)
    if action == "yes":
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"folder:{key}", "1" if task["new_state"] else "0"))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)", (c.from_user.id, f"folder {key} {'on' if task['new_state'] else 'off'}"))
            await db.commit()
    pending.pop(c.from_user.id, None)
    if parent:
        title = await folder_label(parent, parent)
        await c.message.edit_text(f"⚙️ CÀI ĐẶT THƯ MỤC CON\\n{title}\\n\\n{'✅ Đã cập nhật.' if action == 'yes' else '❌ Đã hủy, không thay đổi.'}", reply_markup=await child_folders_kb(parent))
    else:
        await c.message.edit_text(f"⚙️ QUẢN LÝ THƯ MỤC\\n{'✅ Đã cập nhật.' if action == 'yes' else '❌ Đã hủy, không thay đổi.'}", reply_markup=await folders_kb())
    await c.answer("Đã lưu." if action == "yes" else "Đã hủy.")

async def setting_write(key, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
        await db.commit()

@dp.callback_query(F.data.startswith("af:"))
async def admin_toggle_folder(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    if key not in {item[0] for item in FOLDER_DEFS}:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    current = await folder_is_on(key)
    pending[c.from_user.id] = {"folder_toggle_confirm": key, "new_state": not current}
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    shown = await folder_label(key, defs.get(key, key))
    parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), None)
    cancel = f"afchildren:{parent}" if parent else "a:folders"
    await c.message.edit_text(
        f"⚠️ XÁC NHẬN THAY ĐỔI\\n\\nThư mục: {shown}\\nTrạng thái mới: {'🟢 BẬT' if not current else '🔴 TẮT'}\\n\\nBạn xác nhận cập nhật mục này?",
        reply_markup=kb([("✅ XÁC NHẬN", "afconfirm:yes"), ("❌ HỦY", "afconfirm:no"), ("⬅️ QUAY LẠI", cancel)])
    )
    await c.answer()

@dp.callback_query(F.data.startswith("a:"))
async def admin_actions(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    key=c.data.split(":")[1]
    folder_key = {"add":"admin_add","products":"admin_products","deposits":"admin_deposits","orders":"admin_orders","payment":"admin_payment","notify":"admin_notify","notifyall":"admin_notifyall","minitext":"admin_minitext"}.get(key)
    if folder_key and not await folder_is_on(folder_key):
        return await c.answer("Thư mục quản trị này hiện đang tắt.", show_alert=True)
    if key=="folders":
        await c.message.edit_text("⚙️ QUẢN LÝ THƯ MỤC\\nChọn thư mục chính. Mở CÀI ĐẶT để quản lý từng thư mục con:", reply_markup=await folders_kb())
        return await c.answer()
    if key=="refresh":
        await c.message.edit_text("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=await admin_kb())
    elif key=="add":
        await c.message.edit_text("➕ THÊM SẢN PHẨM\\nBƯỚC 1/4 — Chọn danh mục:",reply_markup=kb([("🎮 GAME","apw:GAME"),("🎯 MINIGAME LIVE","apw:MINIGAME LIVE"),("🔗 SHARE","apw:SHARE"),("📩 SMS","apw:SMS"),("🌐 PRX","apw:PRX"),("⬅️ MENU ADMIN","a:refresh")]))
    elif key=="products":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,category,game,name,price,active FROM products ORDER BY id DESC LIMIT 30"); rows=await cur.fetchall()
        body="📦 QUẢN LÝ SẢN PHẨM\\n"+("\\n".join([f"#{i} [{cat}/{g}] {n} — {p:,}đ ({'ĐANG BẬT' if a else 'ĐANG TẮT'})" for i,cat,g,n,p,a in rows]) if rows else "Chưa có sản phẩm.")
        await c.message.edit_text(body,reply_markup=admin_products_kb(rows))
    elif key=="deposits":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,user_id,amount,status FROM deposits WHERE status='pending' ORDER BY id"); rows=await cur.fetchall()
        body="💰 DUYỆT NẠP TIỀN\\n"+("\\n".join([f"#{i} | User {u} | {a:,}đ | {st}" for i,u,a,st in rows]) if rows else "Không có yêu cầu chờ duyệt.")
        await c.message.edit_text(body,reply_markup=admin_deposits_kb(rows))
    elif key=="orders":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,user_id,product_name,price,status,created_at FROM orders ORDER BY id DESC LIMIT 20"); rows=await cur.fetchall()
        body="🧾 QUẢN LÝ ĐƠN HÀNG\\n"+("\\n".join([f"#{i} | User {u} | {n} | {p:,}đ | {st} | {t}" for i,u,n,p,st,t in rows]) if rows else "Chưa có đơn hàng.")
        buttons=[]
        for i,u,n,p,st,t in rows:
            buttons.append((f"⚙️ ĐƠN #{i} · {st}"[:60],f"aord:{i}"))
        buttons.extend([("🔄 TẢI LẠI","a:orders"),("⬅️ MENU ADMIN","a:refresh")])
        await c.message.edit_text(body,reply_markup=kb(buttons))
    elif key=="stats":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM users"); users_total,balance_total=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM orders"); orders_total,sales_total=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'"); deposits_total,deposits_sum=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*) FROM orders WHERE status='processing'"); processing=(await cur.fetchone())[0]
            cur=await db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'"); pending_deposits=(await cur.fetchone())[0]
        body=(f"📊 TỔNG QUAN BOT\\n\\n👥 Thành viên: {users_total}\\n💳 Tổng số dư hiện tại: {balance_total:,}đ\\n"
              f"🧾 Tổng đơn: {orders_total}\\n💵 Tổng giá trị đơn: {sales_total:,}đ\\n"
              f"💰 Tổng nạp đã duyệt: {deposits_sum:,}đ ({deposits_total} lượt)\\n"
              f"⏳ Đơn đang xử lý: {processing}\\n🔔 Yêu cầu nạp chờ duyệt: {pending_deposits}")
        await c.message.edit_text(body,reply_markup=kb([("🔄 CẬP NHẬT","am:stats"),("👥 QUẢN LÝ THÀNH VIÊN","am:users"),("🧾 QUẢN LÝ ĐƠN","a:orders"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="users":
        pending[c.from_user.id]={"admin_user_search":True}
        await c.message.edit_text("👥 QUẢN LÝ THÀNH VIÊN\\nNhập Telegram ID hoặc tên để tìm:",reply_markup=kb([("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="balance":
        pending[c.from_user.id]={"admin_user_search":True}
        await c.message.edit_text("➕➖ ĐIỀU CHỈNH SỐ DƯ\\nNhập Telegram ID hoặc tên thành viên cần thao tác:",reply_markup=kb([("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="payment":
        pending[c.from_user.id]="payment"
        await c.message.answer("🏦 CÀI ĐẶT THANH TOÁN\\nNhập: TÊN NGÂN HÀNG|SỐ TK|CHỦ TK|NỘI DUNG CHUYỂN KHOẢN")
    elif key=="notify":
        pending[c.from_user.id]={"notify_stage":"user_id"}
        await c.message.answer("📢 THÔNG BÁO THEO ID\\nNhập Telegram ID người nhận:")
    elif key=="notifyall":
        pending[c.from_user.id]={"notify_stage":"all_message"}
        await c.message.answer("📣 THÔNG BÁO TẤT CẢ ID ĐÃ /start BOT\\nNhập nội dung muốn gửi:")
    elif key=="minitext":
        pending[c.from_user.id]="minitext"
        await c.message.answer("✏️ NHẬP NỘI DUNG MINIGAME LIVE (chỉ thông tin/thể lệ).")
    await c.answer()

@dp.callback_query(F.data.startswith("apw:"))
async def add_product_category(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    category=c.data.split(":",1)[1]
    if category not in {"GAME","MINIGAME LIVE","SHARE","SMS","PRX"}: return await c.answer("Danh mục không hợp lệ.",show_alert=True)
    if category=="GAME":
        await c.message.edit_text("BƯỚC 2/4 — Chọn game:",reply_markup=kb2([(g,f"agw:{g}") for g in GAMES if await folder_is_on(f"game_{g}")]+[("⬅️ Quay lại","a:add")]))
    elif category=="MINIGAME LIVE":
        await c.message.edit_text("BƯỚC 2/4 — Chọn minigame:",reply_markup=kb2([(g,f"amw:{g}") for g in ["XX8","88CLB","U888"]]+[("⬅️ QUAY LẠI","a:add")]))
    else:
        pending[c.from_user.id]={"add_stage":"name","category":category,"game":""}
        await c.message.edit_text(f"Danh mục: {category}\nBƯỚC 2/4 — Nhập tên sản phẩm/dịch vụ:",reply_markup=kb([("⬅️ QUAY LẠI CHỌN DANH MỤC","apback:category")]))
    await c.answer()

@dp.callback_query(F.data.startswith("amw:"))
async def add_product_minigame(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    game_name=c.data.split(":",1)[1]
    if game_name not in {"XX8","88CLB","U888"}: return await c.answer("Minigame không hợp lệ.",show_alert=True)
    pending[c.from_user.id]={"add_stage":"name","category":"MINIGAME LIVE","game":game_name}
    await c.message.edit_text(f"Danh mục: MINIGAME LIVE\\nMinigame: {game_name}\\nNhập tên sản phẩm:",reply_markup=kb([("⬅️ QUAY LẠI CHỌN MINIGAME","a:add")]))
    await c.answer()

@dp.callback_query(F.data.startswith("agw:"))
async def add_product_game(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    game=c.data.split(":",1)[1]
    if game not in GAMES: return await c.answer("Game không hợp lệ.",show_alert=True)
    pending[c.from_user.id]={"add_stage":"name","category":"GAME","game":game}
    await c.message.edit_text(f"Danh mục: GAME\nGame: {game}\nBƯỚC 3/4 — Nhập tên sản phẩm:",reply_markup=kb([("⬅️ QUAY LẠI CHỌN GAME","apback:game")]))
    await c.answer()

@dp.callback_query(F.data.startswith("apback:"))
async def admin_add_product_back(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    action=c.data.split(":",1)[1]; task=pending.get(c.from_user.id)
    if action=="category":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("➕ THÊM SẢN PHẨM\\nBƯỚC 1/4 — Chọn danh mục:",reply_markup=kb([("🎮 GAME","apw:GAME"),("🎯 MINIGAME LIVE","apw:MINIGAME LIVE"),("🔗 SHARE","apw:SHARE"),("📩 SMS","apw:SMS"),("🌐 PRX","apw:PRX"),("⬅️ MENU ADMIN","a:refresh")]))
    elif action=="game" and isinstance(task,dict):
        await c.message.edit_text("BƯỚC 2/4 — Chọn game:",reply_markup=kb2([(g,f"agw:{g}") for g in GAMES if await folder_is_on(f"game_{g}")]+[("⬅️ QUAY LẠI CHỌN DANH MỤC","apback:category")]))
    elif action in {"name","description","price","confirm"} and isinstance(task,dict) and "add_stage" in task:
        stage={"name":"name","description":"name","price":"description","confirm":"price"}[action]
        task["add_stage"]=stage; pending[c.from_user.id]=task
        labels={"name":"Nhập tên sản phẩm:","description":"Nhập mô tả/chi tiết sản phẩm (không có thì nhập dấu -):","price":"Nhập giá bán bằng số VNĐ:"}
        await c.message.edit_text(f"Danh mục: {task.get(chr(99)+chr(97)+chr(116)+chr(101)+chr(103)+chr(111)+chr(114)+chr(121), chr(63))}\\n{labels[stage]}",reply_markup=kb([("⬅️ QUAY LẠI","apback:"+({"name":"game" if task.get("category")=="GAME" else "category","description":"name","price":"description"}[stage]))]))
    elif action=="detail" and isinstance(task,dict) and "admin_product_field" in task:
        pid=task["product_id"]; pending.pop(c.from_user.id,None); await show_product_detail(c.message,pid)
    else:
        return await c.answer("Không có bước trước để quay lại.",show_alert=True)
    await c.answer()
@dp.callback_query(F.data.startswith("apc:"))
async def add_product_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    task=pending.get(c.from_user.id)
    if not isinstance(task,dict) or task.get("add_stage")!="confirm": return await c.answer("Phiên thêm sản phẩm đã hết.",show_alert=True)
    action=c.data.split(":",1)[1]
    if action=="cancel":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("Đã hủy thêm sản phẩm.",reply_markup=await admin_kb())
    elif action=="edit":
        task["add_stage"]="name"
        pending[c.from_user.id]=task
        await c.message.edit_text("Nhập lại tên sản phẩm:",reply_markup=kb([("⬅️ QUAY LẠI XÁC NHẬN","apback:confirm")]))
    elif action=="save":
        async with aiosqlite.connect(DB) as db:
            final_price = 10000 if task["category"] == "GAME" else task["price"]
            await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",(task["category"],task["game"],task["name"],final_price,task["description"]))
            await db.commit()
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("✅ Đã lưu sản phẩm.",reply_markup=await admin_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("an:"))
async def admin_notification_action(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    action=c.data.split(":")[1]
    task=pending.get(c.from_user.id)
    if not isinstance(task,dict):
        return await c.answer("Phiên thông báo đã hết. Hãy thao tác lại.",show_alert=True)
    if action=="cancel":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("Đã hủy gửi thông báo.",reply_markup=await admin_kb())
        return await c.answer()
    if action=="send" and task.get("notify_stage")=="confirm":
        try:
            await c.bot.send_message(task["target_id"],task["body"])
        except Exception as e:
            pending.pop(c.from_user.id,None)
            await c.message.edit_text(f"❌ Không gửi được đến ID {task['target_id']}. Có thể người nhận chưa từng mở bot hoặc đã chặn bot. Chi tiết: {str(e)[:180]}",reply_markup=await admin_kb())
            return await c.answer("Gửi thất bại.",show_alert=True)
        pending.pop(c.from_user.id,None)
        await c.message.edit_text(f"✅ Đã gửi thông báo thành công đến Telegram ID {task['target_id']}.",reply_markup=await admin_kb())
        return await c.answer("Đã gửi.")
    if action=="sendall" and task.get("notify_stage")=="confirm_all":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id FROM users ORDER BY id")
            recipients=[row[0] for row in await cur.fetchall()]
        sent=0
        failed=0
        for target_id in recipients:
            try:
                await c.bot.send_message(target_id,task["body"])
                sent+=1
                await asyncio.sleep(0.05)
            except Exception:
                failed+=1
        pending.pop(c.from_user.id,None)
        await c.message.edit_text(f"📣 ĐÃ GỬI THÔNG BÁO TOÀN BOT\\nThành công: {sent}\\nKhông gửi được: {failed}\\nTổng tài khoản: {len(recipients)}",reply_markup=await admin_kb())
        return await c.answer("Đã hoàn tất gửi.")
    return await c.answer("Thao tác không hợp lệ.",show_alert=True)

@dp.callback_query(F.data.startswith("am:"))
async def admin_management_menu(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    key=c.data.split(":")[1]
    if key=="stats":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM users"); users_total,balance_total=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM orders"); orders_total,sales_total=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'"); deposits_total,deposits_sum=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*) FROM orders WHERE status='processing'"); processing=(await cur.fetchone())[0]
            cur=await db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'"); pending_deposits=(await cur.fetchone())[0]
        body=(f"📊 TỔNG QUAN BOT\\n\\n👥 Thành viên: {users_total}\\n💳 Tổng số dư hiện tại: {balance_total:,}đ\\n"
              f"🧾 Tổng đơn: {orders_total}\\n💵 Tổng giá trị đơn: {sales_total:,}đ\\n"
              f"💰 Tổng nạp đã duyệt: {deposits_sum:,}đ ({deposits_total} lượt)\\n"
              f"⏳ Đơn đang xử lý: {processing}\\n🔔 Yêu cầu nạp chờ duyệt: {pending_deposits}")
        await c.message.edit_text(body,reply_markup=kb([("🔄 CẬP NHẬT","am:stats"),("👥 QUẢN LÝ THÀNH VIÊN","am:users"),("🧾 QUẢN LÝ ĐƠN","a:orders"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="users":
        pending[c.from_user.id]={"admin_user_search":True}
        await c.message.edit_text("👥 QUẢN LÝ THÀNH VIÊN\\nNhập Telegram ID hoặc tên để tìm:",reply_markup=kb([("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="logs":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT admin_id,action,created_at FROM admin_logs ORDER BY id DESC LIMIT 30")
            rows=await cur.fetchall()
        body="📜 LỊCH SỬ THAO TÁC ADMIN\\n"+("\\n".join([f"{t} | Admin {aid} | {act}" for aid,act,t in rows]) if rows else "Chưa có lịch sử thao tác.")
        await c.message.edit_text(body,reply_markup=kb([("🔄 TẢI LẠI","am:logs"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
    elif key=="staff":
        if c.from_user.id not in ROOT_ADMINS:
            return await c.answer("Chỉ Admin chủ mới được quản lý nhân viên.",show_alert=True)
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT user_id,added_by,created_at FROM admin_staff ORDER BY created_at DESC")
            rows=await cur.fetchall()
        body="🧑‍💼 QUẢN LÝ NHÂN VIÊN\\n"+("\\n".join([f"ID {uid} | Thêm bởi {by} | {created}" for uid,by,created in rows]) if rows else "Chưa có nhân viên phụ.")
        buttons=[(f"🗑 GỠ QUYỀN ID {uid}",f"amsdel:{uid}") for uid,by,created in rows]
        buttons.extend([("➕ THÊM NHÂN VIÊN","am:addstaff"),("⬅️ MENU QUẢN TRỊ","a:refresh")])
        await c.message.edit_text(body,reply_markup=kb(buttons))
    elif key=="addstaff":
        if c.from_user.id not in ROOT_ADMINS:
            return await c.answer("Chỉ Admin chủ mới được thêm nhân viên.",show_alert=True)
        pending[c.from_user.id]={"admin_staff_add":True}
        await c.message.edit_text("➕ THÊM NHÂN VIÊN ADMIN\\nNhập Telegram ID dạng số:",reply_markup=kb([("⬅️ QUAY LẠI","am:staff")]))
    await c.answer()

@dp.callback_query(F.data.startswith("amsdel:"))
async def admin_staff_delete(c: CallbackQuery):
    if c.from_user.id not in ROOT_ADMINS:
        return await c.answer("Chỉ Admin chủ mới được gỡ quyền.",show_alert=True)
    target=int(c.data.split(":")[1])
    if target in ROOT_ADMINS:
        return await c.answer("Không thể gỡ Admin chủ.",show_alert=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM admin_staff WHERE user_id=?",(target,))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(c.from_user.id,f"remove admin staff {target}"))
        await db.commit()
    ADMINS.discard(target)
    await c.answer("Đã gỡ quyền nhân viên.")
    await c.message.edit_text("🧑‍💼 ĐÃ CẬP NHẬT DANH SÁCH NHÂN VIÊN.",reply_markup=kb([("👥 XEM DANH SÁCH","am:staff"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))

@dp.callback_query(F.data.startswith("amu:"))
async def admin_user_detail(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    target=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,name,balance,blocked FROM users WHERE id=?",(target,)); row=await cur.fetchone()
        cur=await db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?",(target,)); order_count=(await cur.fetchone())[0]
        cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM deposits WHERE user_id=? AND status='approved'",(target,)); dep_count,dep_sum=await cur.fetchone()
    if not row: return await c.answer("Không tìm thấy thành viên.",show_alert=True)
    uid,name,balance,blocked=row
    body=f"👤 THÀNH VIÊN\\nTên: {name or 'Chưa cập nhật'}\\nTelegram ID: {uid}\\nSố dư: {balance:,}đ\\nĐơn hàng: {order_count}\\nNạp đã duyệt: {dep_count} lượt / {dep_sum:,}đ\\nTrạng thái: {'ĐANG KHÓA' if blocked else 'HOẠT ĐỘNG'}"
    await c.message.edit_text(body,reply_markup=admin_user_detail_kb(uid,blocked))
    await c.answer()

@dp.callback_query(F.data.startswith("amb:"))
async def admin_balance_prompt(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    _,target,direction=c.data.split(":")
    if direction not in {"add","sub"}: return await c.answer("Thao tác không hợp lệ.",show_alert=True)
    pending[c.from_user.id]={"admin_balance_user_id":int(target),"direction":direction}
    await c.message.answer(f"{'➕ CỘNG' if direction=='add' else '➖ TRỪ'} SỐ DƯ cho ID {target}\\nNhập số tiền VNĐ:",reply_markup=kb([("⬅️ HỦY","ambcancel")]))
    await c.answer()

@dp.callback_query(F.data == "ambok")
async def admin_balance_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    task = pending.get(c.from_user.id)
    if not isinstance(task, dict) or not task.get("admin_balance_confirm"):
        return await c.answer("Thao tác đã hết hạn. Vui lòng thực hiện lại.", show_alert=True)
    target = int(task["admin_balance_user_id"])
    amount = int(task["amount"])
    direction = task["direction"]
    async with aiosqlite.connect(DB) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute("SELECT balance FROM users WHERE id=?", (target,))
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            pending.pop(c.from_user.id, None)
            return await c.answer("Không tìm thấy thành viên.", show_alert=True)
        before = int(row[0])
        if direction == "sub" and before < amount:
            await db.rollback()
            pending.pop(c.from_user.id, None)
            return await c.answer(f"Số dư hiện tại chỉ {before:,}đ, không thể trừ {amount:,}đ.", show_alert=True)
        delta = amount if direction == "add" else -amount
        after = before + delta
        await db.execute("UPDATE users SET balance=? WHERE id=?", (after, target))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)", (c.from_user.id, f"balance {direction} {amount} user {target}; {before}->{after}"))
        await db.commit()
    pending.pop(c.from_user.id, None)
    await c.message.edit_text(
        f"✅ ĐÃ CẬP NHẬT SỐ DƯ\\nID: {target}\\nThao tác: {'CỘNG' if direction == 'add' else 'TRỪ'} {amount:,}đ\\nSố dư trước: {before:,}đ\\nSố dư sau: {after:,}đ",
        reply_markup=kb([("👤 XEM THÀNH VIÊN", f"amu:{target}"), ("➕➖ TIẾP TỤC ĐIỀU CHỈNH", "am:balance"), ("⬅️ MENU QUẢN TRỊ", "a:refresh")])
    )
    try:
        await c.bot.send_message(target, f"💳 Số dư tài khoản đã được Admin {'cộng' if direction == 'add' else 'trừ'} {amount:,}đ.\\nSố dư hiện tại: {after:,}đ.")
    except Exception:
        pass
    await c.answer("Đã cập nhật số dư.")

@dp.callback_query(F.data == "ambcancel")
async def admin_balance_cancel(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    task = pending.get(c.from_user.id)
    target = int(task.get("admin_balance_user_id", 0)) if isinstance(task, dict) else 0
    pending.pop(c.from_user.id, None)
    if target:
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,name,balance,blocked FROM users WHERE id=?", (target,))
            row=await cur.fetchone()
            cur=await db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (target,))
            order_count=(await cur.fetchone())[0]
            cur=await db.execute("SELECT COUNT(*),COALESCE(SUM(amount),0) FROM deposits WHERE user_id=? AND status='approved'", (target,))
            dep_count,dep_sum=await cur.fetchone()
        if row:
            uid,name,balance,blocked=row
            body=f"👤 THÀNH VIÊN\\nTên: {name or 'Chưa cập nhật'}\\nTelegram ID: {uid}\\nSố dư: {balance:,}đ\\nĐơn hàng: {order_count}\\nNạp đã duyệt: {dep_count} lượt / {dep_sum:,}đ\\nTrạng thái: {'ĐANG KHÓA' if blocked else 'HOẠT ĐỘNG'}"
            await c.message.edit_text(body, reply_markup=admin_user_detail_kb(uid,blocked))
        else:
            await c.message.edit_text("Không tìm thấy thành viên.", reply_markup=kb([("🔎 TÌM THÀNH VIÊN", "am:balance"), ("⬅️ MENU QUẢN TRỊ", "a:refresh")]))
    else:
        await c.message.edit_text("➕➖ ĐIỀU CHỈNH SỐ DƯ", reply_markup=kb([("🔎 TÌM THÀNH VIÊN", "am:balance"), ("⬅️ MENU QUẢN TRỊ", "a:refresh")]))
    await c.answer("Đã hủy thao tác.")

@dp.callback_query(F.data.startswith("amlock:"))
async def admin_user_toggle_block(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    target=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT blocked FROM users WHERE id=?",(target,)); row=await cur.fetchone()
        if not row: return await c.answer("Không tìm thấy thành viên.",show_alert=True)
        await db.execute("UPDATE users SET blocked=1-blocked WHERE id=?",(target,))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(c.from_user.id,f"toggle block user {target}"))
        await db.commit()
    await c.answer("Đã cập nhật trạng thái thành viên.")
    await admin_user_detail(c)

@dp.callback_query(F.data.startswith("aord:"))
async def admin_order_detail(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    oid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT user_id,product_name,account,price,status,created_at FROM orders WHERE id=?",(oid,)); row=await cur.fetchone()
    if not row: return await c.answer("Không tìm thấy đơn hàng.",show_alert=True)
    u,name,account,price,status,created=row
    body=f"🧾 CHI TIẾT ĐƠN #{oid}\\nUser: {u}\\nSản phẩm: {name}\\nTài khoản: {account or '-'}\\nGiá: {price:,}đ\\nTrạng thái: {status}\\nTạo lúc: {created}"
    buttons=[("⏳ ĐANG XỬ LÝ",f"aost:{oid}:processing"),("✅ HOÀN THÀNH",f"aost:{oid}:completed"),("❌ ĐÃ HỦY",f"aost:{oid}:cancelled"),("⬅️ DANH SÁCH ĐƠN","a:orders")]
    await c.message.edit_text(body,reply_markup=kb(buttons))
    await c.answer()

@dp.callback_query(F.data.startswith("aost:"))
async def admin_order_set_status(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    parts=c.data.split(":")
    if len(parts)!=3 or parts[2] not in {"processing","completed","cancelled"}:
        return await c.answer("Trạng thái không hợp lệ.",show_alert=True)
    oid=int(parts[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT user_id,status FROM orders WHERE id=?",(oid,)); row=await cur.fetchone()
        if not row: return await c.answer("Không tìm thấy đơn hàng.",show_alert=True)
        await db.execute("UPDATE orders SET status=? WHERE id=?",(parts[2],oid))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(c.from_user.id,f"order {oid} status {parts[2]}"))
        await db.commit()
    try:
        await c.bot.send_message(row[0],f"📦 Đơn hàng #{oid} đã cập nhật trạng thái: {parts[2]}.")
    except Exception: pass
    await c.answer("Đã cập nhật trạng thái đơn.")
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT user_id,product_name,account,price,status,created_at FROM orders WHERE id=?",(oid,)); detail=await cur.fetchone()
    u,name,account,price,status,created=detail
    body=f"🧾 CHI TIẾT ĐƠN #{oid}\\nUser: {u}\\nSản phẩm: {name}\\nTài khoản: {account or '-'}\\nGiá: {price:,}đ\\nTrạng thái: {status}\\nTạo lúc: {created}"
    buttons=[("⏳ ĐANG XỬ LÝ",f"aost:{oid}:processing"),("✅ HOÀN THÀNH",f"aost:{oid}:completed"),("❌ ĐÃ HỦY",f"aost:{oid}:cancelled"),("⬅️ DANH SÁCH ĐƠN","a:orders")]
    await c.message.edit_text(body,reply_markup=kb(buttons))

@dp.callback_query(F.data.startswith("ap:"))
async def admin_edit_price(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    pid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT name,price FROM products WHERE id=?",(pid,)); row=await cur.fetchone()
    if not row: return await c.answer("Không tìm thấy sản phẩm.",show_alert=True)
    pending[c.from_user.id]={"admin_price_id":pid}
    await c.message.answer(f"💵 SỬA GIÁ SẢN PHẨM #{pid} — {row[0]}\\nGiá hiện tại: {row[1]:,}đ\\nNhập giá mới bằng số (VNĐ).")
    await c.answer()

@dp.callback_query(F.data.startswith("at:"))
async def admin_toggle_product(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    pid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT active FROM products WHERE id=?",(pid,)); row=await cur.fetchone()
        if not row: return await c.answer("Không tìm thấy sản phẩm.",show_alert=True)
        await db.execute("UPDATE products SET active=1-active WHERE id=?",(pid,)); await db.commit()
    await c.answer("Đã đổi trạng thái sản phẩm.")
    await show_product_detail(c.message,pid)

@dp.callback_query(F.data.startswith("apd:"))
async def admin_product_detail(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    await show_product_detail(c.message,int(c.data.split(":")[1]))
    await c.answer()

@dp.callback_query(F.data.startswith("apf:"))
async def admin_product_edit_field(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    parts=c.data.split(":")
    if len(parts)!=3 or parts[2] not in {"name","description","price"}: return await c.answer("Thao tác không hợp lệ.",show_alert=True)
    pid=int(parts[1]); field=parts[2]
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT name,description,price FROM products WHERE id=?",(pid,)); row=await cur.fetchone()
    if not row: return await c.answer("Không tìm thấy sản phẩm.",show_alert=True)
    current={"name":row[0],"description":row[1] or "Chưa có","price":f"{row[2]:,}đ"}[field]
    pending[c.from_user.id]={"admin_product_field":field,"product_id":pid}
    await c.message.answer(f"✏️ SỬA {field.upper()} SẢN PHẨM #{pid}\\nHiện tại: {current}\\nNhập nội dung mới:",reply_markup=kb([("⬅️ QUAY LẠI CHI TIẾT SẢN PHẨM","apback:detail")]))
    await c.answer()

@dp.callback_query(F.data.startswith("apdel:"))
async def admin_product_delete_prompt(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)

async def main():
    await init_db()
    bot = Bot(token=TOKEN)
    me = await bot.get_me()
    logging.info("Starting @%s id=%s", me.username, me.id)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by keyboard interrupt")
