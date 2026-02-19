"""
Finite State Machine states for multi-step user interactions.
Used by aiogram's FSM to track conversation context.
"""
from aiogram.fsm.state import State, StatesGroup


class RenameStates(StatesGroup):
    waiting_for_new_name = State()


class TagStates(StatesGroup):
    waiting_for_tags = State()


class TokenStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_new_token = State()
