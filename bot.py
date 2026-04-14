import asyncio
import logging
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

BOT_TOKEN = "8608551495:AAGFhxbLCeL0gQN7Q6LpHZCgJ5S6H4xhljY"  # <-- сюда ВСТАВЬ НОВЫЙ ТОКЕН
OWNER_ID = 7770818181
CHANNEL_ID = -1003349514214  # id канала/группы

# Типы контента и цены в Stars
CONTENT_TYPES = {
    "article": {"title": "Статья", "price": 1},
    "poem": {"title": "Стихотворение", "price": 3},
    "song_text": {"title": "Текст песни", "price": 5},
    "image": {"title": "Картинка", "price": 5},
    "music": {"title": "Музыка", "price": 10},
    "video": {"title": "Видео", "price": 15},
}

# ================== ХРАНИЛИЩЕ ==================
# В реальном проекте лучше БД. Здесь — в памяти.

FILES: Dict[int, Dict[str, Any]] = {}
FILE_COUNTER = 0

# pending_type для владельца: user_id -> type_key
PENDING_TYPE: Dict[int, str] = {}

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
        [KeyboardButton(text="📰 Статья"),
         KeyboardButton(text="🎵 Текст песни")],
        [KeyboardButton(text="✒️ Стихотворение")],
        [KeyboardButton(text="🖼 Картинка"),
         KeyboardButton(text="🎧 Музыка")],
        [KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="⬅️ Отмена")],
    ],
    resize_keyboard=True
)


def buy_buttons(file_internal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оплатить Stars",
                    callback_data=f"buy_{file_internal_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_menu"
                )
            ],
        ]
    )


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ("left", "kicked"):
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False


def get_file_list_text() -> str:
    if not FILES:
        return "Пока нет доступных файлов."
    lines = ["Доступные файлы:"]
    for internal_id, data in FILES.items():
        ctype = CONTENT_TYPES.get(data["type"], {})
        ctitle = ctype.get("title", "Неизвестно")
        price = ctype.get("price", 0)
        lines.append(f"{internal_id}. {data['title']} ({ctitle}, {price}⭐)")
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


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # ---------- /start ----------

    @dp.message(CommandStart())
    async def cmd_start(message: Message):
        text = (
            "Привет!\n\n"
            "Этот бот продаёт контент за Telegram Stars.\n"
            "• Файлы и тексты загружает только владелец.\n"
            "• Пользователи могут покупать доступ к ним.\n\n"
            "Выберите действие из меню."
        )
        await message.answer(text, reply_markup=main_menu)

    # ---------- /help ----------

    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        text = (
            "ℹ️ <b>Помощь</b>\n\n"
            "• Только владелец может загружать файлы и тексты.\n"
            "• Перед загрузкой владелец выбирает тип: статья, текст песни, стихотворение, картинка, музыка, видео.\n"
            "• Цена зависит от типа:\n"
            "  - Статья (текст) — 1⭐\n"
            "  - Стихотворение — 3⭐\n"
            "  - Текст песни — 5⭐\n"
            "  - Картинка — 5⭐\n"
            "  - Музыка — 10⭐\n"
            "  - Видео — 15⭐\n"
            "• Сообщения и файлы отправляются с защитой от пересылки.\n"
        )
        await message.answer(text, reply_markup=main_menu)

    # ---------- Главное меню ----------

    @dp.message(F.text == "📁 Список файлов")
    async def show_files(message: Message):
        await message.answer(get_file_list_text(), reply_markup=main_menu)

    @dp.message(F.text == "⭐ Купить файл")
    async def choose_file_to_buy(message: Message):
        if not FILES:
            await message.answer("Пока нет доступных файлов.", reply_markup=main_menu)
            return
        text = get_file_list_text() + "\n\nОтправь номер файла, который хочешь купить."
        await message.answer(text, reply_markup=main_menu)

    @dp.message(F.text == "📢 Проверить подписку")
    async def check_sub(message: Message):
        subscribed = await is_subscribed(bot, message.from_user.id)
        if subscribed:
            await message.answer("✅ Вы подписаны на канал/группу.", reply_markup=main_menu)
        else:
            await message.answer(
                "❌ Вы не подписаны.\nПодпишитесь и попробуйте снова.",
                reply_markup=main_menu
            )

    @dp.message(F.text == "ℹ️ Помощь")
    async def help_button(message: Message):
        await cmd_help(message)

    @dp.message(F.text == "📤 Отправить файл")
    async def send_file_menu(message: Message):
        if message.from_user.id != OWNER_ID:
            await message.answer("Только владелец бота может загружать файлы.", reply_markup=main_menu)
            return
        await message.answer(
            "Что вы хотите отправить?\nВыберите тип:",
            reply_markup=choose_type_menu
        )

    @dp.message(F.text == "⬅️ Отмена")
    async def cancel_type(message: Message):
        if message.from_user.id == OWNER_ID and message.from_user.id in PENDING_TYPE:
            PENDING_TYPE.pop(message.from_user.id, None)
        await message.answer("Отменено.", reply_markup=main_menu)

    # ---------- Выбор типа контента владельцем ----------

    @dp.message(F.text.in_([
        "📰 Статья",
        "🎵 Текст песни",
        "✒️ Стихотворение",
        "🖼 Картинка",
        "🎧 Музыка",
        "🎬 Видео",
    ]))
    async def owner_choose_type(message: Message):
        if message.from_user.id != OWNER_ID:
            return
        type_key = resolve_type_from_button(message.text)
        if not type_key:
            return
        PENDING_TYPE[message.from_user.id] = type_key
        if type_key in ("article", "poem", "song_text"):
            await message.answer(
                f"Вы выбрали: {CONTENT_TYPES[type_key]['title']}.\n"
                "Теперь отправьте текст.",
                reply_markup=main_menu
            )
        else:
            await message.answer(
                f"Вы выбрали: {CONTENT_TYPES[type_key]['title']}.\n"
                "Теперь отправьте соответствующий файл.",
                reply_markup=main_menu
            )

    # ---------- Приём ТЕКСТА ----------

    @dp.message(F.content_type == ContentType.TEXT)
    async def handle_text(message: Message):
        global FILE_COUNTER

        # Если это число — выбор файла для покупки
        if message.text.isdigit():
            file_internal_id = int(message.text)
            if file_internal_id in FILES:
                file_data = FILES[file_internal_id]
                ctype = CONTENT_TYPES.get(file_data["type"], {})
                price = ctype.get("price", 0)
                text = (
                    f"Вы выбрали: <b>{file_data['title']}</b>\n"
                    f"Тип: {ctype.get('title', 'Неизвестно')}\n"
                    f"Цена: {price}⭐\n\n"
                    "Нажмите кнопку ниже, чтобы оплатить."
                )
                await message.answer(text, reply_markup=buy_buttons(file_internal_id))
                return

        # Владелец + выбран текстовый тип
        if message.from_user.id == OWNER_ID and message.from_user.id in PENDING_TYPE:
            type_key = PENDING_TYPE.pop(message.from_user.id)
            if type_key not in ("article", "poem", "song_text"):
                await message.answer(
                    "Ожидался файл, а не текст. Повторите выбор типа.",
                    reply_markup=main_menu
                )
                return

            FILE_COUNTER += 1
            internal_id = FILE_COUNTER
            FILES[internal_id] = {
                "type": type_key,
                "title": CONTENT_TYPES[type_key]["title"],
                "text": message.text,
                "tg_file_id": None,
            }

            await message.answer(
                f"{CONTENT_TYPES[type_key]['title']} сохранена.\n"
                f"ID внутри бота: {internal_id}",
                reply_markup=main_menu
            )
            return

        await message.answer(
            "Если хотите купить файл — выберите его номер из списка.",
            reply_markup=main_menu
        )

    # ---------- Приём ФАЙЛОВ от владельца ----------

    @dp.message(F.content_type.in_(
        [ContentType.DOCUMENT, ContentType.VIDEO, ContentType.AUDIO, ContentType.PHOTO]
    ))
    async def handle_files(message: Message):
        global FILE_COUNTER

        if message.from_user.id != OWNER_ID:
            await message.answer("Вы не можете отправлять файлы этому боту.")
            return

        if message.from_user.id not in PENDING_TYPE:
            await message.answer(
                "Сначала выберите тип через кнопку «📤 Отправить файл».",
                reply_markup=main_menu
            )
            return

        type_key = PENDING_TYPE.pop(message.from_user.id)
        if type_key not in ("image", "music", "video"):
            await message.answer(
                "Для текстовых типов нужно отправлять текст, а не файл.",
                reply_markup=main_menu
            )
            return

        if message.document:
            tg_file_id = message.document.file_id
            title = message.document.file_name or CONTENT_TYPES[type_key]["title"]
        elif message.video:
            tg_file_id = message.video.file_id
            title = CONTENT_TYPES[type_key]["title"]
        elif message.audio:
            tg_file_id = message.audio.file_id
            title = CONTENT_TYPES[type_key]["title"]
        elif message.photo:
            tg_file_id = message.photo[-1].file_id
            title = CONTENT_TYPES[type_key]["title"]
        else:
            await message.answer("Неизвестный тип файла.")
            return

        FILE_COUNTER += 1
        internal_id = FILE_COUNTER

        FILES[internal_id] = {
            "type": type_key,
            "title": title,
            "tg_file_id": tg_file_id,
            "text": None,
        }

        await message.answer(
            f"Файл сохранён.\nID внутри бота: {internal_id}\nТип: {CONTENT_TYPES[type_key]['title']}",
            reply_markup=main_menu
        )

    # ---------- Callback: назад в меню ----------

    @dp.callback_query(F.data == "back_to_menu")
    async def cb_back_to_menu(callback: CallbackQuery):
        await callback.message.edit_text("Главное меню.")
        await callback.message.answer("Выберите действие:", reply_markup=main_menu)
        await callback.answer()

    # ---------- Покупка файла ----------

    @dp.callback_query(F.data.startswith("buy_"))
    async def cb_buy_file(callback: CallbackQuery):
        data = callback.data.split("_")
        file_internal_id = int(data[1])

        if file_internal_id not in FILES:
            await callback.answer("Файл не найден.", show_alert=True)
            return

        subscribed = await is_subscribed(bot, callback.from_user.id)
        if not subscribed:
            await callback.answer("Сначала подпишитесь на канал/группу.", show_alert=True)
            return

        file_data = FILES[file_internal_id]
        ctype = CONTENT_TYPES.get(file_data["type"], {})
        price = ctype.get("price", 0)

        prices = [LabeledPrice(label=file_data["title"], amount=price)]

        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Покупка: {file_data['title']}",
            description=f"Тип: {ctype.get('title', 'Контент')}",
            payload=f"file_{file_internal_id}",
            provider_token="",  # для Stars можно оставить пустым
            currency="XTR",
            prices=prices,
        )

        await callback.answer()

    # ---------- Pre-checkout ----------

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    # ---------- Успешная оплата ----------

    @dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
    async def successful_payment_handler(message: Message):
        payload = message.successful_payment.invoice_payload
        if not payload.startswith("file_"):
            return

        file_internal_id = int(payload.split("_")[1])

        if file_internal_id not in FILES:
            await message.answer("Файл не найден.")
            return

        file_data = FILES[file_internal_id]
        ctype_key = file_data["type"]

        await message.answer("Оплата получена! Отправляю контент...")

        try:
            if ctype_key in ("article", "poem", "song_text"):
                await message.answer(
                    file_data["text"],
                    protect_content=True
                )
            else:
                if ctype_key == "image":
                    await bot.send_photo(
                        chat_id=message.chat.id,
                        photo=file_data["tg_file_id"],
                        caption=file_data["title"],
                        protect_content=True,
                    )
                elif ctype_key == "music":
                    await bot.send_audio(
                        chat_id=message.chat.id,
                        audio=file_data["tg_file_id"],
                        caption=file_data["title"],
                        protect_content=True,
                    )
                elif ctype_key == "video":
                    await bot.send_video(
                        chat_id=message.chat.id,
                        video=file_data["tg_file_id"],
                        caption=file_data["title"],
                        protect_content=True,
                    )
                else:
                    await bot.send_document(
                        chat_id=message.chat.id,
                        document=file_data["tg_file_id"],
                        caption=file_data["title"],
                        protect_content=True,
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки контента: {e}")
            await message.answer("Произошла ошибка при отправке.")

    # ---------- Запуск ----------

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
