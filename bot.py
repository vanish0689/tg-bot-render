import os
import json
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "db.json"
TRACK_PRICE = 5          # цена за трек в звёздах
REF_PERCENT = 0.20       # 20% реферальный бонус


# ---------------------- БАЗА ДАННЫХ ----------------------

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

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
    if str(user_id) not in db["users"]:
        db["users"][str(user_id)] = {"ref": ref_id, "earned": 0}
    save_db(db)

def add_ref_bonus(buyer_id, price):
    db = load_db()
    buyer = db["users"].get(str(buyer_id))
    if buyer and buyer["ref"]:
        ref = buyer["ref"]
        bonus = int(price * REF_PERCENT)
        if str(ref) not in db["users"]:
            db["users"][str(ref)] = {"ref": None, "earned": 0}
        db["users"][str(ref)]["earned"] += bonus
        save_db(db)


# ---------------------- ЛОВИМ МУЗЫКУ В ГРУППЕ ----------------------

@dp.message()
async def catch_music(message: types.Message):
    if message.chat.type in ("group", "supergroup"):
        if message.audio:
            file_id = message.audio.file_id
            title = message.audio.title or "Без названия"

            add_track(file_id, title)
            await message.reply("🎵 Музыка добавлена в магазин!")
            return


# ---------------------- СТАРТ + РЕФЕРАЛКА ----------------------

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    args = message.text.split()

    if len(args) > 1 and args[1].startswith("ref"):
        ref_id = args[1].replace("ref", "")
        if ref_id != str(message.from_user.id):
            set_referral(message.from_user.id, ref_id)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎧 Музыка", callback_data="open_shop"))
    kb.add(InlineKeyboardButton("👥 Реферальная ссылка", callback_data="ref_link"))

    await message.answer("Добро пожаловать!", reply_markup=kb)


# ---------------------- МАГАЗИН ----------------------

@dp.callback_query(lambda c: c.data == "open_shop")
async def open_shop(callback: types.CallbackQuery):
    tracks = get_tracks()

    if not tracks:
        await callback.message.answer("Пока нет музыки.")
        return

    kb = InlineKeyboardMarkup()
    for t in tracks:
        kb.add(
            InlineKeyboardButton(
                text=f"{t['title']} — {t['price']}⭐",
                callback_data=f"buy_{t['id']}"
            )
        )

    await callback.message.answer("🎧 Выберите трек:", reply_markup=kb)


# ---------------------- ОПЛАТА ----------------------

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_track(callback: types.CallbackQuery):
    track_id = int(callback.data.replace("buy_", ""))
    item = get_track(track_id)

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=item["title"],
        description="Покупка музыкального трека",
        payload=str(track_id),
        provider_token="",  # для звёзд не нужен
        currency="XTR",
        prices=[LabeledPrice(label=item["title"], amount=item["price"])],
    )


@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)


@dp.message()
async def successful_payment(message: types.Message):
    if message.successful_payment:
        track_id = int(message.successful_payment.invoice_payload)
        item = get_track(track_id)

        add_ref_bonus(message.from_user.id, item["price"])

        await message.answer_document(item["file_id"])


# ---------------------- РЕФЕРАЛКА ----------------------

@dp.callback_query(lambda c: c.data == "ref_link")
async def ref_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = f"https://t.me/{(await bot.me()).username}?start=ref{user_id}"

    db = load_db()
    earned = db["users"].get(str(user_id), {}).get("earned", 0)

    await callback.message.answer(
        f"👥 Ваша реферальная ссылка:\n{link}\n\n"
        f"💰 Заработано: {earned}⭐"
    )


# ---------------------- ЗАПУСК ----------------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
