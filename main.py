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
]

async def folder_is_on(key):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (f"folder:{key}",))
        row = await cur.fetchone()
    return row is None or row[0] != "0"

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
        b.button(text=f"💵 SỬA GIÁ #{pid}", callback_data=f"ap:{pid}")
        b.button(text=f"{'🔴 TẮT' if active else '🟢 BẬT'} #{pid}", callback_data=f"at:{pid}")
    b.button(text="🔄 TẢI LẠI", callback_data="a:products")
    b.button(text="⬅️ MENU ADMIN", callback_data="a:refresh")
    b.adjust(2)
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
    await m.answer(f"🏮🏮🏮🏮\n\n🔥 Xin chào, {m.from_user.full_name}!\n\n👥 Chào mừng đến NGHIỆN CODE.\nChọn dịch vụ bên dưới:",reply_markup=await home_kb(m.from_user.id in ADMINS))

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMINS: return await m.answer("Bạn không có quyền.")
    await m.answer("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=await admin_kb())

@dp.callback_query(F.data.startswith("m:"))
async def menus(c: CallbackQuery):
    key=c.data.split(":")[1]
    if key=="home": return await c.message.edit_text("🏠 MENU CHÍNH",reply_markup=await home_kb(c.from_user.id in ADMINS))
    if key=="admin":
        if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
        await c.message.edit_text("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=admin_kb())
        return await c.answer()
    if key in {"code","mini","share","services","account","deposit","orders","contact"}:
        folder_key = {"code":"home_code","mini":"home_mini","share":"home_share","services":"home_services","account":"home_account","deposit":"home_deposit","orders":"home_orders","contact":"home_contact"}[key]
        if not await folder_is_on(folder_key):
            return await c.answer("Thư mục này hiện đang tắt.", show_alert=True)
    if key=="code":
        await c.message.edit_text("Chọn game CODE GAME:",reply_markup=kb([(g,f"game:{g}") for g in GAMES]+[("⬅️ Menu","m:home")]))
    elif key=="share":
        await page_products(c.message,"SHARE")
    elif key=="services":
        await c.message.edit_text("Chọn dịch vụ:",reply_markup=kb([("SMS NHẬN","cat:SMS"),("SMS GỬI","cat:SMS"),("PROXY / PRX","cat:PRX"),("⬅️ Menu","m:home")]))
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
    await page_products(c.message,"GAME",c.data.split(":")[1]); await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def category(c: CallbackQuery):
    await page_products(c.message,c.data.split(":")[1]); await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
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
        await c.message.edit_text("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=admin_kb())
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
        await c.message.edit_text(body,reply_markup=kb([("🔄 TẢI LẠI","a:orders"),("⬅️ MENU ADMIN","a:refresh")]))
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
        await c.message.edit_text("BƯỚC 2/4 — Chọn game:",reply_markup=kb([(g,f"agw:{g}") for g in GAMES]+[("⬅️ Quay lại","a:add")]))
    else:
        pending[c.from_user.id]={"add_stage":"name","category":category,"game":""}
        await c.message.edit_text(f"Danh mục: {category}\nBƯỚC 2/4 — Nhập tên sản phẩm/dịch vụ:")
    await c.answer()

@dp.callback_query(F.data.startswith("agw:"))
async def add_product_game(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    game=c.data.split(":",1)[1]
    if game not in GAMES: return await c.answer("Game không hợp lệ.",show_alert=True)
    pending[c.from_user.id]={"add_stage":"name","category":"GAME","game":game}
    await c.message.edit_text(f"Danh mục: GAME\nGame: {game}\nBƯỚC 3/4 — Nhập tên sản phẩm:")
    await c.answer()

@dp.callback_query(F.data.startswith("apc:"))
async def add_product_confirm(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    task=pending.get(c.from_user.id)
    if not isinstance(task,dict) or task.get("add_stage")!="confirm": return await c.answer("Phiên thêm sản phẩm đã hết.",show_alert=True)
    action=c.data.split(":",1)[1]
    if action=="cancel":
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("Đã hủy thêm sản phẩm.",reply_markup=admin_kb())
    elif action=="edit":
        task["add_stage"]="name"
        pending[c.from_user.id]=task
        await c.message.edit_text("Nhập lại tên sản phẩm:")
    elif action=="save":
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT INTO products(category,game,name,price,description) VALUES(?,?,?,?,?)",(task["category"],task["game"],task["name"],task["price"],task["description"]))
            await db.commit()
        pending.pop(c.from_user.id,None)
        await c.message.edit_text("✅ Đã lưu sản phẩm.",reply_markup=admin_kb())
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
        await c.message.edit_text("Đã hủy gửi thông báo.",reply_markup=admin_kb())
        return await c.answer()
    if action=="send" and task.get("notify_stage")=="confirm":
        try:
            await c.bot.send_message(task["target_id"],task["body"])
        except Exception as e:
            pending.pop(c.from_user.id,None)
            await c.message.edit_text(f"❌ Không gửi được đến ID {task['target_id']}. Có thể người nhận chưa từng mở bot hoặc đã chặn bot. Chi tiết: {str(e)[:180]}",reply_markup=admin_kb())
            return await c.answer("Gửi thất bại.",show_alert=True)
        pending.pop(c.from_user.id,None)
        await c.message.edit_text(f"✅ Đã gửi thông báo thành công đến Telegram ID {task['target_id']}.",reply_markup=admin_kb())
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
        await c.message.edit_text(f"📣 ĐÃ GỬI THÔNG BÁO TOÀN BOT\\nThành công: {sent}\\nKhông gửi được: {failed}\\nTổng tài khoản: {len(recipients)}",reply_markup=admin_kb())
        return await c.answer("Đã hoàn tất gửi.")
    return await c.answer("Thao tác không hợp lệ.",show_alert=True)

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
    async with aiosqlite.connect(DB) as db:
        cur=await db.execute("SELECT id,category,game,name,price,active FROM products ORDER BY id DESC LIMIT 30"); rows=await cur.fetchall()
    body="📦 QUẢN LÝ SẢN PHẨM\\n"+("\\n".join([f"#{i} [{cat}/{g}] {n} — {p:,}đ ({'ĐANG BẬT' if a else 'ĐANG TẮT'})" for i,cat,g,n,p,a in rows]) if rows else "Chưa có sản phẩm.")
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
            await m.answer("BƯỚC TIẾP THEO — Nhập mô tả/chi tiết sản phẩm. Nếu không có, nhập dấu -.")
        elif stage=="description":
            task["description"]="" if value=="-" else value[:1500]
            task["add_stage"]="price"
            pending[uid]=task
            await m.answer("BƯỚC CUỐI — Nhập giá bán bằng số VNĐ (ví dụ 50000).")
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
            await m.answer(preview,reply_markup=kb([("✅ LƯU SẢN PHẨM","apc:save"),("✏️ SỬA TÊN","apc:edit"),("❌ HỦY","apc:cancel")]))
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
        await m.answer(f"✅ Đã cập nhật giá sản phẩm #{pid}: {int(raw):,}đ.",reply_markup=admin_kb())
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
