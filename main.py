import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN
from database import (
    init_db, add_task, get_tasks, delete_task, check_user, set_user_onboarded,
    add_reminder, get_due_reminders, mark_reminder_sent
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- МАШИНА СОСТОЯНИЙ ---
class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_delete_index = State()
    waiting_for_reminder_choice = State()
    waiting_for_reminder_text = State()
    waiting_for_reminder_time = State()


# --- КЛАВИАТУРЫ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="⏰ Добавить напоминание")],
        [KeyboardButton(text="📋 Мои задачи")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие..."
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)


# --- ФОНОВАЯ ЗАДАЧА ДЛЯ НАПОМИНАНИЙ ---
async def reminder_worker():
    while True:
        try:
            due_reminders = get_due_reminders()
            for rem_id, user_id, text in due_reminders:
                await bot.send_message(user_id, f"🔔 **НАПОМИНАНИЕ!**\n\nНе забудь: {text}", parse_mode="Markdown")
                mark_reminder_sent(rem_id)
        except Exception as e:
            logging.error(f"Ошибка воркера: {e}")
        await asyncio.sleep(30)


# --- ОБЩИЕ КОМАНДЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not check_user(message.from_user.id):
        intro_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я — твой личный умный помощник.\n\n"
            "🤖 **Что я умею:**\n"
            "• Сохранять задачи\n"
            "• Напоминать о делах в любое время\n"
            "• Удалять выполненные задачи\n\n"
            "Нажми кнопку ниже, чтобы начать!"
        )
        start_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🚀 Запустить бота", callback_data="onboard_start")]]
        )
        await message.answer(intro_text, reply_markup=start_kb, parse_mode="Markdown")
    else:
        await message.answer(f"С возвращением, {message.from_user.first_name}! 👋", reply_markup=main_keyboard)


@dp.callback_query(F.data == "onboard_start")
async def process_onboard_start(callback: types.CallbackQuery):
    set_user_onboarded(callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer("Отлично! Ты в главном меню.", reply_markup=main_keyboard)
    await callback.answer()


# --- ОТМЕНА ДЕЙСТВИЯ ---
@dp.message(F.text == "❌ Отмена")
async def cancel_action(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Ты и так в главном меню.", reply_markup=main_keyboard)
        return

    await state.clear()
    await message.answer("Действие отменено. Возвращаю в главное меню.", reply_markup=main_keyboard)


# --- ДОБАВЛЕНИЕ ЗАДАЧИ ---
@dp.message(F.text == "➕ Добавить задачу")
async def start_add_task(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("✍️ Напиши текст задачи:", reply_markup=cancel_keyboard)
    await state.set_state(TaskStates.waiting_for_task)


@dp.message(TaskStates.waiting_for_task)
async def process_add_task(message: types.Message, state: FSMContext):
    add_task(message.from_user.id, message.text)
    await state.clear()
    await message.answer(f"✅ Задача добавлена: {message.text}", reply_markup=main_keyboard)


# --- ДОБАВЛЕНИЕ НАПОМИНАНИЯ ---
@dp.message(F.text == "⏰ Добавить напоминание")
async def start_add_reminder(message: types.Message, state: FSMContext):
    await state.clear()
    tasks = get_tasks(message.from_user.id)

    if tasks:
        keyboard = []
        for index, (real_id, task_text) in enumerate(tasks, start=1):
            short_text = task_text[:25] + "..." if len(task_text) > 25 else task_text
            keyboard.append([InlineKeyboardButton(text=f"{index}. {short_text}", callback_data=f"rem_task_{real_id}")])

        keyboard.append([InlineKeyboardButton(text="✍️ Ввести свой текст", callback_data="rem_custom")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await message.answer("Выбери задачу из списка или введи свой текст:", reply_markup=inline_kb)
        await state.set_state(TaskStates.waiting_for_reminder_choice)
    else:
        await message.answer("У тебя нет сохраненных задач. Напиши, о чем тебе нужно напомнить:",
                             reply_markup=cancel_keyboard)
        await state.set_state(TaskStates.waiting_for_reminder_text)


@dp.callback_query(TaskStates.waiting_for_reminder_choice)
async def process_reminder_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "rem_custom":
        await callback.message.edit_text("📝 Напиши, о чем тебе нужно напомнить:")
        await callback.message.answer("Ожидаю текст...", reply_markup=cancel_keyboard)
        await state.set_state(TaskStates.waiting_for_reminder_text)
    elif callback.data.startswith("rem_task_"):
        real_id = int(callback.data.split("_")[2])
        tasks = get_tasks(callback.from_user.id)
        task_text = next((text for tid, text in tasks if tid == real_id), "Задача")

        await state.update_data(reminder_text=task_text)
        await callback.message.edit_text(
            f"Выбрано: {task_text}\n\n"
            "⏰ Введи дату и время в формате `ДД.ММ.ГГГГ ЧЧ:ММ`\n"
            "(например, 25.12.2026 18:30):",
            parse_mode="Markdown"
        )
        await callback.message.answer("Ожидаю дату и время...", reply_markup=cancel_keyboard)
        await state.set_state(TaskStates.waiting_for_reminder_time)
    await callback.answer()


@dp.message(TaskStates.waiting_for_reminder_text)
async def process_reminder_text(message: types.Message, state: FSMContext):
    await state.update_data(reminder_text=message.text)
    await message.answer(
        "⏰ Введи дату и время в формате `ДД.ММ.ГГГГ ЧЧ:ММ`\n"
        "(например, 25.12.2026 18:30):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard
    )
    await state.set_state(TaskStates.waiting_for_reminder_time)


@dp.message(TaskStates.waiting_for_reminder_time)
async def process_reminder_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip()
    try:
        remind_datetime = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
        now = datetime.now()

        if remind_datetime <= now:
            await message.answer("❌ Это время уже прошло. Пожалуйста, введи будущую дату и время:")
            return

        remind_at_str = remind_datetime.strftime("%Y-%m-%d %H:%M")
        data = await state.get_data()
        text = data.get("reminder_text")

        add_reminder(message.from_user.id, text, remind_at_str)
        await state.clear()

        formatted_date = remind_datetime.strftime("%d.%m.%Y в %H:%M")
        await message.answer(
            f"✅ Отлично! Я напомню тебе **{text}**\n📅 {formatted_date}",
            reply_markup=main_keyboard,
            parse_mode="Markdown"
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Пожалуйста, введи дату и время как `25.12.2026 18:30`:")


# --- ПРОСМОТР И УДАЛЕНИЕ ЗАДАЧ ---
@dp.message(F.text == "📋 Мои задачи")
async def show_tasks(message: types.Message, state: FSMContext):
    await state.clear()
    tasks = get_tasks(message.from_user.id)
    if not tasks:
        await message.answer("У тебя пока нет задач.", reply_markup=main_keyboard)
        return
    response = "📋 Твои задачи:\n\n"
    for index, (real_id, task_text) in enumerate(tasks, start=1):
        response += f"{index}. {task_text}\n"

    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗑 Удалить", callback_data="start_delete")]])
    await message.answer(response, reply_markup=inline_kb)


@dp.callback_query(F.data == "start_delete")
async def start_delete_callback(callback: types.CallbackQuery, state: FSMContext):
    tasks = get_tasks(callback.from_user.id)

    if not tasks:
        await callback.message.edit_text("У тебя нет задач для удаления.")
        await callback.answer()
        return

    response = "Напиши номер задачи, которую нужно удалить:\n\n"
    for index, (real_id, task_text) in enumerate(tasks, start=1):
        response += f"{index}. {task_text}\n"

    await callback.message.edit_text(response)
    await callback.message.answer("Ожидаю номер задачи...", reply_markup=cancel_keyboard)
    await state.set_state(TaskStates.waiting_for_delete_index)
    await callback.answer()


@dp.message(TaskStates.waiting_for_delete_index)
async def process_delete_task(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, отправь именно число (номер задачи из списка выше).")
        return

    task_number = int(message.text)
    tasks = get_tasks(message.from_user.id)

    if task_number < 1 or task_number > len(tasks):
        error_msg = f"❌ Задачи с номером {task_number} не существует.\n\nВведи корректный номер из списка:\n\n"
        for index, (real_id, task_text) in enumerate(tasks, start=1):
            error_msg += f"{index}. {task_text}\n"
        await message.answer(error_msg)
        return

    real_task_id = tasks[task_number - 1][0]
    delete_task(message.from_user.id, real_task_id)
    await state.clear()

    await message.answer(f"🗑 Задача №{task_number} успешно удалена!", reply_markup=main_keyboard)


# --- ЗАПУСК ---
async def main():
    init_db()
    print("Бот запущен!")
    asyncio.create_task(reminder_worker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())