from aiogram.fsm.state import State, StatesGroup

class Ban(StatesGroup):
    waiting_for_message = State()
    waiting_for_time = State()
    waiting_for_reason = State()

class Unban(StatesGroup):
    waiting_for_message = State()


class Mute(StatesGroup):
    waiting_for_message = State()
    waiting_for_time = State()
    waiting_for_reason = State()

class Unmute(StatesGroup):
    waiting_for_message = State()

class Warn(StatesGroup):
    waiting_for_message = State()
    waiting_for_time = State()
    waiting_for_reason = State()

class Unwarn(StatesGroup):
    waiting_for_message = State()