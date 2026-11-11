import asyncio
import html
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, BotCommand,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()
DB_PATH = os.getenv("DB_PATH", "bot.db")
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MENU_LABELS = {"services":"🛍️ DỊCH VỤ","profile":"👤 CÁ NHÂN","other":"⚙️ DỊCH VỤ KHÁC","topup":"💳 NẠP TIỀN","referral":"🎁 GIỚI THIỆU","support":"☎️ CSKH","history":"📜 LỊCH SỬ","guide":"❔ HƯỚNG DẪN"}
SUPPORT_URL = "https://t.me/benii2k"
WELCOME_TEMPLATE = """🎉 <b>CHÀO MỪNG BẠN ĐẾN VỚI NGHIEN CODE BOT</b>

📅 Ngày: {date}
🕒 Thời gian: {time}

👋 Xin chào, {name}!

🤖 Chào mừng bạn đến với hệ thống tiện ích của NGHIEN CODE.

━━━━━━━━━━━━━━
🎁 <b>CODE GAME GIÁ RẺ - UY TÍN</b>
🚀 <b>MINIGAME DONE NHANH</b>
━━━━━━━━━━━━━━

💙 Cảm ơn bạn đã sử dụng NGHIEN CODE BOT!"""
HELP_TEMPLATE = """<b>HƯỚNG DẪN SỬ DỤNG</b>
/start - Mở menu chính
/help - Xem hướng dẫn
/id - Xem Telegram ID
/orders - Xem đơn hàng
/admin - Khu vực quản trị"""
ADMIN_WALLET_STATE = {}

SERVICES = {
    "new88": ("NEW88", 10000, "Dịch vụ NEW88"),
    "xx88": ("XX88 CODE TO", 25000, "Dịch vụ XX88 CODE TO"),
    "hi88": ("HI88", 15000, "Dịch vụ HI88"),
    "qq88": ("QQ88", 15000, "Dịch vụ QQ88"),
    "mb66": ("MB66", 10000, "Dịch vụ MB66"),
    "llwin": ("LLWIN", 5000, "Dịch vụ LLWIN"),
    "shbet": ("SHBET", 10000, "Dịch vụ SHBET"),
    "8kbet": ("8KBET", 5000, "Dịch vụ 8KBET"),
    "ad88_mini": ("MINIGAME AD88 - COMBO 200 ĐIỂM", 55000, "Minigame AD88, combo 200 điểm"),
    "xx8_mini": ("MINIGAME XX8 - COMBO 200 ĐIỂM", 55000, "Minigame XX8, combo 200 điểm"),
    "mm88_mini": ("MINIGAME MM88", 35000, "Minigame MM88"),
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def money(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=MENU_LABELS["services"], callback_data="menu:services"),
            InlineKeyboardButton(text=MENU_LABELS["profile"], callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton(text=MENU_LABELS["other"], callback_data="menu:other"),
            InlineKeyboardButton(text=MENU_LABELS["topup"], callback_data="menu:topup"),
        ],
        [
            InlineKeyboardButton(text=MENU_LABELS["referral"], callback_data="menu:referral"),
            InlineKeyboardButton(text=MENU_LABELS["support"], url=SUPPORT_URL),
        ],
        [
            InlineKeyboardButton(text=MENU_LABELS["history"], callback_data="menu:history"),
            InlineKeyboardButton(text=MENU_LABELS["guide"], callback_data="menu:guide"),
        ],
    ])


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 MENU CHÍNH", callback_data="menu:home")]
    ])


def service_keyboard() -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for key, (name, price, _) in SERVICES.items():
        pair.append(InlineKeyboardButton(
            text=f"{name} · {money(price)}",
            callback_data=f"service:{key}"
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text="🏠 MENU CHÍNH", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                joined_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service_key TEXT NOT NULL,
                service_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        await db.execute("CREATE TABLE IF NOT EXISTS wallets (user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0)")
        await db.execute("""CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS bot_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS service_catalog (service_key TEXT PRIMARY KEY, service_name TEXT NOT NULL, price INTEGER NOT NULL, description TEXT NOT NULL)")
        for key, (name, price, desc) in SERVICES.items():
            await db.execute("INSERT OR IGNORE INTO service_catalog VALUES (?, ?, ?, ?)", (key, name, price, desc))
        await db.commit()
    await load_bot_settings()


async def load_bot_settings():
    global SUPPORT_URL, WELCOME_TEMPLATE, HELP_TEMPLATE
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT setting_key, setting_value FROM bot_settings")
        settings = dict(await cur.fetchall())
        cur = await db.execute("SELECT service_key, service_name, price, description FROM service_catalog")
        service_rows = await cur.fetchall()
    SUPPORT_URL = settings.get("support_url", SUPPORT_URL)
    WELCOME_TEMPLATE = settings.get("welcome_text", WELCOME_TEMPLATE)
    HELP_TEMPLATE = settings.get("help_text", HELP_TEMPLATE)
    for key in MENU_LABELS:
        MENU_LABELS[key] = settings.get("menu_" + key, MENU_LABELS[key])
    if service_rows:
        SERVICES.clear()
        for key, name, price, desc in service_rows:
            SERVICES[key] = (name, price, desc)


async def save_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO bot_settings VALUES (?, ?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (key, value))
        await db.commit()


async def save_user(user):
    if not user:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users(user_id, full_name, username, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                username=excluded.username
        """, (
            user.id, user.full_name, user.username,
            datetime.now(TZ).isoformat(timespec="seconds")
        ))
        await db.commit()


async def send_home(message: Message):
    now = datetime.now(TZ)
    first_name = html.escape(message.from_user.first_name or "Bạn")
    text = (
        "🎉 <b>CHÀO MỪNG BẠN ĐẾN VỚI NGHIEN CODE BOT</b>\n\n"
        f"📅 Ngày: {now:%d/%m/%Y}\n"
        f"🕒 Thời gian: {now:%H:%M}\n\n"
        f"👋 Xin chào, {first_name}!\n\n"
        "🤖 Chào mừng bạn đến với hệ thống tiện ích của NGHIEN CODE.\n\n"
        "━━━━━━━━━━━━━━\n"
        "🎁 <b>CODE GAME GIÁ RẺ - UY TÍN</b>\n"
        "🚀 <b>MINIGAME DONE NHANH</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        "💙 Cảm ơn bạn đã sử dụng NGHIEN CODE BOT!"
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(CommandStart())
async def start_handler(message: Message):
    await save_user(message.from_user)
    await send_home(message)


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "<b>HƯỚNG DẪN SỬ DỤNG</b>\n"
        "/start - Mở menu chính\n"
        "/help - Xem hướng dẫn\n"
        "/id - Xem Telegram ID\n"
        "/orders - Xem đơn hàng của bạn\n"
        "/admin - Khu vực quản trị"
    )


@dp.message(Command("id"))
async def id_handler(message: Message):
    await message.answer(f"Telegram ID của bạn: <code>{message.from_user.id}</code>")


@dp.message(Command("orders"))
async def orders_handler(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, service_name, price, status, created_at FROM orders "
            "WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (message.from_user.id,)
        )
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Bạn chưa có đơn hàng nào.", reply_markup=back_menu())
        return
    labels = {"pending": "⏳ Đang chờ ADMIN", "accepted": "✅ Đã xác nhận", "rejected": "❌ Đã từ chối"}
    lines = ["<b>📦 ĐƠN HÀNG CỦA BẠN</b>"]
    for oid, name, price, status, created in rows:
        lines.append(
            f"\n<b>#{oid} · {html.escape(name)}</b>\n"
            f"Giá: {money(price)}\n"
            f"Trạng thái: {labels.get(status, status)}\n"
            f"Thời gian: {html.escape(created)}"
        )
    await message.answer("\n".join(lines), reply_markup=back_menu())


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Bạn không có quyền truy cập.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
        pending = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM orders")
        total = (await cur.fetchone())[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 QUẢN LÝ SỐ DƯ", callback_data="admin:wallet")],
        [InlineKeyboardButton(text="🛍️ QUẢN LÝ DỊCH VỤ", callback_data="admin:services")],
        [InlineKeyboardButton(text="🔘 CHỈNH NÚT MENU", callback_data="admin:buttons")],
        [InlineKeyboardButton(text="📝 CHỈNH LỆNH /start, /help", callback_data="admin:commands")],
        [InlineKeyboardButton(text="📋 ĐƠN CHỜ XỬ LÝ", callback_data="admin:pending")],
        [InlineKeyboardButton(text="🏠 MENU CHÍNH", callback_data="menu:home")]
    ])
    await message.answer(
        "🔐 <b>BẢNG ĐIỀU KHIỂN ADMIN</b>\n\n"
        f"👥 Người dùng: {users}\n"
        f"📦 Tổng đơn: {total}\n"
        f"⏳ Đơn đang chờ: {pending}",
        reply_markup=kb
    )


@dp.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery):
    await call.answer()
    now = datetime.now(TZ)
    name = html.escape(call.from_user.first_name or "Bạn")
    text = (
        "🎉 <b>CHÀO MỪNG BẠN ĐẾN VỚI NGHIEN CODE BOT</b>\n\n"
        f"📅 Ngày: {now:%d/%m/%Y}\n🕒 Thời gian: {now:%H:%M}\n\n"
        f"👋 Xin chào, {name}!\n\n"
        "🤖 Chào mừng bạn đến với hệ thống tiện ích của NGHIEN CODE.\n\n"
        "━━━━━━━━━━━━━━\n"
        "🎁 <b>CODE GAME GIÁ RẺ - UY TÍN</b>\n"
        "🚀 <b>MINIGAME DONE NHANH</b>\n"
        "━━━━━━━━━━━━━━\n\n"
        "💙 Cảm ơn bạn đã sử dụng NGHIEN CODE BOT!"
    )
    await call.message.edit_text(text, reply_markup=main_menu())


@dp.callback_query(F.data == "menu:services")
async def menu_services(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "🛍️ <b>DANH SÁCH DỊCH VỤ</b>\n\n"
        "🎮 <b>DỊCH VỤ CODE</b>\n"
        + "\n".join(
            f"• {html.escape(name)} — {money(price)}"
            for key, (name, price, _) in list(SERVICES.items())[:8]
        )
        + "\n\n🎯 <b>DỊCH VỤ MINIGAME</b>\n"
        + "\n".join(
            f"• {html.escape(name)} — {money(price)}"
            for key, (name, price, _) in list(SERVICES.items())[8:]
        )
        + "\n\nChọn dịch vụ bên dưới để xem chi tiết và tạo đơn.",
        reply_markup=service_keyboard()
    )


@dp.callback_query(F.data.startswith("service:"))
async def service_detail(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    if key not in SERVICES:
        await call.answer("Dịch vụ không tồn tại.", show_alert=True)
        return
    name, price, description = SERVICES[key]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 ĐẶT DỊCH VỤ", callback_data=f"order:{key}")],
        [InlineKeyboardButton(text="🔙 DANH SÁCH DỊCH VỤ", callback_data="menu:services")],
        [InlineKeyboardButton(text="🏠 MENU CHÍNH", callback_data="menu:home")]
    ])
    await call.answer()
    await call.message.edit_text(
        f"📌 <b>{html.escape(name)}</b>\n\n"
        f"📝 {html.escape(description)}\n"
        f"💰 Giá: <b>{money(price)}</b>\n\n"
        "Bấm ĐẶT DỊCH VỤ để gửi yêu cầu đến ADMIN. "
        "Đơn chỉ được thực hiện sau khi ADMIN xác nhận.",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("order:"))
async def create_order(call: CallbackQuery, bot: Bot):
    key = call.data.split(":", 1)[1]
    if key not in SERVICES:
        await call.answer("Dịch vụ không tồn tại.", show_alert=True)
        return
    name, price, _ = SERVICES[key]
    now = datetime.now(TZ).isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO orders(user_id, service_key, service_name, price, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (call.from_user.id, key, name, price, now, now)
        )
        order_id = cur.lastrowid
        await db.commit()

    user_label = html.escape(call.from_user.full_name)
    username = f"@{html.escape(call.from_user.username)}" if call.from_user.username else "Không có"
    admin_text = (
        "🆕 <b>YÊU CẦU ĐẶT DỊCH VỤ</b>\n\n"
        f"🧾 Mã đơn: <code>#{order_id}</code>\n"
        f"📦 Dịch vụ: <b>{html.escape(name)}</b>\n"
        f"💰 Giá: <b>{money(price)}</b>\n"
        f"👤 Khách: {user_label}\n"
        f"🔗 Username: {username}\n"
        f"🆔 Telegram ID: <code>{call.from_user.id}</code>\n"
        f"🕒 Thời gian: {html.escape(now)}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ XÁC NHẬN", callback_data=f"orderstatus:accepted:{order_id}"),
            InlineKeyboardButton(text="❌ TỪ CHỐI", callback_data=f"orderstatus:rejected:{order_id}")
        ]
    ])
    delivered = False
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=admin_kb)
            delivered = True
        except Exception:
            logging.exception("Cannot notify admin %s", admin_id)

    await call.answer("Đã tạo yêu cầu đặt dịch vụ.")
    await call.message.edit_text(
        f"✅ <b>ĐÃ GỬI YÊU CẦU ĐẶT DỊCH VỤ</b>\n\n"
        f"🧾 Mã đơn: <code>#{order_id}</code>\n"
        f"📦 Dịch vụ: {html.escape(name)}\n"
        f"💰 Giá: {money(price)}\n"
        "⏳ Trạng thái: Đang chờ ADMIN xác nhận.\n\n"
        + ("ADMIN đã được thông báo." if delivered else "Chưa gửi được thông báo đến ADMIN. Vui lòng liên hệ hỗ trợ.")
        + "\n\nDùng /orders để xem trạng thái đơn.",
        reply_markup=back_menu()
    )


@dp.callback_query(F.data.startswith("orderstatus:"))
async def update_order_status(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Bạn không có quyền thực hiện.", show_alert=True)
        return
    _, status, order_id_text = call.data.split(":")
    if status not in ("accepted", "rejected"):
        await call.answer("Trạng thái không hợp lệ.", show_alert=True)
        return
    order_id = int(order_id_text)
    now = datetime.now(TZ).isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, service_name, status FROM orders WHERE id=?", (order_id,)
        )
        row = await cur.fetchone()
        if not row:
            await call.answer("Không tìm thấy đơn hàng.", show_alert=True)
            return
        user_id, service_name, old_status = row
        if old_status != "pending":
            await call.answer("Đơn này đã được xử lý trước đó.", show_alert=True)
            return
        await db.execute(
            "UPDATE orders SET status=?, updated_at=? WHERE id=? AND status='pending'",
            (status, now, order_id)
        )
        await db.commit()

    label = "✅ ĐÃ XÁC NHẬN" if status == "accepted" else "❌ ĐÃ TỪ CHỐI"
    await call.answer("Đã cập nhật trạng thái đơn.")
    await call.message.edit_text(call.message.text + f"\n\n<b>Trạng thái: {label}</b>")
    try:
        await bot.send_message(
            user_id,
            f"📦 <b>CẬP NHẬT ĐƠN HÀNG #{order_id}</b>\n"
            f"Dịch vụ: {html.escape(service_name)}\n"
            f"Trạng thái: {label}\n"
            "Nếu cần hỗ trợ, vui lòng liên hệ ADMIN."
        )
    except Exception:
        logging.exception("Cannot notify user for order %s", order_id)


@dp.callback_query(F.data == "admin:pending")
async def admin_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Bạn không có quyền truy cập.", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, service_name, price, created_at FROM orders "
            "WHERE status='pending' ORDER BY id DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    await call.answer()
    if not rows:
        await call.message.edit_text("✅ Hiện không có đơn hàng chờ xử lý.", reply_markup=back_menu())
        return
    lines = ["⏳ <b>DANH SÁCH ĐƠN ĐANG CHỜ</b>"]
    for oid, uid, name, price, created in rows:
        lines.append(
            f"\n<b>#{oid}</b> · {html.escape(name)} · {money(price)}\n"
            f"Khách ID: <code>{uid}</code>\n"
            f"{html.escape(created)}"
        )
    await call.message.edit_text("\n".join(lines), reply_markup=back_menu())


@dp.callback_query(F.data == "menu:topup")
async def menu_topup(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "💳 <b>NẠP TIỀN</b>\n\n"
        "Thông tin thanh toán chưa được ADMIN cấu hình.\n"
        "Vui lòng liên hệ ADMIN để được hướng dẫn. "
        "Bot chưa tự động nhận hoặc xác minh thanh toán.",
        reply_markup=back_menu()
    )


@dp.callback_query(F.data == "menu:guide")
async def menu_guide(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "❔ <b>HƯỚNG DẪN SỬ DỤNG NGHIEN CODE BOT</b>\n\n"
        "1. Chọn DỊCH VỤ và chọn sản phẩm bạn cần.\n"
        "2. Bấm ĐẶT DỊCH VỤ để gửi yêu cầu.\n"
        "3. Chờ ADMIN xác nhận và liên hệ nếu cần bổ sung thông tin.\n"
        "4. Chọn LỊCH SỬ để theo dõi trạng thái đơn hàng.\n\n"
        "💳 Nạp tiền hiện cần ADMIN hướng dẫn/xác nhận thủ công.\n"
        "☎️ CSKH: @benii2k",
        reply_markup=back_menu()
    )


@dp.callback_query(F.data == "menu:history")
async def menu_history(call: CallbackQuery):
    await call.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, service_name, price, status, created_at FROM orders "
            "WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (call.from_user.id,)
        )
        rows = await cur.fetchall()
    if not rows:
        await call.message.edit_text(
            "📜 <b>LỊCH SỬ GIAO DỊCH</b>\n\nBạn chưa có đơn hàng nào.",
            reply_markup=back_menu()
        )
        return
    labels = {"pending": "⏳ Đang chờ ADMIN", "accepted": "✅ Đã xác nhận", "rejected": "❌ Đã từ chối"}
    lines = ["📜 <b>LỊCH SỬ GIAO DỊCH</b>"]
    for oid, name, price, status, created in rows:
        lines.append(
            f"\n<b>Đơn #{oid}</b> · {html.escape(name)}\n"
            f"💰 {money(price)} · {labels.get(status, status)}\n"
            f"🕒 {html.escape(created)}"
        )
    await call.message.edit_text("\n".join(lines), reply_markup=back_menu())


@dp.callback_query(F.data == "menu:profile")
async def menu_profile(call: CallbackQuery):
    await call.answer()
    user = call.from_user
    await call.message.edit_text(
        "👤 <b>THÔNG TIN CÁ NHÂN</b>\n\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"👤 Tên: {html.escape(user.full_name)}\n"
        f"🔗 Username: @{html.escape(user.username) if user.username else 'Chưa thiết lập'}\n\n"
        "📦 Dùng /orders để xem lịch sử đơn hàng.\n"
        "💰 Số dư: Chưa được kích hoạt.",
        reply_markup=back_menu()
    )


@dp.callback_query(F.data == "menu:referral")
async def menu_referral(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "🎁 <b>GIỚI THIỆU BẠN BÈ</b>\n\n"
        "Chức năng mã giới thiệu và phần thưởng đang chờ ADMIN cấu hình.",
        reply_markup=back_menu()
    )


@dp.callback_query(F.data == "menu:other")
async def menu_other(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "⚙️ <b>DỊCH VỤ KHÁC</b>\n\n"
        "📞 Liên hệ ADMIN: @benii2k\n"
        "🆘 Cần hỗ trợ, hãy nhắn trực tiếp ADMIN.",
        reply_markup=back_menu()
    )



@dp.callback_query(F.data == "admin:wallet")
async def admin_wallet_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ CỘNG TIỀN", callback_data="admin:wallet:add"),
         InlineKeyboardButton(text="➖ TRỪ TIỀN", callback_data="admin:wallet:sub")],
        [InlineKeyboardButton(text="🔎 KIỂM TRA SỐ DƯ", callback_data="admin:wallet:check"),
         InlineKeyboardButton(text="📜 LỊCH SỬ", callback_data="admin:wallet:history")],
        [InlineKeyboardButton(text="🔙 ADMIN", callback_data="admin:back")]
    ])
    await call.message.edit_text("💰 <b>QUẢN LÝ SỐ DƯ</b>", reply_markup=kb)


@dp.callback_query(F.data.in_({"admin:wallet:add", "admin:wallet:sub", "admin:wallet:check"}))
async def admin_wallet_prompt(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    action = call.data.rsplit(":", 1)[1]
    ADMIN_WALLET_STATE[call.from_user.id] = action
    await call.answer()
    prompt = "Gửi Telegram ID người dùng." if action == "check" else "Gửi theo mẫu: <code>TelegramID SốTiền Ghi chú</code>\nVí dụ: <code>123456789 50000 Hoàn tiền đơn #12</code>\nGửi /cancel để hủy."
    await call.message.answer(prompt)


@dp.callback_query(F.data == "admin:wallet:history")
async def admin_wallet_history(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT admin_id,user_id,amount,note,created_at FROM wallet_transactions ORDER BY id DESC LIMIT 15")
        rows = await cur.fetchall()
    text = "\n".join(
        f"UID <code>{uid}</code> · {amount:+,}đ\nADMIN {admin} · {html.escape(note)} · {html.escape(created)}"
        for admin, uid, amount, note, created in rows
    ) if rows else "Chưa có giao dịch."
    await call.message.edit_text("📜 <b>LỊCH SỬ CỘNG/TRỪ TIỀN</b>\n\n" + text,
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 ADMIN", callback_data="admin:back")]]))


@dp.callback_query(F.data == "admin:back")
async def admin_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 CỘNG/TRỪ TIỀN", callback_data="admin:wallet")],
        [InlineKeyboardButton(text="📋 ĐƠN CHỜ XỬ LÝ", callback_data="admin:pending")]
    ])
    await call.message.edit_text("🔐 <b>BẢNG ĐIỀU KHIỂN ADMIN</b>", reply_markup=kb)


@dp.message(Command("cancel"))
async def admin_cancel(message: Message):
    ADMIN_WALLET_STATE.pop(message.from_user.id, None)
    await message.answer("Đã hủy thao tác.")


@dp.message(F.text)
async def admin_wallet_input(message: Message):
    uid = message.from_user.id
    action = ADMIN_WALLET_STATE.get(uid)
    if not action:
        return
    if not is_admin(uid):
        ADMIN_WALLET_STATE.pop(uid, None)
        return
    raw = (message.text or "").strip()
    if raw == "/cancel":
        ADMIN_WALLET_STATE.pop(uid, None)
        await message.answer("Đã hủy thao tác.")
        return
    try:
        if action == "check":
            if not raw.isdigit():
                raise ValueError("Gửi Telegram ID dạng số.")
            target = int(raw)
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute("SELECT balance FROM wallets WHERE user_id=?", (target,))
                row = await cur.fetchone()
            balance = row[0] if row else 0
            ADMIN_WALLET_STATE.pop(uid, None)
            await message.answer(f"UID <code>{target}</code>\nSố dư: <b>{money(balance)}</b>")
            return
        parts = raw.split(maxsplit=2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise ValueError("Dùng: TelegramID SốTiền Ghi chú")
        target, amount = int(parts[0]), int(parts[1])
        if target <= 0 or amount <= 0:
            raise ValueError("ID và số tiền phải lớn hơn 0.")
        note = parts[2] if len(parts) > 2 else "Điều chỉnh bởi ADMIN"
        delta = amount if action == "add" else -amount
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES (?,0)", (target,))
            cur = await db.execute("SELECT balance FROM wallets WHERE user_id=?", (target,))
            balance = (await cur.fetchone())[0]
            if balance + delta < 0:
                raise ValueError(f"Số dư hiện tại {money(balance)}, không thể trừ.")
            await db.execute("UPDATE wallets SET balance=balance+? WHERE user_id=?", (delta,target))
            await db.execute("INSERT INTO wallet_transactions(admin_id,user_id,amount,note,created_at) VALUES (?,?,?,?,?)",
                             (uid,target,delta,note,datetime.now(TZ).isoformat(timespec="seconds")))
            await db.commit()
        ADMIN_WALLET_STATE.pop(uid, None)
        await message.answer(f"✅ Đã {'cộng' if delta > 0 else 'trừ'} {money(amount)} cho UID <code>{target}</code>.\nSố dư mới: <b>{money(balance+delta)}</b>")
        try:
            await message.bot.send_message(target, f"💰 Số dư được ADMIN điều chỉnh: <b>{delta:+,}đ</b>\nSố dư hiện tại: <b>{money(balance+delta)}</b>\nGhi chú: {html.escape(note)}")
        except Exception:
            logging.info("Không gửi được thông báo số dư UID %s", target)
    except ValueError as exc:
        await message.answer("⚠️ " + html.escape(str(exc)) + "\nGửi lại hoặc /cancel.")


@dp.callback_query(F.data == "admin:services")
async def admin_services_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    rows = [[InlineKeyboardButton(text=f"✏️ {name} · {money(price)}", callback_data=f"admin:service:{key}")]
            for key, (name, price, _) in SERVICES.items()]
    rows.append([InlineKeyboardButton(text="🔙 ADMIN", callback_data="admin:back")])
    await call.message.edit_text("🛍️ <b>CHỌN DỊCH VỤ CẦN SỬA</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("admin:service:"))
async def admin_service_prompt(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    key = call.data.split(":", 2)[2]
    if key not in SERVICES:
        await call.answer("Không tìm thấy dịch vụ.", show_alert=True)
        return
    ADMIN_WALLET_STATE[call.from_user.id] = "service:" + key
    await call.answer()
    await call.message.answer("Gửi theo mẫu: <code>Tên mới | Giá mới | Mô tả mới</code>\n/cancel để hủy.")


@dp.callback_query(F.data == "admin:buttons")
async def admin_buttons_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    rows = [[InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"admin:button:{key}")]
            for key, label in MENU_LABELS.items()]
    rows.append([InlineKeyboardButton(text="🔗 SỬA LINK CSKH", callback_data="admin:button:support_url")])
    rows.append([InlineKeyboardButton(text="🔙 ADMIN", callback_data="admin:back")])
    await call.message.edit_text("🔘 <b>CHỌN NÚT MENU CẦN SỬA</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("admin:button:"))
async def admin_button_prompt(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    key = call.data.split(":", 2)[2]
    if key == "support_url":
        ADMIN_WALLET_STATE[call.from_user.id] = "support_url"
        prompt = "Gửi link CSKH mới bắt đầu bằng https://"
    elif key in MENU_LABELS:
        ADMIN_WALLET_STATE[call.from_user.id] = "button:" + key
        prompt = "Gửi tên mới cho nút menu."
    else:
        await call.answer("Không tìm thấy nút.", show_alert=True)
        return
    await call.answer()
    await call.message.answer(prompt)


@dp.callback_query(F.data == "admin:commands")
async def admin_commands_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ SỬA NỘI DUNG /start", callback_data="admin:command:welcome")],
        [InlineKeyboardButton(text="✏️ SỬA NỘI DUNG /help", callback_data="admin:command:help")],
        [InlineKeyboardButton(text="🔙 ADMIN", callback_data="admin:back")]
    ])
    await call.message.edit_text("📝 <b>CHỈNH NỘI DUNG LỆNH</b>\n/start hỗ trợ {name}, {date}, {time}." , reply_markup=kb)


@dp.callback_query(F.data.startswith("admin:command:"))
async def admin_command_prompt(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Không có quyền.", show_alert=True)
        return
    key = call.data.split(":", 2)[2]
    if key not in ("welcome", "help"):
        await call.answer("Lệnh không hợp lệ.", show_alert=True)
        return
    ADMIN_WALLET_STATE[call.from_user.id] = "command:" + key
    await call.answer()
    await call.message.answer("Gửi toàn bộ nội dung mới. HTML Telegram được hỗ trợ. /cancel để hủy.")


@dp.message(F.text)
async def admin_config_input(message: Message):
    global SUPPORT_URL, WELCOME_TEMPLATE, HELP_TEMPLATE
    uid = message.from_user.id
    state = ADMIN_WALLET_STATE.get(uid)
    if not state or not is_admin(uid):
        return
    raw = (message.text or "").strip()
    if raw == "/cancel":
        ADMIN_WALLET_STATE.pop(uid, None)
        await message.answer("Đã hủy.")
        return
    try:
        if state.startswith("service:"):
            key = state.split(":", 1)[1]
            parts = [x.strip() for x in raw.split("|", 2)]
            if len(parts) != 3 or not parts[1].isdigit():
                raise ValueError("Dùng: Tên | Giá | Mô tả")
            name, price, desc = parts[0], int(parts[1]), parts[2]
            if not name or not desc or price < 0:
                raise ValueError("Thông tin dịch vụ không hợp lệ.")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE service_catalog SET service_name=?,price=?,description=? WHERE service_key=?", (name, price, desc, key))
                await db.commit()
            SERVICES[key] = (name, price, desc)
            ADMIN_WALLET_STATE.pop(uid, None)
            await message.answer(f"✅ Đã sửa dịch vụ {html.escape(name)} · {money(price)}")
        elif state.startswith("button:"):
            key = state.split(":", 1)[1]
            if len(raw) > 64:
                raise ValueError("Tên nút tối đa 64 ký tự.")
            await save_setting("menu_" + key, raw)
            MENU_LABELS[key] = raw
            ADMIN_WALLET_STATE.pop(uid, None)
            await message.answer("✅ Đã đổi tên nút. Mở lại /start để xem.")
        elif state == "support_url":
            if not raw.startswith("https://"):
                raise ValueError("Link phải bắt đầu bằng https://")
            await save_setting("support_url", raw)
            SUPPORT_URL = raw
            ADMIN_WALLET_STATE.pop(uid, None)
            await message.answer("✅ Đã đổi link CSKH. Mở lại /start để xem.")
        elif state.startswith("command:"):
            key = state.split(":", 1)[1]
            if len(raw) > 3500:
                raise ValueError("Nội dung tối đa 3500 ký tự.")
            if key == "welcome":
                await save_setting("welcome_text", raw)
                WELCOME_TEMPLATE = raw
            else:
                await save_setting("help_text", raw)
                HELP_TEMPLATE = raw
            ADMIN_WALLET_STATE.pop(uid, None)
            await message.answer("✅ Đã lưu nội dung lệnh.")
    except ValueError as exc:
        await message.answer("⚠️ " + html.escape(str(exc)) + "\nGửi lại đúng mẫu hoặc /cancel.")


async def main():
    await init_db()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    await bot.set_my_commands([
        BotCommand(command="start", description="Mở menu chính"),
        BotCommand(command="help", description="Hướng dẫn"),
        BotCommand(command="id", description="Xem Telegram ID"),
        BotCommand(command="orders", description="Xem đơn hàng"),
        BotCommand(command="admin", description="Khu vực quản trị"),
    ])
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
