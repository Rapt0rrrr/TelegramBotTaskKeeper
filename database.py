import sqlite3
from datetime import datetime


def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Таблица задач
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS tasks
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER,
                       task_text
                       TEXT
                   )
                   ''')

    # Таблица пользователей
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       user_id
                       INTEGER
                       PRIMARY
                       KEY,
                       is_onboarded
                       INTEGER
                       DEFAULT
                       0
                   )
                   ''')

    # НОВАЯ ТАБЛИЦА: Напоминания
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS reminders
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER,
                       reminder_text
                       TEXT,
                       remind_at
                       TEXT,
                       is_sent
                       INTEGER
                       DEFAULT
                       0
                   )
                   ''')

    conn.commit()
    conn.close()


# ... (функции add_task, get_tasks, delete_task, check_user, set_user_onboarded оставляем без изменений) ...

# --- НОВЫЕ ФУНКЦИИ ДЛЯ НАПОМИНАНИЙ ---

def add_reminder(user_id: int, text: str, remind_at_str: str):
    """Сохраняет напоминание в БД"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO reminders (user_id, reminder_text, remind_at) VALUES (?, ?, ?)',
                   (user_id, text, remind_at_str))
    conn.commit()
    conn.close()


def get_due_reminders():
    """Возвращает напоминания, время которых уже наступило, но они еще не отправлены"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Ищем неотправленные напоминания, где время меньше или равно текущему
    cursor.execute('SELECT id, user_id, reminder_text FROM reminders WHERE is_sent = 0 AND remind_at <= ?', (now_str,))
    reminders = cursor.fetchall()
    conn.close()
    return reminders


def mark_reminder_sent(reminder_id: int):
    """Отмечает напоминание как отправленное"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE reminders SET is_sent = 1 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()
# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ЗАДАЧАМИ ---

def add_task(user_id: int, text: str):
    """Добавляет новую задачу"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO tasks (user_id, task_text) VALUES (?, ?)', (user_id, text))
    conn.commit()
    conn.close()


def get_tasks(user_id: int):
    """Возвращает все задачи пользователя (отсортированные)"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Сортируем по ID, чтобы список всегда был в порядке добавления
    cursor.execute('SELECT id, task_text FROM tasks WHERE user_id = ? ORDER BY id ASC', (user_id,))
    tasks = cursor.fetchall()
    conn.close()
    return tasks


def delete_task(user_id: int, task_id: int):
    """Удаляет задачу по ID"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
    conn.commit()
    conn.close()


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ (ОНБОРДИНГ) ---

def check_user(user_id: int) -> bool:
    """Проверяет, прошел ли пользователь онбординг"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_onboarded FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    # Если результата нет или флаг равен 0, возвращаем False
    return bool(result and result[0] == 1)


def set_user_onboarded(user_id: int):
    """Отмечает, что пользователь нажал 'Запустить'"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Создаем запись, если ее нет
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    # Ставим флаг 1
    cursor.execute('UPDATE users SET is_onboarded = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()