import aiosqlite
import json
import re
import os
import time 
import asyncio
from aiogram import Bot
from aiogram.types import ChatPermissions

from config import DB_NAME, GROUP_ID, TOKEN

bot = Bot(token=TOKEN)

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
    
# Фоновая задача для проверки и удаления истекших банов (обновлена на асинхронные функции)
async def check_expired_bans():
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждые 60 секунд
            blacklist = await load_blacklist()
            current_time = int(time.time())
            to_remove = []
            for uname, data in blacklist.items():
                if data.get("until", 0) > 0 and data["until"] < current_time:
                    to_remove.append(uname)
                    user_id = data["id"]
                    # Отправляем сообщение в чат
                    try:
                        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь @{uname} разбанен (бан истек).")
                    except Exception as e:
                        print(f"Ошибка отправки в чат для @{uname}: {e}")
                    # Отправляем личное сообщение пользователю
                    try:
                        await bot.send_message(chat_id=user_id, text="Ваш бан истек, вы разбанены.")
                    except Exception as e:
                        print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")
            if to_remove:
                for uname in to_remove:
                    del blacklist[uname]
                await save_blacklist(blacklist)
                print(f"Удалены истекшие баны: {to_remove}")
        except Exception as e:
            print(f"Ошибка в check_expired_bans: {e}")
            await asyncio.sleep(60)  # Ждем перед следующей попыткой

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

# Обновленная функция для бана по ID или username с временем и причиной
async def ban_user_by_id_or_username(identifier: str, until_date: int = 0, reason: str = "") -> str:
    """
    Забанить пользователя по ID (число) или @username с указанным временем и причиной.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Бан доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_blacklist = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Баним по ID: {user_id}")
            # Для черного списка попробуем найти username по ID (если есть в базе данных)
            users = await load_users()
            for uname, data in users.items():
                if data.get("id") == user_id:
                    username_for_blacklist = uname
                    break
        elif identifier.startswith('@'):  # Если @username
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_blacklist = username
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."

        # Вычисляем until_date
        ban_until = int(time.time()) + until_date if until_date > 0 else 0

        # Баним пользователя
        await bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id, until_date=ban_until if ban_until > 0 else None)

        # Добавляем в черный список
        if username_for_blacklist:
            blacklist = await load_blacklist()
            blacklist[username_for_blacklist] = {
                "id": user_id,
                "until": ban_until,
                "reason": reason if reason else "Не указана"
            }
            await save_blacklist(blacklist)
            print(f"Пользователь @{username_for_blacklist} добавлен в черный список.")

        ban_type = "временно" if until_date > 0 else "постоянно"
        time_text = f" на {format_time(until_date)}" if until_date > 0 else ""
        reason_text = f" по причине: {reason}" if reason else ""

        # Отправляем сообщение в чат
        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь {identifier} забанен {ban_type}{time_text}{reason_text}.")

        # Отправляем личное сообщение пользователю
        try:
            await bot.send_message(chat_id=user_id, text=f"Вы забанены {ban_type}{time_text}{reason_text}.")
        except Exception as e:
            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

        return f"Пользователь {identifier} забанен {ban_type}{time_text} и добавлен в черный список." + (f"\nПричина: {reason}" if reason else "")
    except Exception as e:
        print(f"Ошибка при бане: {e}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."

# Новая функция для разбана по ID или username
async def unban_user_by_id_or_username(identifier: str) -> str:
    """
    Разбанить пользователя по ID (число) или @username.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Разбан доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_blacklist = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Разбаниваем по ID: {user_id}")
            # Для черного списка попробуем найти username по ID
            users = await load_users()
            for uname, data in users.items():
                if data.get("id") == user_id:
                    username_for_blacklist = uname
                    break
        elif identifier.startswith('@'):  # Если @username
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_blacklist = username
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."

        # Разбаниваем пользователя
        await bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)

        # Удаляем из черного списка
        if username_for_blacklist:
            blacklist = await load_blacklist()
            if username_for_blacklist in blacklist:
                del blacklist[username_for_blacklist]
                await save_blacklist(blacklist)
                print(f"Пользователь @{username_for_blacklist} удален из черного списка.")

        # Отправляем сообщение в чат
        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь {identifier} разбанен.")

        # Отправляем личное сообщение пользователю
        try:
            await bot.send_message(chat_id=user_id, text="Вы разбанены.")
        except Exception as e:
            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

        return f"Пользователь {identifier} разбанен и удален из черного списка."
    except Exception as e:
        print(f"Ошибка при разбане: {e}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."
    

async def check_expired_mutes():
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждые 60 секунд
            users = await load_users()
            current_time = int(time.time())
            to_unmute = []
            for uname, data in users.items():
                if data.get("muted_until", 0) > 0 and data["muted_until"] < current_time:
                    to_unmute.append(uname)
                    user_id = data["id"]
                    # Отправляем сообщение в чат
                    try:
                        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь @{uname} больше не заглушен (мут истек).")
                    except Exception as e:
                        print(f"Ошибка отправки в чат для @{uname}: {e}")
                    # Отправляем личное сообщение пользователю
                    try:
                        await bot.send_message(chat_id=user_id, text="Ваш мут истек, вы больше не заглушены.")
                    except Exception as e:
                        print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")
            if to_unmute:
                for uname in to_unmute:
                    users[uname]["muted_until"] = 0
                    users[uname]["muted_reason"] = ""
                await save_users(users)
                print(f"Удалены истекшие муты: {to_unmute}")
        except Exception as e:
            print(f"Ошибка в check_expired_mutes: {e}")
            await asyncio.sleep(60)  # Ждем перед следующей попыткой
    

# Функция для мута по ID или username с временем и причиной
async def mute_user_by_id_or_username(identifier: str, until_date: int = 0, reason: str = "") -> str:
    """
    Замутить пользователя по ID (число) или @username с указанным временем и причиной.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Мут доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_muted = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Мутим по ID: {user_id}")
            # Для списка мутов попробуем найти username по ID (если есть в базе данных)
            users = await load_users()
            for uname, data in users.items():
                if isinstance(data, dict) and data.get("id") == user_id:
                    username_for_muted = uname
                    break
        elif identifier.startswith('@'):  # Если @username
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_muted = username
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."

        # Вычисляем until_date
        mute_until = int(time.time()) + until_date if until_date > 0 else 0

        permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_other_messages=False)

        # Мутим пользователя
        await bot.restrict_chat_member(chat_id=GROUP_ID, user_id=user_id, permissions=permissions, until_date=mute_until if mute_until > 0 else None)

        # Обновляем базу данных (добавляем/обновляем данные о муте)
        users = await load_users()
        if username_for_muted not in users:
            users[username_for_muted] = {"id": user_id}
        users[username_for_muted]["muted_until"] = mute_until
        users[username_for_muted]["muted_reason"] = reason if reason else "Не указана"
        await save_users(users)

        mute_type = "временно" if until_date > 0 else "постоянно"
        time_text = f" на {format_time(until_date)}" if until_date > 0 else ""
        reason_text = f" по причине: {reason}" if reason else ""

        # Отправляем сообщение в чат
        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь {identifier} заглушён {mute_type}{time_text}{reason_text}.")

        # Отправляем личное сообщение пользователю
        try:
            await bot.send_message(chat_id=user_id, text=f"Вы заглушены {mute_type}{time_text}{reason_text}.")
        except Exception as e:
            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

        return f"Пользователь {identifier} заглушён {mute_type}{time_text}" + (f"\nПричина: {reason}" if reason else "")
    except Exception as e:
        print(f"Ошибка при муте: {e}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."


# Функция для размута по ID или username
async def unmute_user_by_id_or_username(identifier: str) -> str:
    """
    Размутить пользователя по ID (число) или @username.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Размут доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_muted = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Размутиваем по ID: {user_id}")
            # Для списка мутов попробуем найти username по ID (если есть в базе данных)
            users = await load_users()
            for uname, data in users.items():
                if isinstance(data, dict) and data.get("id") == user_id:
                    username_for_muted = uname
                    break
        elif identifier.startswith('@'):  # Если @username
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_muted = username
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."

        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True)

        # Размутиваем пользователя
        await bot.restrict_chat_member(chat_id=GROUP_ID, user_id=user_id, permissions=permissions)

        # Обновляем базу данных (очищаем данные о муте)
        users = await load_users()
        if username_for_muted in users:
            users[username_for_muted]["muted_until"] = 0
            users[username_for_muted]["muted_reason"] = ""
            await save_users(users)

        # Отправляем сообщение в чат
        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь {identifier} больше не заглушен.")

        # Отправляем личное сообщение пользователю
        try:
            await bot.send_message(chat_id=user_id, text="Вы больше не заглушены.")
        except Exception as e:
            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

        return f"Пользователь {identifier} размучен."
    except Exception as e:
        print(f"Ошибка при размуте: {e}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."
    
async def check_expired_warnings():
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждые 60 секунд
            async with aiosqlite.connect(DB_NAME) as conn:
                cursor = await conn.execute("SELECT id, username, user_id, warnings, warning_1_data, warning_2_data, warning_3_data FROM users")
                rows = await cursor.fetchall()
                current_time = int(time.time())
                for row in rows:
                    db_id, username, user_id, warnings, w1, w2, w3 = row
                    expired_columns = []
                    if w1 > 0 and w1 < current_time:
                        expired_columns.append("warning_1_data")
                    if w2 > 0 and w2 < current_time:
                        expired_columns.append("warning_2_data")
                    if w3 > 0 and w3 < current_time:
                        expired_columns.append("warning_3_data")
                    
                    if expired_columns:
                        # Уменьшаем warnings на количество истекших
                        decrement_count = len(expired_columns)
                        new_warnings = max(0, warnings - decrement_count)
                        await conn.execute(
                            "UPDATE users SET warnings = ?, warning_1_data = CASE WHEN warning_1_data < ? THEN 0 ELSE warning_1_data END, warning_2_data = CASE WHEN warning_2_data < ? THEN 0 ELSE warning_2_data END, warning_3_data = CASE WHEN warning_3_data < ? THEN 0 ELSE warning_3_data END WHERE id = ?",
                            (new_warnings, current_time, current_time, current_time, db_id)
                        )
                        # Отправляем сообщение в чат
                        try:
                            await bot.send_message(chat_id=GROUP_ID, text=f"У пользователя @{username} истекло {decrement_count} предупреждение(й). Осталось предупреждений: {new_warnings}.")
                        except Exception as e:
                            print(f"Ошибка отправки в чат для @{username}: {e}")
                        # Отправляем личное сообщение пользователю
                        try:
                            await bot.send_message(chat_id=user_id, text=f"У вас истекло {decrement_count} предупреждение(й). Осталось предупреждений: {new_warnings}.")
                        except Exception as e:
                            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")
                await conn.commit()
        except Exception as e:
            print(f"Ошибка в check_expired_warnings: {e}")
            await asyncio.sleep(60)  # Ждем перед следующей попыткой
    

async def warn_user_by_id_or_username(identifier: str, until_date: int = 0, reason: str = "") -> str:
    """
    Выдать предупреждение пользователю по ID (число) или @username с указанным временем и причиной.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Бан доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_blacklist = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Выдаём придупреждение по ID: {user_id}")
            # Выдаём предупреждение пользователю
            await increment_warnings(user_id=user_id)
            warning_count = await load_warnings_count(user_id=user_id)
            # Для черного списка попробуем найти username по ID (если есть в базе данных)
            users = await load_users()
            for uname, data in users.items():
                if data.get("id") == user_id:
                    username_for_blacklist = uname
                    break
        elif identifier.startswith('@'):  # Если @usernameЫЫЫ
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_blacklist = username
            # Выдаём предупреждение пользователю
            await increment_warnings(username=username)
            warning_count = await load_warnings_count(username=username)
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."
        
        if warning_count >= 3:
            await bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id, until_date=0)

            # Добавляем в черный список
            if username_for_blacklist:
                blacklist = await load_blacklist()
                blacklist[username_for_blacklist] = {
                    "id": user_id,
                    "until": 0,
                    "reason": reason if reason else "Не указана"
                }
                await save_blacklist(blacklist)
                print(f"Пользователь @{username_for_blacklist} добавлен в черный список.")
        

            # Отправляем сообщение в чат
            await bot.send_message(chat_id=GROUP_ID, text=f"Пользователь {identifier} забанен постоенно по причине: Правила были нарушены 3 раза.")

            # Отправляем личное сообщение пользователю
            try:
                await bot.send_message(chat_id=user_id, text=f"Вы забанены постоенно по причине: Правила были нарушены 3 раза.")
            except Exception as e:
                print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

            return f"Пользователь {identifier} забанен постоенно и добавлен в черный список." + (f"\nПричина: Правила были нарушены 3 раза.")

        else:
            # Вычисляем until_date
            warn_until = int(time.time()) + until_date if until_date > 0 else 0

            # Добавляем в список предупреждений,я хз ещё думаем как реализовать


            warn_type = "временное" if until_date > 0 else "постоянное"
            time_text = f" на {format_time(until_date)}" if until_date > 0 else ""
            reason_text = f" по причине: {reason}" if reason else ""
            

            # Отправляем сообщение в чат
            await bot.send_message(chat_id=GROUP_ID, text=f"Пользователю {identifier} было выдано {warn_type} предупреждение{time_text}{reason_text}.\nПредупреждений осталось: {3-warning_count}.")

            # Отправляем личное сообщение пользователю
            try:
                await bot.send_message(chat_id=user_id, text=f"Вам выдано {warn_type} предупреждение{time_text}{reason_text}.\nПредупреждений осталось: {3-warning_count}.")
            except Exception as e:
                print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

            return f"Пользователю {identifier} выдано {warn_type} предупреждение {time_text}" + (f"\nПричина: {reason}" if reason else "") + f" Предупреждений осталось: {3-warning_count}."
    except Exception as e:
        print(f"Ошибка при выдаче предупреждения: {e}, warning_count = {warning_count}, {identifier}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."
    
# Новая функция для разбана по ID или username
async def unwarn_user_by_id_or_username(identifier: str) -> str:
    """
    Снять предупреждение с пользователя по ID (число) или @username.
    Возвращает сообщение об успехе или ошибке.
    """
    try:
        # Проверяем тип чата
        chat = await bot.get_chat(GROUP_ID)
        if chat.type not in ["supergroup", "channel"]:
            return f"Ошибка: Разбан доступен только в супергруппах и каналах. Тип чата: {chat.type}."

        username_for_blacklist = None
        if identifier.isdigit():  # Если это ID (число)
            user_id = int(identifier)
            print(f"Разбаниваем по ID: {user_id}")
            await decrement_warnings(user_id=user_id)
            warning_count = await load_warnings_count(user_id=user_id)
            # Для черного списка попробуем найти username по ID ПОКА ОСТАВЛЮ
            users = await load_users()
            for uname, data in users.items():
                if data.get("id") == user_id:
                    username_for_blacklist = uname
                    break
        elif identifier.startswith('@'):  # Если @username
            username = identifier[1:]  # Убираем '@'
            print(f"Получаем ID по username: {username}")
            user_id = await get_user_id_by_username_in_group(username)  # Из базы данных
            username_for_blacklist = username
            await decrement_warnings(username=username)
            warning_count = await load_warnings_count(username=username)
            if not user_id:
                return f"Пользователь @{username} не найден в базе данных. Возможно, он не писал сообщения или не добавлен. Попробуйте ввести его ID (число)."
        else:
            return "Неверный формат. Введите ID (число) или @username."

        # Отправляем сообщение в чат
        await bot.send_message(chat_id=GROUP_ID, text=f"Пользователю {identifier} сняли 1 предупреждение.")

        # Отправляем личное сообщение пользователю
        try:
            await bot.send_message(chat_id=user_id, text="Вам сняли одно предупреждение.")
        except Exception as e:
            print(f"Не удалось отправить личное сообщение пользователю {user_id}: {e}")

        return f"Пользователю {identifier} сняли предупрждение."
    except Exception as e:
        print(f"Ошибка при разбане: {e}")
        return f"Ошибка: {str(e)}. Проверьте права бота или ID группы."

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
    
