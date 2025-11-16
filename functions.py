import aiosqlite
import json
import re
import os

DB_NAME = 'bot.sqlite'

# Функция для инициализации БД (вызывайте один раз, теперь async)
async def init_db():
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Создаём таблицы с новой схемой (если их нет)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    username TEXT PRIMARY KEY,
                    ban_data TEXT NOT NULL
                )
            """)
            # Миграция для blacklist (если столбца ban_data нет)
            try:
                await conn.execute("SELECT ban_data FROM blacklist LIMIT 1")
            except aiosqlite.OperationalError:
                await conn.execute("ALTER TABLE blacklist ADD COLUMN ban_data TEXT NOT NULL DEFAULT '{}'")
                print("Столбец ban_data добавлен в таблицу blacklist.")
            # Миграция для users: проверяем и добавляем столбец id, если его нет
            try:
                await conn.execute("SELECT id FROM users LIMIT 1")
            except aiosqlite.OperationalError:
                print("Выполняем миграцию таблицы users...")
                # Создаём временную таблицу с новой схемой
                await conn.execute("""
                    CREATE TABLE users_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        user_id INTEGER NOT NULL
                    )
                """)
                # Копируем существующие данные (id присвоится автоматически: 1, 2, 3...)
                await conn.execute("INSERT INTO users_temp (username, user_id) SELECT username, user_id FROM users")
                # Удаляем старую таблицу
                await conn.execute("DROP TABLE users")
                # Переименовываем временную таблицу
                await conn.execute("ALTER TABLE users_temp RENAME TO users")
                print("Миграция таблицы users завершена.")
            await conn.commit()
        print("База данных инициализирована.")
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")

# Функция для загрузки пользователей из SQL таблицы (теперь async)
async def load_users():
    try:
        if not os.path.exists(DB_NAME):
            return {}  # Если файла нет, возвращаем пустой словарь
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT id, username, user_id FROM users")
            rows = await cursor.fetchall()
            users = {row[1]: {"db_id": row[0], "id": row[2], "muted_until": 0, "muted_reason": ""} for row in rows}  # row[0] - db_id, row[1] - username, row[2] - user_id
        return users
    except Exception as e:
        print(f"Ошибка загрузки пользователей: {e}")
        return {}

# Функция для сохранения пользователей в SQL таблицу (теперь async)
async def save_users(users):
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("DELETE FROM users")  # Очищаем таблицу перед вставкой
            for username, data in users.items():
                # Вставляем с автоинкрементом id (если db_id есть, используем его; иначе - NULL для авто)
                db_id = data.get("db_id", None)
                await conn.execute("INSERT INTO users (id, username, user_id) VALUES (?, ?, ?)", (db_id, username, data["id"]))
            await conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения пользователей: {e}")

# Функция для загрузки черного списка из SQL таблицы (теперь async)
async def load_blacklist():
    try:
        if not os.path.exists(DB_NAME):
            return {}  # Если файла нет, возвращаем пустой словарь
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT username, ban_data FROM blacklist")
            rows = await cursor.fetchall()
            blacklist = {}
            for row in rows:
                username = row[0]
                ban_data = json.loads(row[1])  # Десериализуем JSON обратно в словарь
                blacklist[username] = ban_data
        return blacklist
    except Exception as e:
        print(f"Ошибка загрузки blacklist: {e}")
        return {}

# Функция для сохранения черного списка в SQL таблицу (теперь async)
async def save_blacklist(blacklist):
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("DELETE FROM blacklist")
            for username, ban_data in blacklist.items():
                ban_data_json = json.dumps(ban_data)  # Сериализуем словарь в JSON
                await conn.execute("INSERT INTO blacklist (username, ban_data) VALUES (?, ?)", (username, ban_data_json))
            await conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения blacklist: {e}")

# Остальные функции без изменений
time_designation = {"s": 1, "m": 60, "h": 3600, "d": 86400}

def parse_time(time_str: str) -> int:
    if not time_str.strip() or time_str.strip() == '0':
        return 0
    match = re.match(r'^(\d+)([smhd])$', time_str.strip().lower())
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        return num * time_designation.get(unit, 1)
    return 0

def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds // 60} мин"
    elif seconds < 86400:
        return f"{seconds // 3600} ч"
    else:
        return f"{seconds // 86400} д"
    
async def get_user_id_by_username_in_group(username: str) -> int | None:
    try:
        if not os.path.exists(DB_NAME):
            return None
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = await cursor.fetchone()
        if result:
            user_id = result[0]
            print(f"ID найден в SQL: @{username} -> {user_id}")
            return user_id
        print(f"ID не найден в SQL для @{username}")
        return None
    except Exception as e:
        print(f"Ошибка получения ID по username: {e}")
        return None