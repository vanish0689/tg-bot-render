import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup, 
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command

# ========================= КОНФИГУРАЦИЯ =========================
# Вставь сюда новый токен. Метод .strip() уберет случайные пробелы.
TOKEN_STR = "8608551495:AAGFhxbLCeL0gQN7Q6LpHZCgJ5S6H4xhljY" 
BOT_TOKEN = TOKEN_STR.strip()

PRICES = {
    "photo": 5,
    "video": 15,
    "document": 10,
    "audio": 10,
    "voice": 8,
}

ADMINS = [7770818181]
CHANNEL_ID = -1003349514214
# ================================================================

# Инициализация бота с защитой от ошибок валидации
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# Работа с базой данных
conn = sqlite3.connect("media_bot.db", check_same_thread=False)
cur = conn.cursor()

def init_db():
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    file_id TEXT,
                    file_type TEXT,
                    price INTEGER,
                    charge_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT,
                    file_type TEXT,
                    price INTEGER)""")
    conn.commit()

init_db()

# =================== ЛОГИКА КАНАЛА ===================

@router.channel_post(F.chat.id == CHANNEL_ID)
async def handle_channel_post(message: Message):
    # Извлекаем file_id в зависимости от типа медиа
    file_id = None
    file_type = None

    if message.photo:
        file_type, file_id = "photo", message.photo[-1].file_id
    elif message.video:
        file_type, file_id = "video", message.video.file_id
    elif message.document:
        file_type, file_id = "document", message.document.file_id
    elif message.audio:
        file_type, file_id = "audio", message.audio.file_id
    elif message.voice:
        file_type, file_id = "voice", message.voice.file_id

    if not file_id:
        return

    price = PRICES.get(file_type, 10)
    
    # Сохраняем в БД, чтобы в кнопке передать только ID (лимит 64 байта)
    cur.execute("INSERT INTO items (file_id, file_type, price) VALUES (?, ?, ?)", 
                (file_id, file_type, price))
    conn.commit()
    item_id = cur.lastrowid 

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💎 Скачать за {price} Stars",
            callback_data=f"buy_{item_id}"
        )
    ]])

    caption = message.caption or ""
    new_caption = f"{caption}\n\n📸 {file_type.capitalize()} • Доступен после оплаты"

    try:
        await bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=new_caption,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка при добавлении кнопки: {e}")

# =================== ОПЛАТА И СЧЕТА ===================

@router.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    try:
        item_id = callback.data.split("_")[1]
        cur.execute("SELECT file_id, file_type, price FROM items WHERE id = ?", (item_id,))
        item = cur.fetchone()
        
        if not item:
            return await callback.answer("Файл не найден.", show_alert=True)

        file_id, file_type, price = item

        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="Доступ к контенту",
            description=f"Оплата файла типа {file_type}",
            payload=f"it_{item_id}", # Короткий payload
            provider_token="", 
            currency="XTR",
            prices=[LabeledPrice(label="Оплата", amount=int(price))],
            protect_content=True
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("Пожалуйста, сначала запустите бота в ЛС!", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    item_id = message.successful_payment.invoice_payload.split("_")[1]
    
    cur.execute("SELECT file_id, file_type FROM items WHERE id = ?", (item_id,))
    item = cur.fetchone()
    if not item: return

    file_id, file_type = item

    # Логируем покупку
    cur.execute("INSERT INTO payments (user_id, file_id, file_type, price, charge_id) VALUES (?, ?, ?, ?, ?)",
                (message.from_user.id, file_id, file_type, message.successful_payment.total_amount, 
                 message.successful_payment.telegram_payment_charge_id))
    conn.commit()

    await message.answer("✅ Оплата принята! Лови файл:")
    
    # Отправка контента
    methods = {
        "photo": message.answer_photo,
        "video": message.answer_video,
        "audio": message.answer_audio,
        "voice": message.answer_voice
    }
    send_method = methods.get(file_type, message.answer_document)
    await send_method(file_id)

# =================== ЗАПУСК ===================

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Сброс вебхука и старых апдейтов для предотвращения ConflictError
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("✨ Бот запущен корректно.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")
