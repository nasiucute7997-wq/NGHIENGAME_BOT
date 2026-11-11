import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BotCommand

from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dp.message(CommandStart())
async def start_handler(message: Message):
    name = message.from_user.full_name if message.from_user else "ban"
    await message.answer(
        f"Xin chao <b>{name}</b>!\n\n"
        "Chao mung den voi <b>NGHIEN CODE</b> 🤖\n"
        "Dung /help de xem cac lenh."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "<b>HUONG DAN SU DUNG</b>\n"
        "/start - Bat dau\n"
        "/help - Xem huong dan\n"
        "/id - Xem Telegram ID\n"
        "/admin - Khu vuc quan tri"
    )


@dp.message(Command("id"))
async def id_handler(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    await message.answer(f"Telegram ID cua ban: <code>{user_id}</code>")


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("⛔ Ban khong co quyen truy cap.")
        return

    await message.answer(
        "✅ <b>QUAN TRI NGHIEN CODE</b>\n"
        f"ID admin: <code>{user_id}</code>\n"
        "Trang thai: Da xac thuc quyen admin."
    )


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    await bot.set_my_commands([
        BotCommand(command="start", description="Bat dau"),
        BotCommand(command="help", description="Huong dan"),
        BotCommand(command="id", description="Xem Telegram ID"),
        BotCommand(command="admin", description="Khu vuc quan tri"),
    ])
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
