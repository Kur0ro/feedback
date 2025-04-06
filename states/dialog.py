from aiogram.dispatcher.filters.state import State, StatesGroup

class DialogStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_user_id = State()
    waiting_for_block_id = State()
    waiting_for_reply = State()
    waiting_for_add_admin_id = State()  # New state for adding admin
    waiting_for_remove_admin_id = State()  # New state for removing admin