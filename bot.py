import asyncio
import logging
import sqlite3
import time
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    PreCheckoutQuery,
    LabeledPrice,
    ContentType,
)
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = "8608551495:AAGFhxbLCeL0gQN7Q6LpHZCgJ5S6H4xhljY"   # <-- ВСТАВЬ СВОЙ ТОКЕН
BOT_USERNAME = "er_e4r_bot"         # <-- имя бота без @

OWNER_ID = 7770818181
CHANNEL_ID = -1003349514214
CHANNEL_URL = "https://t.me/Kastle202589"

DB_PATH = "bot.db"

# Типы контента и цены в Stars
CONTENT_TYPES = {
    "article": {"title": "Статья", "price": 1},
    "poem": {"title": "Стихотворение", "price": 3},
    "song_text": {"title": "Текст песни", "price": 5},
    "image": {"title": "Картинка", "price": 5},
    "music": {"title": "Музыка", "price": 10},
    "video": {"title": "Видео", "price": 15},
}

# ================== БД ==================

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        title TEXT,
        tg_file_id TEXT,
        text_content TEXT,
        created_at INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS balances (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL, -- pending, approved, declined
        created_at INTEGER,
        processed_by INTEGER,
        processed_at INTEGER,
        note TEXT
    )
    """)
    conn.commit()
    return conn

DB = init_db()

def db_add_file(owner_id: int, type_key: str, title: str, tg_file_id: Optional[str], text_content: Optional[str]) -> int:
    cur = DB.cursor()
    cur.execute(
        "INSERT INTO files (owner_id, type, title, tg_file_id, text_content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (owner_id, type_key, title, tg_file_id, text_content, int(time.time()))
    )
    DB.commit()
    return cur.lastrowid

def db_get_file(file_id: int) -> Optional[Dict[str, Any]]:
    cur = DB.cursor()
    cur.execute("SELECT id, owner_id, type, title, tg_file_id, text_content FROM files WHERE id = ?", (file_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "owner_id": row[1],
        "type": row[2],
        "title": row[3],
        "tg_file_id": row[4],
        "text": row[5],
    }

def db_list_files() -> Dict[int, Dict[str, Any]]:
    cur = DB.cursor()
    cur.execute("SELECT id, owner_id, type, title FROM files ORDER BY id ASC")
    rows = cur.fetchall()
    result = {}
    for r in rows:
        result[r[0]] = {"id": r[0], "owner_id": r[1], "type": r[2], "title": r[3]}
    return result

def db_get_balance(user_id: int) -> int:
    cur = DB.cursor()
    cur.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0

def db_add_balance(user_id: int, amount: int):
    cur = DB.cursor()
    cur.execute("INSERT INTO balances(user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                (user_id, amount, amount))
    DB.commit()

def db_create_withdraw_request(user_id: int, amount: int) -> int:
    cur = DB.cursor()
    cur.execute("INSERT INTO withdraw_requests(user_id, amount, status, created_at) VALUES (?, ?, ?, ?)",
                (user_id, amount, "pending", int(time.time())))
    DB.commit()
    return cur.lastrowid

def db_get_withdraw_request(req_id: int) -> Optional[Dict[str, Any]]:
    cur = DB.cursor()
    cur.execute("SELECT id, user_id, amount, status, created_at, processed_by, processed_at, note FROM withdraw_requests WHERE id = ?", (req_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "amount": row[2],
        "status": row[3],
        "created_at": row[4],
        "processed_by": row[5],
        "processed_at": row[6],
        "note": row[7],
    }

def db_update_withdraw(req_id: int, status: str, processed_by: Optional[int] = None, note: Optional[str] = None):
    cur = DB.cursor()
    cur.execute("UPDATE withdraw_requests SET status = ?, processed_by = ?, processed_at = ?, note = ? WHERE id = ?",
                (status, processed_by, int(time.time()) if processed_by else None, note, req_id))
    DB.commit()

# ================== Меню и утилиты ==================

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📁 Список файлов")],
        [KeyboardButton(text="⭐ Купить файл")],
        [KeyboardButton(text="📢 Проверить подписку")],
        [KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="📤 Отправить файл")],
    ],
    resize_keyboard=True
)

choose_type_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📰 Статья"), KeyboardButton(text="🎵 Текст песни")],
        [KeyboardButton(text="✒️ Стихотворение")],
        [KeyboardButton(text="🖼 Картинка"), KeyboardButton(text="🎧 Музыка")],
        [KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="⬅️ Отмена")],
    ],
    resize_keyboard=True
)

def buy_buttons(file_internal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оплатить Stars", callback_data=f"buy_{file_internal_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
        ]
    )

def get_file_list_text() -> str:
    files = db_list_files()
    if not files:
        return "Пока нет доступных файлов."
    lines = ["Доступные файлы:"]
    for fid, data in files.items():
        c = CONTENT_TYPES[data["type"]]
        lines.append(f"{fid}. {data['title']} ({c['title']}, {c['price']}⭐)")
    return "\n".join(lines)

def resolve_type_from_button(text: str) -> Optional[str]:
    mapping = {
        "📰 Статья": "article",
        "🎵 Текст песни": "song_text",
        "✒️ Стихотворение": "poem",
        "🖼 Картинка": "image",
        "🎧 Музыка": "music",
        "🎬 Видео": "video",
    }
    return mapping.get(text)

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        return False

# ================== Основной бот ==================

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # /start с deep-link
    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""

        if args.startswith("file_"):
            try:
                fid = int(args.replace("file_", ""))
            except:
                await message.answer("Неверная ссылка.")
                return

            file = db_get_file(fid)
            if not file:
                await message.answer("Файл не найден или ссылка неверна.")
                return

            subscribed = await is_subscribed(bot, message.from_user.id)
            subscribe_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                    [InlineKeyboardButton(text="🔄 Я подписался", callback_data=f"check_sub_{fid}")],
                ]
            )

            if not subscribed:
                await message.answer("Чтобы получить доступ к файлу, подпишитесь на канал:", reply_markup=subscribe_kb)
                return

            # Показываем превью и кнопку покупки
            c = CONTENT_TYPES[file["type"]]
            try:
                if file["type"] in ("article", "poem", "song_text"):
                    await message.answer(file["text"], protect_content=True)
                elif file["type"] == "image":
                    await message.answer_photo(file["tg_file_id"], caption=file["title"], protect_content=True)
                elif file["type"] == "music":
                    await message.answer_audio(file["tg_file_id"], caption=file["title"], protect_content=True)
                elif file["type"] == "video":
                    await message.answer_video(file["tg_file_id"], caption=file["title"], protect_content=True)
                else:
                    await message.answer_document(file["tg_file_id"], caption=file["title"], protect_content=True)
            except Exception as e:
                logger.error(f"Ошибка превью при /start file_: {e}")
                await message.answer("Не удалось показать превью файла.")

            await message.answer(
                f"<b>{file['title']}</b>\nТип: {c['title']}\nЦена: {c['price']}⭐",
                reply_markup=buy_buttons(fid)
            )
            return

        # Обычный /start
        subscribed = await is_subscribed(bot, message.from_user.id)
        subscribe_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="🔄 Я подписался", callback_data="check_sub_again")],
            ]
        )

        if not subscribed:
            await message.answer("Чтобы пользоваться ботом, нужно подписаться на канал 👇", reply_markup=subscribe_kb)
            return

        await message.answer("Добро пожаловать!", reply_markup=main_menu)

    # Кнопка "Я подписался" общая
    @dp.callback_query(F.data == "check_sub_again")
    async def check_sub_again(callback: CallbackQuery):
        subscribed = await is_subscribed(callback.bot, callback.from_user.id)
        if subscribed:
            await callback.message.edit_text("Спасибо за подписку!")
            await callback.message.answer("Главное меню:", reply_markup=main_menu)
        else:
            await callback.answer("Вы всё ещё не подписаны.", show_alert=True)

    # Кнопка "Я подписался" для конкретного файла
    @dp.callback_query(F.data.regexp(r"^check_sub_\d+$"))
    async def check_sub_for_file(callback: CallbackQuery):
        fid = int(callback.data.split("_")[2])
        subscribed = await is_subscribed(callback.bot, callback.from_user.id)
        if not subscribed:
            await callback.answer("Вы всё ещё не подписаны.", show_alert=True)
            return
        file = db_get_file(fid)
        if not file:
            await callback.message.edit_text("Файл не найден.")
            return
        c = CONTENT_TYPES[file["type"]]
        try:
            if file["type"] in ("article", "poem", "song_text"):
                await callback.message.answer(file["text"], protect_content=True)
            elif file["type"] == "image":
                await callback.message.answer_photo(file["tg_file_id"], caption=file["title"], protect_content=True)
            elif file["type"] == "music":
                await callback.message.answer_audio(file["tg_file_id"], caption=file["title"], protect_content=True)
            elif file["type"] == "video":
                await callback.message.answer_video(file["tg_file_id"], caption=file["title"], protect_content=True)
            else:
                await callback.message.answer_document(file["tg_file_id"], caption=file["title"], protect_content=True)
        except Exception as e:
            logger.error(f"Ошибка превью после подписки: {e}")
            await callback.message.answer("Не удалось показать превью файла.")
        await callback.message.answer(f"<b>{file['title']}</b>\nТип: {c['title']}\nЦена: {c['price']}⭐", reply_markup=buy_buttons(fid))
        await callback.answer()

    # Вспомогательная проверка подписки
    async def require_sub(message: Message) -> bool:
        if not await is_subscribed(bot, message.from_user.id):
            await message.answer("❌ Сначала подпишитесь на канал.")
            return False
        return True

    # Команда владельца: посмотреть баланс
    @dp.message(Command("owner_balance"))
    async def owner_balance(message: Message):
        if message.from_user.id != OWNER_ID:
            return
        bal = db_get_balance(OWNER_ID)
        await message.answer(f"Баланс владельца: {bal}⭐")

    # Команда /withdraw — создаёт запрос на вывод
    @dp.message(Command("withdraw"))
    async def withdraw(message: Message):
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Использование: /withdraw <сумма>")
            return
        amount = int(parts[1])
        bal = db_get_balance(message.from_user.id)
        if amount <= 0 or amount > bal:
            await message.answer("Недостаточно средств или неверная сумма.")
            return
        req_id = db_create_withdraw_request(message.from_user.id, amount)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_withdraw:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_withdraw:{req_id}")
            ]
        ])
        await bot.send_message(OWNER_ID, f"Новый запрос на вывод #{req_id}\nПользователь: {message.from_user.id}\nСумма: {amount}⭐", reply_markup=kb)
        await message.answer("Запрос на вывод отправлен владельцу. Ожидайте подтверждения.")

    # Обработчики подтверждения/отклонения владельцем
    @dp.callback_query(F.data.regexp(r"^approve_withdraw:\d+$"))
    async def approve_withdraw(callback: CallbackQuery):
        if callback.from_user.id != OWNER_ID:
            await callback.answer("Только владелец может подтверждать.", show_alert=True)
            return
        req_id = int(callback.data.split(":")[1])
        req = db_get_withdraw_request(req_id)
        if not req or req["status"] != "pending":
            await callback.answer("Запрос не найден или уже обработан.", show_alert=True)
            return
        user_id = req["user_id"]
        amount = req["amount"]
        if db_get_balance(user_id) < amount:
            db_update_withdraw(req_id, "failed", OWNER_ID, "Недостаточно средств")
            await callback.message.edit_text(f"Запрос #{req_id} не выполнен — недостаточно средств.")
            await callback.answer()
            return
        # списываем баланс
        cur = DB.cursor()
        cur.execute("UPDATE balances SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        DB.commit()
        db_update_withdraw(req_id, "approved", OWNER_ID, "Подтверждён владельцем")
        await callback.message.edit_text(f"Запрос #{req_id} подтверждён. Выплатите {amount}⭐ пользователю {user_id} вручную.")
        try:
            await bot.send_message(user_id, f"Ваш запрос на вывод #{req_id} подтверждён. Ожидайте перевод от владельца.")
        except Exception:
            pass
        await callback.answer("Подтверждено.")

    @dp.callback_query(F.data.regexp(r"^decline_withdraw:\d+$"))
    async def decline_withdraw(callback: CallbackQuery):
        if callback.from_user.id != OWNER_ID:
            await callback.answer("Только владелец может отклонять.", show_alert=True)
            return
        req_id = int(callback.data.split(":")[1])
        req = db_get_withdraw_request(req_id)
        if not req or req["status"] != "pending":
            await callback.answer("Запрос не найден или уже обработан.", show_alert=True)
            return
        db_update_withdraw(req_id, "declined", OWNER_ID, "Отклонён владельцем")
        await callback.message.edit_text(f"Запрос #{req_id} отклонён владельцем.")
        try:
            await bot.send_message(req["user_id"], f"Ваш запрос на вывод #{req_id} отклонён владельцем.")
        except Exception:
            pass
        await callback.answer("Отклонено.")

    # Главное меню
    @dp.message(F.text == "📁 Список файлов")
    async def show_files(message: Message):
        if not await require_sub(message): return
        await message.answer(get_file_list_text(), reply_markup=main_menu)

    @dp.message(F.text == "⭐ Купить файл")
    async def choose_file_to_buy(message: Message):
        if not await require_sub(message): return
        files = db_list_files()
        if not files:
            await message.answer("Пока нет файлов.", reply_markup=main_menu)
            return
        await message.answer(get_file_list_text() + "\n\nВведите номер файла.")

    @dp.message(F.text == "📢 Проверить подписку")
    async def check_sub_button(message: Message):
        subscribed = await is_subscribed(bot, message.from_user.id)
        if subscribed:
            await message.answer("✅ Вы подписаны.", reply_markup=main_menu)
        else:
            await message.answer("❌ Вы не подписаны.", reply_markup=main_menu)

    @dp.message(F.text == "ℹ️ Помощь")
    async def help_button(message: Message):
        await message.answer(
            "• Только владелец может загружать файлы.\n"
            "• Перед загрузкой выбирается тип (статья, текст песни, стих, картинка, музыка, видео).\n"
            "• Цена зависит от типа.\n"
            "• Все сообщения и файлы защищены от пересылки.\n"
            "• После загрузки бот выдаёт ссылку для публикации в канале.",
            reply_markup=main_menu
        )

    @dp.message(F.text == "📤 Отправить файл")
    async def send_file_menu(message: Message):
        if message.from_user.id != OWNER_ID:
            await message.answer("Только владелец может загружать файлы.")
            return
        await message.answer("Выберите тип:", reply_markup=choose_type_menu)

    @dp.message(F.text == "⬅️ Отмена")
    async def cancel_type(message: Message):
        # отмена загрузки
        await message.answer("Отменено.", reply_markup=main_menu)

    # Выбор типа владельцем
    PENDING_TYPE: Dict[int, str] = {}

    @dp.message(F.text.in_([
        "📰 Статья", "🎵 Текст песни", "✒️ Стихотворение",
        "🖼 Картинка", "🎧 Музыка", "🎬 Видео"
    ]))
    async def owner_choose_type(message: Message):
        if message.from_user.id != OWNER_ID:
            return
        type_key = resolve_type_from_button(message.text)
        if not type_key:
            return
        PENDING_TYPE[message.from_user.id] = type_key
        if type_key in ("article", "poem", "song_text"):
            await message.answer("Теперь отправьте текст.", reply_markup=main_menu)
        else:
            await message.answer("Теперь отправьте файл.", reply_markup=main_menu)

    # Ввод номера файла (просмотр + покупка)
    @dp.message(F.text.regexp(r"^\d+$"))
    async def handle_file_number(message: Message):
        if not await require_sub(message): return
        file_id = int(message.text)
        file = db_get_file(file_id)
        if not file:
            await message.answer("Файл не найден.")
            return
        c = CONTENT_TYPES[file["type"]]
        try:
            if file["type"] in ("article", "poem", "song_text"):
                await message.answer(file["text"], protect_content=True)
            elif file["type"] == "image":
                await message.answer_photo(file["tg_file_id"], caption=file["title"], protect_content=True)
            elif file["type"] == "music":
                await message.answer_audio(file["tg_file_id"], caption=file["title"], protect_content=True)
            elif file["type"] == "video":
                await message.answer_video(file["tg_file_id"], caption=file["title"], protect_content=True)
            else:
                await message.answer_document(file["tg_file_id"], caption=file["title"], protect_content=True)
        except Exception as e:
            logger.error(f"Ошибка превью: {e}")
            await message.answer("Ошибка при показе файла.")
        await message.answer(f"<b>{file['title']}</b>\nТип: {c['title']}\nЦена: {c['price']}⭐", reply_markup=buy_buttons(file_id))

    # Приём текстового контента от владельца
    @dp.message(F.content_type == ContentType.TEXT)
    async def handle_text(message: Message):
        if message.from_user.id == OWNER_ID and message.from_user.id in PENDING_TYPE:
            type_key = PENDING_TYPE.pop(message.from_user.id)
            if type_key not in ("article", "poem", "song_text"):
                await message.answer("Ожидался файл, а не текст.")
                return
            fid = db_add_file(OWNER_ID, type_key, CONTENT_TYPES[type_key]["title"], None, message.text)
            link = f"https://t.me/{BOT_USERNAME}?start=file_{fid}"
            await message.answer(f"{CONTENT_TYPES[type_key]['title']} сохранена.\nID: {fid}\nСсылка для публикации:\n{link}", reply_markup=main_menu)
            return
        await message.answer("Если хотите купить файл — выберите его номер из списка.", reply_markup=main_menu)

    # Приём файлов от владельца
    @dp.message(F.content_type.in_([ContentType.DOCUMENT, ContentType.VIDEO, ContentType.AUDIO, ContentType.PHOTO]))
    async def handle_files(message: Message):
        if message.from_user.id != OWNER_ID:
            await message.answer("Только владелец может отправлять файлы.")
            return
        if message.from_user.id not in PENDING_TYPE:
            await message.answer("Сначала выберите тип через «📤 Отправить файл».")
            return
        type_key = PENDING_TYPE.pop(message.from_user.id)
        if type_key not in ("image", "music", "video"):
            await message.answer("Для текстовых типов нужен текст.")
            return
        if message.document:
            tg_file_id = message.document.file_id
            title = message.document.file_name or CONTENT_TYPES[type_key]["title"]
        elif message.video:
            tg_file_id = message.video.file_id
            title = "Видео"
        elif message.audio:
            tg_file_id = message.audio.file_id
            title = "Музыка"
        elif message.photo:
            tg_file_id = message.photo[-1].file_id
            title = "Картинка"
        else:
            await message.answer("Неизвестный тип файла.")
            return
        fid = db_add_file(OWNER_ID, type_key, title, tg_file_id, None)
        link = f"https://t.me/{BOT_USERNAME}?start=file_{fid}"
        await message.answer(f"Файл сохранён.\nID: {fid}\nСсылка для публикации:\n{link}", reply_markup=main_menu)

    # Покупка файла (инвойс)
    @dp.callback_query(F.data.startswith("buy_"))
    async def cb_buy_file(callback: CallbackQuery):
        file_id = int(callback.data.split("_")[1])
        file = db_get_file(file_id)
        if not file:
            await callback.answer("Файл не найден.", show_alert=True)
            return
        c = CONTENT_TYPES[file["type"]]
        prices = [LabeledPrice(label=file["title"], amount=c["price"])]
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=file["title"],
            description=c["title"],
            payload=f"file_{file_id}",
            provider_token="",  # <-- вставь provider_token если используешь платежи
            currency="XTR",
            prices=prices,
        )
        await callback.answer()

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    # Успешная оплата — фиксируем и отправляем файл
    @dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
    async def successful_payment_handler(message: Message):
        payload = message.successful_payment.invoice_payload
        if not payload.startswith("file_"):
            return
        try:
            file_id = int(payload.split("_")[1])
        except:
            await message.answer("Неверный payload.")
            return
        file = db_get_file(file_id)
        if not file:
            await message.answer("Файл не найден.")
            return
        price = CONTENT_TYPES[file["type"]]["price"]
        # Начисляем всю сумму владельцу
        db_add_balance(OWNER_ID, price)
        await message.answer("Оплата получена! Отправляю контент...")
        try:
            if file["type"] in ("article", "poem", "song_text"):
                await message.answer(file["text"], protect_content=True)
            elif file["type"] == "image":
                await message.answer_photo(file["tg_file_id"], protect_content=True)
            elif file["type"] == "music":
                await message.answer_audio(file["tg_file_id"], protect_content=True)
            elif file["type"] == "video":
                await message.answer_video(file["tg_file_id"], protect_content=True)
            else:
                await message.answer_document(file["tg_file_id"], protect_content=True)
        except Exception as e:
            logger.error(f"Ошибка отправки контента после оплаты: {e}")
            await message.answer("Не удалось отправить файл, свяжитесь с владельцем.")

    # Callback: назад в меню
    @dp.callback_query(F.data == "back_to_menu")
    async def cb_back_to_menu(callback: CallbackQuery):
        await callback.message.edit_text("Главное меню.")
        await callback.message.answer("Выберите действие:", reply_markup=main_menu)
        await callback.answer()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
