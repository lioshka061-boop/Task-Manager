import asyncio
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from dotenv import load_dotenv
from repository import TaskRepository
from storage import save_user_state, load_user_state
from aiosqlite import connect

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()
repo = TaskRepository()


def task_inline_menu(task_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Готово", callback_data=f"task_done:{task_id}"),
            InlineKeyboardButton(text="❌ Пропустити", callback_data=f"task_skip:{task_id}")
        ],
        [
            InlineKeyboardButton(text="⏰ Відкласти", callback_data=f"task_delay:{task_id}"),
            InlineKeyboardButton(text="📎 Деталі", callback_data=f"task_details:{task_id}")
        ]
    ])


@dp.message(Command("start"))
async def start_cmd(msg: Message):
    state = await load_user_state(msg.from_user.id)
    if state:
        state["last_action"] = "start"
        await save_user_state(msg.from_user.id, state)

    await msg.answer("Привіт 👋 Я твій менеджер задач. Створи перше завдання командою /add ✨")


@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "/start – Почати\n"
        "/help – Допомога\n"
        "/add <текст> – Додати задачу\n"
        "/list – Показати список\n"
        "/done <номер> – Позначити виконаною\n"
        "/skip <номер> – Видалити задачу\n"
        "/stats – Статистика задач"
    )


@dp.message(Command("add"))
async def add_cmd(msg: Message):
    content = msg.text.replace("/add", "").strip()
    if not content:
        await msg.answer("Будь ласка, додай текст задачі. Наприклад: /add підготувати звіт 📄")
        return

    await repo.add(msg.from_user.id, content)

    state = await load_user_state(msg.from_user.id)
    state["last_action"] = "add"
    state["last_added"] = content
    await save_user_state(msg.from_user.id, state)

    async with connect(repo.db_path) as db:
        cursor = await db.execute("SELECT id FROM tasks ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        task_id = row[0]

    await msg.answer(
        f"Додав нову задачу 👇\n• {content}",
        reply_markup=task_inline_menu(task_id)
    )


@dp.message(Command("list"))
async def list_cmd(msg: Message):
    state = await load_user_state(msg.from_user.id)
    state["last_action"] = "list"
    await save_user_state(msg.from_user.id, state)

    async with connect(repo.db_path) as db:
        cursor = await db.execute(
            "SELECT id, name FROM tasks WHERE user_id=? ORDER BY id",
            (msg.from_user.id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await msg.answer("Список задач порожній 🤷")
        return

    text = "Ось твої задачі 📋:\n\n"
    for i, (tid, name) in enumerate(rows, 1):
        text += f"{i}. {name}\n"

    await msg.answer(text)

    for tid, name in rows:
        await msg.answer(name, reply_markup=task_inline_menu(tid))


@dp.message(Command("done"))
async def done_cmd(msg: Message):
    try:
        index = int(msg.text.split()[1]) - 1
    except:
        await msg.answer("Вкажи номер задачі. Наприклад: /done 1")
        return

    async with connect(repo.db_path) as db:
        cursor = await db.execute(
            "SELECT id FROM tasks WHERE user_id=? ORDER BY id",
            (msg.from_user.id,)
        )
        rows = await cursor.fetchall()

    if 0 <= index < len(rows):
        await repo.mark_done(msg.from_user.id, index)

        state = await load_user_state(msg.from_user.id)
        state["last_action"] = "done"
        state["last_done_index"] = index + 1
        await save_user_state(msg.from_user.id, state)

        await msg.answer("Готово! Завдання виконане ✔️")
    else:
        await msg.answer("Такої задачі не існує ❗")


@dp.message(Command("skip"))
async def skip_cmd(msg: Message):
    try:
        index = int(msg.text.split()[1]) - 1
    except:
        await msg.answer("Вкажи номер задачі. Наприклад: /skip 1")
        return

    async with connect(repo.db_path) as db:
        cursor = await db.execute(
            "SELECT id FROM tasks WHERE user_id=? ORDER BY id",
            (msg.from_user.id,)
        )
        rows = await cursor.fetchall()

        if 0 <= index < len(rows):
            task_id = rows[index][0]
            await db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            await db.commit()

            state = await load_user_state(msg.from_user.id)
            state["last_action"] = "skip"
            state["last_skipped_index"] = index + 1
            await save_user_state(msg.from_user.id, state)

            await msg.answer("Задачу видалено 🗑️")
        else:
            await msg.answer("Такої задачі немає ❗")


async def build_stats_report(user_id: int) -> str:
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    async with connect(repo.db_path) as db:
        cursor = await db.execute(
            "SELECT status, created_date FROM tasks WHERE user_id=?",
            (user_id,)
        )
        rows = await cursor.fetchall()

    total = len(rows)
    done_total = len([s for (s, d) in rows if s == "done"])
    active_total = total - done_total

    done_today = 0
    done_week = 0

    for status, created in rows:
        if status != "done":
            continue
        if not created:
            continue
        try:
            created_dt = datetime.fromisoformat(created)
        except:
            continue

        if created_dt >= today_start:
            done_today += 1
        if created_dt >= week_start:
            done_week += 1

    p_total = round((done_total / total) * 100, 1) if total else 0
    p_today = round((done_today / total) * 100, 1) if total else 0
    p_week = round((done_week / total) * 100, 1) if total else 0

    state = await load_user_state(user_id)
    state["last_action"] = "stats"
    await save_user_state(user_id, state)

    report = (
        "📊 *Твій прогрес*\n\n"
        f"📦 Усього задач: *{total}*\n"
        f"✅ Виконано: *{done_total}* ({p_total}%)\n"
        f"🟡 Активні: *{active_total}*\n\n"
        f"📅 *Сьогодні:* {done_today} ({p_today}%)\n"
        f"📆 *Цього тижня:* {done_week} ({p_week}%)\n\n"
        "Тримай темп і рухайся далі 🚀"
    )
    return report


@dp.message(Command("stats"))
async def stats_cmd(msg: Message):
    report = await build_stats_report(msg.from_user.id)
    await msg.answer(report, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("task_done"))
async def inline_done(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])

    async with connect(repo.db_path) as db:
        await db.execute(
            "UPDATE tasks SET status='done', created_date=? WHERE id=?",
            (datetime.utcnow().isoformat(), task_id)
        )
        await db.commit()

    state = await load_user_state(call.from_user.id)
    state["last_action"] = "inline_done"
    state["last_task_id"] = task_id
    await save_user_state(call.from_user.id, state)

    await call.message.edit_text("Задачу виконано ✔️")
    await call.answer("Готово!")


@dp.callback_query(F.data.startswith("task_skip"))
async def inline_skip(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])

    async with connect(repo.db_path) as db:
        await db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        await db.commit()

    state = await load_user_state(call.from_user.id)
    state["last_action"] = "inline_skip"
    state["last_task_id"] = task_id
    await save_user_state(call.from_user.id, state)

    await call.message.edit_text("Задачу видалено 🗑️")
    await call.answer("Пропущено!")


@dp.callback_query(F.data.startswith("task_delay"))
async def inline_delay(call: CallbackQuery):
    state = await load_user_state(call.from_user.id)
    state["last_action"] = "inline_delay"
    await save_user_state(call.from_user.id, state)

    await call.answer("Перенесення дедлайну скоро буде доступне ⏳", show_alert=True)


@dp.callback_query(F.data.startswith("task_details"))
async def inline_details(call: CallbackQuery):
    task_id = int(call.data.split(":")[1])

    async with connect(repo.db_path) as db:
        cursor = await db.execute(
            "SELECT name, status, created_date FROM tasks WHERE id=?",
            (task_id,)
        )
        row = await cursor.fetchone()

    state = await load_user_state(call.from_user.id)
    state["last_action"] = "inline_details"
    state["last_task_id"] = task_id
    await save_user_state(call.from_user.id, state)

    if not row:
        await call.answer("Задачу не знайдено ❗", show_alert=True)
        return

    name, status, created = row
    mark = "🟢 Виконано" if status == "done" else "🟡 Активна"

    await call.answer()
    await call.message.answer(
        f"📎 *Деталі задачі*\n\n"
        f"Назва: *{name}*\n"
        f"Статус: *{mark}*\n"
        f"Створено: *{created}*",
        parse_mode="Markdown"
    )


async def send_daily_reports():
    async with connect(repo.db_path) as db:
        cursor = await db.execute("SELECT DISTINCT user_id FROM tasks")
        rows = await cursor.fetchall()

    user_ids = [r[0] for r in rows]

    for user_id in user_ids:
        report = await build_stats_report(user_id)
        try:
            await bot.send_message(
                chat_id=user_id,
                text="🕗 Щоденний звіт о 20:00\n\n" + report,
                parse_mode="Markdown"
            )
        except:
            continue


async def daily_report_worker():
    while True:
        now = datetime.now()
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        try:
            await send_daily_reports()
        except:
            continue


async def main():
    await repo.init()
    asyncio.create_task(daily_report_worker())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
