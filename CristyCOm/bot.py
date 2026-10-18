import asyncio
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable; do not put the token in source code.")

INITIAL_ADMINS = {7894051808, 5969266721}
DB_PATH = os.getenv("DB_PATH", "cristyvpn_bot.sqlite3")
CONTACT_USERNAME = "fymce"
MAX_SCREENSHOTS = 50
bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Flow(StatesGroup):
    collecting_proof = State()
    waiting_task_text = State()
    waiting_admin_id = State()
    waiting_reject_reason = State()
    waiting_withdraw_amount = State()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
            referrer INTEGER, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            task_id INTEGER, status TEXT NOT NULL DEFAULT 'pending',
            requested_screens INTEGER NOT NULL DEFAULT 0, awarded INTEGER NOT NULL DEFAULT 0,
            reject_reason TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS screenshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER NOT NULL,
            file_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT
        );
        """)
        for aid in INITIAL_ADMINS:
            c.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (aid,))
        c.execute("INSERT OR IGNORE INTO tasks(title,description,active,created_at) VALUES(?,?,1,?)",
                  ("Комментарий о CristyVPN", "Оставьте уместный, честный комментарий о своём опыте или характеристиках CristyVPN. Не копируйте массово одинаковые тексты и соблюдайте правила TikTok. Если комментарий оплачен, раскройте рекламный характер там, где это требуется.", datetime.utcnow().isoformat()))

def is_admin(uid):
    with db() as c:
        return c.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None

def user_row(uid):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def ensure_user(user, referrer=None):
    with db() as c:
        c.execute("""INSERT OR IGNORE INTO users(user_id,username,first_name,referrer,created_at)
                     VALUES(?,?,?,?,?)""",
                  (user.id, user.username, user.first_name, referrer if referrer != user.id else None, datetime.utcnow().isoformat()))
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                  (user.username, user.first_name, user.id))

PROMO_TEMPLATES = [
    "Реклама: у CristyVPN есть пробный период на 3 дня и безлимитный тариф. Подробности — @CristyVPN_bot.",
    "Реклама CristyVPN: можно попробовать сервис бесплатно 3 дня; условия и совместимость уточняйте в боте @CristyVPN_bot.",
    "Реклама: CristyVPN предлагает безлимитный доступ по условиям сервиса и 3 дня пробного периода — @CristyVPN_bot.",
    "Реклама: ищете VPN? У CristyVPN заявлены 3 дня пробного доступа и безлимитный тариф. Проверьте условия: @CristyVPN_bot.",
    "Реклама CristyVPN: информация о пробных 3 днях, тарифах и поддерживаемых сетях есть в @CristyVPN_bot.",
    "Реклама: у CristyVPN есть 3-дневный пробный период. Перед подключением проверьте актуальные условия и совместимость — @CristyVPN_bot.",
    "Реклама: CristyVPN заявляет безлимитный тариф и пробный доступ на 3 дня. Детали доступны в @CristyVPN_bot.",
    "Реклама CristyVPN: если нужен VPN-сервис, посмотрите условия пробного периода на 3 дня в @CristyVPN_bot.",
    "Реклама: протестируйте CristyVPN в течение пробных 3 дней и сами оцените работу на своей сети — @CristyVPN_bot.",
    "Реклама: CristyVPN — VPN с пробным периодом на 3 дня. Доступность функций зависит от сети и условий сервиса: @CristyVPN_bot.",
    "Реклама CristyVPN: описание безлимитного тарифа и пробного периода можно посмотреть в боте @CristyVPN_bot.",
    "Реклама: у CristyVPN предусмотрены 3 дня для знакомства с сервисом. Проверяйте текущие условия перед подключением — @CristyVPN_bot.",
    "Реклама: интересует CristyVPN? В боте указаны пробные 3 дня и условия безлимитного тарифа — @CristyVPN_bot.",
    "Реклама CristyVPN: сервис заявляет поддержку некоторых ограниченных сетевых сценариев; гарантии обхода ограничений нет. Подробности: @CristyVPN_bot.",
    "Реклама: перед выбором VPN проверьте, поддерживает ли CristyVPN нужную вам сеть и устройство. Пробный период — 3 дня: @CristyVPN_bot.",
    "Реклама CristyVPN: можно начать с пробного периода на 3 дня и оценить соединение самостоятельно — @CristyVPN_bot.",
    "Реклама: CristyVPN предлагает безлимитный тариф по своим условиям. Ознакомиться с ними можно в @CristyVPN_bot.",
    "Реклама CristyVPN: проверьте описание сервиса, тарифы и поддерживаемые сети в официальном боте — @CristyVPN_bot.",
    "Реклама: у CristyVPN есть пробный период на 3 дня; фактическая работа может зависеть от оператора и региона — @CristyVPN_bot.",
    "Реклама CristyVPN: если хотите попробовать VPN, начните с пробных 3 дней и проверьте совместимость со своим устройством — @CristyVPN_bot.",
    "Реклама: условия безлимитного тарифа CristyVPN и пробного доступа опубликованы в @CristyVPN_bot.",
    "Реклама CristyVPN: перед использованием прочитайте актуальные условия сервиса и оцените качество соединения на своей сети — @CristyVPN_bot.",
    "Реклама: CristyVPN предлагает 3 дня пробного доступа. Наличие доступа к отдельным ресурсам не гарантируется — @CristyVPN_bot.",
    "Реклама CristyVPN: подробности о тарифах, пробном периоде и поддерживаемых сетях — в @CristyVPN_bot.",
    "Реклама: можно изучить CristyVPN и его 3-дневный пробный период в боте @CristyVPN_bot; публикуйте только то, что соответствует вашему опыту.",
]

def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Взять задание"), KeyboardButton(text="⭐ Баланс")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💸 Вывести")],
        [KeyboardButton(text="👥 Рефералы"), KeyboardButton(text="❓ Задать вопрос")]
    ], resize_keyboard=True)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Заявки на проверку", callback_data="admin:submissions")],
        [InlineKeyboardButton(text="💸 Заявки на выплату", callback_data="admin:withdrawals")],
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="admin:add")],
        [InlineKeyboardButton(text="➕ Добавить задание", callback_data="admin:addtask")],
    ])

def user_display(uid):
    r = user_row(uid)
    if not r:
        return f"ID {uid}"
    return f"{r['first_name'] or 'Пользователь'} (@{r['username'] or 'нет username'}, ID {uid})"

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    ref = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref = int(parts[1][4:])
        except ValueError:
            pass
    ensure_user(message.from_user, ref)
    row = user_row(message.from_user.id)
    await message.answer(
        f"👋 Добро пожаловать в CristyVPN Tasks!\n\n"
        f"⭐ Баланс: {row['balance']} звёзд\n"
        f"📝 Выполнено заданий: {row['completed']}\n\n"
        "Выбирайте задание, отправляйте скриншоты и дождитесь проверки администратора.",
        reply_markup=main_menu()
    )

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer("Панель администратора:", reply_markup=admin_menu())

@dp.message(F.text == "📝 Взять задание")
async def take_task(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    with db() as c:
        tasks = c.execute("SELECT * FROM tasks WHERE active=1 ORDER BY id").fetchall()
    if not tasks:
        return await message.answer("Сейчас нет активных заданий.", reply_markup=main_menu())
    for t in tasks:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Посмотреть 25 вариантов текста", callback_data="templates")],
            [InlineKeyboardButton(text="📸 Начать и отправить скриншоты", callback_data=f"task:{t['id']}")]
        ])
        await message.answer(f"📝 <b>{t['title']}</b>\n\n{t['description']}", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "templates")
async def show_templates(call: CallbackQuery):
    # Each button sends one transparent advertising draft as a separate message,
    # so the user can copy it from Telegram. The bot cannot silently copy to clipboard.
    for start in range(0, len(PROMO_TEMPLATES), 5):
        rows = []
        for idx in range(start, min(start + 5, len(PROMO_TEMPLATES))):
            rows.append([InlineKeyboardButton(
                text=f"📋 Вариант {idx + 1}",
                callback_data=f"template:{idx}"
            )])
        await call.message.answer(
            "Выберите текст. Варианты помечены как реклама; публикуйте только достоверные сведения.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await call.answer()

@dp.callback_query(F.data.startswith("template:"))
async def send_template(call: CallbackQuery):
    try:
        idx = int(call.data.split(":")[1])
        template = PROMO_TEMPLATES[idx]
    except (ValueError, IndexError):
        return await call.answer("Вариант не найден.", show_alert=True)
    await call.message.answer(template)
    await call.answer("Текст отправлен в чат — его можно скопировать.")

@dp.callback_query(F.data.startswith("task:"))
async def task_start(call: CallbackQuery, state: FSMContext):
    task_id = int(call.data.split(":")[1])
    with db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
    if not task:
        await call.answer("Задание больше недоступно.", show_alert=True)
        return
    await state.set_state(Flow.collecting_proof)
    await state.update_data(task_id=task_id, screenshots=[])
    await call.message.answer(
        f"Отправляйте скриншоты выполнения задания (фото, максимум {MAX_SCREENSHOTS}).\n"
        "Когда закончите, нажмите «Отправить на проверку». Не отправляйте чужие или изменённые доказательства.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Отправить на проверку"), KeyboardButton(text="❌ Отменить")]], resize_keyboard=True)
    )
    await call.answer()

@dp.message(Flow.collecting_proof, F.text == "❌ Отменить")
async def cancel_proof(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправка отменена.", reply_markup=main_menu())

@dp.message(Flow.collecting_proof, F.photo)
async def add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    pics = data.get("screenshots", [])
    if len(pics) >= MAX_SCREENSHOTS:
        return await message.answer(f"Достигнут лимит: {MAX_SCREENSHOTS} скриншотов.")
    pics.append(message.photo[-1].file_id)
    await state.update_data(screenshots=pics)
    await message.answer(f"Скриншот добавлен: {len(pics)}/{MAX_SCREENSHOTS}.")

@dp.message(Flow.collecting_proof, F.text == "✅ Отправить на проверку")
async def submit_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    pics = data.get("screenshots", [])
    if not pics:
        return await message.answer("Сначала отправьте хотя бы один скриншот.")
    task_id = data["task_id"]
    with db() as c:
        cur = c.execute("INSERT INTO submissions(user_id,task_id,status,requested_screens,created_at) VALUES(?,?, 'pending', ?, ?)",
                        (message.from_user.id, task_id, len(pics), datetime.utcnow().isoformat()))
        sid = cur.lastrowid
        c.executemany("INSERT INTO screenshots(submission_id,file_id) VALUES(?,?)", [(sid, p) for p in pics])
        admins = [r["user_id"] for r in c.execute("SELECT user_id FROM admins").fetchall()]
        task = c.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
    await state.clear()
    await message.answer(f"✅ Заявка #{sid} отправлена на проверку. Скриншотов: {len(pics)}.", reply_markup=main_menu())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Открыть заявку", callback_data=f"review:{sid}")],
    ])
    for aid in admins:
        try:
            await bot.send_message(aid, f"📥 Новая заявка #{sid}\nПользователь: {user_display(message.from_user.id)}\nЗадание: {task['title']}\nСкриншотов: {len(pics)}", reply_markup=kb)
        except Exception:
            pass

@dp.message(F.text == "⭐ Баланс")
async def balance(message: Message):
    ensure_user(message.from_user)
    r = user_row(message.from_user.id)
    await message.answer(f"⭐ Ваш баланс: {r['balance']} звёзд.")

@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):
    ensure_user(message.from_user)
    r = user_row(message.from_user.id)
    await message.answer(f"👤 Профиль\nID: {r['user_id']}\nВыполнено заданий: {r['completed']}\nБаланс: {r['balance']} ⭐")

@dp.message(F.text == "👥 Рефералы")
async def referrals(message: Message):
    ensure_user(message.from_user)
    with db() as c:
        count = c.execute("SELECT COUNT(*) n FROM users WHERE referrer=?", (message.from_user.id,)).fetchone()["n"]
    me = await bot.get_me()
    await message.answer(f"👥 Ваши рефералы: {count}\nВаша ссылка:\nhttps://t.me/{me.username}?start=ref_{message.from_user.id}")

@dp.message(F.text == "❓ Задать вопрос")
async def question(message: Message):
    await message.answer(f"Напишите в личные сообщения: https://t.me/{CONTACT_USERNAME}")

@dp.message(F.text == "💸 Вывести")
async def withdraw_start(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    r = user_row(message.from_user.id)
    if r["balance"] < 1:
        return await message.answer("Пока недостаточно звёзд для вывода.")
    await state.set_state(Flow.waiting_withdraw_amount)
    await message.answer(f"Доступно: {r['balance']} ⭐\nВведите количество звёзд для вывода (целое число).")

@dp.message(Flow.waiting_withdraw_amount)
async def withdraw_submit(message: Message, state: FSMContext):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        return await message.answer("Введите целое число.")
    r = user_row(message.from_user.id)
    if amount < 1 or not r or amount > r["balance"]:
        return await message.answer("Некорректная сумма. Проверьте баланс и попробуйте снова.")
    with db() as c:
        cur = c.execute("INSERT INTO withdrawals(user_id,amount,status,created_at) VALUES(?,?,'pending',?)",
                        (message.from_user.id, amount, datetime.utcnow().isoformat()))
        wid = cur.lastrowid
        admins = [x["user_id"] for x in c.execute("SELECT user_id FROM admins").fetchall()]
    await state.clear()
    await message.answer(f"Заявка на вывод #{wid} создана: {amount} ⭐. Дождитесь решения администратора.", reply_markup=main_menu())
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📂 Открыть выплату", callback_data=f"payout:{wid}")]])
    for aid in admins:
        try:
            await bot.send_message(aid, f"💸 Новая заявка на вывод #{wid}\n{user_display(message.from_user.id)}\nСумма: {amount} ⭐", reply_markup=kb)
        except Exception:
            pass

@dp.callback_query(F.data == "admin:submissions")
async def admin_submissions(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    with db() as c:
        rows = c.execute("SELECT id,user_id,requested_screens FROM submissions WHERE status='pending' ORDER BY id DESC LIMIT 30").fetchall()
    if not rows:
        await call.message.answer("Нет заявок на проверку.")
    for r in rows:
        await call.message.answer(f"Заявка #{r['id']} · {user_display(r['user_id'])} · скринов: {r['requested_screens']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"review:{r['id']}")]]))
    await call.answer()

@dp.callback_query(F.data.startswith("review:"))
async def review_submission(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    sid = int(call.data.split(":")[1])
    with db() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        pics = c.execute("SELECT file_id FROM screenshots WHERE submission_id=? ORDER BY id", (sid,)).fetchall()
        task = c.execute("SELECT title FROM tasks WHERE id=?", (s["task_id"],)).fetchone() if s and s["task_id"] else None
    if not s:
        return await call.answer("Заявка не найдена.", show_alert=True)
    await call.message.answer(f"Заявка #{sid}\nПользователь: {user_display(s['user_id'])}\nСтатус: {s['status']}\nЗадание: {task['title'] if task else '—'}\nСкриншотов: {len(pics)}")
    for i, p in enumerate(pics, 1):
        try:
            await bot.send_photo(call.from_user.id, p["file_id"], caption=f"Заявка #{sid} · скриншот {i}/{len(pics)}")
        except Exception:
            pass
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выплатить все (1 ⭐/скрин)", callback_data=f"approve:{sid}:{len(pics)}")],
        [InlineKeyboardButton(text="⭐ Выплатить частично", callback_data=f"partial:{sid}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject:{sid}")],
    ])
    await call.message.answer("Выберите решение:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("approve:"))
async def approve_submission(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    _, sid_s, amount_s = call.data.split(":")
    sid, amount = int(sid_s), int(amount_s)
    await finalize_submission(call, sid, amount, "approved")

@dp.callback_query(F.data.startswith("partial:"))
async def partial_submission(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    sid = int(call.data.split(":")[1])
    await state.set_state(Flow.waiting_task_text)
    await state.update_data(partial_sid=sid)
    await call.message.answer(f"Введите количество звёзд для частичного начисления по заявке #{sid} (0 или больше).")
    await call.answer()

async def finalize_submission(call, sid, amount, status):
    with db() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s or s["status"] != "pending":
            return await call.answer("Заявка уже обработана или не найдена.", show_alert=True)
        c.execute("UPDATE submissions SET status=?, awarded=? WHERE id=?", (status, amount, sid))
        c.execute("UPDATE users SET balance=balance+?, completed=completed+1 WHERE user_id=?", (amount, s["user_id"]))
    await bot.send_message(s["user_id"], f"✅ Заявка #{sid} проверена. Начислено: {amount} ⭐.")
    await call.message.answer(f"Заявка #{sid}: начислено {amount} ⭐.")
    await call.answer("Готово.")

async def finalize_submission_message(message, sid, amount, status):
    with db() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s or s["status"] != "pending":
            return await message.answer("Заявка уже обработана или не найдена.")
        c.execute("UPDATE submissions SET status=?, awarded=? WHERE id=?", (status, amount, sid))
        c.execute("UPDATE users SET balance=balance+?, completed=completed+1 WHERE user_id=?", (amount, s["user_id"]))
    await bot.send_message(s["user_id"], f"✅ Заявка #{sid} проверена. Начислено: {amount} ⭐.")
    await message.answer(f"Заявка #{sid}: начислено {amount} ⭐.")

@dp.callback_query(F.data.startswith("reject:"))
async def reject_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    sid = int(call.data.split(":")[1])
    await state.set_state(Flow.waiting_reject_reason)
    await state.update_data(reject_sid=sid)
    await call.message.answer(f"Введите причину отказа по заявке #{sid}.")
    await call.answer()

@dp.message(Flow.waiting_reject_reason)
async def reject_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    sid = data.get("reject_sid")
    if not sid:
        return
    reason = (message.text or "").strip()[:500]
    with db() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s or s["status"] != "pending":
            await state.clear()
            return await message.answer("Заявка уже обработана или не найдена.")
        c.execute("UPDATE submissions SET status='rejected', reject_reason=? WHERE id=?", (reason, sid))
    await state.clear()
    await bot.send_message(s["user_id"], f"❌ По заявке #{sid} отказано.\nПричина: {reason}")
    await message.answer(f"По заявке #{sid} отказано.")

@dp.callback_query(F.data == "admin:withdrawals")
async def admin_withdrawals(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    with db() as c:
        rows = c.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 30").fetchall()
    if not rows:
        await call.message.answer("Нет заявок на выплату.")
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Выплатить", callback_data=f"pay:{r['id']}"),
             InlineKeyboardButton(text="Отказать", callback_data=f"deny:{r['id']}")]
        ])
        await call.message.answer(f"Выплата #{r['id']}\n{user_display(r['user_id'])}\nСумма: {r['amount']} ⭐", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("payout:"))
async def open_payout(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    wid = int(call.data.split(":")[1])
    with db() as c:
        r = c.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if not r:
        return await call.answer("Заявка не найдена.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выплатить", callback_data=f"pay:{wid}"),
         InlineKeyboardButton(text="Отказать", callback_data=f"deny:{wid}")]
    ])
    await call.message.answer(f"Выплата #{wid}\n{user_display(r['user_id'])}\nСумма: {r['amount']} ⭐", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("pay:"))
async def pay_withdrawal(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    wid = int(call.data.split(":")[1])
    with db() as c:
        r = c.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not r or r["status"] != "pending":
            return await call.answer("Заявка уже обработана.", show_alert=True)
        u = c.execute("SELECT balance FROM users WHERE user_id=?", (r["user_id"],)).fetchone()
        if not u or u["balance"] < r["amount"]:
            c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
            return await call.answer("Недостаточно средств на балансе; заявка закрыта.", show_alert=True)
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (r["amount"], r["user_id"]))
        c.execute("UPDATE withdrawals SET status='paid' WHERE id=?", (wid,))
    await bot.send_message(r["user_id"], f"💸 Заявка на вывод #{wid} отмечена администратором как выплаченная: {r['amount']} ⭐.")
    await call.message.answer(f"Выплата #{wid} отмечена как выплаченная.")
    await call.answer("Готово.")

@dp.callback_query(F.data.startswith("deny:"))
async def deny_withdrawal(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    wid = int(call.data.split(":")[1])
    with db() as c:
        r = c.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not r or r["status"] != "pending":
            return await call.answer("Заявка уже обработана.", show_alert=True)
        c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    await bot.send_message(r["user_id"], f"❌ В заявке на вывод #{wid} отказано. Баланс не списан.")
    await call.message.answer(f"Выплата #{wid} отклонена.")
    await call.answer()

@dp.callback_query(F.data == "admin:add")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    await state.set_state(Flow.waiting_admin_id)
    await call.message.answer("Отправьте Telegram user ID нового администратора (числом).")
    await call.answer()

@dp.message(Flow.waiting_admin_id)
async def add_admin_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        aid = int((message.text or "").strip())
    except ValueError:
        return await message.answer("ID должен быть числом.")
    with db() as c:
        c.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (aid,))
    await state.clear()
    await message.answer(f"✅ Администратор {aid} добавлен.")

@dp.callback_query(F.data == "admin:addtask")
async def add_task_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("Нет доступа.", show_alert=True)
    await state.set_state(Flow.waiting_task_text)
    await state.update_data(adding_task=True)
    await call.message.answer("Отправьте задание одним сообщением в формате:\nЗаголовок | Описание")
    await call.answer()

# Shared text state handler for add-task and partial-award input.
@dp.message(Flow.waiting_task_text)
async def task_or_partial_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    if "partial_sid" in data:
        try:
            amount = int((message.text or "").strip())
            if amount < 0: raise ValueError
        except ValueError:
            return await message.answer("Введите целое число 0 или больше.")
        sid = data["partial_sid"]
        await state.clear()
        return await finalize_submission_message(message, sid, amount, "partial")
    if data.get("adding_task"):
        raw = (message.text or "").strip()
        if "|" not in raw:
            return await message.answer("Нужен формат: Заголовок | Описание")
        title, desc = [x.strip() for x in raw.split("|", 1)]
        if not title or not desc:
            return await message.answer("Заполните заголовок и описание.")
        with db() as c:
            c.execute("INSERT INTO tasks(title,description,active,created_at) VALUES(?,?,1,?)",
                      (title[:150], desc[:3000], datetime.utcnow().isoformat()))
        await state.clear()
        return await message.answer("✅ Задание добавлено.")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
