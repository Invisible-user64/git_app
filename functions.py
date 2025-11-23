import aiosqlite
import json
import re
import os
import time 

from config import DB_NAME

# Функция для инициализации БД (вызывайте один раз, теперь async)
async def init_db():
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Создаём таблицы с новой схемой (если их нет)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    warnings INTEGER NOT NULL,
                    warning_1_data INTEGER NOT NULL,
                    warning_2_data INTEGER NOT NULL,   
                    warning_3_data INTEGER NOT NULL
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
                        user_id INTEGER NOT NULL,
                        warnings INTEGER NOT NULL,
                        warning_1_data INTEGER NOT NULL,
                        warning_2_data INTEGER NOT NULL,   
                        warning_3_data INTEGER NOT NULL
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
                await conn.execute("INSERT INTO users (id, username, user_id, warnings, warning_1_data, warning_2_data, warning_3_data) VALUES (?, ?, ?, ?, ?, ?, ?)", (db_id, username, data["id"], 0, 0, 0, 0))
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

async def load_warnings_count(username: str = None, user_id: int = None) -> int | None:
    """
    Возвращает количество предупреждений пользователя по username или user_id.
    Возвращает None, если пользователь не найден.
    """
    if not username and not user_id:
        print("Ошибка: укажите username или user_id.")
        return None
    
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Определяем условие поиска
            if user_id is not None:
                condition = "WHERE user_id = ?"
                param = (user_id,)
            else:
                condition = "WHERE username = ?"
                param = (username,)
            
            # Выполняем SELECT для получения warnings
            cursor = await conn.execute(
                f"SELECT warnings FROM users {condition}",
                param
            )
            result = await cursor.fetchone()
            
            if result:
                warnings_count = result[0]
                identifier = user_id if user_id else username
                print(f"Warnings для {identifier}: {warnings_count}")
                return warnings_count
            else:
                identifier = user_id if user_id else username
                print(f"Пользователь с {identifier} не найден.")
                return None
    except Exception as e:
        print(f"Ошибка при загрузке warnings: {e}")
        return None

async def increment_warnings(username: str = None, user_id: int = None):
    """
    Увеличивает warnings на 1 для пользователя по username или user_id.
    Возвращает True, если обновление прошло успешно, иначе False.
    """
    if not username and not user_id:
        print("Ошибка: укажите username или user_id.")
    
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Определяем условие поиска
            if user_id is not None:
                condition = "WHERE user_id = ?"
                param = (user_id,)
            else:
                condition = "WHERE username = ?"
                param = (username,)
            
            # Обновляем warnings
            await conn.execute(
                f"UPDATE users SET warnings = warnings + 1 {condition}",
                param
            )
            await conn.commit()
            
            # Проверяем, сколько строк обновлено
            cursor = await conn.execute("SELECT changes()")
            changes = await cursor.fetchone()
            if changes and changes[0] > 0:
                identifier = user_id if user_id else username
                print(f"Warnings для {identifier} увеличены на 1.")

            else:
                identifier = user_id if user_id else username
                print(f"Пользователь с {identifier} не найден.")

    except Exception as e:
        print(f"Ошибка при увеличении warnings: {e}")

async def decrement_warnings(username: str = None, user_id: int = None):
    """
    Уменьшает warnings на 1 для пользователя по username или user_id.
    Возвращает True, если обновление прошло успешно, иначе False.
    """
    if not username and not user_id:
        print("Ошибка: укажите username или user_id.")
        return False
    
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Определяем условие поиска
            if user_id is not None:
                warnings_count_raw = await load_warnings_count(user_id=user_id)
                condition = "WHERE user_id = ?"
                param = (user_id,)
            else:
                warnings_count_raw = await load_warnings_count(username=username)
                condition = "WHERE username = ?"
                param = (username,)
            
            # Преобразуем и проверяем warnings_count
            try:
                warnings_count = int(warnings_count_raw)  # Преобразуем в int
                if warnings_count < 0:
                    raise ValueError("warnings_count не может быть отрицательным")
            except (ValueError, TypeError):
                print(f"Ошибка: warnings_count '{warnings_count_raw}' не является допустимым целым числом.")
                return False
            
            # Обновляем warnings
            await conn.execute(
                f"UPDATE users SET warnings = warnings - 1 {condition}",
                param
            )
            await conn.execute(
                f"UPDATE users SET warning_{warnings_count}_data = 0 {condition}", param
            )
            await conn.commit()
            
            # Проверяем, сколько строк обновлено
            cursor = await conn.execute("SELECT changes()")
            changes = await cursor.fetchone()
            if changes and changes[0] > 0:
                identifier = user_id if user_id else username
                print(f"Warnings для {identifier} уменьшены на 1.")
                return True
            else:
                identifier = user_id if user_id else username
                print(f"Пользователь с {identifier} не найден.")
                return False
    
    except Exception as e:
        print(f"Ошибка при уменьшении warnings: {e}")
        return False



async def set_warning_expiry(username: str = None, user_id: int = None, expiry_time: int = None):
    """
    Устанавливает время окончания предупреждения (timestamp) в соответствующий столбец.
    expiry_time: длительность в секундах (например, 3600 для 1 часа). Конвертируется в timestamp (текущее время + длительность).
    Если expiry_time == 0 (бесконечное), ничего не устанавливает.
    """
    if not username and not user_id:
        print("Ошибка: укажите username или user_id.")
        return False
    if expiry_time is None:
        print("Ошибка: укажите expiry_time.")
        return False
    
    # Если бесконечное предупреждение, не устанавливаем expiry
    if expiry_time == 0:
        print("Бесконечное предупреждение: expiry не установлен.")
        return True
    
    # Конвертируем длительность в timestamp
    timestamp = int(time.time()) + expiry_time
    
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            # Определяем условие поиска
            if user_id is not None:
                condition = "WHERE user_id = ?"
                param = (user_id,)
            else:
                condition = "WHERE username = ?"
                param = (username,)
            
            # Получаем текущее значение warnings
            cursor = await conn.execute(f"SELECT warnings FROM users {condition}", param)
            result = await cursor.fetchone()
            if not result:
                identifier = user_id if user_id else username
                print(f"Пользователь с {identifier} не найден.")
                return False
            
            warnings_count = result[0]
            
            # Определяем, какой столбец обновлять
            if warnings_count == 1:
                column = "warning_1_data"
            elif warnings_count == 2:
                column = "warning_2_data"
            elif warnings_count == 3:
                column = "warning_3_data"
            else:
                identifier = user_id if user_id else username
                print(f"Невозможно установить expiry для {identifier}: warnings = {warnings_count} (должен быть 1-3).")
                return False
            
            # Обновляем соответствующий столбец с timestamp
            await conn.execute(
                f"UPDATE users SET {column} = ? {condition}",
                (timestamp, *param)
            )
            await conn.commit()
            
            # Проверяем, сколько строк обновлено
            cursor = await conn.execute("SELECT changes()")
            changes = await cursor.fetchone()
            if changes and changes[0] > 0:
                identifier = user_id if user_id else username
                print(f"Expiry time для {identifier} установлен в {column}: {timestamp} (timestamp)")
                return True
            else:
                identifier = user_id if user_id else username
                print(f"Не удалось обновить expiry для {identifier}.")
                return False
    except Exception as e:
        print(f"Ошибка при установке expiry time: {e}")
        return False

def check_forbidden_words(text: str) -> bool:
    """
    Проверяет, содержит ли сообщение запрещённые слова из файла forbidden_words.txt.
    Возвращает True, если найдено хотя бы одно слово, иначе False.
    """
    # Путь к файлу (предполагается, что он в той же директории)
    file_path = "forbidden_words.txt"
    
    # Если файл не существует, возвращаем False
    if not os.path.exists(file_path):
        return False
    
    try:
        # Читаем файл и создаём список слов (в нижнем регистре, без пустых строк)
        with open(file_path, "r", encoding="utf-8") as file:
            forbidden_words = [line.strip().lower() for line in file if line.strip()]
        
        # Если список пуст, возвращаем False
        if not forbidden_words:
            return False
        
        # Преобразуем сообщение в нижний регистр и проверяем наличие слов
        message_lower = text.lower()
        for word in forbidden_words:
            if word in message_lower:
                return True
        
        return False
    
    except Exception as e:
        # В случае ошибки (например, проблемы с чтением файла) возвращаем False
        print(f"Ошибка при чтении файла forbidden_words.txt: {e}")
        return False

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