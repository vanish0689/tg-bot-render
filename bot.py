import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup, 
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery)
from aiogram.filters import Command

# ========================= НАСТРОЙКИ =========================
# ВНИМАНИЕ: Замени на новый токен, старый нужно аннулировать!
BOT_TOKEN = "ТВОЙ_НОВЫЙ_ТОКЕН" 

PRICES = {
    "photo": 5,
    "video": 15,
    "document": 10,
    "audio": 10,
    "voice": 8,
}

ADMINS = [7770818181]
CHANNEL_ID = -1003349514214
# ============================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
router = Router()
dp.include_router(router)

# Подключение к БД
conn = sqlite3.connect("media_bot.db", check_same_thread=False)
cur = conn.cursor()

# Таблица платежей
cur.execute("""CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                file_id TEXT,
                file_type TEXT,
                price INTEGER,
                charge_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")

# Таблица для временного хранения инфо о файлах (чтобы callback_data был коротким)
cur.execute("""CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT,
                file_type TEXT,
                price INTEGER)""")
conn.commit()

def get_price(file_type: str) -> int:
    return PRICES.get(file_type, 10)

# =================== ОБРАБОТКА ПОСТОВ В КАНАЛЕ ===================
@router.channel_post(F.chat.id == CHANNEL_ID)
async def handle_channel_post(message: Message):
    if not (message.photo or message.video or message.document or message.audio or message.voice):
        return

    # Определяем тип и file_id
    file_id = None
    file_type = None

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

    if not file_id:
        return

    price = get_price(file_type)
    
    # СОХРАНЯЕМ В БД для сокращения callback_data
    cur.execute("INSERT INTO items (file_id, file_type, price) VALUES (?, ?, ?)", 
                (file_id, file_type, price))
    conn.commit()
    item_id = cur.lastrowid 

    # Кнопка теперь содержит только ID записи из нашей БД (короткая строка)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💎 Скачать за {price} Stars",
            callback_data=f"buy_{item_id}"
        )
    ]])

    original_caption = message.caption or ""
    new_caption = f"{original_caption}\n\n📸 {file_type.capitalize()} • Доступен после оплаты"

    try:
        await bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=new_caption,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка редактирования: {e}")

# =================== ОБРАБОТКА ОПЛАТЫ ===================
@router.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    item_id = callback.data.split("_")[1]
    
    # Достаем реальный file_id из базы
    cur.execute("SELECT file_id, file_type, price FROM items WHERE id = ?", (item_id,))
    item = cur.fetchone()
    
    if not item:
        await callback.answer("Файл не найден или устарел 😔", show_alert=True)
        return

    file_id, file_type, price = item

    # Отправляем инвойс в ЛИЧКУ пользователю
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Доступ к файлу ({file_type})",
            description="Оплатите доступ, чтобы получить файл в личные сообщения.",
            payload=f"media_{item_id}", 
            provider_token="", # Пусто для Telegram Stars
            currency="XTR",
            prices=[LabeledPrice(label="Оплата контента", amount=int(price))],
            protect_content=True
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("Сначала запустите бота в ЛС!", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    item_id = payload.split("_")[1]

    # Получаем данные файла по ID из payload
    cur.execute("SELECT file_id, file_type, price FROM items WHERE id = ?", (item_id,))
    item = cur.fetchone()

    if not item:
        await message.answer("Ошибка: данные файла не найдены.")
        return

    file_id, file_type, price = item

    # Сохраняем факт оплаты
    cur.execute("INSERT INTO payments (user_id, file_id, file_type, price, charge_id) VALUES (?, ?, ?, ?, ?)",
                (message.from_user.id, file_id, file_type, price, message.successful_payment.telegram_payment_charge_id))
    conn.commit()

    # Отправляем файл
    await message.answer("✅ Оплата прошла успешно! Отправляю файл:")
    
    try:
        if file_type == "photo":
            await message.answer_photo(file_id)
        elif file_type == "video":
            await message.answer_video(file_id)
        elif file_type == "audio":
            await message.answer_audio(file_id)
        elif file_type == "voice":
            await message.answer_voice(file_id)
        else:
            await message.answer_document(file_id)
    except Exception as e:
        await message.answer(f"Ошибка при отправке: {e}")

@router.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id not in ADMINS:
        return
    cur.execute("SELECT COUNT(*), SUM(price) FROM payments")
    count, earned = cur.fetchone()
    await message.answer(f"📊 Статистика:\nПродаж: {count}\nЗаработано: {earned or 0} Stars")

# =================== ЗАПУСК ===================
async def main():
    logging.basicConfig(level=logging.INFO)
    
    # 1. Удаляем вебхук и старые обновления, чтобы избежать ConflictError
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("🚀 Бот запущен и очищен от старых сессий.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
