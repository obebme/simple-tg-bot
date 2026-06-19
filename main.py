import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
import aiosqlite 
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DB_DIR = Path("data")
DB_PATH = DB_DIR / "bookings.db"

bot = None
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

SERVICES = [
    "Замена масла",
    "Диагностика",
    "Шиномонтаж",
    "Ремонт ходовой",
    "Технический осмотр",
]


class BookingStates(StatesGroup):
    choose_service = State()
    enter_date = State()
    enter_time = State()
    enter_car_model = State()
    enter_phone = State()
    confirm = State()
    support_message = State()


async def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                service TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                car_model TEXT NOT NULL,
                phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Новая',
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Записаться на услугу", callback_data="menu_book")],
        [InlineKeyboardButton(text="Контакты", callback_data="menu_contacts")],
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="Панель администратора", callback_data="menu_admin")])
    else:
        buttons.append([InlineKeyboardButton(text="📄 Мои записи", callback_data="menu_my_bookings")])
        buttons.append([InlineKeyboardButton(text="Обратная связь", callback_data="menu_support")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def services_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    for service in SERVICES:
        keyboard.append([InlineKeyboardButton(text=service, callback_data=f"service:{service}")])
    keyboard.append([InlineKeyboardButton(text="Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить запись", callback_data="confirm_booking")],
        [InlineKeyboardButton(text="Отменить", callback_data="cancel_booking")],
    ])


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Просмотреть записи", callback_data="admin_view_bookings")],
        [InlineKeyboardButton(text="Обновить меню", callback_data="back_to_menu")],
    ])


def admin_bookings_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Поступившие", callback_data="admin_filter_новая")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="admin_filter_выполнено")],
        [InlineKeyboardButton(text="❌ Отменённые", callback_data="admin_filter_отменено")],
        [InlineKeyboardButton(text="Назад в панель", callback_data="back_to_admin")],
    ])


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Связаться с администратором", callback_data="support_contact")],
        [InlineKeyboardButton(text="Назад в меню", callback_data="back_to_menu")],
    ])


@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    text = (
        "<b>Добро пожаловать в автосервис!</b>\n\n"
        "Я помогу записаться на услугу, сохранить ваши данные и уведомить администратора."
    )
    await message.answer(text, reply_markup=main_menu_keyboard(message.from_user.id))


@dp.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(
        "Вы вернулись в главное меню.",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_book")
async def callback_menu_book(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(
        "Выберите услугу для записи:",
        reply_markup=services_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_contacts")
async def callback_menu_contacts(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(
        "<b>Контакты автосервиса:</b>\n"
        "📍 Адрес: Адрес сервиса\n"
        "📞 Телефон: Контактный телефон\n"
        "⏰ Время работы: Время работы\n\n",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_support")
async def callback_menu_support(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(
        "Если у вас есть вопросы, обратитесь к администратору.",
        reply_markup=support_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_my_bookings")
async def callback_menu_my_bookings(callback: types.CallbackQuery) -> None:
    user_bookings = await load_user_bookings(callback.from_user.id)
    if not user_bookings:
        await callback.message.edit_text(
            "📋 У вас нет записей на услуги.",
            reply_markup=main_menu_keyboard(callback.from_user.id)
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"<b>📄 Ваши записи ({len(user_bookings)}):</b>",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    for booking in user_bookings:
        status_emoji = "📋" if booking['status'] == "Новая" else (
            "✅" if booking['status'] == "Выполнено" else "❌"
        )
        text = (
            f"<b>{status_emoji} #{booking['id']} — {booking['status']}</b>\n"
            f"<b>Услуга:</b> {booking['service']}\n"
            f"<b>Дата:</b> {booking['date']}\n"
            f"<b>Время:</b> {booking['time']}\n"
            f"<b>Автомобиль:</b> {booking['car_model']}\n"
            f"<b>Телефон:</b> {booking['phone']}\n"
            f"<b>Состояние:</b> {booking['status']}"
        )
        await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "support_contact")
async def callback_support_contact(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BookingStates.support_message)
    await callback.message.edit_text(
        "Пожалуйста, напишите ваше сообщение для администратора:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="cancel_support")]
        ])
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_admin")
async def callback_menu_admin(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await callback.message.edit_text(
        "<b>Панель администратора</b>\nВыберите действие:",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("service:"))
async def callback_choose_service(callback: types.CallbackQuery, state: FSMContext) -> None:
    service = callback.data.split(":", 1)[1]
    await state.update_data(service=service)
    await state.set_state(BookingStates.enter_date)
    await callback.message.edit_text(
        f"Вы выбрали: <b>{service}</b>\n\nВведите желаемую дату записи в формате <i>ДД.ММ.ГГГГ</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена записи", callback_data="cancel_booking")]
        ])
    )
    await callback.answer()


@dp.message(BookingStates.enter_date)
async def state_enter_date(message: types.Message, state: FSMContext) -> None:
    date_text = message.text.strip()
    try:
        datetime.strptime(date_text, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ.")
        return
    await state.update_data(date=date_text)
    await state.set_state(BookingStates.enter_time)
    await message.answer("Укажите удобное время в формате ЧЧ:ММ.")


@dp.message(BookingStates.enter_time)
async def state_enter_time(message: types.Message, state: FSMContext) -> None:
    time_text = message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.")
        return
    await state.update_data(time=time_text)
    await state.set_state(BookingStates.enter_car_model)
    await message.answer("Укажите марку и модель автомобиля.")


@dp.message(BookingStates.enter_car_model)
async def state_enter_car_model(message: types.Message, state: FSMContext) -> None:
    car_model = message.text.strip()
    if len(car_model) < 3:
        await message.answer("Пожалуйста, укажите марку и модель автомобиля более подробно.")
        return
    await state.update_data(car_model=car_model)
    await state.set_state(BookingStates.enter_phone)
    await message.answer("Оставьте ваш контактный телефон для подтверждения записи.")


@dp.message(BookingStates.enter_phone)
async def state_enter_phone(message: types.Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if not any(ch.isdigit() for ch in phone) or len([ch for ch in phone if ch.isdigit()]) < 7:
        await message.answer("Пожалуйста, укажите корректный телефонный номер.")
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    summary = (
        f"<b>Проверка записи</b>\n"
        f"Услуга: {data['service']}\n"
        f"Дата: {data['date']}\n"
        f"Время: {data['time']}\n"
        f"Автомобиль: {data['car_model']}\n"
        f"Телефон: {phone}\n"
    )
    await state.set_state(BookingStates.confirm)
    await message.answer(summary, reply_markup=confirm_keyboard())


@dp.message(BookingStates.support_message)
async def state_support_message(message: types.Message, state: FSMContext) -> None:
    support_text = message.text.strip()
    if len(support_text) < 5:
        await message.answer("Пожалуйста, напишите более развернутое сообщение (минимум 5 символов).")
        return
    await notify_admins_support(message.from_user, support_text)
    await state.clear()
    await message.answer(
        "✅ Ваше сообщение отправлено администратору. Спасибо за обращение!",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )


@dp.callback_query(F.data == "cancel_support", StateFilter(BookingStates.support_message))
async def callback_cancel_support(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Отправка сообщения отменена.",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel_booking", StateFilter(BookingStates))
async def callback_cancel_booking(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Запись отменена. Вы можете начать заново.",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()


@dp.callback_query(F.data == "confirm_booking", StateFilter(BookingStates.confirm))
async def callback_confirm_booking(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await save_booking(
        user_id=callback.from_user.id,
        user_name=callback.from_user.full_name,
        service=data["service"],
        date=data["date"],
        time=data["time"],
        car_model=data["car_model"],
        phone=data["phone"],
    )
    await notify_admins(data, callback.from_user)
    await state.clear()
    await callback.message.edit_text(
        "✅ Ваша запись успешно отправлена. Администратор свяжется с вами для подтверждения.",
        reply_markup=main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer("Запись подтверждена")


async def save_booking(user_id: int, user_name: str, service: str, date: str, time: str, car_model: str, phone: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO bookings (user_id, user_name, service, date, time, car_model, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_name, service, date, time, car_model, phone, datetime.utcnow().isoformat())
        )
        await db.commit()


async def notify_admins(data: dict, user: types.User) -> None:
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS не настроены. Невозможно отправить уведомление администратору.")
        return
    text = (
        f"<b>Новая заявка на автосервис</b>\n"
        f"Пользователь: {user.full_name} (ID: {user.id})\n"
        f"Услуга: {data['service']}\n"
        f"Дата: {data['date']}\n"
        f"Время: {data['time']}\n"
        f"Автомобиль: {data['car_model']}\n"
        f"Телефон: {data['phone']}\n"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.exception("Не удалось отправить уведомление администратору %s: %s", admin_id, exc)


async def notify_admins_support(user: types.User, support_text: str) -> None:
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS не настроены. Невозможно отправить сообщение поддержки администратору.")
        return
    text = (
        f"<b>Сообщение поддержки от пользователя</b>\n"
        f"От: {user.full_name} (ID: {user.id})\n"
        f"Контакт: @{user.username if user.username else 'Нет username'}\n\n"
        f"<b>Сообщение:</b>\n{support_text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.exception("Не удалось отправить сообщение поддержки администратору %s: %s", admin_id, exc)


@dp.callback_query(F.data == "admin_view_bookings")
async def callback_admin_view_bookings(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await callback.message.edit_text(
        "<b>Фильтр записей</b>\nВыберите статус для просмотра:",
        reply_markup=admin_bookings_filter_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_filter_"))
async def callback_admin_filter_bookings(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    status_key = callback.data.split("admin_filter_", 1)[1]
    status_map = {
        "новая": "Новая",
        "выполнено": "Выполнено",
        "отменено": "Отменено"
    }
    status = status_map.get(status_key, status_key)
    bookings = await load_bookings_by_status(status)
    if not bookings:
        await callback.message.edit_text(
            f"<b>{status} записи не найдены.</b>",
            reply_markup=admin_bookings_filter_keyboard()
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"<b>Записи со статусом \"{status}\" ({len(bookings)}):</b>",
        reply_markup=admin_bookings_filter_keyboard()
    )
    for booking in bookings:
        text = (
            f"<b>#{booking['id']} — {booking['status']}</b>\n"
            f"Пользователь: {booking['user_name']} (ID {booking['user_id']})\n"
            f"Услуга: {booking['service']}\n"
            f"Дата: {booking['date']}\n"
            f"Время: {booking['time']}\n"
            f"Автомобиль: {booking['car_model']}\n"
            f"Телефон: {booking['phone']}\n"
            f"Создано: {booking['created_at']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Выполнено", callback_data=f"admin_action:{booking['id']}:completed")],
            [InlineKeyboardButton(text="Отменить", callback_data=f"admin_action:{booking['id']}:cancelled")],
        ])
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data == "back_to_admin")
async def callback_back_to_admin(callback: types.CallbackQuery) -> None:
    await callback.message.edit_text(
        "<b>Панель администратора</b>\nВыберите действие:",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()


async def load_recent_bookings(limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def load_bookings_by_status(status: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM bookings WHERE status = ? ORDER BY created_at DESC",
            (status,)
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@dp.callback_query(F.data.startswith("admin_action:"))
async def callback_admin_action(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    _, booking_id, action = callback.data.split(":", 2)
    booking_id_int = int(booking_id)
    status = "Выполнено" if action == "completed" else "Отменено"
    await update_booking_status(booking_id_int, status)
    
    # Get updated booking info
    booking = await load_booking_by_id(booking_id_int)
    if booking:
        text = (
            f"<b>#{booking['id']} ✅ Обновлено</b>\n\n"
            f"<b>Статус:</b> {booking['status']}\n"
            f"<b>Пользователь:</b> {booking['user_name']} (ID {booking['user_id']})\n"
            f"<b>Услуга:</b> {booking['service']}\n"
            f"<b>Дата:</b> {booking['date']}\n"
            f"<b>Время:</b> {booking['time']}\n"
            f"<b>Автомобиль:</b> {booking['car_model']}\n"
            f"<b>Телефон:</b> {booking['phone']}\n"
            f"<b>Создано:</b> {booking['created_at']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Назад к фильтру", callback_data="admin_view_bookings")],
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    
    await callback.answer(f"✅ Запись #{booking_id} переведена в статус '{status}'")


async def load_user_bookings(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def load_booking_by_id(booking_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,)
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def update_booking_status(booking_id: int, status: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (status, booking_id)
        )
        await db.commit()


@dp.message()
async def fallback_message(message: types.Message) -> None:
    await message.answer(
        "Приветствую, напиши /start и посмотрим, что из этого выйдет\n"
        "Будут кнопки, потыкай и увидишь",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )


async def main() -> None:
    global bot
    if not BOT_TOKEN:
        logger.error("Токен бота не задан. Установите переменную окружения BOT_TOKEN.")
        return
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
