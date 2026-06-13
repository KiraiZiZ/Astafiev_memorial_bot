"""
Telegram-бот для Мемориального комплекса В.П. Астафьева в Овсянке
С поддержкой вебхуков для работы на Render
"""

import asyncio
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    WebhookInfo
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client
from aiohttp import web
import ssl

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # URL вашего Render сервиса (например: https://your-bot.onrender.com)

# Проверка, что переменные заданы
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в переменных окружения")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL или SUPABASE_KEY не заданы")

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========== ПРОВЕРКА АДМИНА ==========
def is_admin(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в таблице admins"""
    try:
        result = supabase.table("admins").select("user_id").eq("user_id", user_id).execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Ошибка проверки админа: {e}")
        return False

# ========== ГЛАВНОЕ МЕНЮ ==========
def get_main_keyboard(user_id: int):
    """Создаёт клавиатуру с учётом прав администратора"""
    keyboard = [
        [KeyboardButton(text="🏛️ О комплексе")],
        [KeyboardButton(text="🎟️ Объекты"), KeyboardButton(text="📅 Афиша")],
        [KeyboardButton(text="🚆 Как добраться"), KeyboardButton(text="📞 Контакты")]
    ]
    if is_admin(user_id):
        keyboard.append([KeyboardButton(text="🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🏛️ *Добро пожаловать в бот Мемориального комплекса В.П. Астафьева!*\n\n"
        "Я помогу вам узнать всё о музеях в Овсянке:\n"
        "• Национальный центр\n"
        "• Дом-музей писателя\n"
        "• Музей повести «Последний поклон»\n"
        "• Выставочный зал\n\n"
        "Выберите нужный пункт в меню 👇",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🏛️ О комплексе")
async def about_complex(message: types.Message):
    text = (
        "🏛️ *Мемориальный комплекс В.П. Астафьева в Овсянке*\n\n"
        "Открыт 1 мая 2024 года к 100-летию писателя.\n\n"
        "📍 *В состав комплекса входят:*\n"
        "• Национальный центр (ул. Щетинкина, 30)\n"
        "• Дом-музей Астафьева (ул. Щетинкина, 26)\n"
        "• Музей «Последний поклон» (ул. Щетинкина, 24)\n"
        "• Выставочный зал (ул. Щетинкина, 35)\n\n"
        "🕐 *Режим работы:*\n"
        "Вторник – Воскресенье: 10:00 – 18:00\n"
        "Четверг: 10:00 – 21:00\n"
        "Понедельник — выходной\n\n"
        "📞 *Справки:* +7 (391) 234-74-00"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟️ Объекты")
async def show_objects(message: types.Message):
    """Показывает список объектов из Supabase"""
    try:
        result = supabase.table("objects").select("*").eq("is_active", True).order("order_index").execute()
        objects = result.data
        
        if not objects:
            await message.answer("Информация об объектах временно недоступна.")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=obj["name_ru"], callback_data=f"obj_{obj['id']}")]
            for obj in objects
        ])
        
        await message.answer("🏛️ *Выберите объект:*", reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка загрузки объектов: {e}")
        await message.answer("❌ Ошибка загрузки данных. Попробуйте позже.")

@dp.callback_query(F.data.startswith("obj_"))
async def show_object_detail(callback: types.CallbackQuery):
    """Детальная информация об объекте"""
    try:
        obj_id = int(callback.data.split("_")[1])
        result = supabase.table("objects").select("*").eq("id", obj_id).execute()
        
        if not result.data:
            await callback.answer("Объект не найден")
            return
        
        obj = result.data[0]
        
        text = (
            f"🏛️ *{obj['name_ru']}*\n\n"
            f"📍 *Адрес:* {obj['address']}\n"
            f"🕐 *Часы работы:* {obj['working_hours']}\n\n"
            f"💰 *Цены:*\n"
            f"• Взрослые — {obj['price_adult']}₽\n"
            f"• Льготный (дети/студенты/пенсионеры) — {obj['price_discount']}₽\n"
            f"• Многодетные/ветераны — {obj['price_special']}₽\n\n"
            f"{obj['description']}\n\n"
            f"Действует Пушкинская карта."
        )
        
        if obj.get('photo_url'):
            await callback.message.answer_photo(photo=obj['photo_url'], caption=text, parse_mode="Markdown")
        else:
            await callback.message.answer(text, parse_mode="Markdown")
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка загрузки деталей объекта: {e}")
        await callback.message.answer("❌ Ошибка загрузки информации об объекте.")
        await callback.answer()

@dp.message(F.text == "📅 Афиша")
async def show_events(message: types.Message):
    """Показывает список мероприятий"""
    try:
        result = supabase.table("events").select("*").eq("is_active", True).order("event_date").execute()
        events = result.data
        
        if not events:
            await message.answer("На данный момент запланированных мероприятий нет. Следите за обновлениями!")
            return
        
        text = "📅 *Афиша мероприятий:*\n\n"
        for event in events:
            date_str = event['event_date']
            time_str = f" {event['start_time']}" if event.get('start_time') else ""
            text += f"• *{date_str}*{time_str} — {event['title']}\n"
            if event.get('description'):
                text += f"  _{event['description']}_\n"
            if event.get('price'):
                text += f"  Стоимость: {event['price']}\n"
            text += "\n"
        
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка загрузки афиши: {e}")
        await message.answer("❌ Ошибка загрузки афиши.")

@dp.message(F.text == "🚆 Как добраться")
async def how_to_get(message: types.Message):
    text = (
        "🚆 *Как добраться до Овсянки из Красноярска*\n\n"
        "🚂 *Электричка:*\n"
        "От ж/д вокзала Красноярска до станции Овсянка\n"
        "Время в пути: ~1 час\n\n"
        "🚌 *Автобус:*\n"
        "№146 от автовокзала, №106 от Предмостной площади\n\n"
        "🚗 *Автомобиль:*\n"
        "Трасса Р-257 «Енисей» в сторону Дивногорска, ~40 км"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📞 Контакты")
async def contacts(message: types.Message):
    text = (
        "📞 *Контакты Мемориального комплекса*\n\n"
        "🏛️ *Администрация:* +7 (391) 234-74-00\n"
        "📧 Email: astafiev@kkkm.ru\n\n"
        "🌐 *Сайт:* astafiev.kkkm.ru\n"
        "📱 *ВКонтакте:* Мемориальный комплекс В.П. Астафьева в Овсянке\n\n"
        "📍 *Физический адрес:*\n"
        "Красноярский край, с. Овсянка, ул. Щетинкина, 30"
    )
    await message.answer(text, parse_mode="Markdown")

# ========== АДМИН-ПАНЕЛЬ ==========
class AddEventState(StatesGroup):
    title = State()
    description = State()
    date = State()
    time = State()
    price = State()

@dp.message(F.text == "🔧 Админ-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить мероприятие", callback_data="admin_add_event")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ])
    
    await message.answer(
        "🔧 *Админ-панель*\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "admin_add_event")
async def add_event_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    await state.set_state(AddEventState.title)
    await callback.message.answer("📝 Введите *название мероприятия*:")
    await callback.answer()

@dp.message(AddEventState.title)
async def add_event_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddEventState.description)
    await message.answer("📄 Введите *описание* (или '-' чтобы пропустить):", parse_mode="Markdown")

@dp.message(AddEventState.description)
async def add_event_description(message: types.Message, state: FSMContext):
    desc = message.text if message.text != "-" else ""
    await state.update_data(description=desc)
    await state.set_state(AddEventState.date)
    await message.answer("📅 Введите *дату* в формате ГГГГ-ММ-ДД\nНапример: 2026-06-20")

@dp.message(AddEventState.date)
async def add_event_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    await state.set_state(AddEventState.time)
    await message.answer("⏰ Введите *время* (например, 14:00) или '-' чтобы пропустить:")

@dp.message(AddEventState.time)
async def add_event_time(message: types.Message, state: FSMContext):
    time_val = message.text if message.text != "-" else None
    await state.update_data(time=time_val)
    await state.set_state(AddEventState.price)
    await message.answer("💰 Введите *стоимость* (например, 'Бесплатно' или '250 руб.'):")

@dp.message(AddEventState.price)
async def add_event_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    try:
        supabase.table("events").insert({
            "title": data['title'],
            "description": data['description'],
            "event_date": data['date'],
            "start_time": data['time'],
            "price": message.text,
            "is_active": True
        }).execute()
        
        await message.answer(f"✅ Мероприятие *«{data['title']}»* успешно добавлено!\n\nОно появится в разделе «Афиша».", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка добавления мероприятия: {e}")
        await message.answer(f"❌ Ошибка при добавлении мероприятия: {str(e)}")
    
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён")
        return
    
    try:
        objects_count = supabase.table("objects").select("id", count="exact").execute()
        events_count = supabase.table("events").select("id", count="exact").execute()
        admins_count = supabase.table("admins").select("user_id", count="exact").execute()
        
        await callback.message.answer(
            f"📊 *Статистика бота*\n\n"
            f"🏛️ Объектов в базе: {objects_count.count}\n"
            f"📅 Мероприятий: {events_count.count}\n"
            f"👥 Администраторов: {admins_count.count}\n\n"
            f"⚡ Работает на Supabase + aiogram",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
    
    await callback.answer()

# ========== ВЕБХУКИ ДЛЯ RENDER ==========
async def on_startup():
    """Настройка вебхука при запуске"""
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL не задан, работаем через polling")
        return
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    logger.info(f"Настройка вебхука: {webhook_url}")
    
    # Удаляем старый вебхук
    await bot.delete_webhook()
    
    # Устанавливаем новый вебхук
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True
    )
    
    # Проверяем установку
    webhook_info = await bot.get_webhook_info()
    logger.info(f"Вебхук установлен: {webhook_info.url}")

async def on_shutdown():
    """Очистка при выключении"""
    logger.info("Выключение бота...")
    await bot.delete_webhook()
    await bot.session.close()

# Веб-обработчик для вебхуков
async def webhook_handle(request):
    """Обработка входящих запросов от Telegram"""
    try:
        update = types.Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return web.Response(status=200)  # Возвращаем 200 даже при ошибке, чтобы Telegram не переотправлял

async def health_check(request):
    """Endpoint для проверки здоровья сервера"""
    return web.Response(text="Bot is running", status=200)

def main():
    """Запуск бота в режиме вебхука или polling"""
    app = web.Application()
    
    # Маршруты
    app.router.post("/webhook", webhook_handle)
    app.router.get("/health", health_check)
    app.router.get("/", health_check)
    
    if WEBHOOK_URL:
        # Режим с вебхуком
        app.on_startup.append(lambda _: on_startup())
        app.on_shutdown.append(lambda _: on_shutdown())
        logger.info(f"Запуск в режиме вебхука на порту {PORT}")
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        # Режим polling (для локальной разработки)
        logger.info("Запуск в режиме polling")
        async def polling_main():
            await on_startup()
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
        asyncio.run(polling_main())

if __name__ == "__main__":
    main()
