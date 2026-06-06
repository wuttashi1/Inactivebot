from aiogram.fsm.state import State, StatesGroup


class PanelStates(StatesGroup):
    waiting_bind = State()
    add_admin = State()
    remove_admin = State()
    whitelist_add = State()
    whitelist_remove = State()
    transfer_owner = State()
    autoclean_period = State()
