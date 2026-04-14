import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
import sqlite3

# ========================= НАСТРОЙКИ =========================
BOT_TOKEN = "8608551495:AAGFhxbLCeL0gQN7Q6LpHZCgJ5S6H4xhljY"

# Цены по типам медиа (меняй здесь как хочешь)
PRICES = {
    "photo": 5,
    "video": 15,
    "document": 10,
    "audio": 10,
    "voice": 8,
}

ADMINS = [7770818181]

# Твой канал (уже вставлен)
CHANNEL_ID = -1003349514214

# ============================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# База данных
conn = sqlite3.connect("media_bot.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                file_id TEXT,
                file_type TEXT,
                price INTEGER,
                charge_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
conn.commit()

def get_price(file_type: str) -> int:
    return PRICES.get(file_type, 10)

# =================== РЕАКЦИЯ НА ПОСТЫ В КАНАЛЕ ===================
@router.message(F.chat.id == CHANNEL_ID)
async def handle_channel_post(message: Message):
    if not (message.photo or message.video or message.document or message.audio or message.voice):
        return

    # Определяем тип и file_id
    if message.photo:
        file_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        file_type = "video"
        file_id = message.video.file_id
    elif message.document:
        file_type = "document"
        file_id = message.document.file_id
    elif message.audio:
        file_type = "audio"
        file_id = message.audio.file_id
    elif message.voice:
        file_type = "voice"
        file_id = message.voice.file_id
    else:
        return

    price = get_price(file_type)
    original_caption = message.caption or ""

    # Кнопка оплаты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💎 Скачать за {price} Stars",
            callback_data=f"buy_{file_type}_{file_id}_{price}"
        )
    ]])

    # Новая подпись
    new_caption = f"{original_caption}\n\n📸 {file_type.capitalize()} • Скачать за {price} Stars"

    try:
        # Пытаемся отредактировать подпись и добавить кнопку
        await bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=new_caption,
            reply_markup=keyboard
        )
    except:
        # Если не получилось (например, пост без подписи), добавляем текст под постом
        await bot.send_message(
            chat_id=message.chat.id,
            text=new_caption,
            reply_to_message_id=message.message_id,
            reply_markup=keyboard
        )

# =================== ОПЛАТА ===================
@router.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    _, file_type, file_id, price_str = callback.data.split("_", 3)
    price = int(price_str)

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Скачать {file_type}",
        description="Полный файл без ограничений",
        payload=f"media_{file_id}_{file_type}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{file_type.capitalize()}", amount=price)],
        protect_content=True
    )
    await callback.answer("Переходим к оплате...")

@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload

    try:
        _, file_id, file_type = payload.split("_")[:3]
    except:
        await message.answer("Ошибка при отправке файла 😔")
        return

    # Сохраняем продажу
    cur.execute("INSERT INTO payments (user_id, file_id, file_type, price, charge_id) VALUES (?, ?, ?, ?, ?)",
                (message.from_user.id, file_id, file_type, payment.total_amount, payment.telegram_payment_charge_id))
    conn.commit()

    # Отправляем полный файл в ЛС
    try:
        if file_type == "photo":
            await bot.send_photo(message.from_user.id, file_id, caption="✅ Вот твой полный файл. Спасибо!")
        elif file_type == "video":
            await bot.send_video(message.from_user.id, file_id, caption="✅ Вот твой полный файл. Спасибо!")
        else:
            await bot.send_document(message.from_user.id, file_id, caption="✅ Вот твой полный файл. Спасибо!")
    except:
        await message.answer("Не удалось отправить файл. Напиши мне напрямую.")

# =================== АДМИН ===================
@router.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id not in ADMINS:
        return
    cur.execute("SELECT COUNT(*) as total, SUM(price) as earned FROM payments")
    row = cur.fetchone()
    await message.answer(f"📊 Статистика бота:\n\nПродаж: {row[0]}\nЗаработано Stars: {row[1] or 0}")

# =================== ЗАПУСК ===================
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Бот для канала @Kastle202589 запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
