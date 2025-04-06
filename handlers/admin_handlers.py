from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from states.dialog import DialogStates
from database.db import db  # Ensure db is imported
from utils.keyboards import get_main_keyboard, get_dialog_navigation_keyboard, get_admin_message_keyboard
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import MessageNotModified, BotBlocked, MessageToEditNotFound
import aiosqlite  # Add this import for the database connection in delete_dialog

async def show_all_dialogs(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await db.is_user_admin(callback_query.from_user.id):
            await callback_query.answer("Недостаточно прав", show_alert=True)
            return
        current_page = (await state.get_data()).get("current_page", 1)
        dialogs = await db.get_all_dialogs(callback_query.from_user.id)
        total_pages = (len(dialogs) + 9) // 10
        if current_page < 1:
            current_page = 1
        elif current_page > total_pages:
            current_page = total_pages
        start_index = (current_page - 1) * 10
        end_index = min(start_index + 10, len(dialogs))
        page_dialogs = dialogs[start_index:end_index]
        keyboard = InlineKeyboardMarkup(row_width=2)
        for dialog in page_dialogs:
            keyboard.add(
                InlineKeyboardButton(
                    f"{dialog['full_name']} (@{dialog['username'] if dialog['username'] else 'Отсутствует'})",
                    callback_data=f"dialog_{dialog['user_id']}"
                )
            )
        if total_pages > 1:
            navigation_buttons = []
            if current_page > 1:
                navigation_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{current_page - 1}"))
            navigation_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="ignore"))
            if current_page < total_pages:
                navigation_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{current_page + 1}"))
            keyboard.add(*navigation_buttons)
        keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
        await state.update_data({"current_page": current_page})
        await callback_query.message.edit_text(
            "📋 Список диалогов:",
            reply_markup=keyboard
        )
    except MessageNotModified:
        await callback_query.answer()
    except BotBlocked:
        print(f"Ошибка: Не удалось показать диалоги. Бот заблокирован пользователем {callback_query.from_user.id}")

async def process_page_change(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        page = int(callback_query.data.split('_')[1])
        await state.update_data({"current_page": page})
        await show_all_dialogs(callback_query, state)
    except BotBlocked:
        print(f"Ошибка: Не удалось изменить страницу. Бот заблокирован пользователем {callback_query.from_user.id}")

async def ignore_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()

async def show_dialog(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        user_id = int(callback_query.data.split('_')[1])
        history = await db.get_dialog_history(user_id, callback_query.from_user.id)
        if not history:
            await callback_query.answer("Диалог пуст", show_alert=True)
            return
        history_text = f"📋 Диалог с пользователем {user_id}:\n\n"
        for msg in history:
            if msg['from_id'] == callback_query.from_user.id:
                direction = f"👑 Админ (@{msg['username'] if msg['username'] else 'Отсутствует'}):"
            else:
                direction = f"👤 Пользователь (@{msg['username'] if msg['username'] else 'Отсутствует'}):"
            history_text += f"{direction} {msg['message']}\n"
            history_text += f"Дата: {msg['date']}\n"
            history_text += "➖➖➖➖➖➖➖➖\n"
        keyboard = InlineKeyboardMarkup(row_width=2)
        is_blocked = await db.is_user_blocked(user_id)
        keyboard.add(
            InlineKeyboardButton("🔓 Разблокировать" if is_blocked else "🔒 Заблокировать", 
                                callback_data=f"{'unblock' if is_blocked else 'block'}_{user_id}"),
            InlineKeyboardButton("✍️ Ответить", callback_data=f"reply_{user_id}")
        )
        keyboard.add(
            InlineKeyboardButton("🗑️ Удалить диалог", callback_data=f"delete_dialog_{user_id}"),
            InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")
        )
        await callback_query.message.edit_text(
            history_text,
            reply_markup=keyboard
        )
        await state.update_data(reply_to=user_id)
    except BotBlocked:
        print(f"Ошибка: Не удалось показать диалог. Бот заблокирован пользователем {callback_query.from_user.id}")

async def delete_dialog(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await db.is_user_admin(callback_query.from_user.id):
            await callback_query.answer("Недостаточно прав", show_alert=True)
            return
        user_id = int(callback_query.data.split('_')[2])
        async with aiosqlite.connect("feedback.db") as db_conn:
            await db_conn.execute(
                "DELETE FROM messages WHERE (from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?)",
                (user_id, callback_query.from_user.id, callback_query.from_user.id, user_id)
            )
            await db_conn.commit()
        await callback_query.answer("Диалог удален", show_alert=True)
        await show_all_dialogs(callback_query, state)
    except BotBlocked:
        print(f"Ошибка: Не удалось удалить диалог. Бот заблокирован пользователем {callback_query.from_user.id}")

async def block_user(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await db.is_user_admin(callback_query.from_user.id):
            await callback_query.answer("Недостаточно прав", show_alert=True)
            return
        user_id = int(callback_query.data.split('_')[1])
        await db.block_user(user_id)
        await callback_query.answer("Пользователь заблокирован", show_alert=True)
        await show_dialog(callback_query, state)
    except BotBlocked:
        print(f"Ошибка: Не удалось заблокировать пользователя. Бот заблокирован пользователем {callback_query.from_user.id}")

async def unblock_user(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await db.is_user_admin(callback_query.from_user.id):
            await callback_query.answer("Недостаточно прав", show_alert=True)
            return
        user_id = int(callback_query.data.split('_')[1])
        await db.unblock_user(user_id)
        await callback_query.answer("Пользователь разблокирован", show_alert=True)
        await show_dialog(callback_query, state)
    except BotBlocked:
        print(f"Ошибка: Не удалось разблокировать пользователя. Бот заблокирован пользователем {callback_query.from_user.id}")

async def reply_to_user(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await db.is_user_admin(callback_query.from_user.id):
            await callback_query.answer("Недостаточно прав", show_alert=True)
            return
        user_id = int(callback_query.data.split('_')[1])
        await state.update_data(reply_to=user_id)
        await callback_query.message.edit_text(
            "✍️ Введите ваш ответ:",
            reply_markup=None
        )
        await DialogStates.waiting_for_reply.set()
    except BotBlocked:
        print(f"Ошибка: Не удалось ответить. Бот заблокирован пользователем {callback_query.from_user.id}")

async def process_admin_reply(message: types.Message, state: FSMContext):
    if not await db.is_user_admin(message.from_user.id):
        return
    data = await state.get_data()
    user_id = data.get('reply_to')
    await db.add_message(
        from_id=message.from_user.id,
        to_id=user_id,
        message=message.text
    )
    await message.answer(
        "✅ Ответ отправлен",
        reply_markup=get_main_keyboard(True)
    )
    try:
        await message.bot.send_message(
            user_id,
            f"📨 Ответ от администратора:\n\n{message.text}",
            reply_markup=get_main_keyboard(False)
        )
    except BotBlocked:
        print(f"Ошибка: Не удалось отправить ответ пользователю {user_id}. Бот заблокирован.")
    await state.finish()

async def manage_admins(callback_query: types.CallbackQuery, state: FSMContext):
    if not await db.is_user_admin(callback_query.from_user.id):
        await callback_query.answer("Недостаточно прав", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin"),
        InlineKeyboardButton("➖ Удалить админа", callback_data="remove_admin")
    )
    keyboard.add(
        InlineKeyboardButton("📋 Список админов", callback_data="list_admins"),
        InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")
    )
    await callback_query.message.edit_text(
        "👑 Управление администраторами:",
        reply_markup=keyboard
    )

async def list_admins(callback_query: types.CallbackQuery, state: FSMContext):
    if not await db.is_user_admin(callback_query.from_user.id):
        await callback_query.answer("Недостаточно прав", show_alert=True)
        return
    admin_ids = await db.get_all_admins()
    if not admin_ids:
        await callback_query.message.edit_text(
            "Список администраторов пуст",
            reply_markup=get_main_keyboard(True)
        )
        return
    
    admin_list_text = "📋 Список администраторов:\n\n"
    for admin_id in admin_ids:
        user_info = await db.get_user_info(admin_id)
        if user_info:
            username = f"@{user_info['username']}" if user_info['username'] else "Отсутствует"
            admin_list_text += f"ID: {admin_id}\n"
            admin_list_text += f"Имя: {user_info['full_name']}\n"
            admin_list_text += f"Юзернейм: {username}\n"
            admin_list_text += "➖➖➖➖➖➖➖➖\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Управление админами", callback_data="manage_admins"))
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    
    await callback_query.message.edit_text(
        admin_list_text,
        reply_markup=keyboard
    )

async def add_admin(callback_query: types.CallbackQuery, state: FSMContext):
    if not await db.is_user_admin(callback_query.from_user.id):
        await callback_query.answer("Недостаточно прав", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    prompt_message = await callback_query.message.edit_text(
        "Введите ID пользователя для назначения администратором:",
        reply_markup=keyboard
    )
    await state.update_data(prompt_message_id=prompt_message.message_id)
    await DialogStates.waiting_for_add_admin_id.set()

async def process_add_admin(message: types.Message, state: FSMContext):
    if not await db.is_user_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text)
        user_info = await db.get_user_info(user_id)
        if user_info:
            await db.promote_to_admin(user_id)
            await message.answer(
                f"Пользователь {user_id} назначен администратором.",
                reply_markup=get_main_keyboard(True)
            )
        else:
            await db.add_user(user_id, "Unknown", "Unknown", is_admin=True)
            await message.answer(
                f"Пользователь {user_id} добавлен и назначен администратором.",
                reply_markup=get_main_keyboard(True)
            )
        try:
            await message.bot.send_message(
                user_id,
                "🎉 Вы были назначены администратором!\nВыберите действие в меню ниже:",
                reply_markup=get_main_keyboard(True)
            )
        except BotBlocked:
            print(f"Ошибка: Не удалось уведомить нового админа {user_id}. Бот заблокирован.")
        except Exception as e:
            print(f"Ошибка при уведомлении нового админа {user_id}: {str(e)}")
        
        data = await state.get_data()
        prompt_message_id = data.get('prompt_message_id')
        try:
            await message.bot.edit_message_text(
                "Вы вернулись в главное меню.",
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                reply_markup=get_main_keyboard(await db.is_user_admin(message.from_user.id))
            )
        except MessageToEditNotFound:
            await message.answer(
                "Вы вернулись в главное меню.",
                reply_markup=get_main_keyboard(await db.is_user_admin(message.from_user.id))
            )
        await state.finish()
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID (число).")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

async def remove_admin(callback_query: types.CallbackQuery, state: FSMContext):
    if not await db.is_user_admin(callback_query.from_user.id):
        await callback_query.answer("Недостаточно прав", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu"))
    prompt_message = await callback_query.message.edit_text(
        "Введите ID администратора для удаления:",
        reply_markup=keyboard
    )
    await state.update_data(prompt_message_id=prompt_message.message_id)
    await DialogStates.waiting_for_remove_admin_id.set()

async def process_remove_admin(message: types.Message, state: FSMContext):
    if not await db.is_user_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text)
        if not await db.is_user_admin(user_id):
            await message.answer("Этот пользователь не является администратором.")
        elif user_id == message.from_user.id:
            await message.answer("Вы не можете удалить себя из администраторов.")
        else:
            admin_count = len(await db.get_all_admins())
            if admin_count <= 1:
                await message.answer("Нельзя удалить последнего администратора.")
            else:
                await db.demote_from_admin(user_id)
                await message.answer(
                    f"Пользователь {user_id} удален из администраторов.",
                    reply_markup=get_main_keyboard(True)
                )
                try:
                    await message.bot.send_message(
                        user_id,
                        "ℹ️ Вы были удалены из администраторов.\nВыберите действие в меню ниже:",
                        reply_markup=get_main_keyboard(False)
                    )
                except BotBlocked:
                    print(f"Ошибка: Не удалось уведомить пользователя {user_id}. Бот заблокирован.")
                except Exception as e:
                    print(f"Ошибка при уведомлении пользователя {user_id}: {str(e)}")
                
                data = await state.get_data()
                prompt_message_id = data.get('prompt_message_id')
                try:
                    await message.bot.edit_message_text(
                        "Вы вернулись в главное меню.",
                        chat_id=message.chat.id,
                        message_id=prompt_message_id,
                        reply_markup=get_main_keyboard(await db.is_user_admin(message.from_user.id))
                    )
                except MessageToEditNotFound:
                    await message.answer(
                        "Вы вернулись в главное меню.",
                        reply_markup=get_main_keyboard(await db.is_user_admin(message.from_user.id))
                    )
        await state.finish()
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID (число).")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

async def main_menu(callback_query: types.CallbackQuery, state: FSMContext):
    is_admin = await db.is_user_admin(callback_query.from_user.id)
    await callback_query.message.edit_text(
        "Вы вернулись в главное меню.",
        reply_markup=get_main_keyboard(is_admin)
    )
    await state.finish()

def register_admin_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(show_all_dialogs, lambda c: c.data == 'all_dialogs', state="*")
    dp.register_callback_query_handler(process_page_change, lambda c: c.data.startswith('page_'), state="*")
    dp.register_callback_query_handler(ignore_callback, lambda c: c.data == 'ignore', state="*")
    dp.register_callback_query_handler(show_dialog, lambda c: c.data.startswith('dialog_'))
    dp.register_callback_query_handler(delete_dialog, lambda c: c.data.startswith('delete_dialog_'))
    dp.register_callback_query_handler(block_user, lambda c: c.data.startswith('block_'))
    dp.register_callback_query_handler(unblock_user, lambda c: c.data.startswith('unblock_'))
    dp.register_callback_query_handler(reply_to_user, lambda c: c.data.startswith('reply_'))
    dp.register_callback_query_handler(manage_admins, lambda c: c.data == 'manage_admins', state="*")
    dp.register_callback_query_handler(add_admin, lambda c: c.data == 'add_admin', state="*")
    dp.register_callback_query_handler(remove_admin, lambda c: c.data == 'remove_admin', state="*")
    dp.register_callback_query_handler(list_admins, lambda c: c.data == 'list_admins', state="*")
    dp.register_callback_query_handler(main_menu, lambda c: c.data == 'main_menu', state="*")
    dp.register_message_handler(process_admin_reply, state=DialogStates.waiting_for_reply)
    dp.register_message_handler(process_add_admin, state=DialogStates.waiting_for_add_admin_id)
    dp.register_message_handler(process_remove_admin, state=DialogStates.waiting_for_remove_admin_id)