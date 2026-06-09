"""Aiogram FSM states for planning_bot."""
from aiogram.fsm.state import State, StatesGroup


class ReflectionState(StatesGroup):
    waiting = State()


class DailyCheckinState(StatesGroup):
    active = State()
