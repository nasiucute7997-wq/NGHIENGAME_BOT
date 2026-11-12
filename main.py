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
DB = os.getenv("DB_PATH", "/data/bot.db")
if not TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
dp = Dispatcher()
pending = {}

GAMES = ["XX8", "AD88", "U888", "ABC8", "MM88", "RR88", "XX88", "GG88"]

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
        """)
        try:
            await db.execute("ALTER TABLE products ADD COLUMN description TEXT DEFAULT ''")
        except Exception:
            pass
        await db.commit()

def kb(rows):
    b = InlineKeyboardBuilder()
    for label, data in rows: b.button(text=label, callback_data=data)
    b.adjust(1)
    return b.as_markup()


def back():
    return kb([("⬅️ QUAY LẠI MENU", "m:home")])


FOLDER_DEFS = [
    ("home_code", "🎮 CODE GAME", "Thư mục khách hàng"),
    ("home_mini", "🎯 MINIGAME LIVE", "Thư mục khách hàng"),
    ("home_share", "🔗 CODE SHARE", "Thư mục khách hàng"),
    ("home_services", "🛠 DỊCH VỤ KHÁC", "Thư mục khách hàng"),
    ("home_account", "👤 TÀI KHOẢN", "Thư mục khách hàng"),
    ("home_deposit", "💳 NẠP TIỀN", "Thư mục khách hàng"),
    ("home_orders", "📋 LỊCH SỬ ĐƠN", "Thư mục khách hàng"),
    ("home_contact", "📞 LIÊN HỆ ADMIN", "Thư mục khách hàng"),
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
        ("home_code", "🎮 CODE GAME","m:code"),("home_mini","🎯 MINIGAME LIVE","m:mini"),
        ("home_share","🔗 CODE SHARE","m:share"),("home_services","🛠 DỊCH VỤ KHÁC","m:services"),
        ("home_account","👤 TÀI KHOẢN","m:account"),("home_deposit","💳 NẠP TIỀN","m:deposit"),
        ("home_orders","📋 LỊCH SỬ ĐƠN","m:orders"),("home_contact","📞 LIÊN HỆ ADMIN","m:contact")
    ]
    for key, label, data in items:
        if await folder_is_on(key):
            b.button(text=label, callback_data=data)
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
    for key, label, data in items:
        if await folder_is_on(key):
            b.button(text=label, callback_data=data)
    b.button(text="⚙️ BẬT/TẮT TẤT CẢ THƯ MỤC", callback_data="a:folders")
    b.button(text="🔄 LÀM MỚI MENU", callback_data="a:refresh")
    b.button(text="⬅️ MENU CHÍNH", callback_data="m:home")
    b.adjust(2)
    return b.as_markup()

async def folders_kb():
    b = InlineKeyboardBuilder()
    for key, label, group in FOLDER_DEFS:
        enabled = await folder_is_on(key)
        b.button(text=f"{'🟢 ON' if enabled else '🔴 OFF'} | {label}", callback_data=f"af:{key}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:folders")
    b.button(text="⬅️ MENU ADMIN", callback_data="a:refresh")
    b.adjust(1)
    return b.as_markup()

def admin_products_kb(rows):
    b = InlineKeyboardBuilder()
    for pid, category, game, name, price, active in rows:
        site = f"{category}/{game}" if game else category
        b.button(text=f"⚙️ THAO TÁC #{pid} · {site}"[:64], callback_data=f"apd:{pid}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:products")
    b.button(text="⬅️ MENU ADMIN", callback_data="a:refresh")
    b.adjust(1)
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
        label = f"{'🚫' if blocked else '👤'} {name or 'Thành viên'} · ID {uid}"[:60]
        b.button(text=label, callback_data=f"amu:{uid}")
    b.button(text="🔎 TÌM THÀNH VIÊN KHÁC", callback_data="am:users")
    b.button(text="⬅️ MENU QUẢN TRỊ", callback_data="a:refresh")
    b.adjust(1)
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
        cur=await db.execute("SELECT id,name,price FROM products WHERE active=1 AND category=? AND (game=? OR game='') ORDER BY id",(category,game))
        rows=await cur.fetchall()
    if not rows:
        await message.edit_text("Hiện chưa có sản phẩm được mở bán.",reply_markup=back()); return
    await message.edit_text("Chọn sản phẩm:",reply_markup=kb([(f"{n} — {p:,}đ",f"buy:{i}") for i,n,p in rows]+[("⬅️ Quay lại","m:home")]))

@dp.message(CommandStart())
async def start(m: Message):
    await ensure_user(m.from_user)
    if m.from_user.id not in ADMINS:
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT blocked FROM users WHERE id=?",(m.from_user.id,)); blocked=(await cur.fetchone())[0]
        if blocked:
            return await m.answer("🚫 Tài khoản của bạn hiện đang bị khóa. Vui lòng liên hệ Admin.")
    await m.answer(f"🏮🏮🏮🏮\n\n🔥 Xin chào, {m.from_user.full_name}!\n\n👥 Chào mừng đến NGHIỆN CODE.\nChọn dịch vụ bên dưới:",reply_markup=await home_kb(m.from_user.id in ADMINS))

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
    if key=="home": return await c.message.edit_text("🏠 MENU CHÍNH",reply_markup=await home_kb(c.from_user.id in ADMINS))
    if key=="admin":
        if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
        await c.message.edit_text("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=await admin_kb())
        return await c.answer()
    if key in {"code","mini","share","services","account","deposit","orders","contact"}:
        folder_key = {"code":"home_code","mini":"home_mini","share":"home_share","services":"home_services","account":"home_account","deposit":"home_deposit","orders":"home_orders","contact":"home_contact"}[key]
        if not await folder_is_on(folder_key):
            return await c.answer("Thư mục này hiện đang tắt.", show_alert=True)
    if key=="code":
        await c.message.edit_text("Chọn game CODE GAME:",reply_markup=kb2([(g,f"game:{g}") for g in GAMES if await folder_is_on(f"game_{g}")]+[("⬅️ Menu","m:home")]))
    elif key=="share":
        await page_products(c.message,"SHARE")
    elif key=="services":
        await c.message.edit_text("Chọn dịch vụ:",reply_markup=kb([(label,data) for key,label,data in [("service_sms_receive","SMS NHẬN","cat:SMS"),("service_sms_send","SMS GỬI","cat:SMS"),("service_proxy","PROXY / PRX","cat:PRX")] if await folder_is_on(key)]+[("⬅️ Menu","m:home")]))
    elif key=="account":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT balance FROM users WHERE id=?",(c.from_user.id,)); row=await cur.fetchone()
        me=await c.bot.get_me()
        await c.message.edit_text(f"👤 TÀI KHOẢN\nTên: {c.from_user.full_name}\nID: {c.from_user.id}\nSố dư: {(row[0] if row else 0):,}đ\n\nLink chia sẻ: https://t.me/{me.username}?start=ref_{c.from_user.id}",reply_markup=back())
    elif key=="deposit":
        pending[c.from_user.id]="deposit"
        qr=await setting("qr_file_id")
        detail=await setting("payment_text","Admin chưa cài thông tin thanh toán.")
        text="💳 NẠP TIỀN\n"+detail+"\n\nNhập số tiền muốn nạp (VNĐ)."
        if qr:
            try: await c.message.answer_photo(qr,caption=text)
            except Exception: await c.message.answer(text)
        else: await c.message.answer(text)
    elif key=="orders":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,product_name,price,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",(c.from_user.id,))
            rows=await cur.fetchall()
        text="📋 LỊCH SỬ ĐƠN\n"+("\n".join([f"#{i} | {n} | {p:,}đ | {s} | {t}" for i,n,p,s,t in rows]) if rows else "Chưa có đơn hàng.")
        await c.message.edit_text(text,reply_markup=back())
    elif key=="mini":
        body=await setting("minigame_text","Thông tin Minigame LIVE sẽ được Admin cập nhật tại đây. Vui lòng đọc kỹ thể lệ và điều kiện tham gia do đơn vị tổ chức công bố.")
        await c.message.edit_text("🎯 MINIGAME LIVE\n\n"+body,reply_markup=back())
    elif key=="contact":
        await c.message.edit_text("📞 Vui lòng liên hệ Admin để được hỗ trợ.",reply_markup=back())
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
    await c.message.answer("Vui lòng nhập tên tài khoản cần đặt. Nếu không yêu cầu tài khoản, nhập dấu -.")
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
    await c.message.edit_text("⚙️ BẬT/TẮT THƯ MỤC\\nĐã cập nhật trạng thái. Chọn tiếp thư mục:", reply_markup=await folders_kb())
    await c.answer("Đã đổi trạng thái.")

@dp.callback_query(F.data.startswith("a:"))
async def admin_actions(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    key=c.data.split(":")[1]
    folder_key = {"add":"admin_add","products":"admin_products","deposits":"admin_deposits","orders":"admin_orders","payment":"admin_payment","notify":"admin_notify","notifyall":"admin_notifyall","minitext":"admin_minitext"}.get(key)
    if folder_key and not await folder_is_on(folder_key):
        return await c.answer("Thư mục quản trị này hiện đang tắt.", show_alert=True)
    if key=="folders":
        await c.message.edit_text("⚙️ BẬT/TẮT THƯ MỤC\\nBấm ON/OFF để thay đổi trạng thái:", reply_markup=await folders_kb())
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
    else:
        pending[c.from_user.id]={"add_stage":"name","category":category,"game":""}
        await c.message.edit_text(f"Danh mục: {category}\nBƯỚC 2/4 — Nhập tên sản phẩm/dịch vụ:",reply_markup=kb([("⬅️ QUAY LẠI CHỌN DANH MỤC","apback:category")]))
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
    await c.answer()

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
    await c.message.answer(f"{'➕ CỘNG' if direction=='add' else '➖ TRỪ'} SỐ DƯ cho ID {target}\\nNhập số tiền VNĐ:",reply_markup=kb([("⬅️ HỦY","amcancel:"+target)]))
    await c.answer()

@dp.callback_query(F.data.startswith("amcancel:"))
async def admin_balance_cancel(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    pending.pop(c.from_user.id,None)
    await admin_user_detail(c)
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
    if isinstance(task,dict) and "admin_balance_user_id" in task:
        raw=re.sub(r"[^0-9]","",m.text or "")
        if not raw or int(raw)<=0:
            await m.answer("Số tiền không hợp lệ. Nhập số VNĐ lớn hơn 0.")
            return True
        target=int(task["admin_balance_user_id"]); amount=int(raw); direction=task["direction"]
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT balance FROM users WHERE id=?",(target,)); row=await cur.fetchone()
            if not row:
                pending.pop(uid,None)
                await m.answer("Không tìm thấy thành viên.")
                return True
            if direction=="sub" and row[0]<amount:
                await m.answer(f"Số dư hiện tại chỉ {row[0]:,}đ, không thể trừ {amount:,}đ.")
                return True
            delta=amount if direction=="add" else -amount
            await db.execute("UPDATE users SET balance=balance+? WHERE id=?",(delta,target))
            await db.execute("INSERT INTO admin_logs(admin_id,action) VALUES(?,?)",(uid,f"balance {direction} {amount} user {target}"))
            await db.commit()
        pending.pop(uid,None)
        await m.answer(f"Đã {'cộng' if direction=='add' else 'trừ'} {amount:,}đ cho ID {target}.",reply_markup=kb([("👤 XEM THÀNH VIÊN",f"amu:{target}"),("⬅️ MENU QUẢN TRỊ","a:refresh")]))
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
        pending.pop(uid,None); await m.answer(f"Đã cập nhật sản phẩm #{pid}.")
        if row: await m.answer("Chọn thao tác tiếp theo:",reply_markup=product_detail_kb(pid,row[0]))
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
    elif isinstance(task,dict):
        p=task; account=(m.text or "").strip()[:120]
        async with aiosqlite.connect(DB) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur=await db.execute("SELECT balance FROM users WHERE id=?",(uid,)); row=await cur.fetchone(); bal=row[0] if row else 0
            if bal<p["price"]:
                await db.rollback(); return await m.answer(f"Không đủ số dư. Hiện có {bal:,}đ, cần {p['price']:,}đ.")
            await db.execute("UPDATE users SET balance=balance-? WHERE id=?",(p["price"],uid))
            cur=await db.execute("INSERT INTO orders(user_id,product_id,category,product_name,game,account,price) VALUES(?,?,?,?,?,?,?)",(uid,p["product_id"],p["category"],p["name"],p["game"],account,p["price"]))
            oid=cur.lastrowid; await db.commit()
        await m.answer(f"Đã tạo đơn #{oid}. Sản phẩm: {p['name']}\nTài khoản: {account}\nSố tiền: {p['price']:,}đ. Đơn đang xử lý.")
        for aid in ADMINS:
            try: await m.bot.send_message(aid,f"ĐƠN #{oid}\nUser {uid}\n{p['name']}\nTK: {account}\n{p['price']:,}đ")
            except Exception: pass

async def main():
    await init_db()
    bot=Bot(TOKEN)
    try:
        me=await bot.get_me()
        logging.info("Starting @%s id=%s",me.username,me.id)
        await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally: await bot.session.close()

if __name__=="__main__": asyncio.run(main())
