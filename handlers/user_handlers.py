from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from states.dialog import DialogStates
from database.db import db
from utils.keyboards import get_main_keyboard, get_admin_message_keyboard
from aiogram.utils.exceptions import BotBlocked
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import json

with open('config.json', 'r') as f:
    config = json.load(f)

async def start_cmd(message: types.Message):
    # Initial check using config['ADMIN_IDS'] for first-time users
    is_admin_from_config = message.from_user.id in config['ADMIN_IDS']
    # Add or update user in the database
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
        is_admin_from_config
    )
    # Fetch the current admin status from the database
    is_admin = await db.is_user_admin(message.from_user.id)
    keyboard = get_main_keyboard(is_admin)
    await message.answer(
        "👋 Добро пожаловать в систему обратной связи!\n"
        "Выберите действие в меню ниже:",
        reply_markup=keyboard
    )

async def show_profile(callback_query: types.CallbackQuery):
    try:
        user_info = await db.get_user_info(callback_query.from_user.id)
        username = f"@{user_info['username']}" if user_info['username'] else "Отсутствует"
        profile_text = (
            f"👤 Ваш профиль:\n\n"
            f"📌 ID: {user_info['user_id']}\n"
            f"👤 Имя: {user_info['full_name']}\n"
            f"🔗 Юзернейм: {username}\n"
            f"📅 Дата регистрации: {user_info['registration_date']}\n"
            f"👑 Админ: {'Да' if user_info['is_admin'] else 'Нет'}"
        )
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
        
        await callback_query.message.edit_text(
            profile_text,
            reply_markup=keyboard
        )
    except BotBlocked:
        print(f"Ошибка: Не удалось показать профиль. Бот заблокирован пользователем {callback_query.from_user.id}")

async def show_dialog_history(callback_query: types.CallbackQuery):
    try:
        user_info = await db.get_user_info(callback_query.from_user.id)
        admin_ids = await db.get_all_admins()
        if not admin_ids:
            await callback_query.message.edit_text("Нет доступных администраторов.")
            return
        history = await db.get_dialog_history(callback_query.from_user.id, admin_ids[0])
        if not history:
            await callback_query.message.edit_text(
                "История диалогов пуста",
                reply_markup=get_main_keyboard(user_info['is_admin'])
            )
            return
        history_text = "📋 История диалога:\n\n"
        for msg in history:
            direction = "📤" if msg['from_id'] == callback_query.from_user.id else "📥"
            history_text += f"{direction} {msg['message']}\n"
            history_text += f"Дата: {msg['date']}\n"
            history_text += "➖➖➖➖➖➖➖➖\n"
        await callback_query.message.edit_text(
            history_text,
            reply_markup=get_main_keyboard(user_info['is_admin'])
        )
    except BotBlocked:
        print(f"Ошибка: Не удалось показать историю. Бот заблокирован пользователем {callback_query.from_user.id}")

async def start_message(callback_query: types.CallbackQuery, state: FSMContext):
    if await db.is_user_blocked(callback_query.from_user.id):
        await callback_query.answer("Вы заблокированы в системе", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_message"))
    await callback_query.message.edit_text(
        "📝 Введите ваше сообщение:",
        reply_markup=keyboard
    )
    await DialogStates.waiting_for_message.set()

async def cancel_message(callback_query: types.CallbackQuery, state: FSMContext):
    is_admin = await db.is_user_admin(callback_query.from_user.id)
    await callback_query.message.edit_text(
        "Отправка сообщения отменена.",
        reply_markup=get_main_keyboard(is_admin)
    )
    await state.finish()
    await callback_query.answer()

async def process_message(message: types.Message, state: FSMContext):
    if await db.is_user_blocked(message.from_user.id):
        await message.answer("Вы заблокированы в системе")
        return
    admin_ids = await db.get_all_admins()
    if not admin_ids:
        await message.answer("Нет доступных администраторов.")
        return
    await db.add_message(
        from_id=message.from_user.id,
        to_id=admin_ids[0],
        message=message.text
    )
    await message.answer(
        "✅ Сообщение отправлено администратору",
        reply_markup=get_main_keyboard(await db.is_user_admin(message.from_user.id))
    )
    for admin_id in admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"📨 Новое сообщение от @{message.from_user.username if message.from_user.username else 'Отсутствует'} (ID: {message.from_user.id}):\n\n{message.text}",
                reply_markup=get_admin_message_keyboard(message.from_user.id)
            )
        except BotBlocked:
            print(f"Ошибка: Админ {admin_id} заблокировал бота.")
    await state.finish()

def register_user_handlers(dp: Dispatcher):
    dp.register_message_handler(start_cmd, commands=['start'])
    dp.register_callback_query_handler(show_profile, lambda c: c.data == 'profile')
    dp.register_callback_query_handler(show_dialog_history, lambda c: c.data == 'dialog_history')
    dp.register_callback_query_handler(start_message, lambda c: c.data == 'write_message')
    dp.register_callback_query_handler(cancel_message, lambda c: c.data == 'cancel_message', state=DialogStates.waiting_for_message)
    dp.register_message_handler(process_message, state=DialogStates.waiting_for_message)