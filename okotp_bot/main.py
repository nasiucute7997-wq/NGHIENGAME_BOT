import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape

import aiosqlite
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "6369714149").split(",") if x.strip()}
DB_PATH = os.getenv("DB_PATH", "bot.db")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN environment variable.")

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

def money(n: int) -> str:
    return f"{n:,}".replace(",", ".") + " VNĐ"

def admin(uid: int) -> bool:
    return uid in ADMIN_IDS

async def connect():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    async with await connect() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL, service_name TEXT NOT NULL,
            price INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL)""")
        await db.commit()

async def ensure_user(user):
    async with await connect() as db:
        await db.execute("""INSERT INTO users(user_id,username,full_name,created_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username, full_name=excluded.full_name""",
            (user.id, user.username or "", user.full_name or "", datetime.now(timezone.utc).isoformat()))
        await db.commit()

async def balance(uid):
    async with await connect() as db:
        cur = await db.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

def home_kb(uid):
    kb = InlineKeyboardBuilder()
    for label, data in [
        ("📱 Dịch vụ OTP", "services"), ("👤 Tài khoản", "account"),
        ("💳 Nạp số dư", "deposit"), ("📦 Đơn hàng", "orders"),
        ("☎️ Hỗ trợ", "support")]:
        kb.button(text=label, callback_data=data)
    if admin(uid):
        kb.button(text="🛠 Quản trị", callback_data="admin")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()

def back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Menu", callback_data="home")
    return kb.as_markup()

async def services_kb():
    async with await connect() as db:
        cur = await db.execute("SELECT id,name,price FROM services WHERE active=1 ORDER BY id")
        rows = await cur.fetchall()
    kb = InlineKeyboardBuilder()
    for sid, name, price in rows:
        kb.button(text=f"{name} · {money(price)}", callback_data=f"buy:{sid}")
    kb.button(text="⬅️ Menu", callback_data="home")
    kb.adjust(1)
    return kb.as_markup(), rows

async def show_orders(uid, send):
    async with await connect() as db:
        cur = await db.execute("SELECT id,service_name,price,status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
        rows = await cur.fetchall()
    if not rows:
        await send("Bạn chưa có đơn hàng nào.")
        return
    lines = ["📦 <b>ĐƠN HÀNG GẦN ĐÂY</b>"]
    for oid, name, price, status in rows:
        lines.append(f"#{oid} · {escape(name)} · {money(price)} · <b>{escape(status)}</b>")
    await send("\n".join(lines))

@dp.message(CommandStart())
async def start(m: Message):
    await ensure_user(m.from_user)
    await m.answer("🎉 <b>CHÀO MỪNG ĐẾN VỚI BOT DỊCH VỤ OTP</b>\n\nChọn chức năng bên dưới. Chỉ sử dụng mã xác minh cho tài khoản/dịch vụ bạn sở hữu hoặc được phép xác minh.", reply_markup=home_kb(m.from_user.id))

@dp.message(Command("menu"))
async def menu(m: Message):
    await ensure_user(m.from_user)
    await m.answer("🏠 <b>MENU CHÍNH</b>", reply_markup=home_kb(m.from_user.id))

@dp.message(Command("balance"))
async def balance_cmd(m: Message):
    await ensure_user(m.from_user)
    await m.answer(f"💰 Số dư: <b>{money(await balance(m.from_user.id))}</b>")

@dp.message(Command("services"))
async def services_cmd(m: Message):
    await ensure_user(m.from_user)
    kb, rows = await services_kb()
    await m.answer("📱 <b>DANH SÁCH DỊCH VỤ</b>" if rows else "Hiện chưa có dịch vụ.", reply_markup=kb)

@dp.message(Command("orders"))
async def orders_cmd(m: Message):
    await ensure_user(m.from_user)
    await show_orders(m.from_user.id, m.answer)

@dp.message(Command("deposit"))
async def deposit_cmd(m: Message):
    await m.answer("Tạo yêu cầu nạp bằng cú pháp: <code>/nap 50000</code>. Admin sẽ kiểm tra và duyệt thủ công.")

@dp.message(Command("nap"))
async def deposit_request(m: Message):
    await ensure_user(m.from_user)
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        await m.answer("Cú pháp: <code>/nap 50000</code>")
        return
    amount = int(p[1])
    if not 10000 <= amount <= 100000000:
        await m.answer("Số tiền phải từ 10.000 đến 100.000.000 VNĐ.")
        return
    async with await connect() as db:
        cur = await db.execute("INSERT INTO deposits(user_id,amount,created_at) VALUES(?,?,?)",
            (m.from_user.id, amount, datetime.now(timezone.utc).isoformat()))
        dep_id = cur.lastrowid
        await db.commit()
    await m.answer(f"✅ Đã tạo yêu cầu nạp #{dep_id}: <b>{money(amount)}</b>. Chờ admin xác nhận.")
    for aid in ADMIN_IDS:
        try:
            await m.bot.send_message(aid, f"💳 Yêu cầu nạp #{dep_id}\nUser: <code>{m.from_user.id}</code>\nSố tiền: <b>{money(amount)}</b>\nDuyệt: <code>/duyetnap {dep_id}</code> · Từ chối: <code>/huy nap {dep_id}</code>")
        except Exception:
            logging.exception("Cannot notify admin")

@dp.callback_query(F.data == "home")
async def cb_home(c: CallbackQuery):
    await c.message.edit_text("🏠 <b>MENU CHÍNH</b>", reply_markup=home_kb(c.from_user.id))
    await c.answer()

@dp.callback_query(F.data == "services")
async def cb_services(c: CallbackQuery):
    kb, rows = await services_kb()
    await c.message.edit_text("📱 <b>DANH SÁCH DỊCH VỤ</b>" if rows else "Hiện chưa có dịch vụ.", reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "account")
async def cb_account(c: CallbackQuery):
    await ensure_user(c.from_user)
    username = "@" + c.from_user.username if c.from_user.username else "Chưa đặt"
    await c.message.edit_text(f"👤 <b>THÔNG TIN TÀI KHOẢN</b>\n\nID: <code>{c.from_user.id}</code>\nTên: {escape(c.from_user.full_name)}\nUsername: {escape(username)}\nSố dư: <b>{money(await balance(c.from_user.id))}</b>", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "deposit")
async def cb_deposit(c: CallbackQuery):
    await c.message.edit_text("💳 <b>NẠP SỐ DƯ</b>\nGửi lệnh <code>/nap 50000</code>. Admin sẽ kiểm tra thủ công.", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "orders")
async def cb_orders(c: CallbackQuery):
    await c.answer()
    await show_orders(c.from_user.id, c.message.answer)

@dp.callback_query(F.data == "support")
async def cb_support(c: CallbackQuery):
    contact = "@" + SUPPORT_USERNAME.lstrip("@") if SUPPORT_USERNAME else "Vui lòng liên hệ admin."
    await c.message.edit_text(f"☎️ <b>HỖ TRỢ</b>\n{escape(contact)}", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "admin")
async def cb_admin(c: CallbackQuery):
    if not admin(c.from_user.id):
        await c.answer("Không có quyền truy cập.", show_alert=True)
        return
    await c.message.edit_text("🛠 <b>QUẢN TRỊ</b>\n/addservice Tên dịch vụ|Giá\n/delservice ID\n/duyetnap ID\n/huy nap ID\n/setbalance USER_ID SỐ_TIỀN\n/stats", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(c: CallbackQuery):
    await ensure_user(c.from_user)
    try:
        sid = int(c.data.split(":", 1)[1])
    except ValueError:
        await c.answer("Mã dịch vụ không hợp lệ.", show_alert=True)
        return
    async with await connect() as db:
        cur = await db.execute("SELECT name,price FROM services WHERE id=? AND active=1", (sid,))
        service = await cur.fetchone()
        if not service:
            await c.answer("Dịch vụ không còn hoạt động.", show_alert=True)
            return
        name, price = service
        cur = await db.execute("SELECT balance FROM users WHERE user_id=?", (c.from_user.id,))
        row = await cur.fetchone()
        if not row or int(row[0]) < price:
            await c.answer("Số dư không đủ. Hãy nạp thêm.", show_alert=True)
            return
        await db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (price, c.from_user.id))
        cur = await db.execute("INSERT INTO orders(user_id,service_id,service_name,price,status,created_at) VALUES(?,?,?,?,?,?)",
            (c.from_user.id, sid, name, price, "pending", datetime.now(timezone.utc).isoformat()))
        oid = cur.lastrowid
        await db.commit()
    await c.message.edit_text(f"✅ Đã tạo đơn <b>#{oid}</b>\nDịch vụ: {escape(name)}\nGiá: {money(price)}\nTrạng thái: <b>pending</b>\nĐơn đang chờ xử lý.", reply_markup=back_kb())
    for aid in ADMIN_IDS:
        try:
            await c.bot.send_message(aid, f"📦 Đơn mới #{oid}\nUser: {c.from_user.id}\nDịch vụ: {escape(name)}")
        except Exception:
            pass
    await c.answer("Đã tạo đơn.")

@dp.message(Command("addservice"))
async def add_service(m: Message):
    if not admin(m.from_user.id): return
    raw = (m.text or "").partition(" ")[2]
    if "|" not in raw:
        await m.answer("Cú pháp: <code>/addservice Tên dịch vụ|Giá</code>"); return
    name, price_s = [x.strip() for x in raw.rsplit("|", 1)]
    if not name or not price_s.isdigit() or int(price_s) <= 0:
        await m.answer("Tên hoặc giá không hợp lệ."); return
    async with await connect() as db:
        cur = await db.execute("INSERT INTO services(name,price) VALUES(?,?)", (name, int(price_s)))
        sid = cur.lastrowid
        await db.commit()
    await m.answer(f"✅ Đã thêm dịch vụ ID <b>{sid}</b>: {escape(name)} · {money(int(price_s))}")

@dp.message(Command("delservice"))
async def del_service(m: Message):
    if not admin(m.from_user.id): return
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        await m.answer("Cú pháp: <code>/delservice ID</code>"); return
    async with await connect() as db:
        await db.execute("UPDATE services SET active=0 WHERE id=?", (int(p[1]),))
        await db.commit()
    await m.answer("✅ Đã tắt dịch vụ.")

@dp.message(Command("duyetnap"))
async def approve_deposit(m: Message):
    if not admin(m.from_user.id): return
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        await m.answer("Cú pháp: <code>/duyetnap ID</code>"); return
    did = int(p[1])
    async with await connect() as db:
        cur = await db.execute("SELECT user_id,amount,status FROM deposits WHERE id=?", (did,))
        row = await cur.fetchone()
        if not row:
            await m.answer("Không tìm thấy yêu cầu."); return
        uid, amount, status = row
        if status != "pending":
            await m.answer("Yêu cầu đã được xử lý."); return
        await db.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
        await db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
        await db.commit()
    await m.answer(f"✅ Đã duyệt nạp #{did}: {money(amount)}.")
    try: await m.bot.send_message(uid, f"🎉 Nạp tiền thành công: <b>{money(amount)}</b>.")
    except Exception: pass

@dp.message(Command("huy"))
async def reject_deposit(m: Message):
    if not admin(m.from_user.id): return
    p = (m.text or "").split()
    if len(p) != 3 or p[1].lower() != "nap" or not p[2].isdigit():
        await m.answer("Cú pháp: <code>/huy nap ID</code>"); return
    did = int(p[2])
    async with await connect() as db:
        cur = await db.execute("SELECT user_id,status FROM deposits WHERE id=?", (did,))
        row = await cur.fetchone()
        if not row:
            await m.answer("Không tìm thấy yêu cầu."); return
        uid, status = row
        if status != "pending":
            await m.answer("Yêu cầu đã được xử lý."); return
        await db.execute("UPDATE deposits SET status='rejected' WHERE id=?", (did,))
        await db.commit()
    await m.answer(f"Đã từ chối yêu cầu nạp #{did}.")
    try: await m.bot.send_message(uid, f"Yêu cầu nạp #{did} đã bị từ chối.")
    except Exception: pass

@dp.message(Command("setbalance"))
async def set_balance(m: Message):
    if not admin(m.from_user.id): return
    p = (m.text or "").split()
    if len(p) != 3 or not p[1].isdigit() or not p[2].isdigit():
        await m.answer("Cú pháp: <code>/setbalance USER_ID SỐ_TIỀN</code>"); return
    uid, amount = int(p[1]), int(p[2])
    async with await connect() as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id=?", (uid,))
        if not await cur.fetchone():
            await m.answer("User chưa từng mở bot."); return
        await db.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, uid))
        await db.commit()
    await m.answer(f"✅ Đã đặt số dư user {uid}: {money(amount)}")

@dp.message(Command("stats"))
async def stats(m: Message):
    if not admin(m.from_user.id): return
    async with await connect() as db:
        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
        pending = (await (await db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")).fetchone())[0]
    await m.answer(f"📊 <b>THỐNG KÊ</b>\nNgười dùng: {users}\nĐơn hàng: {orders}\nNạp chờ duyệt: {pending}")

@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not admin(m.from_user.id):
        await m.answer("Bạn không có quyền."); return
    await m.answer("🛠 <b>LỆNH ADMIN</b>\n/addservice Tên|Giá\n/delservice ID\n/duyetnap ID\n/huy nap ID\n/setbalance USER_ID SỐ_TIỀN\n/stats")

async def main():
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
