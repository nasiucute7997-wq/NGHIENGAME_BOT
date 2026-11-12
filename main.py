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
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, game TEXT DEFAULT '', name TEXT NOT NULL, price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER, category TEXT, product_name TEXT, game TEXT, account TEXT, price INTEGER, status TEXT DEFAULT 'processing', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        await db.commit()

def kb(rows):
    b = InlineKeyboardBuilder()
    for label, data in rows: b.button(text=label, callback_data=data)
    b.adjust(1)
    return b.as_markup()

def home_kb():
    return kb([
        ("🎮 CODE GAME","m:code"),("🎯 MINIGAME LIVE","m:mini"),
        ("🔗 CODE SHARE","m:share"),("🛠 DỊCH VỤ KHÁC","m:services"),
        ("👤 TÀI KHOẢN","m:account"),("💳 NẠP TIỀN","m:deposit"),
        ("📋 LỊCH SỬ ĐƠN","m:orders"),("📞 LIÊN HỆ ADMIN","m:contact")
    ])

def back(): return kb([("⬅️ MENU CHÍNH","m:home")])
def admin_kb(): return kb([
    ("➕ THÊM SẢN PHẨM","a:add"),("📦 DANH SÁCH SẢN PHẨM","a:products"),
    ("💰 DUYỆT NẠP TIỀN","a:deposits"),("🧾 ĐƠN HÀNG","a:orders"),
    ("🏦 CÀI ĐẶT THANH TOÁN","a:payment"),("✏️ SỬA NỘI DUNG MINIGAME","a:minitext"),
    ("⬅️ MENU CHÍNH","m:home")
])

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
    await m.answer(f"🏮🏮🏮🏮\n\n🔥 Xin chào, {m.from_user.full_name}!\n\n👥 Chào mừng đến NGHIỆN CODE.\nChọn dịch vụ bên dưới:",reply_markup=home_kb())

@dp.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in ADMINS: return await m.answer("Bạn không có quyền.")
    await m.answer("🛠 TRUNG TÂM QUẢN TRỊ",reply_markup=admin_kb())

@dp.callback_query(F.data.startswith("m:"))
async def menus(c: CallbackQuery):
    key=c.data.split(":")[1]
    if key=="home": return await c.message.edit_text("🏠 MENU CHÍNH",reply_markup=home_kb())
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

@dp.callback_query(F.data.startswith("a:"))
async def admin_actions(c: CallbackQuery):
    if c.from_user.id not in ADMINS: return await c.answer("Không có quyền.",show_alert=True)
    key=c.data.split(":")[1]
    if key=="add":
        pending[c.from_user.id]="addproduct"
        await c.message.answer("Nhập: DANH_MỤC|GAME|TÊN SẢN PHẨM|GIÁ\nVí dụ: GAME|XX8|CODE 100K|50000\nDanh mục: GAME, SHARE, SMS, PRX.")
    elif key=="products":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,category,game,name,price,active FROM products ORDER BY id DESC LIMIT 30"); rows=await cur.fetchall()
        await c.message.answer("📦 SẢN PHẨM\n"+("\n".join([f"#{i} [{cat}/{g}] {n} — {p:,}đ ({'ON' if a else 'OFF'})" for i,cat,g,n,p,a in rows]) if rows else "Chưa có sản phẩm.")+"\nSửa giá: /price ID GIÁ | Bật/tắt: /toggle ID")
    elif key=="deposits":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,user_id,amount,status FROM deposits WHERE status='pending' ORDER BY id"); rows=await cur.fetchall()
        await c.message.answer("💰 YÊU CẦU NẠP\n"+("\n".join([f"#{i} User {u} — {a:,}đ — {s}" for i,u,a,s in rows]) if rows else "Không có yêu cầu chờ duyệt.")+"\nDuyệt: /duyetnap ID")
    elif key=="orders":
        async with aiosqlite.connect(DB) as db:
            cur=await db.execute("SELECT id,user_id,product_name,price,status FROM orders ORDER BY id DESC LIMIT 20"); rows=await cur.fetchall()
        await c.message.answer("🧾 ĐƠN HÀNG\n"+("\n".join([f"#{i} User {u} {n} {p:,}đ [{s}]" for i,u,n,p,s in rows]) if rows else "Chưa có đơn."))
    elif key=="payment":
        pending[c.from_user.id]="payment"
        await c.message.answer("Nhập thông tin thanh toán: TÊN NGÂN HÀNG|SỐ TK|CHỦ TK|NỘI DUNG CHUYỂN KHOẢN")
    elif key=="minitext":
        pending[c.from_user.id]="minitext"
        await c.message.answer("Nhập nội dung hiển thị cho mục MINIGAME LIVE (chỉ thông tin/thể lệ).")
    await c.answer()

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
    if uid not in ADMINS or not isinstance(task,str): return False
    if task=="addproduct":
        p=(m.text or "").split("|",3)
        if len(p)!=4 or p[0].strip().upper() not in {"GAME","SHARE","SMS","PRX"} or not p[3].strip().isdigit():
            await m.answer("Sai định dạng. Ví dụ: GAME|XX8|CODE 100K|50000"); return True
        async with aiosqlite.connect(DB) as db: await db.execute("INSERT INTO products(category,game,name,price) VALUES(?,?,?,?)",(p[0].strip().upper(),p[1].strip().upper(),p[2].strip(),int(p[3]))); await db.commit()
        pending.pop(uid,None); await m.answer("Đã thêm sản phẩm."); return True
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
