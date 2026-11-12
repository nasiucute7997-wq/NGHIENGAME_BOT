import asyncio
import logging
import os
import sqlite3
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
BRANDS = ["XX8", "AD88", "U888", "ABC8", "MM88", "RR88", "XX88", "GG88"]
SPECIAL = {"THU": "HI88", "FRI": "QQ88"}

def now():
    return datetime.now(timezone.utc).isoformat()

def money(value):
    return f"{int(value):,}".replace(",", ".") + " VNĐ"

def is_admin(uid):
    return uid in ADMIN_IDS

async def db_connect():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    async with await db_connect() as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS services(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
        columns = await (await db.execute("PRAGMA table_info(services)")).fetchall()
        if "category" not in {row[1] for row in columns}:
            await db.execute("ALTER TABLE services ADD COLUMN category TEXT NOT NULL DEFAULT 'OTHER'")
        await db.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL, service_name TEXT NOT NULL,
            price INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS saved_accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            alias TEXT NOT NULL, game TEXT NOT NULL, account_ref TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(user_id,alias))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS captured_codes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL, game TEXT NOT NULL, code TEXT NOT NULL,
            source_chat_id INTEGER, source_message_id INTEGER,
            status TEXT NOT NULL DEFAULT 'saved', created_at TEXT NOT NULL,
            UNIQUE(user_id,code))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS minigame_rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL,
            title TEXT NOT NULL, starts_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', result TEXT DEFAULT '',
            created_at TEXT NOT NULL)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS minigame_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(room_id,user_id))""")
        await db.commit()

async def ensure_user(user):
    async with await db_connect() as db:
        await db.execute("""INSERT INTO users(user_id,username,full_name,created_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username, full_name=excluded.full_name""",
            (user.id, user.username or "", user.full_name or "", now()))
        await db.commit()

async def get_balance(uid):
    async with await db_connect() as db:
        row = await (await db.execute("SELECT balance FROM users WHERE user_id=?", (uid,))).fetchone()
        return int(row[0]) if row else 0

def home_kb(uid):
    kb = InlineKeyboardBuilder()
    for label, data in [
        ("🎮 CODE GAME", "cat:GAME"),
        ("🏆 MINIGAME LIVE", "minigames"),
        ("🧩 DỊCH VỤ KHÁC", "other_services"),
        ("👤 Tài khoản", "account"),
        ("💳 Nạp tiền", "deposit"),
        ("📦 Lịch sử đơn", "orders"),
        ("📖 Hướng dẫn", "guide"),
        ("☎️ Liên hệ Admin", "support"),
    ]:
        kb.button(text=label, callback_data=data)
    if is_admin(uid):
        kb.button(text="🛠 ADMIN PANEL", callback_data="admin")
    kb.adjust(2, 1, 2, 2, 1, 1)
    return kb.as_markup()

def back_kb(target="home"):
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Quay lại", callback_data=target)
    return kb.as_markup()

async def service_keyboard(category):
    async with await db_connect() as db:
        rows = await (await db.execute(
            "SELECT id,name,price FROM services WHERE active=1 AND category=? ORDER BY id",
            (category,))).fetchall()
    kb = InlineKeyboardBuilder()
    for sid, name, price in rows:
        kb.button(text=f"{name} · {money(price)}", callback_data=f"buy:{sid}")
    kb.button(text="⬅️ Menu chính", callback_data="home")
    kb.adjust(1)
    return kb.as_markup(), rows

async def send_orders(uid, send):
    async with await db_connect() as db:
        rows = await (await db.execute(
            "SELECT id,service_name,price,status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (uid,))).fetchall()
    if not rows:
        await send("Bạn chưa có đơn hàng nào.")
        return
    lines = ["📦 <b>LỊCH SỬ ĐƠN HÀNG</b>"]
    for oid, name, price, status in rows:
        lines.append(f"#{oid} · {escape(name)} · {money(price)} · <b>{escape(status)}</b>")
    await send("\n".join(lines))


def code_menu_kb(accounts, code):
    kb = InlineKeyboardBuilder()
    for aid, alias, game, account_ref in accounts:
        kb.button(text=f"{alias} · {game}", callback_data=f"codeacct:{aid}:{code}")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("addaccount"))
async def add_saved_account(m: Message):
    await ensure_user(m.from_user)
    parts = [x.strip() for x in (m.text or "").partition(" ")[2].split("|")]
    if len(parts) != 3 or not all(parts):
        await m.answer("Cú pháp: <code>/addaccount Tên_gợi_nhớ|GAME|Tên_đăng_nhập</code>\\nVí dụ: <code>/addaccount Acc chính|XX8|user123</code>\\nKhông nhập mật khẩu hoặc mã OTP.")
        return
    alias, game, account_ref = parts
    if len(alias) > 40 or len(game) > 30 or len(account_ref) > 80:
        await m.answer("Thông tin quá dài. Vui lòng rút gọn.")
        return
    async with await db_connect() as db:
        try:
            await db.execute("INSERT INTO saved_accounts(user_id,alias,game,account_ref,created_at) VALUES(?,?,?,?,?)",
                             (m.from_user.id, alias, game.upper(), account_ref, now()))
            await db.commit()
        except sqlite3.IntegrityError:
            await m.answer("Tên gợi nhớ này đã tồn tại. Hãy chọn tên khác.")
            return
    await m.answer(f"✅ Đã lưu tài khoản <b>{escape(alias)}</b> · {escape(game.upper())} · <code>{escape(account_ref)}</code>.")

@dp.message(Command("accounts"))
async def list_saved_accounts(m: Message):
    await ensure_user(m.from_user)
    async with await db_connect() as db:
        rows = await (await db.execute("SELECT id,alias,game,account_ref FROM saved_accounts WHERE user_id=? ORDER BY id DESC",
                                       (m.from_user.id,))).fetchall()
    if not rows:
        await m.answer("Bạn chưa lưu tài khoản. Dùng /addaccount Tên_gợi_nhớ|GAME|Tên_đăng_nhập")
        return
    lines = ["👤 <b>TÀI KHOẢN ĐÃ LƯU</b>"]
    for aid, alias, game, ref in rows:
        lines.append(f"#{aid} · {escape(alias)} · {escape(game)} · <code>{escape(ref)}</code>")
    await m.answer("\\n".join(lines))

def extract_code(text):
    import re
    if not text:
        return None
    # Chỉ nhận chuỗi được gắn nhãn CODE/MÃ/GIFT/VOUCHER để hạn chế quét nhầm.
    patterns = [
        r"(?i)(?:CODE|MÃ\\s*CODE|GIFT\\s*CODE|VOUCHER)\\s*[:：=\\-]?\\s*([A-Z0-9][A-Z0-9-]{5,31})",
        r"(?i)(?:MÃ|CODE)\\s*[:：]\\s*([A-Z0-9][A-Z0-9-]{5,31})"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).upper()
    return None

@dp.message(Command("scan"))
async def scan_telegram_message(m: Message):
    await ensure_user(m.from_user)
    source = m.reply_to_message
    if not source:
        await m.answer("Hãy trả lời (Reply) tin nhắn Telegram có mã rồi gửi /scan.")
        return
    body = source.text or source.caption or ""
    code = extract_code(body)
    if not code:
        await m.answer("❌ Không tìm thấy mã theo định dạng có nhãn CODE/MÃ/GIFT/VOUCHER. Bạn có thể gửi lại tin nhắn kèm cú pháp CODE: ABC123.")
        return
    async with await db_connect() as db:
        exists = await (await db.execute("SELECT id FROM captured_codes WHERE user_id=? AND code=?",
                                         (m.from_user.id, code))).fetchone()
        if exists:
            await m.answer(f"⚠️ Mã <code>{escape(code)}</code> đã được lưu trước đó (#{exists[0]}).")
            return
        accounts = await (await db.execute("SELECT id,alias,game,account_ref FROM saved_accounts WHERE user_id=? ORDER BY id",
                                           (m.from_user.id,))).fetchall()
    if not accounts:
        await m.answer("Bạn chưa có tài khoản lưu sẵn. Tạo bằng /addaccount Tên_gợi_nhớ|GAME|Tên_đăng_nhập rồi quét lại.")
        return
    await m.answer(f"🔎 Phát hiện mã: <code>{escape(code)}</code>\\nChọn tài khoản muốn gắn mã:", reply_markup=code_menu_kb(accounts, code))

@dp.callback_query(F.data.startswith("codeacct:"))
async def choose_code_account(c: CallbackQuery):
    if not c.message:
        await c.answer()
        return
    try:
        _, aid_text, code = c.data.split(":", 2)
        aid = int(aid_text)
    except (ValueError, AttributeError):
        await c.answer("Dữ liệu không hợp lệ.", show_alert=True)
        return
    async with await db_connect() as db:
        account = await (await db.execute("SELECT alias,game,account_ref FROM saved_accounts WHERE id=? AND user_id=?",
                                          (aid,c.from_user.id))).fetchone()
    if not account:
        await c.answer("Không tìm thấy tài khoản của bạn.", show_alert=True)
        return
    alias, game, account_ref = account
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Xác nhận lưu mã", callback_data=f"codesave:{aid}:{code}")
    kb.button(text="❌ Hủy", callback_data="home")
    kb.adjust(1)
    await c.message.edit_text(
        f"🔐 <b>XÁC NHẬN GẮN MÃ</b>\\nMã: <code>{escape(code)}</code>\\nGame: <b>{escape(game)}</b>\\nTài khoản: <b>{escape(alias)}</b> (<code>{escape(account_ref)}</code>)\\n\\nBot chỉ lưu mã vào danh sách của tài khoản; chưa tự đăng nhập hoặc đổi thưởng.",
        reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("codesave:"))
async def save_captured_code(c: CallbackQuery):
    try:
        _, aid_text, code = c.data.split(":", 2)
        aid = int(aid_text)
    except (ValueError, AttributeError):
        await c.answer("Dữ liệu không hợp lệ.", show_alert=True)
        return
    async with await db_connect() as db:
        account = await (await db.execute("SELECT game FROM saved_accounts WHERE id=? AND user_id=?",
                                          (aid,c.from_user.id))).fetchone()
        if not account:
            await c.answer("Tài khoản không hợp lệ.", show_alert=True)
            return
        try:
            cur = await db.execute(
                "INSERT INTO captured_codes(user_id,account_id,game,code,source_chat_id,source_message_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (c.from_user.id,aid,account[0],code,None,None,now()))
            code_id = cur.lastrowid
            await db.commit()
        except sqlite3.IntegrityError:
            await c.answer("Mã này đã được lưu rồi.", show_alert=True)
            return
    await c.message.edit_text(f"✅ Đã lưu mã #{code_id} vào tài khoản.\\nGame: <b>{escape(account[0])}</b>\\nMã: <code>{escape(code)}</code>\\nTrạng thái: <b>Đã lưu – chờ bạn tự đổi thưởng</b>.")
    await c.answer("Đã lưu mã.")

@dp.message(Command("mycodes"))
async def list_my_codes(m: Message):
    await ensure_user(m.from_user)
    async with await db_connect() as db:
        rows = await (await db.execute(
            "SELECT c.id,c.game,c.code,a.alias,c.status FROM captured_codes c JOIN saved_accounts a ON a.id=c.account_id WHERE c.user_id=? ORDER BY c.id DESC LIMIT 30",
            (m.from_user.id,))).fetchall()
    if not rows:
        await m.answer("Chưa có mã nào được lưu.")
        return
    lines = ["🎟 <b>MÃ CODE ĐÃ LƯU</b>"]
    for cid, game, code, alias, status in rows:
        lines.append(f"#{cid} · {escape(game)} · {escape(alias)} · <code>{escape(code)}</code> · {escape(status)}")
    await m.answer("\\n".join(lines))

@dp.message(CommandStart())
async def start(m: Message):
    await ensure_user(m.from_user)
    await m.answer("🎉 <b>CHÀO MỪNG ĐẾN VỚI NGHIỆN CODE BOT</b>\n\nChọn danh mục bạn cần bên dưới.", reply_markup=home_kb(m.from_user.id))

@dp.message(Command("menu"))
async def menu(m: Message):
    await ensure_user(m.from_user)
    await m.answer("🏠 <b>MENU CHÍNH</b>", reply_markup=home_kb(m.from_user.id))

@dp.message(Command("balance"))
async def balance_cmd(m: Message):
    await ensure_user(m.from_user)
    await m.answer(f"💰 Số dư: <b>{money(await get_balance(m.from_user.id))}</b>")

@dp.message(Command("services"))
async def services_cmd(m: Message):
    kb, rows = await service_keyboard("OTHER")
    await m.answer("🧩 <b>DỊCH VỤ KHÁC</b>" if rows else "Chưa có sản phẩm. Vui lòng quay lại sau.", reply_markup=kb)

@dp.message(Command("orders"))
async def orders_cmd(m: Message):
    await ensure_user(m.from_user)
    await send_orders(m.from_user.id, m.answer)

@dp.message(Command("nap"))
async def deposit_request(m: Message):
    await ensure_user(m.from_user)
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Cú pháp: <code>/nap 50000</code>")
        return
    amount = int(parts[1])
    if not 10000 <= amount <= 100000000:
        await m.answer("Số tiền phải từ 10.000 đến 100.000.000 VNĐ.")
        return
    async with await db_connect() as db:
        cur = await db.execute("INSERT INTO deposits(user_id,amount,created_at) VALUES(?,?,?)",
                               (m.from_user.id, amount, now()))
        dep_id = cur.lastrowid
        await db.commit()
    await m.answer(f"✅ Đã tạo yêu cầu nạp #{dep_id}: <b>{money(amount)}</b>. Chờ Admin xác nhận.")
    for aid in ADMIN_IDS:
        try:
            await m.bot.send_message(aid, f"💳 Yêu cầu nạp #{dep_id}\nUser: <code>{m.from_user.id}</code>\nSố tiền: <b>{money(amount)}</b>\nDuyệt: <code>/duyetnap {dep_id}</code> · Từ chối: <code>/huy nap {dep_id}</code>")
        except Exception:
            logging.exception("Cannot notify admin")

@dp.callback_query(F.data == "home")
async def cb_home(c: CallbackQuery):
    await c.message.edit_text("🏠 <b>MENU CHÍNH</b>", reply_markup=home_kb(c.from_user.id))
    await c.answer()

@dp.callback_query(F.data == "cat:GAME")
async def cb_game(c: CallbackQuery):
    kb, rows = await service_keyboard("GAME")
    await c.message.edit_text("🎮 <b>CODE GAME</b>\nChọn sản phẩm cần mua." if rows else "🎮 <b>CODE GAME</b>\nHiện chưa có code trong kho.", reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "other_services")
async def cb_other(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="📩 SMS – dịch vụ gửi/nhận hợp pháp", callback_data="cat:SMS")
    kb.button(text="🌐 PRX – Proxy", callback_data="cat:PRX")
    kb.button(text="⬅️ Menu chính", callback_data="home")
    kb.adjust(1)
    await c.message.edit_text("🧩 <b>DỊCH VỤ KHÁC</b>\nChọn nhóm dịch vụ.", reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(c: CallbackQuery):
    category = c.data.split(":", 1)[1]
    if category not in {"SMS", "PRX"}:
        await c.answer("Danh mục không hợp lệ.", show_alert=True)
        return
    kb, rows = await service_keyboard(category)
    title = "📩 SMS" if category == "SMS" else "🌐 PRX – PROXY"
    await c.message.edit_text(f"<b>{title}</b>\nChọn sản phẩm." if rows else f"<b>{title}</b>\nHiện chưa có sản phẩm.", reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "minigames")
async def cb_minigames(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for brand in BRANDS:
        kb.button(text=f"🎯 MINIGAME {brand}", callback_data=f"mg:{brand}")
    kb.button(text="⭐ MINIGAME HI88 · THỨ 5", callback_data="mg:HI88")
    kb.button(text="⭐ MINIGAME QQ88 · THỨ 6", callback_data="mg:QQ88")
    kb.button(text="📋 Phòng đang mở", callback_data="rooms")
    kb.button(text="⬅️ Menu chính", callback_data="home")
    kb.adjust(2, 2, 2, 2, 1, 1, 1)
    await c.message.edit_text("🏆 <b>MINIGAME LIVE</b>\n\n<b>Danh sách thường:</b> XX8 · AD88 · U888 · ABC8 · MM88 · RR88 · XX88 · GG88\n\n<b>Đặc biệt:</b> Thứ 5 – HI88 | Thứ 6 – QQ88", reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("mg:"))
async def cb_brand(c: CallbackQuery):
    brand = c.data.split(":", 1)[1]
    async with await db_connect() as db:
        rooms = await (await db.execute(
            "SELECT id,title,starts_at,status FROM minigame_rooms WHERE brand=? ORDER BY id DESC LIMIT 10",
            (brand,))).fetchall()
    kb = InlineKeyboardBuilder()
    for rid, title, starts, status in rooms:
        kb.button(text=f"#{rid} · {title} · {status}", callback_data=f"room:{rid}")
    kb.button(text="⬅️ Danh sách Minigame", callback_data="minigames")
    kb.adjust(1)
    lines = [f"🎯 <b>MINIGAME {escape(brand)}</b>"]
    if brand == "HI88":
        lines.append("Lịch đặc biệt: Thứ 5")
    if brand == "QQ88":
        lines.append("Lịch đặc biệt: Thứ 6")
    lines.append("Chưa có phòng được Admin tạo." if not rooms else "Chọn phòng để xem chi tiết.")
    await c.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data == "rooms")
async def cb_rooms(c: CallbackQuery):
    async with await db_connect() as db:
        rooms = await (await db.execute(
            "SELECT id,brand,title,starts_at,status FROM minigame_rooms WHERE status IN ('open','full') ORDER BY starts_at LIMIT 20")).fetchall()
    kb = InlineKeyboardBuilder()
    for rid, brand, title, starts, status in rooms:
        kb.button(text=f"{brand} · #{rid} · {title}", callback_data=f"room:{rid}")
    kb.button(text="⬅️ Minigame", callback_data="minigames")
    kb.adjust(1)
    await c.message.edit_text("📋 <b>PHÒNG ĐANG MỞ</b>" if rooms else "Hiện chưa có phòng đang mở.", reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("room:"))
async def cb_room(c: CallbackQuery):
    try:
        rid = int(c.data.split(":", 1)[1])
    except ValueError:
        await c.answer("Phòng không hợp lệ.", show_alert=True)
        return
    async with await db_connect() as db:
        room = await (await db.execute(
            "SELECT brand,title,starts_at,status,result FROM minigame_rooms WHERE id=?", (rid,))).fetchone()
        count = await (await db.execute("SELECT COUNT(*) FROM minigame_entries WHERE room_id=?", (rid,))).fetchone()
    if not room:
        await c.answer("Không tìm thấy phòng.", show_alert=True)
        return
    brand, title, starts, status, result = room
    kb = InlineKeyboardBuilder()
    if status == "open":
        kb.button(text="📝 Đăng ký tham gia", callback_data=f"join:{rid}")
    kb.button(text="⬅️ Danh sách Minigame", callback_data=f"mg:{brand}")
    kb.adjust(1)
    body = f"🎯 <b>{escape(brand)} – {escape(title)}</b>\nThời gian: {escape(starts)}\nTrạng thái: <b>{escape(status)}</b>\nSố người đăng ký: <b>{count[0]}</b>"
    if result:
        body += f"\n\n🏁 <b>KẾT QUẢ</b>\n{escape(result)}"
    await c.message.edit_text(body, reply_markup=kb.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("join:"))
async def cb_join(c: CallbackQuery):
    try:
        rid = int(c.data.split(":", 1)[1])
    except ValueError:
        await c.answer("Mã phòng không hợp lệ.", show_alert=True)
        return
    async with await db_connect() as db:
        room = await (await db.execute("SELECT status FROM minigame_rooms WHERE id=?", (rid,))).fetchone()
        if not room or room[0] != "open":
            await c.answer("Phòng đã đóng đăng ký hoặc không tồn tại.", show_alert=True)
            return
        try:
            await db.execute("INSERT INTO minigame_entries(room_id,user_id,created_at) VALUES(?,?,?)",
                             (rid, c.from_user.id, now()))
            await db.commit()
        except sqlite3.IntegrityError:
            await c.answer("Bạn đã đăng ký phòng này rồi.", show_alert=True)
            return
    await c.answer("Đăng ký thành công!", show_alert=True)
    await c.message.edit_text("✅ Bạn đã đăng ký tham gia phòng. Hãy theo dõi trạng thái và kết quả tại phòng này.", reply_markup=back_kb("rooms"))

@dp.callback_query(F.data == "account")
async def cb_account(c: CallbackQuery):
    await ensure_user(c.from_user)
    username = "@" + c.from_user.username if c.from_user.username else "Chưa đặt"
    await c.message.edit_text(
        f"👤 <b>THÔNG TIN TÀI KHOẢN</b>\n\nID: <code>{c.from_user.id}</code>\nTên: {escape(c.from_user.full_name)}\nUsername: {escape(username)}\nSố dư: <b>{money(await get_balance(c.from_user.id))}</b>",
        reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "deposit")
async def cb_deposit(c: CallbackQuery):
    await c.message.edit_text("💳 <b>NẠP TIỀN</b>\nGửi lệnh <code>/nap 50000</code> để tạo yêu cầu. Admin xác nhận thủ công.", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "orders")
async def cb_orders(c: CallbackQuery):
    await c.answer()
    await send_orders(c.from_user.id, c.message.answer)

@dp.callback_query(F.data == "codes_help")
async def cb_codes_help(c: CallbackQuery):
    await c.message.edit_text("🎟 <b>QUÉT MÃ TỪ TELEGRAM</b>\\n1. Lưu tài khoản: <code>/addaccount Tên_gợi_nhớ|GAME|Tên_đăng_nhập</code>\\n2. Reply tin nhắn Telegram có mã rồi gửi <code>/scan</code>.\\n3. Chọn tài khoản và xác nhận lưu.\\n4. Xem mã bằng <code>/mycodes</code>.\\n\\nBot chỉ lưu mã và gắn vào tài khoản bạn chọn; không tự đăng nhập hoặc tự đổi thưởng.", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "mycodes")
async def cb_my_codes(c: CallbackQuery):
    await c.answer()
    async with await db_connect() as db:
        rows = await (await db.execute(
            "SELECT c.id,c.game,c.code,a.alias,c.status FROM captured_codes c JOIN saved_accounts a ON a.id=c.account_id WHERE c.user_id=? ORDER BY c.id DESC LIMIT 20",
            (c.from_user.id,))).fetchall()
    if not rows:
        await c.message.answer("Chưa có mã nào được lưu. Dùng /mycodes để xem hướng dẫn.")
        return
    lines=["🎟 <b>MÃ CODE ĐÃ LƯU</b>"]
    for cid,game,code,alias,status in rows:
        lines.append(f"#{cid} · {escape(game)} · {escape(alias)} · <code>{escape(code)}</code> · {escape(status)}")
    await c.message.answer("\\n".join(lines))

@dp.callback_query(F.data == "guide")
async def cb_guide(c: CallbackQuery):
    await c.message.edit_text("📖 <b>HƯỚNG DẪN</b>\n1. Chọn danh mục.\n2. Chọn sản phẩm/phòng Minigame.\n3. Xác nhận yêu cầu.\n4. Theo dõi trạng thái tại Lịch sử đơn hoặc phòng Minigame.\n\nDịch vụ SMS chỉ dùng cho hệ thống bạn sở hữu/được ủy quyền. Proxy phải có nguồn cung hợp pháp.", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "support")
async def cb_support(c: CallbackQuery):
    contact = "@" + SUPPORT_USERNAME.lstrip("@") if SUPPORT_USERNAME else "Vui lòng liên hệ Admin."
    await c.message.edit_text(f"☎️ <b>LIÊN HỆ HỖ TRỢ</b>\n{escape(contact)}", reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data == "admin")
async def cb_admin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Không có quyền truy cập.", show_alert=True)
        return
    await c.message.edit_text(
        "🛠 <b>ADMIN PANEL – LỆNH QUẢN LÝ</b>\n\n"
        "<b>Sản phẩm:</b>\n/addservice GAME|Tên code|Giá\n/addservice SMS|Tên dịch vụ|Giá\n/addservice PRX|Tên proxy|Giá\n/delservice ID\n\n"
        "<b>Minigame:</b>\n/addroom BRAND|Tên phòng|YYYY-MM-DD HH:MM\n/roomstatus ID|open hoặc closed\n/result ID|Nội dung kết quả\n/roomsadmin\n\n"
        "<b>Tài khoản & nạp:</b>\n/duyetnap ID\n/huy nap ID\n/setbalance USER_ID SỐ_TIỀN\n/stats",
        reply_markup=back_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(c: CallbackQuery):
    await ensure_user(c.from_user)
    try:
        sid = int(c.data.split(":", 1)[1])
    except ValueError:
        await c.answer("Mã sản phẩm không hợp lệ.", show_alert=True)
        return
    async with await db_connect() as db:
        service = await (await db.execute(
            "SELECT name,price FROM services WHERE id=? AND active=1", (sid,))).fetchone()
        if not service:
            await c.answer("Sản phẩm không còn hoạt động.", show_alert=True)
            return
        name, price = service
        row = await (await db.execute("SELECT balance FROM users WHERE user_id=?", (c.from_user.id,))).fetchone()
        if not row or int(row[0]) < price:
            await c.answer("Số dư không đủ. Hãy nạp thêm.", show_alert=True)
            return
        await db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (price, c.from_user.id))
        cur = await db.execute(
            "INSERT INTO orders(user_id,service_id,service_name,price,status,created_at) VALUES(?,?,?,?,?,?)",
            (c.from_user.id, sid, name, price, "pending", now()))
        oid = cur.lastrowid
        await db.commit()
    await c.message.edit_text(
        f"✅ Đã tạo đơn <b>#{oid}</b>\nSản phẩm: {escape(name)}\nGiá: {money(price)}\nTrạng thái: <b>pending</b>\nĐơn đang chờ Admin xử lý.",
        reply_markup=back_kb())
    for aid in ADMIN_IDS:
        try:
            await c.bot.send_message(aid, f"📦 Đơn mới #{oid}\nUser: <code>{c.from_user.id}</code>\nSản phẩm: {escape(name)}")
        except Exception:
            logging.exception("Cannot notify admin")
    await c.answer("Đã tạo đơn.")

@dp.message(Command("addservice"))
async def add_service(m: Message):
    if not is_admin(m.from_user.id):
        return
    raw = (m.text or "").partition(" ")[2]
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 3 or parts[0].upper() not in {"GAME", "SMS", "PRX"} or not parts[2].isdigit() or int(parts[2]) <= 0:
        await m.answer("Cú pháp: <code>/addservice GAME|Tên code|Giá</code> hoặc SMS/PRX.")
        return
    category, name, price = parts[0].upper(), parts[1], int(parts[2])
    if not name:
        await m.answer("Tên sản phẩm không được để trống.")
        return
    async with await db_connect() as db:
        cur = await db.execute("INSERT INTO services(name,price,category) VALUES(?,?,?)", (name, price, category))
        sid = cur.lastrowid
        await db.commit()
    await m.answer(f"✅ Đã thêm sản phẩm #{sid}: <b>{escape(name)}</b> · {category} · {money(price)}")

@dp.message(Command("delservice"))
async def del_service(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Cú pháp: <code>/delservice ID</code>")
        return
    async with await db_connect() as db:
        await db.execute("UPDATE services SET active=0 WHERE id=?", (int(parts[1]),))
        await db.commit()
    await m.answer("✅ Đã ẩn sản phẩm.")

@dp.message(Command("addroom"))
async def add_room(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = [x.strip() for x in (m.text or "").partition(" ")[2].split("|")]
    if len(parts) != 3 or parts[0].upper() not in set(BRANDS + ["HI88", "QQ88"]):
        await m.answer("Cú pháp: <code>/addroom XX8|Tên phòng|2026-11-12 20:00</code>")
        return
    brand, title, starts = parts[0].upper(), parts[1], parts[2]
    try:
        datetime.strptime(starts, "%Y-%m-%d %H:%M")
    except ValueError:
        await m.answer("Thời gian phải theo định dạng YYYY-MM-DD HH:MM.")
        return
    async with await db_connect() as db:
        cur = await db.execute("INSERT INTO minigame_rooms(brand,title,starts_at,created_at) VALUES(?,?,?,?)",
                               (brand, title, starts, now()))
        rid = cur.lastrowid
        await db.commit()
    await m.answer(f"✅ Đã tạo phòng Minigame #{rid}: <b>{escape(brand)} – {escape(title)}</b> · {escape(starts)}")

@dp.message(Command("roomstatus"))
async def room_status(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = [x.strip() for x in (m.text or "").partition(" ")[2].split("|")]
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in {"open", "closed", "full"}:
        await m.answer("Cú pháp: <code>/roomstatus ID|open</code> (hoặc closed/full)")
        return
    async with await db_connect() as db:
        cur = await db.execute("UPDATE minigame_rooms SET status=? WHERE id=?", (parts[1], int(parts[0])))
        await db.commit()
    await m.answer("✅ Đã cập nhật trạng thái phòng." if cur.rowcount else "Không tìm thấy phòng.")

@dp.message(Command("result"))
async def publish_result(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = [x.strip() for x in (m.text or "").partition(" ")[2].split("|", 1)]
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1]:
        await m.answer("Cú pháp: <code>/result ID|Nội dung kết quả</code>")
        return
    rid, result = int(parts[0]), parts[1]
    async with await db_connect() as db:
        cur = await db.execute("UPDATE minigame_rooms SET result=?,status='finished' WHERE id=?", (result, rid))
        await db.commit()
    await m.answer("🏁 Đã công bố kết quả." if cur.rowcount else "Không tìm thấy phòng.")

@dp.message(Command("roomsadmin"))
async def rooms_admin(m: Message):
    if not is_admin(m.from_user.id):
        return
    async with await db_connect() as db:
        rows = await (await db.execute(
            "SELECT id,brand,title,starts_at,status FROM minigame_rooms ORDER BY id DESC LIMIT 30")).fetchall()
    if not rows:
        await m.answer("Chưa có phòng Minigame.")
        return
    lines = ["📋 <b>DANH SÁCH PHÒNG</b>"]
    for rid, brand, title, starts, status in rows:
        lines.append(f"#{rid} · {escape(brand)} · {escape(title)} · {escape(starts)} · {escape(status)}")
    await m.answer("\n".join(lines))

@dp.message(Command("duyetnap"))
async def approve_deposit(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Cú pháp: <code>/duyetnap ID</code>")
        return
    did = int(parts[1])
    async with await db_connect() as db:
        row = await (await db.execute("SELECT user_id,amount,status FROM deposits WHERE id=?", (did,))).fetchone()
        if not row:
            await m.answer("Không tìm thấy yêu cầu.")
            return
        uid, amount, status = row
        if status != "pending":
            await m.answer("Yêu cầu đã được xử lý.")
            return
        await db.execute("UPDATE deposits SET status='approved' WHERE id=?", (did,))
        await db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
        await db.commit()
    await m.answer(f"✅ Đã duyệt nạp #{did}: {money(amount)}.")
    try:
        await m.bot.send_message(uid, f"🎉 Nạp tiền thành công: <b>{money(amount)}</b>.")
    except Exception:
        pass

@dp.message(Command("huy"))
async def reject_deposit(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 3 or parts[1].lower() != "nap" or not parts[2].isdigit():
        await m.answer("Cú pháp: <code>/huy nap ID</code>")
        return
    did = int(parts[2])
    async with await db_connect() as db:
        row = await (await db.execute("SELECT user_id,status FROM deposits WHERE id=?", (did,))).fetchone()
        if not row:
            await m.answer("Không tìm thấy yêu cầu.")
            return
        uid, status = row
        if status != "pending":
            await m.answer("Yêu cầu đã được xử lý.")
            return
        await db.execute("UPDATE deposits SET status='rejected' WHERE id=?", (did,))
        await db.commit()
    await m.answer(f"Đã từ chối yêu cầu nạp #{did}.")
    try:
        await m.bot.send_message(uid, f"Yêu cầu nạp #{did} đã bị từ chối.")
    except Exception:
        pass

@dp.message(Command("setbalance"))
async def set_balance(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await m.answer("Cú pháp: <code>/setbalance USER_ID SỐ_TIỀN</code>")
        return
    uid, amount = int(parts[1]), int(parts[2])
    async with await db_connect() as db:
        cur = await db.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, uid))
        await db.commit()
    await m.answer("✅ Đã cập nhật số dư." if cur.rowcount else "Không tìm thấy người dùng.")

@dp.message(Command("stats"))
async def stats(m: Message):
    if not is_admin(m.from_user.id):
        return
    async with await db_connect() as db:
        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        orders = (await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone())[0]
        pending = (await (await db.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")).fetchone())[0]
        rooms = (await (await db.execute("SELECT COUNT(*) FROM minigame_rooms")).fetchone())[0]
    await m.answer(f"📊 <b>THỐNG KÊ</b>\nNgười dùng: {users}\nĐơn hàng: {orders}\nNạp chờ duyệt: {pending}\nPhòng Minigame: {rooms}")

@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("Bạn không có quyền.")
        return
    await m.answer("🛠 <b>LỆNH ADMIN</b>\n/addservice GAME|Tên|Giá\n/addservice SMS|Tên|Giá\n/addservice PRX|Tên|Giá\n/addroom BRAND|Tên phòng|YYYY-MM-DD HH:MM\n/roomstatus ID|open\n/result ID|Kết quả\n/roomsadmin\n/duyetnap ID\n/huy nap ID\n/setbalance USER_ID SỐ_TIỀN\n/stats")

async def main():
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
