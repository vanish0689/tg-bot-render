import asyncio
import logging
import secrets
from typing import Dict, Any

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
BOT_USERNAME = "YourBotUsername"    # <-- ВСТАВЬ username бота без @

OWNER_ID = 7770818181
CHANNEL_ID = -1003349514214
CHANNEL_URL = "https://t.me/Kastle202589"

ADMIN_PERCENT = 80   # доля админа
OWNER_PERCENT = 20   # доля владельца

CONTENT_TYPES = {
    "article":   {"title": "Статья",       "price": 1},
    "poem":      {"title": "Стихотворение","price": 3},
    "song_text": {"title": "Текст песни",  "price": 5},
    "image":     {"title": "Картинка",     "price": 5},
    "music":     {"title": "Музыка",       "price": 10},
    "video":     {"title": "Видео",        "price": 15},
}

# ================== ХРАНИЛИЩЕ ==================

ADMINS: set[int] = {OWNER_ID}
ADMIN_TOKENS: Dict[str, int] = {}   # token -> creator_id
BALANCE: Dict[int, int] = {}        # user_id -> stars

FILES: Dict[int, Dict[str, Any]] = {}  # file_id -> data
FILE_COUNTER = 0

PENDING_TYPE: Dict[int, str] = {}   # user_id -> type_key

# ================== МЕНЮ ==================

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


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked")
    except:
        return False


def get_file_list_text() -> str:
    if not FILES:
        return "Пока нет доступных файлов."
    lines = ["Доступные файлы:"]
    for fid, data in FILES.items():
        c = CONTENT_TYPES[data["type"]]
        lines.append(f"{fid}. {data['title']} ({c['title']}, {c['price']}⭐)")
    return "\n".join(lines)


def resolve_type_from_button(text: str) -> str | None:
    mapping = {
        "📰 Статья": "article",
        "🎵 Текст песни": "song_text",
        "✒️ Стихотворение": "poem",
        "🖼 Картинка": "image",
        "🎧 Музыка": "music",
        "🎬 Видео": "video",
    }
    return mapping.get(text)


def add_balance(user_id: int, amount: int):
    if amount <= 0:
        return
    BALANCE[user_id] = BALANCE.get(user_id, 0) + amount


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # ---------- /start с deep-link ----------

    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        text = message.text or ""
        parts = text.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""

        if args.startswith("admin_"):
            token = args.replace("admin_", "")
            if token in ADMIN_TOKENS:
                ADMINS.add(message.from_user.id)
                del ADMIN_TOKENS[token]
                await message.answer("Вы назначены администратором бота.")
            else:
                await message.answer("Недействительная или уже использованная ссылка.")

        subscribed = await is_subscribed(bot, message.from_user.id)

        subscribe_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="🔄 Я подписался", callback_data="check_sub_again")],
            ]
        )

        if not subscribed:
            await message.answer(
                "Чтобы пользоваться ботом, нужно подписаться на канал 👇",
                reply_markup=subscribe_kb
            )
            return

        await message.answer("Добро пожаловать!", reply_markup=main_menu)

    # ---------- Кнопка “Я подписался” ----------

    @dp.callback_query(F.data == "check_sub_again")
    async def check_sub_again(callback: CallbackQuery):
        subscribed = await is_subscribed(callback.bot, callback.from_user.id)

        if subscribed:
            await callback.message.edit_text("Спасибо за подписку!")
            await callback.message.answer("Главное меню:", reply_markup=main_menu)
        else:
            await callback.answer("Вы всё ещё не подписаны.", show_alert=True)

    # ---------- Вспомогательная проверка подписки ----------

    async def require_sub(message: Message) -> bool:
        if not await is_subscribed(bot, message.from_user.id):
            await message.answer("❌ Сначала подпишитесь на канал.")
            return False
        return True

    # ---------- /myref для всех админов ----------

    @dp.message(Command("myref"))
    async def myref(message: Message):
        if not is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администраторам.")
            return

        token = secrets.token_urlsafe(8)
        ADMIN_TOKENS[token] = message.from_user.id

        link = f"https://t.me/{BOT_USERNAME}?start=admin_{token}"
        await message.answer(f"Ваша реферальная ссылка для нового админа:\n{link}")

    # ---------- Балансы и статистика ----------

    @dp.message(Command("balance"))
    async def cmd_balance(message: Message):
        bal = BALANCE.get(message.from_user.id, 0)
        await message.answer(f"Ваш баланс: {bal}⭐")

    @dp.message(Command("owner_stats"))
    async def owner_stats(message: Message):
        if message.from_user.id != OWNER_ID:
            return
        bal = BALANCE.get(OWNER_ID, 0)
        await message.answer(f"Доход владельца: {bal}⭐")

    @dp.message(Command("withdraw"))
    async def withdraw(message: Message):
        if not is_admin(message.from_user.id):
            return

        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Использование: /withdraw <сумма>")
            return

        amount = int(parts[1])
        bal = BALANCE.get(message.from_user.id, 0)

        if amount <= 0 or amount > bal:
            await message.answer("Недостаточно средств или неверная сумма.")
            return

        text = (
            f"Запрос на вывод:\n"
            f"Пользователь: {message.from_user.id}\n"
            f"Сумма: {amount}⭐\n"
            f"Текущий баланс: {bal}⭐"
        )
        try:
            await bot.send_message(OWNER_ID, text)
        except Exception as e:
            logger.error(f"Не удалось отправить запрос владельцу: {e}")

        await message.answer("Запрос на вывод отправлен владельцу. Ожидайте подтверждения.")

    # ---------- Главное меню ----------

    @dp.message(F.text == "📁 Список файлов")
    async def show_files(message: Message):
        if not await require_sub(message): return
        await message.answer(get_file_list_text(), reply_markup=main_menu)

    @dp.message(F.text == "⭐ Купить файл")
    async def choose_file_to_buy(message: Message):
        if not await require_sub(message): return
        if not FILES:
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
            "• Только админы могут загружать файлы.\n"
            "• Перед загрузкой выбирается тип (статья, текст песни, стих, картинка, музыка, видео).\n"
            "• Цена зависит от типа.\n"
            "• Все сообщения и файлы защищены от пересылки.\n"
            "• Есть реферальная система админов и баланс.",
            reply_markup=main_menu
        )

    @dp.message(F.text == "📤 Отправить файл")
    async def send_file_menu(message: Message):
        if not is_admin(message.from_user.id):
            await message.answer("У вас нет прав администратора.")
            return
        await message.answer("Выберите тип:", reply_markup=choose_type_menu)

    @dp.message(F.text == "⬅️ Отмена")
    async def cancel_type(message: Message):
        PENDING_TYPE.pop(message.from_user.id, None)
        await message.answer("Отменено.", reply_markup=main_menu)

    # ---------- Выбор типа контента админом ----------

    @dp.message(F.text.in_([
        "📰 Статья", "🎵 Текст песни", "✒️ Стихотворение",
        "🖼 Картинка", "🎧 Музыка", "🎬 Видео"
    ]))
    async def owner_choose_type(message: Message):
        if not is_admin(message.from_user.id):
            return
        type_key = resolve_type_from_button(message.text)
        if not type_key:
            return
        PENDING_TYPE[message.from_user.id] = type_key

        if type_key in ("article", "poem", "song_text"):
            await message.answer("Теперь отправьте текст.", reply_markup=main_menu)
        else:
            await message.answer("Теперь отправьте файл.", reply_markup=main_menu)

    # ---------- Ввод номера файла (просмотр + покупка) ----------

    @dp.message(F.text.regexp(r"^\d+$"))
    async def handle_file_number(message: Message):
        if not await require_sub(message): return

        file_id = int(message.text)
        if file_id not in FILES:
            await message.answer("Файл не найден.")
            return

        file = FILES[file_id]
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

        await message.answer(
            f"<b>{file['title']}</b>\nТип: {c['title']}\nЦена: {c['price']}⭐",
            reply_markup=buy_buttons(file_id)
        )

    # ---------- Приём текстового контента от админа ----------

    @dp.message(F.content_type == ContentType.TEXT)
    async def handle_text(message: Message):
        if is_admin(message.from_user.id) and message.from_user.id in PENDING_TYPE:
            type_key = PENDING_TYPE.pop(message.from_user.id)
            if type_key not in ("article", "poem", "song_text"):
                await message.answer("Ожидался файл, а не текст.")
                return

            global FILE_COUNTER
            FILE_COUNTER += 1

            FILES[FILE_COUNTER] = {
                "owner_id": message.from_user.id,
                "type": type_key,
                "title": CONTENT_TYPES[type_key]["title"],
                "text": message.text,
                "tg_file_id": None,
            }

            await message.answer(
                f"{CONTENT_TYPES[type_key]['title']} сохранена.\nID: {FILE_COUNTER}",
                reply_markup=main_menu
            )
            return

        await message.answer(
            "Если хотите купить файл — выберите его номер из списка.",
            reply_markup=main_menu
        )

    # ---------- Приём файлов от админа ----------

    @dp.message(F.content_type.in_([ContentType.DOCUMENT, ContentType.VIDEO, ContentType.AUDIO, ContentType.PHOTO]))
    async def handle_files(message: Message):
        if not is_admin(message.from_user.id):
            await message.answer("Вы не можете отправлять файлы.")
            return

        if message.from_user.id not in PENDING_TYPE:
            await message.answer("Сначала выберите тип через «📤 Отправить файл».")
            return

        type_key = PENDING_TYPE.pop(message.from_user.id)

        if type_key not in ("image", "music", "video"):
            await message.answer("Для текстовых типов нужно отправлять текст.")
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

        global FILE_COUNTER
        FILE_COUNTER += 1

        FILES[FILE_COUNTER] = {
            "owner_id": message.from_user.id,
            "type": type_key,
            "title": title,
            "tg_file_id": tg_file_id,
            "text": None,
        }

        await message.answer(
            f"Файл сохранён.\nID: {FILE_COUNTER}",
            reply_markup=main_menu
        )

    # ---------- Покупка файла ----------

    @dp.callback_query(F.data.startswith("buy_"))
    async def cb_buy_file(callback: CallbackQuery):
        file_id = int(callback.data.split("_")[1])
        if file_id not in FILES:
            await callback.answer("Файл не найден.", show_alert=True)
            return

        file = FILES[file_id]
        c = CONTENT_TYPES[file["type"]]

        prices = [LabeledPrice(label=file["title"], amount=c["price"])]

        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=file["title"],
            description=c["title"],
            payload=f"file_{file_id}",
            provider_token="",
            currency="XTR",
            prices=prices,
        )

        await callback.answer()

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
    async def successful_payment_handler(message: Message):
        payload = message.successful_payment.invoice_payload
        if not payload.startswith("file_"):
            return

        file_id = int(payload.split("_")[1])
        if file_id not in FILES:
            await message.answer("Файл не найден.")
            return

        file = FILES[file_id]
        c = CONTENT_TYPES[file["type"]]
        price = c["price"]

        owner_id = file["owner_id"]
        admin_cut = price * ADMIN_PERCENT // 100
        owner_cut = price - admin_cut

        add_balance(owner_id, admin_cut)
        add_balance(OWNER_ID, owner_cut)

        await message.answer("Оплата получена! Отправляю контент...")

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

    # ---------- Callback: назад в меню ----------

    @dp.callback_query(F.data == "back_to_menu")
    async def cb_back_to_menu(callback: CallbackQuery):
        await callback.message.edit_text("Главное меню.")
        await callback.message.answer("Выберите действие:", reply_markup=main_menu)
        await callback.answer()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
