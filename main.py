import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADM_IDS", "").split(",") if x.strip().isdigit()}

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN environment variable")

dp = Dispatcher()

def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎮 CODE GAME", callback_data="menu:code")
    kb.button(text="🏆 MINIGAME LIVE", callback_data="menu:minigame")
    kb.button(text="🧰 DỊCH VỤ KHÁC", callback_data="menu:services")
    kb.button(text="👤 TÀI KHOẢN CÁ NHÂN", callback_data="menu:account")
    kb.button(text="📖 HƯỚNG DẪN", callback_data="menu:help")
    kb.adjust(1)
    return kb.as_markup()

def back_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ VỀ MENU CHÍNH", callback_data="menu:home")
    return kb.as_markup()

@dp.message(CommandStart())
async def start(message: Message):
    name = message.from_user.full_name if message.from_user else "bạn"
    await message.answer(
        f"🏮🏮🏮🏮\n\n🔥 Xin chào, {name}!\n\n"
        "👥 Chào mừng bạn đến với NGHIỆN CODE.\n"
        "Vui lòng chọn dịch vụ bên dưới:",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "menu:home")
async def home(call: CallbackQuery):
    await call.message.edit_text("🏠 MENU CHÍNH\nVui lòng chọn dịch vụ:", reply_markup=main_keyboard())
    await call.answer()

@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    pages = {
        "code": ("🎮 CODE GAME", "Chọn game và sản phẩm CODE GAME.\n\nDanh mục dự kiến: XX8, AD88, U888, ABC8, MM88.\nTính năng đặt hàng và giao code sẽ được bật sau khi cấu hình kho code và thanh toán."),
        "minigame": ("🏆 MINIGAME LIVE", "Thông tin các chương trình MINIGAME LIVE: XX8, AD88, U888, ABC8.\nLịch và thể lệ sẽ được cập nhật tại đây."),
        "services": ("🧰 DỊCH VỤ KHÁC", "Danh mục dịch vụ: SMS NHẬN, SMS GỬI và PRX.\nChức năng đặt dịch vụ cần cấu hình nhà cung cấp hợp pháp trước khi mở bán."),
        "account": ("👤 TÀI KHOẢN CÁ NHÂN", f"👤 Tên: {call.from_user.full_name}\n🆔 Telegram ID: {call.from_user.id}\n\nSố dư: Chưa kết nối hệ thống thanh toán."),
        "help": ("📖 HƯỚNG DẪN SỬ DỤNG", "1. Chọn DỊCH VỤ.\n2. Chọn sản phẩm cần đặt.\n3. Kiểm tra thông tin đơn hàng.\n4. Chỉ thanh toán qua phương thức được bot xác nhận.\n\nNếu cần hỗ trợ, vui lòng liên hệ quản trị viên.")
    }
    title, body = pages.get(key, ("Thông báo", "Danh mục chưa được cấu hình."))
    await call.message.edit_text(f"{title}\n\n{body}", reply_markup=back_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin(message: Message):
    if not message.from_user or message.from_user.id not in ADMIN_IDS:
        await message.answer("Bạn không có quyền truy cập.")
        return
    await message.answer("🛠 ADMIN\nBot đã nhận diện quyền quản trị. Các công cụ quản lý sản phẩm, đơn hàng, kho code và nội dung sẽ được triển khai ở các bước tiếp theo.")

async def main():
    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        logging.info("Starting @%s (id=%s)", me.username, me.id)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
