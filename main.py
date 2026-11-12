import asyncio
import logging
import os
import re
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
        defaults = [
            ("MINIGAME LIVE","XX8","MINIGAME XX8",65000,"Minigame LIVE XX8"),
            ("MINIGAME LIVE","88CLB","MINIGAME 88CLB",60000,"Minigame LIVE 88CLB"),
            ("SHARE","","SHARE QQ88",50000,"Chương trình CODE SHARE QQ88"),
            ("SHARE","","SHARE HI88",60000,"Chương trình CODE SHARE HI88"),
        ]
        for cat, game_name, name, price, desc in defaults:
            cur = await db.execute("SELECT id FROM products WHERE category=? AND game=? AND name=? LIMIT 1",(cat,game_name,name))
            if not await cur.fetchone():
                await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",(cat,game_name,name,price,desc))
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
    ("mini_XX8", "🎯 MINIGAME XX8", "Chi tiết Minigame"),
    ("mini_AD88", "🎯 MINIGAME AD88", "Chi tiết Minigame"),
    ("mini_U888", "🎯 MINIGAME U888", "Chi tiết Minigame"),
    ("mini_88CLB", "🎯 MINIGAME 88CLB", "Chi tiết Minigame"),
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
        ("home_houses", "🏦 HỆ THỐNG NHÀ CÁI", "m:houses")
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
    "home_codegame": [f"game_{g}" for g in GAMES],
    "home_mini": ["mini_XX8", "mini_AD88", "mini_U888", "mini_88CLB"],
    "home_share": ["share_QQ88", "share_HI88"],
}

async def folders_kb():
    b = InlineKeyboardBuilder()
    for key, label, group in FOLDER_DEFS:
        if key.startswith(("game_", "mini_", "share_")):
            continue
        enabled = await folder_is_on(key)
        shown = await folder_label(key, label)
        b.button(text=f"{'🟢 ON' if enabled else '🔴 OFF'} | {shown}"[:64], callback_data=f"af:{key}")
        config_callback = f"afchildren:{key}" if key in CHILD_FOLDER_KEYS else f"afe:{key}"
        b.button(text=f"⚙️ CÀI ĐẶT | {shown}"[:64], callback_data=config_callback)
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
        b.button(text=f"{'🟢 ON' if enabled else '🔴 OFF'} | {shown}"[:64], callback_data=f"af:{key}")
        b.button(text=f"⚙️ CÀI ĐẶT | {shown}"[:64], callback_data=f"afe:{key}")
    b.button(text="🔄 TẢI LẠI", callback_data=f"afchildren:{parent}")
    b.button(text="⬅️ QUAY LẠI THƯ MỤC CHÍNH", callback_data="a:folders")
    b.adjust(2)
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
    welcome = (f"╔══════════════════════════════════╗\\n"
               f"🌟🎉 XIN CHÀO, {m.from_user.full_name}! 🎉🌟\\n"
               "╠══════════════════════════════════╣\\n"
               "💎 CHÀO MỪNG BẠN ĐẾN VỚI NGHIỆN CODE 💎\\n"
               "🎮 CODE GAME HOT – MINIGAME LIVE\\n"
               "⚡ GIAO DỊCH NHANH – THAO TÁC TIỆN LỢI\\n"
               "🤖 HỆ THỐNG TỰ ĐỘNG – HỖ TRỢ 24/7\\n"
               "╠══════════════════════════════════╣\\n"
               "🚀 BẠN MUỐN SỬ DỤNG DỊCH VỤ NÀO? 👇👇👇\\n"
               "🎯 VUI LÒNG CHỌN DANH MỤC BÊN DƯỚI ĐỂ BẮT ĐẦU! 💖\\n"
               "╚══════════════════════════════════╝")
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
        game_rows=[(await folder_label(f"game_{g}",g),f"game:{g}") for g in GAMES if await folder_is_on(f"game_{g}")]
        await c.message.edit_text((await folder_label("home_codegame","🎮 CODE GAME"))+"\n\nChọn game:",reply_markup=kb2(game_rows+[("⬅️ QUAY LẠI","m:code")]))
    elif key=="mini":
        rows=[(await folder_label(f"mini_{g}",f"🎯 MINIGAME {g}"),f"miniitem:{g}") for g in ["XX8","AD88","U888","88CLB"] if await folder_is_on(f"mini_{g}")]
        rows.append(("⬅️ QUAY LẠI","m:code"))
        await c.message.edit_text((await folder_label("home_mini","🎯 MINIGAME LIVE"))+"\n\nChọn minigame:",reply_markup=kb2(rows))
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
    if game_name not in {"XX8","AD88","U888","88CLB"}:
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
    pending[c.from_user.id]={"product_id":pid,"category":p[0],"game":p[1],"name":p[2],"price":p[3]}
    await c.message.answer("📝 Vui lòng điền tên tài khoản cần mua. Nếu không yêu cầu tài khoản, nhập dấu -.",reply_markup=kb([("❌ HỦY ĐẶT HÀNG","buyact:cancel")]))
    await c.answer()


@dp.callback_query(F.data.startswith("buyact:"))
async def purchase_action(c: CallbackQuery):
    action=c.data.split(":",1)[1]
    task=pending.get(c.from_user.id)
    if action=="cancel":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("❌ Đã hủy thao tác mua hàng.",reply_markup=kb([("🏠 MENU CHÍNH","m:home")]))
        return await c.answer("Đã hủy.")
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
    return (None, None)

async def folder_config_kb(key):
    b = InlineKeyboardBuilder()
    category, game = await folder_config_products(key)
    if category:
        b.button(text="🎮 SITE GAME", callback_data=f"cfgsite:{key}")
        b.button(text="📝 NỘI DUNG", callback_data=f"cfgfield:description:{key}")
        b.button(text="💵 GIÁ", callback_data=f"cfgfield:price:{key}")
    else:
        b.button(text="✏️ ĐỔI TÊN HIỂN THỊ", callback_data=f"cfgsite:{key}")
    parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), None)
    back_callback = f"afchildren:{parent}" if parent else "a:folders"
    b.button(text="⬅️ QUAY LẠI THƯ MỤC", callback_data=back_callback)
    b.adjust(2)
    return b.as_markup()

@dp.callback_query(F.data.startswith("afchildren:"))
async def admin_child_folders(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    parent = c.data.split(":",1)[1]
    if parent not in CHILD_FOLDER_KEYS:
        return await c.answer("Thư mục chính không hợp lệ.", show_alert=True)
    defs = {item[0]: item[1] for item in FOLDER_DEFS}
    title = await folder_label(parent, defs.get(parent, parent))
    await c.message.edit_text(f"⚙️ CÀI ĐẶT THƯ MỤC CON\\n{title}\\n\\nChọn từng SITE để bật/tắt hoặc cài đặt SITE GAME / NỘI DUNG / GIÁ:", reply_markup=await child_folders_kb(parent))
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
    if field not in {"description","price"}:
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
    if field not in {"description","price"}:
        return await c.answer("Mục chỉnh sửa không hợp lệ.", show_alert=True)
    pid = int(raw_pid)
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT name,description,price FROM products WHERE id=?", (pid,))
        row = await cur.fetchone()
    if not row:
        return await c.answer("Không tìm thấy sản phẩm.", show_alert=True)
    pending[c.from_user.id] = {"admin_product_field": field, "product_id": pid, "config_return": key}
    if field == "description":
        current_value = row[1] or "Chưa có"
        prompt = f"📝 NHẬP NỘI DUNG MỚI CHO {row[0]}\\nHiện tại: {current_value}\\n\\nGửi dấu - nếu muốn xóa nội dung."
    else:
        prompt = f"💵 NHẬP GIÁ MỚI CHO {row[0]}\\nHiện tại: {row[2]:,}đ\\n\\nNhập số tiền VNĐ."
    await c.message.edit_text(prompt, reply_markup=kb([("⬅️ QUAY LẠI CHỌN SẢN PHẨM", f"cfgfield:{field}:{key}"), ("⬅️ CÀI ĐẶT THƯ MỤC", f"cfgback:{key}")]))
    await c.answer()

@dp.callback_query(F.data.startswith("af:"))
async def admin_toggle_folder(c: CallbackQuery):
    if c.from_user.id not in ADMINS:
        return await c.answer("Không có quyền.", show_alert=True)
    key = c.data.split(":",1)[1]
    if key not in {item[0] for item in FOLDER_DEFS}:
        return await c.answer("Thư mục không hợp lệ.", show_alert=True)
    current = await folder_is_on(key)
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"folder:{key}", "0" if current else "1"))
        await db.commit()
    parent = next((p for p, children in CHILD_FOLDER_KEYS.items() if key in children), None)
    if parent:
        defs = {item[0]: item[1] for item in FOLDER_DEFS}
        title = await folder_label(parent, defs.get(parent, parent))
        await c.message.edit_text(f"⚙️ CÀI ĐẶT THƯ MỤC CON\\n{title}\\n\\nĐã cập nhật trạng thái thư mục con:", reply_markup=await child_folders_kb(parent))
    else:
        await c.message.edit_text("⚙️ QUẢN LÝ THƯ MỤC\\nĐã cập nhật trạng thái:", reply_markup=await folders_kb())
    await c.answer("Đã đổi trạng thái.")

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
        await c.message.edit_text("BƯỚC 2/4 — Chọn minigame:",reply_markup=kb2([(g,f"amw:{g}") for g in ["XX8","AD88","U888","88CLB"]]+[("⬅️ QUAY LẠI","a:add")]))
    else:
        pending[c.from_user.id]={"add_stage":"name","category":category,"game":""}
        await c.message.edit_text(f"Danh mục: {category}\nBƯỚC 2/4 — Nhập tên sản phẩm/dịch vụ:",reply_markup=kb([("⬅️ QUAY LẠI CHỌN DANH MỤC","apback:category")]))
    await c.answer()

@dp.callback_query(F.data.startswith("amw:"))
async def add_product_minigame(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    game_name=c.data.split(":",1)[1]
    if game_name not in {"XX8","AD88","U888","88CLB"}: return await c.answer("Minigame không hợp lệ.",show_alert=True)
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
            await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",(task["category"],task["game"],task["name"],task["price"],task["description"]))
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
    pid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT name FROM products WHERE id=?",(pid,)); row=await cur.fetchone()
    if not row: return await c.answer("Không tìm thấy sản phẩm.",show_alert=True)
    await c.message.edit_text(f"XÁC NHẬN XÓA #{pid}\\n{row[0]}\\nĐơn hàng cũ vẫn được giữ nguyên.",reply_markup=kb([("🗑 XÁC NHẬN",f"apdelok:{pid}"),("⬅️ HỦY",f"apd:{pid}")]))
    await c.answer()

@dp.callback_query(F.data.startswith("apdelok:"))
async def admin_product_delete(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    pid=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM products WHERE id=?",(pid,)); await db.commit()
        cur=await db.execute("SELECT id,category,game,name,price,active FROM products ORDER BY id DESC LIMIT 30"); rows=await cur.fetchall()
    await c.answer("Đã xóa sản phẩm.")
    body="📦 QUẢN LÝ SẢN PHẨM\\n"+("\\n".join([f"#{i} [{cat}/{g}] {n} — {p:,}đ" for i,cat,g,n,p,a in rows]) if rows else "Chưa có sản phẩm.")
    await c.message.edit_text(body,reply_markup=admin_products_kb(rows))
@dp.callback_query(F.data.startswith("adok:"))
async def admin_approve_deposit_button(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    did=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur=await db.execute("SELECT user_id,amount,status FROM deposits WHERE id=?",(did,)); row=await cur.fetchone()
        if not row or row[2]!="pending":
            await db.rollback(); return await c.answer("Yêu cầu không còn chờ duyệt.",show_alert=True)
        await db.execute("INSERT OR IGNORE INTO users(id,name) VALUES(?,?)",(row[0],str(row[0])))
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?",(row[1],row[0]))
        await db.execute("UPDATE deposits SET status='approved' WHERE id=?",(did,))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(c.from_user.id,f"approve deposit {did}"))
        await db.commit()
    try: await c.bot.send_message(row[0],f"✅ Yêu cầu nạp #{did} đã được duyệt: +{row[1]:,}đ.")
    except Exception: pass
    await c.answer("Đã duyệt nạp tiền.")
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,user_id,amount,status FROM deposits WHERE status='pending' ORDER BY id"); rows=await cur.fetchall()
    body="💰 DUYỆT NẠP TIỀN\\n"+("\\n".join([f"#{i} | User {u} | {a:,}đ | {st}" for i,u,a,st in rows]) if rows else "Không có yêu cầu chờ duyệt.")
    await c.message.edit_text(body,reply_markup=admin_deposits_kb(rows))

@dp.callback_query(F.data.startswith("adno:"))
async def admin_reject_deposit_button(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    did=int(c.data.split(":")[1])
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT user_id,status FROM deposits WHERE id=?",(did,)); row=await cur.fetchone()
        if not row or row[1]!="pending": return await c.answer("Yêu cầu không còn chờ duyệt.",show_alert=True)
        await db.execute("UPDATE deposits SET status='rejected' WHERE id=?",(did,))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(c.from_user.id,f"reject deposit {did}"))
        await db.commit()
    try: await c.bot.send_message(row[0],f"❌ Yêu cầu nạp #{did} đã bị từ chối. Vui lòng liên hệ Admin nếu cần hỗ trợ.")
    except Exception: pass
    await c.answer("Đã từ chối yêu cầu nạp.")
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,user_id,amount,status FROM deposits WHERE status='pending' ORDER BY id"); rows=await cur.fetchall()
    body="💰 DUYỆT NẠP TIỀN\\n"+("\\n".join([f"#{i} | User {u} | {a:,}đ | {st}" for i,u,a,st in rows]) if rows else "Không có yêu cầu chờ duyệt.")
    await c.message.edit_text(body,reply_markup=admin_deposits_kb(rows))

@dp.message(Command("duyetnap"))
async def approve_deposit(m: Message):
    if m.from_user.id not in ADMINS: return
    parts=(m.text or "").split()
    if len(parts)!=2 or not parts[1].isdigit(): return await m.answer("Dùng: /duyetnap ID")
    did=int(parts[1])
    async with aiosqlite.connect(DB) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur=await db.execute("SELECT user_id,amount,status FROM deposits WHERE id=?",(did,)); row=await cur.fetchone()
        if not row or row[2]!="pending": await db.rollback(); return await m.answer("Không tìm thấy yêu cầu chờ duyệt.")
        await db.execute("INSERT OR IGNORE INTO users(id,name) VALUES(?,?)",(row[0],str(row[0])))
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?",(row[1],row[0]))
        await db.execute("UPDATE deposits SET status='approved' WHERE id=?",(did,))
        await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(m.from_user.id,f"approve deposit {did}"))
        await db.commit()
    await m.answer(f"Đã duyệt yêu cầu nạp #{did}.")
    try: await m.bot.send_message(row[0],f"✅ Yêu cầu nạp #{did} đã được duyệt: +{row[1]:,}đ.")
    except Exception: pass

@dp.message(Command("price"))
async def price(m: Message):
    if m.from_user.id not in ADMINS: return
    p=(m.text or "").split()
    if len(p)!=3 or not p[1].isdigit() or not p[2].isdigit(): return await m.answer("Dùng: /price ID GIÁ")
    async with aiosqlite.connect(DB) as db: await db.execute("UPDATE products SET price=? WHERE id=?",(int(p[2]),int(p[1]))); await db.commit()
    await m.answer("Đã cập nhật giá.")

@dp.message(Command("toggle"))
async def toggle(m: Message):
    if m.from_user.id not in ADMINS: return
    p=(m.text or "").split()
    if len(p)!=2 or not p[1].isdigit(): return await m.answer("Dùng: /toggle ID")
    async with aiosqlite.connect(DB) as db: await db.execute("UPDATE products SET active=1-active WHERE id=?",(int(p[1]),)); await db.commit()
    await m.answer("Đã đổi trạng thái sản phẩm.")

@dp.message(Command("huy"))
async def reject_deposit(m: Message):
    if m.from_user.id not in ADMINS: return
    p=(m.text or "").split()
    if len(p)!=3 or p[1].lower()!="nap" or not p[2].isdigit(): return await m.answer("Dùng: /huy nap ID")
    async with aiosqlite.connect(DB) as db: await db.execute("UPDATE deposits SET status='rejected' WHERE id=? AND status='pending'",(int(p[2]),)); await db.commit()
    await m.answer("Đã từ chối yêu cầu nạp nếu yêu cầu còn chờ.")

@dp.message(F.photo)
async def photo_input(m: Message):
    if m.from_user.id in ADMINS and pending.get(m.from_user.id)=="qr":
        async with aiosqlite.connect(DB) as db: await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('qr_file_id',?)",(m.photo[-1].file_id,)); await db.commit()
        pending.pop(m.from_user.id,None); await m.answer("Đã lưu QR thanh toán.")

async def process_admin_text(m: Message):
    uid=m.from_user.id
    task=pending.get(uid)
    if uid not in ADMINS: return False
    if isinstance(task,dict) and task.get("folder_label_edit"):
        key = task["folder_label_edit"]
        value = (m.text or "").strip()
        if not value:
            await m.answer("Tên thư mục không được để trống. Nhập lại hoặc bấm HỦY.")
            return True
        value = value[:60]
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"folder_label:{key}", value))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)", (uid, f"rename folder {key} to {value}"))
            await db.commit()
        pending.pop(uid, None)
        await m.answer(f"✅ Đã cập nhật SITE GAME: {value}", reply_markup=await folder_config_kb(key) if task.get("config_return") else await folders_kb())
        return True
    if isinstance(task,dict) and task.get("admin_staff_add"):
        raw=(m.text or "").strip()
        if not raw.isdigit() or int(raw)<=0:
            await m.answer("Telegram ID không hợp lệ. Vui lòng nhập ID dạng số.")
            return True
        target=int(raw)
        if target in ROOT_ADMINS:
            pending.pop(uid,None)
            await m.answer("ID này đã là Admin chủ.")
            return True
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT OR IGNORE INTO admin_staff(user_id,added_by) VALUES(?,?)",(target,uid))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(uid,f"add admin staff {target}"))
            await db.commit()
        ADMINS.add(target)
        pending.pop(uid,None)
        await m.answer(f"✅ Đã cấp quyền Admin nhân viên cho ID {target}. Nhân viên có quyền quản trị bot; chỉ Admin chủ được thêm/gỡ quyền.",reply_markup=kb([("🧑‍💼 DANH SÁCH NHÂN VIÊN","am:staff"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
        return True
    if isinstance(task,dict) and task.get("admin_user_search"):
        query=(m.text or "").strip()
        if not query:
            await m.answer("Nhập Telegram ID hoặc tên thành viên.")
            return True
        async with aiosqlite.connect(DB) as db:
            if query.isdigit():
                cur=await db.execute("SELECT id,name,balance,blocked FROM users WHERE id=? LIMIT 20",(int(query),))
            else:
                cur=await db.execute("SELECT id,name,balance,blocked FROM users WHERE name LIKE ? ORDER BY id DESC LIMIT 20",(f"%{query}%",))
            rows=await cur.fetchall()
        pending.pop(uid,None)
        await m.answer(("🔎 KẾT QUẢ TÌM KIẾM\\n" if rows else "Không tìm thấy thành viên phù hợp."),reply_markup=admin_users_kb(rows) if rows else kb([("🔎 TÌM LẠI","am:users"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
        return True
    if isinstance(task,dict) and "admin_balance_user_id" in task and not task.get("admin_balance_confirm"):
        raw=re.sub(r"[^0-9]","",m.text or "")
        if not raw or int(raw)<=0:
            await m.answer("Số tiền không hợp lệ. Nhập số VNĐ lớn hơn 0.")
            return True
        target=int(task["admin_balance_user_id"]); amount=int(raw); direction=task["direction"]
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT name,balance FROM users WHERE id=?",(target,)); row=await cur.fetchone()
        if not row:
            pending.pop(uid,None)
            await m.answer("Không tìm thấy thành viên.")
            return True
        if direction=="sub" and row[1]<amount:
            await m.answer(f"Số dư hiện tại chỉ {row[1]:,}đ, không thể trừ {amount:,}đ. Nhập lại số tiền.")
            return True
        pending[uid]={"admin_balance_confirm":True,"admin_balance_user_id":target,"direction":direction,"amount":amount}
        await m.answer(
            f"📋 XÁC NHẬN ĐIỀU CHỈNH SỐ DƯ\\nTên: {row[0] or 'Thành viên'}\\nTelegram ID: {target}\\nSố dư hiện tại: {row[1]:,}đ\\nThao tác: {'CỘNG' if direction=='add' else 'TRỪ'} {amount:,}đ\\nSố dư sau thao tác: {(row[1]+amount if direction=='add' else row[1]-amount):,}đ\\n\\nXác nhận thực hiện?",
            reply_markup=kb([("✅ XÁC NHẬN", "ambok"), ("❌ HỦY", "ambcancel")])
        )
        return True
    if isinstance(task,dict) and "admin_product_field" in task:
        value=(m.text or "").strip(); field=task["admin_product_field"]; pid=task["product_id"]
        if not value: await m.answer("Nội dung không được để trống."); return True
        if field=="price":
            digits=re.sub(r"[^0-9]","",value)
            if not digits or int(digits)<=0: await m.answer("Giá không hợp lệ. Nhập số VNĐ lớn hơn 0."); return True
            value=int(digits)
        elif field=="description": value="" if value=="-" else value[:1500]
        else: value=value[:120]
        async with aiosqlite.connect(DB) as db:
            await db.execute(f"UPDATE products SET {field}=? WHERE id=?",(value,pid)); await db.commit()
            cur=await db.execute("SELECT active FROM products WHERE id=?",(pid,)); row=await cur.fetchone()
        pending.pop(uid,None)
        await m.answer(f"✅ Đã cập nhật sản phẩm #{pid}.")
        if task.get("config_return"):
            key = task["config_return"]
            defs = {item[0]: item[1] for item in FOLDER_DEFS}
            await m.answer("Chọn mục tiếp theo:", reply_markup=await folder_config_kb(key))
        elif row:
            await m.answer("Chọn thao tác tiếp theo:",reply_markup=product_detail_kb(pid,row[0]))
        return True
    if isinstance(task,dict) and task.get("add_stage") in {"name","description","price"}:
        value=(m.text or "").strip()
        stage=task["add_stage"]
        if not value:
            await m.answer("Thông tin không được để trống. Vui lòng nhập lại.")
            return True
        if stage=="name":
            task["name"]=value[:120]
            task["add_stage"]="description"
            pending[uid]=task
            await m.answer("BƯỚC TIẾP THEO — Nhập mô tả/chi tiết sản phẩm. Nếu không có, nhập dấu -.",reply_markup=kb([("⬅️ QUAY LẠI SỬA TÊN","apback:name")]))
        elif stage=="description":
            task["description"]="" if value=="-" else value[:1500]
            task["add_stage"]="price"
            pending[uid]=task
            await m.answer("BƯỚC CUỐI — Nhập giá bán bằng số VNĐ (ví dụ 50000).",reply_markup=kb([("⬅️ QUAY LẠI SỬA MÔ TẢ","apback:description")]))
        else:
            digits=re.sub(r"[^0-9]","",value)
            if not digits or int(digits)<=0:
                pending[uid]=task
                await m.answer("Giá không hợp lệ. Nhập số tiền VNĐ lớn hơn 0.")
                return True
            task["price"]=int(digits)
            task["add_stage"]="confirm"
            pending[uid]=task
            preview=(f"📋 XÁC NHẬN SẢN PHẨM\nDanh mục: {task['category']}\n"
                     f"Game/Dịch vụ: {task['game'] or 'Không áp dụng'}\nTên: {task['name']}\n"
                     f"Mô tả: {task['description'] or 'Chưa có'}\nGiá: {task['price']:,}đ\n\n"
                     "Chọn lưu hoặc sửa lại:")
            await m.answer(preview,reply_markup=kb([("✅ LƯU SẢN PHẨM","apc:save"),("✏️ SỬA TÊN","apc:edit"),("⬅️ QUAY LẠI SỬA GIÁ","apback:price"),("❌ HỦY","apc:cancel")]))
        return True
    if not isinstance(task,str) and not (isinstance(task,dict) and ("notify_stage" in task or "admin_price_id" in task)): return False
    if isinstance(task,dict) and task.get("notify_stage")=="user_id":
        raw=(m.text or "").strip()
        if not raw.isdigit():
            pending[uid]=task
            await m.answer("Telegram ID không hợp lệ. Vui lòng nhập ID dạng số.")
            return True
        pending[uid]={"notify_stage":"message","target_id":int(raw)}
        await m.answer(f"Đã chọn người nhận ID: {int(raw)}\\nBây giờ nhập nội dung thông báo:")
        return True
    if isinstance(task,dict) and task.get("notify_stage") in {"message","all_message"}:
        body=(m.text or "").strip()
        if not body:
            pending[uid]=task
            await m.answer("Nội dung không được để trống. Vui lòng nhập lại.")
            return True
        stage=task["notify_stage"]
        pending[uid]={"notify_stage":"confirm_all" if stage=="all_message" else "confirm","target_id":task.get("target_id"),"body":body[:3500]}
        if stage=="all_message":
            async with aiosqlite.connect(DB) as db:
                cur=await db.execute("SELECT COUNT(*) FROM users")
                total=(await cur.fetchone())[0]
            preview=f"📣 XÁC NHẬN GỬI THÔNG BÁO TOÀN BOT\\nSố tài khoản đã tham gia: {total}\\n\\n{body[:3500]}"
            buttons=[("✅ XÁC NHẬN GỬI TẤT CẢ","an:sendall"),("❌ HỦY","an:cancel")]
        else:
            preview=f"📢 XÁC NHẬN THÔNG BÁO\\nNgười nhận ID: {task['target_id']}\\n\\n{body[:3500]}"
            buttons=[("✅ XÁC NHẬN GỬI","an:send"),("❌ HỦY","an:cancel")]
        await m.answer(preview,reply_markup=kb(buttons))
        return True
    if isinstance(task,dict) and "admin_price_id" in task:
        raw=re.sub(r"[^0-9]","",m.text or "")
        if not raw or int(raw)<=0:
            await m.answer("Giá không hợp lệ. Nhập lại giá bằng số.")
            return True
        pid=task["admin_price_id"]
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE products SET price=? WHERE id=?",(int(raw),pid)); await db.commit()
        pending.pop(uid,None)
        await m.answer(f"✅ Đã cập nhật giá sản phẩm #{pid}: {int(raw):,}đ.",reply_markup=await admin_kb())
        return True
    if task=="payment":
        p=(m.text or "").split("|")
        if len(p)!=4: await m.answer("Cần đủ 4 mục, phân cách bằng |."); return True
        async with aiosqlite.connect(DB) as db: await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('payment_text',?)",("Ngân hàng: "+p[0]+"\nSố TK: "+p[1]+"\nChủ TK: "+p[2]+"\nNội dung: "+p[3])); await db.commit()
        pending[uid]="qr"; await m.answer("Đã lưu thông tin. Gửi tiếp ảnh QR để cài QR (hoặc /start để bỏ qua)."); return True
    if task=="minitext":
        async with aiosqlite.connect(DB) as db: await db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('minigame_text',?)",(m.text or "",)); await db.commit()
        pending.pop(uid,None); await m.answer("Đã cập nhật nội dung Minigame."); return True
    return False

# Admin text input handler runs before the general user text handler.
@dp.message(F.text)
async def admin_text_router(m: Message):
    if await process_admin_text(m): return
    # Continue to normal purchase/deposit input.
    uid=m.from_user.id
    if uid not in pending: return
    task=pending.pop(uid)
    if task=="deposit":
        try: amount=int(re.sub(r"[^0-9]","",m.text or ""))
        except ValueError: amount=0
        if amount<1000: return await m.answer("Số tiền không hợp lệ. Nhấn NẠP TIỀN để thử lại.")
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("INSERT INTO deposits(user_id,amount) VALUES(?,?)",(uid,amount)); did=cur.lastrowid; await db.commit()
        await m.answer(f"Đã tạo yêu cầu nạp #{did} — {amount:,}đ. Admin cần đối chiếu giao dịch thực tế trước khi duyệt.")
        for aid in ADMINS:
            try: await m.bot.send_message(aid,f"YÊU CẦU NẠP #{did}\nUser: {uid}\nSố tiền: {amount:,}đ\nDuyệt: /duyetnap {did}")
            except Exception: pass
    elif isinstance(task,dict) and "product_id" in task:
        account=(m.text or "").strip()[:120]
        if not account:
            pending[uid]=task
            return await m.answer("Tên tài khoản không được để trống. Vui lòng nhập lại.")
        task["account"]=account
        task["purchase_confirm"]=True
        pending[uid]=task
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT balance FROM users WHERE id=?",(uid,)); row=await cur.fetchone()
        balance=row[0] if row else 0
        await m.answer(f"📋 XÁC NHẬN ĐƠN HÀNG\n\nSản phẩm: {task['name']}\nTài khoản: {account}\nGiá: {task['price']:,}đ\nSố dư hiện tại: {balance:,}đ\n\nVui lòng xác nhận thanh toán.",reply_markup=kb([("✅ XÁC NHẬN THANH TOÁN","buyact:confirm"),("❌ HỦY ĐƠN","buyact:cancel")]))

async def main():
    await init_db()
    bot=Bot(TOKEN)
    try:
        me=await bot.get_me()
        logging.info("Starting @%s id=%s",me.username,me.id)
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally: await bot.session.close()

if __name__=="__main__": asyncio.run(main())
