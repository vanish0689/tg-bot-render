import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardButton, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# --- ТВОИ ДАННЫЕ (УЖЕ ВСТАВЛЕНЫ) ---
TOKEN = "8608551495:AAE82eaqbxy-sTKkmDpuYBcyGpAcHOsSWZE"  # <--- ВСТАВЬ СЮДА ТОКЕН
CHANNEL_ID = -1003349514214  # ID канала
CHANNEL_URL = "https://t.me/Kastle202589"
ADMIN_ID = 7770818181
SUPPORT_USERNAME = "@Kastle2025"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- FSM СОСТОЯНИЯ ---
class AddProduct(StatesGroup):
    category = State()
    file = State()
    name = State()
    price = State()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetch=False):
    with sqlite3.connect("store.db") as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch: return cur.fetchall()
        conn.commit()

db_query('''CREATE TABLE IF NOT EXISTS products 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, name TEXT, file_id TEXT, price INTEGER)''')
db_query('''CREATE TABLE IF NOT EXISTS sales 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, amount INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    builder = ReplyKeyboardBuilder()
    buttons = ["🖼 Изображения", "🎵 Музыка", "📹 Видео", "📜 Стихи", "📝 Тексты песен", "📱 Приложения"]
    for text in buttons:
        builder.add(KeyboardButton(text=text))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return m.status in ["member", "administrator", "creator"]
    except: return False

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Прямая проверка: если это ТЫ (админ), пускаем сразу без проверок
    if message.from_user.id == ADMIN_ID:
        return await message.answer("Привет, Хозяин! Твоё меню:", reply_markup=get_main_kb())

    # Для остальных проверяем подписку
    is_subscribed = await check_sub(message.from_user.id)
    if is_subscribed:
        await message.answer("Подписка подтверждена! Выберите категорию:", reply_markup=get_main_kb())
    else:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔔 Подписаться на канал", url=CHANNEL_URL))
        kb.row(InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub"))
        # Шлем инлайн-кнопку, чтобы человек точно увидел, что делать
        await message.answer("Для использования бота нужно подписаться на наш канал!", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        # Удаляем сообщение с кнопкой подписки и шлем меню
        await callback.message.delete()
        await callback.message.answer("Отлично! Теперь всё доступно:", reply_markup=get_main_kb())
    else:
        await callback.answer("Вы всё еще не подписаны на канал!", show_alert=True)
@dp.message(F.text.in_(["🖼 Изображения", "🎵 Музыка", "📹 Видео", "📜 Стихи", "📝 Тексты песен", "📱 Приложения"]))
async def show_items(message: types.Message):
    cat_map = {"🖼 Изображения": "image", "🎵 Музыка": "music", "📹 Видео": "video", "📜 Стихи": "poem", "📝 Тексты песен": "lyrics", "📱 Приложения": "app"}
    items = db_query("SELECT id, name FROM products WHERE category=?", (cat_map[message.text],), fetch=True)
    if not items: return await message.answer(f"Пусто. Поддержка: {SUPPORT_USERNAME}")
    kb = InlineKeyboardBuilder()
    for i_id, name in items:
        kb.row(InlineKeyboardButton(text=name, callback_data=f"buy_{i_id}"))
    await message.answer(f"Раздел {message.text}:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def send_inv(callback: types.CallbackQuery):
    p_id = callback.data.split("_")[1]
    res = db_query("SELECT name, price FROM products WHERE id=?", (p_id,), fetch=True)
    if res:
        name, price = res[0]
        await bot.send_invoice(callback.from_user.id, title=name, description=f"Поддержка: {SUPPORT_USERNAME}", 
                               payload=p_id, provider_token="", currency="XTR", prices=[LabeledPrice(label=name, amount=int(price))])

@dp.pre_checkout_query()
async def pre_check(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def pay_ok(message: types.Message):
    p_id = message.successful_payment.invoice_payload
    db_query("INSERT INTO sales (product_id, amount) VALUES (?, ?)", (p_id, message.successful_payment.total_amount))
    res = db_query("SELECT file_id, category FROM products WHERE id=?", (p_id,), fetch=True)
    f_id, cat = res[0]
    try:
        if cat == "image": await message.answer_photo(f_id)
        elif cat == "music": await message.answer_audio(f_id)
        elif cat == "video": await message.answer_video(f_id)
        else: await message.answer_document(f_id)
    except: await message.answer(f"Ошибка. Свяжитесь: {SUPPORT_USERNAME}")

# --- АДМИН ПАНЕЛЬ ---
@dp.message(F.from_user.id == ADMIN_ID, Command("admin"))
async def admin_menu(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add"), InlineKeyboardButton(text="🗑 Удалить", callback_data="admin_del"))
    kb.row(InlineKeyboardButton(text="💰 Баланс", callback_data="admin_balance"))
    await message.answer("Админ-панель:", reply_markup=kb.as_markup())

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_balance")
async def show_balance(callback: types.CallbackQuery):
    res = db_query("SELECT SUM(amount), COUNT(*) FROM sales", fetch=True)
    await callback.message.answer(f"💰 Баланс: {res[0][0] or 0} ⭐ (Продаж: {res[0][1]})")

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_add")
async def admin_add_start(callback: types.CallbackQuery, state: FSMContext):
    cats = {"Картинка": "image", "Музыка": "music", "Видео": "video", "Стих": "poem", "Текст": "lyrics", "Приложение": "app"}
    kb = InlineKeyboardBuilder()
    for t, c in cats.items(): kb.row(InlineKeyboardButton(text=t, callback_data=f"setcat_{c}"))
    await callback.message.answer("Выберите категорию:", reply_markup=kb.as_markup())
    await state.set_state(AddProduct.category)

@dp.callback_query(StateFilter(AddProduct.category), F.data.startswith("setcat_"))
async def admin_cat(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(category=callback.data.split("_")[1])
    await callback.message.answer("Пришлите файл:")
    await state.set_state(AddProduct.file)

@dp.message(StateFilter(AddProduct.file))
async def admin_file(message: types.Message, state: FSMContext):
    f_id = None
    
    # Проверяем по очереди все типы контента
    if message.photo:
        f_id = message.photo[-1].file_id
    elif message.audio:
        f_id = message.audio.file_id
    elif message.video:
        f_id = message.video.file_id
    elif message.document:
        f_id = message.document.file_id
    elif message.voice: # На всякий случай добавим голос
        f_id = message.voice.file_id

    if not f_id:
        return await message.answer("❌ Я не вижу тут файла. Пожалуйста, пришлите фото, видео, музыку или документ.")

    # Если файл найден, сохраняем и идем дальше
    await state.update_data(file_id=f_id)
    await message.answer("✅ Файл принят! Теперь введите название товара:")
    await state.set_state(AddProduct.name)

@dp.message(StateFilter(AddProduct.name))
async def admin_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену в звездах:")
    await state.set_state(AddProduct.price)

@dp.message(StateFilter(AddProduct.price))
async def admin_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db_query("INSERT INTO products (category, name, file_id, price) VALUES (?,?,?,?)", (data['category'], data['name'], data['file_id'], int(message.text)))
    await message.answer("✅ Товар добавлен!")
    await state.clear()

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_del")
async def admin_del_list(callback: types.CallbackQuery):
    items = db_query("SELECT id, name FROM products", fetch=True)
    kb = InlineKeyboardBuilder()
    for i_id, name in items: kb.row(InlineKeyboardButton(text=f"❌ {name}", callback_data=f"del_{i_id}"))
    await callback.message.answer("Выберите для удаления:", reply_markup=kb.as_markup())

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("del_"))
async def admin_del_confirm(callback: types.CallbackQuery):
    db_query("DELETE FROM products WHERE id=?", (callback.data.split("_")[1],))
    await callback.message.delete()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
