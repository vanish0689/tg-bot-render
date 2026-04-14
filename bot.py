import os
import json
import asyncio
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
)

# ---------------------- НАСТРОЙКИ ----------------------

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
router = Router()

# Пока ставим None — позже заменим на реальный ID
GROUP_ID = None  

DB_FILE = "db.json"
TRACK_PRICE = 5
REF_PERCENT = 0.20


# ---------------------- ВРЕМЕННЫЙ ХЕНДЛЕР ДЛЯ ПОЛУЧЕНИЯ ID ----------------------

@router.message()
async def debug_chat_id(message: types.Message):
    await message.answer(f"Chat ID: {message.chat.id}")
    print("GROUP ID:", message.chat.id)


# ---------------------- БАЗА ДАННЫХ ----------------------

def load_db():
    if not os.path.exists(DB_FILE):
        return {"tracks": [], "users": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

def add_track(file_id, title):
    db = load_db()
    track_id = len(db["tracks"]) + 1
    db["tracks"].append({
        "id": track_id,
        "title": title,
        "file_id": file_id,
        "price": TRACK_PRICE
    })
    save_db(db)

def get_tracks():
    return load_db()["tracks"]

def get_track(track_id):
    db = load_db()
    for t in db["tracks"]:
        if t["id"] == track_id:
            return t
    return None

def set_referral(user_id, ref_id):
    db = load_db()
    users = db.setdefault("users", {})
    if str(user_id) not in users:
        users[str(user_id)] = {"ref": ref_id, "earned": 0}
    save_db(db)

def add_ref_bonus(buyer_id, price):
    db = load_db()
    users = db.setdefault("users", {})
    buyer = users.get(str(buyer_id))
    if buyer and buyer.get("ref"):
        ref = buyer["ref"]
        bonus = int(price * REF_PERCENT)
        if str(ref) not in users:
            users[str(ref)] = {"ref": None, "earned": 0}
        users[str(ref)]["earned"] += bonus
        save_db(db)


# ---------------------- ЛОВИМ МЕДИА ----------------------

@router.message(
    (F.chat.id == GROUP_ID)
    & (F.audio | F.photo | F.video | F.document | F.voice | F.video_note)
)
async def catch_media(message: types.Message):
    file_id = None
    title = "Медиа"

    if message.audio:
        file_id = message.audio.file_id
        title = message.audio.title or message.audio.file_name or "Аудио"

    elif message.document:
        file_id = message.document.file_id
        title = message.document.file_name or "Документ"

    elif message.photo:
        file_id = message.photo[-1].file_id
        title = "Фото"

    elif message.video:
        file_id = message.video.file_id
        title = "Видео"

    elif message.voice:
        file_id = message.voice.file_id
        title = "Голосовое"

    elif message.video_note:
        file_id = message.video_note.file_id
        title = "Видеосообщение"

    if not file_id:
        return

    add_track(file_id, title)
    await message.reply(f"✅ Добавлено в магазин: {title}")


# ---------------------- СТАРТ ----------------------

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    args = message.text.split()

    if len(args) > 1 and args[1].startswith("ref"):
        ref_id = args[1].replace("ref", "")
        if ref_id != str(message.from_user.id):
            set_referral(message.from_user.id, ref_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Магазин", callback_data="open_shop")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="ref_link")],
    ])

    await message.answer("Добро пожаловать!", reply_markup=kb)


# ---------------------- МАГАЗИН ----------------------

@router.callback_query(F.data == "open_shop")
async def open_shop(callback: types.CallbackQuery):
    tracks = get_tracks()

    if not tracks:
        await callback.message.answer("Пока нет медиа в магазине.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{t['title']} — {t['price']}⭐",
            callback_data=f"buy_{t['id']}"
        )]
        for t in tracks
    ])

    await callback.message.answer("🎧 Выберите медиа:", reply_markup=kb)


# ---------------------- ОПЛАТА ----------------------

@router.callback_query(F.data.startswith("buy_"))
async def buy_track(callback: types.CallbackQuery):
    track_id = int(callback.data.replace("buy_", ""))
    item = get_track(track_id)
    if not item:
        await callback.message.answer("Медиа не найдено.")
        return

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=item["title"],
        description="Покупка медиа",
        payload=str(track_id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=item["title"], amount=item["price"])],
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: types.Message):
    track_id = int(message.successful_payment.invoice_payload)
    item = get_track(track_id)
    if not item:
        await message.answer("Медиа не найдено.")
        return

    add_ref_bonus(message.from_user.id, item["price"])
    await message.answer_document(item["file_id"])


# ---------------------- РЕФЕРАЛКА ----------------------

@router.callback_query(F.data == "ref_link")
async def ref_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    me = await bot.me()
    link = f"https://t.me/{me.username}?start=ref{user_id}"

    db = load_db()
    earned = db.get("users", {}).get(str(user_id), {}).get("earned", 0)

    await callback.message.answer(
        f"👥 Ваша реферальная ссылка:\n{link}\n\n"
        f"💰 Заработано: {earned}⭐"
    )


# ---------------------- ЗАПУСК ----------------------

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
