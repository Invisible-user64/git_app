import asyncio
import re
import aiosqlite
import time  # Добавлен импорт для работы с временем
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, ChatMemberUpdated, ChatPermissions
from aiogram.fsm.context import FSMContext

from config import TOKEN, ADMIN_ID, GROUP_ID, DB_NAME
from functions import load_users, save_users, load_blacklist, save_blacklist, parse_time, format_time, get_user_id_by_username_in_group, init_db
from functions import increment_warnings, decrement_warnings, load_warnings_count, set_warning_expiry, check_forbidden_words
from keyboards import cmd_start_kb, cmds_kb
from FSM import Ban, Unban, Mute, Unmute, Warn, Unwarn

bot = Bot(token=TOKEN)
dp = Dispatcher()


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


@dp.message(F.chat.id == GROUP_ID)
async def moderation(message: Message):
    text = message.text
    username = f"@{message.from_user.username}"
    if check_forbidden_words(text=text):
        await ban_user_by_id_or_username(identifier=username, until_date=0, reason="Было произнесенно запретное слово")



# Новый обработчик для проверки группы
@dp.message(Command("groupinfo"), F.chat.id == GROUP_ID)
async def group_info(message: Message):
    try:
        chat = await bot.get_chat(GROUP_ID)
        await message.answer(f"ID группы: {chat.id}\nТип: {chat.type}\nНазвание: {chat.title}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    if message.from_user.id in ADMIN_ID:
        await message.answer("Команды:\n/warn\n/unwarn\n/mute\n/unmute\n/ban\n/unban\n/blacklist", reply_markup=cmds_kb)
    else:
        await message.answer("У вас нет прав доступа!")

@dp.callback_query(F.data == "to_cmds")
async def to_commands(callback: CallbackQuery):
    await callback.message.edit_text("Команды:\n/warn\n/unwarn\n/mute\n/unmute\n/ban\n/unban\n/blacklist", reply_markup=cmds_kb)

@dp.callback_query(F.data == "to_btns")
async def to_commands(callback: CallbackQuery):
    await callback.message.edit_text("Управление кнопками:", reply_markup=cmd_start_kb)

@dp.callback_query(F.data == "ban")
async def ban_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Ban.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя:")

@dp.message(Ban.waiting_for_message)
async def process_ban_identifier(message: Message, state: FSMContext):
    identifier = message.text.strip()
    await state.update_data(identifier=identifier)
    await state.set_state(Ban.waiting_for_time)
    await message.answer(
        "Введите время бана в формате Nt (например, 1h для 1 часа, 30m для 30 минут):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Бесконечный бан", callback_data="infinite_ban")]])
    )

@dp.message(Ban.waiting_for_time)
async def process_ban_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    until_seconds = parse_time(time_str)
    await state.update_data(until_seconds=until_seconds)
    await state.set_state(Ban.waiting_for_reason)
    await message.answer(
        "Введите причину бана:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_reason")]])
    )

@dp.callback_query(F.data == "infinite_ban", Ban.waiting_for_time)
async def infinite_ban(callback: CallbackQuery, state: FSMContext):
    await state.update_data(until_seconds=0)
    await state.set_state(Ban.waiting_for_reason)
    await callback.message.edit_text(
        "Введите причину бана:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_reason")]])
    )

@dp.message(Ban.waiting_for_reason)
async def process_ban_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)

    result = await ban_user_by_id_or_username(identifier, until_seconds, reason)
    await message.answer(result)

    await state.clear()

@dp.callback_query(F.data == "skip_reason", Ban.waiting_for_reason)
async def skip_reason(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)

    result = await ban_user_by_id_or_username(identifier, until_seconds, "")
    await callback.message.edit_text(result)

    await state.clear()

@dp.callback_query(F.data == "unban")
async def unban_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Unban.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя для разбана:")

@dp.message(Unban.waiting_for_message)
async def process_unban(message: Message, state: FSMContext):
    identifier = message.text.strip()

    result = await unban_user_by_id_or_username(identifier)
    await message.answer(result)

    await state.clear()

@dp.callback_query(F.data == "mute")
async def mute_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Mute.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя:")

@dp.message(Mute.waiting_for_message)
async def process_mute_identifier(message: Message, state: FSMContext):
    identifier = message.text.strip()
    await state.update_data(identifier=identifier)
    await state.set_state(Mute.waiting_for_time)
    await message.answer(
        "Введите время мута в формате Nt (например, 1h для 1 часа, 30m для 30 минут):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Бесконечный мут", callback_data="infinite_mute")]])
    )

@dp.message(Mute.waiting_for_time)
async def process_mute_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    until_seconds = parse_time(time_str)
    await state.update_data(until_seconds=until_seconds)
    await state.set_state(Mute.waiting_for_reason)
    await message.answer(
        "Введите причину мута:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_mute_reason")]])
    )

@dp.callback_query(F.data == "infinite_mute", Mute.waiting_for_time)
async def infinite_mute(callback: CallbackQuery, state: FSMContext):
    await state.update_data(until_seconds=0)
    await state.set_state(Mute.waiting_for_reason)
    await callback.message.edit_text(
        "Введите причину мута:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_mute_reason")]])
    )

@dp.message(Mute.waiting_for_reason)
async def process_mute_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)

    result = await mute_user_by_id_or_username(identifier, until_seconds, reason)
    await message.answer(result)

    await state.clear()

@dp.callback_query(F.data == "skip_mute_reason", Mute.waiting_for_reason)
async def skip_reason(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)

    result = await mute_user_by_id_or_username(identifier, until_seconds, "")
    await callback.message.edit_text(result)

    await state.clear()

@dp.callback_query(F.data == "unmute")
async def unmute_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Unmute.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя для размута:")

@dp.message(Unmute.waiting_for_message)
async def process_unmute(message: Message, state: FSMContext):
    identifier = message.text.strip()

    result = await unmute_user_by_id_or_username(identifier)
    await message.answer(result)

    await state.clear()

@dp.callback_query(F.data == "warn")
async def warn_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Warn.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя:")

@dp.message(Warn.waiting_for_message)
async def process_warn_identifier(message: Message, state: FSMContext):
    identifier = message.text.strip()
    await state.update_data(identifier=identifier)
    await state.set_state(Warn.waiting_for_time)
    await message.answer(
        "Введите время бана в формате Nt (например, 1h для 1 часа, 30m для 30 минут):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Бесконечное придупреждение", callback_data="infinite_warn")]])
    )

@dp.message(Warn.waiting_for_time)
async def process_warn_time(message: Message, state: FSMContext):
    time_str = message.text.strip()
    until_seconds = parse_time(time_str)
    await state.update_data(until_seconds=until_seconds)
    await state.set_state(Warn.waiting_for_reason)
    await message.answer(
        "Введите причину предупреждения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_warn_reason")]])
    )

@dp.callback_query(F.data == "infinite_warn", Warn.waiting_for_time)
async def infinite_warn(callback: CallbackQuery, state: FSMContext):
    await state.update_data(until_seconds=0)
    await state.set_state(Warn.waiting_for_reason)
    await callback.message.edit_text(
        "Введите причину предупреждения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить причину", callback_data="skip_warn_reason")]])
    )

@dp.message(Warn.waiting_for_reason)
async def process_warn_reason(message: Message, state: FSMContext):
    reason = message.text.strip()
    reason = message.text.strip()
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)
    
    user_id = None
    if identifier.startswith('@'):
        username = identifier[1:]
        user_id = await get_user_id_by_username_in_group(username)
        if user_id is None:
            # Пользователь не найден, используем user_id из callback (предполагая, что это цель)
            user_id = message.from_user.id  # Замените на правильный user_id, если известен иначе
            # Вставляем в БД
            try:
                async with aiosqlite.connect(DB_NAME) as conn:
                    await conn.execute("""
                        INSERT INTO users (username, user_id, warnings, warning_1_data, warning_2_data, warning_3_data) 
                        VALUES (?, ?, 0, 0, 0, 0)
                    """, (username, user_id))
                    await conn.commit()
                print(f"Пользователь @{username} с user_id {user_id} добавлен.")
            except Exception as e:
                print(f"Ошибка добавления пользователя @{username}: {e}")
                await message.answer("Ошибка: не удалось добавить пользователя.")
                await state.clear()
                return
    elif identifier.isdigit():
        user_id = int(identifier)
    
    result = await warn_user_by_id_or_username(identifier, until_seconds, reason)
    await message.answer(result)
    
    # Теперь user_id известен, вызываем set_warning_expiry
    await set_warning_expiry(user_id=user_id, expiry_time=until_seconds)
    
    await state.clear()

@dp.callback_query(F.data == "skip_warn_reason", Warn.waiting_for_reason)
async def skip_reason(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    identifier = data.get("identifier")
    until_seconds = data.get("until_seconds", 0)
    
    user_id = None
    if identifier.startswith('@'):
        username = identifier[1:]
        user_id = await get_user_id_by_username_in_group(username)
        if user_id is None:
            # Пользователь не найден, используем user_id из callback (предполагая, что это цель)
            user_id = callback.from_user.id  # Замените на правильный user_id, если известен иначе
            # Вставляем в БД
            try:
                async with aiosqlite.connect(DB_NAME) as conn:
                    await conn.execute("""
                        INSERT INTO users (username, user_id, warnings, warning_1_data, warning_2_data, warning_3_data) 
                        VALUES (?, ?, 0, 0, 0, 0)
                    """, (username, user_id))
                    await conn.commit()
                print(f"Пользователь @{username} с user_id {user_id} добавлен.")
            except Exception as e:
                print(f"Ошибка добавления пользователя @{username}: {e}")
                await callback.message.edit_text("Ошибка: не удалось добавить пользователя.")
                await state.clear()
                return
    elif identifier.isdigit():
        user_id = int(identifier)
    
    result = await warn_user_by_id_or_username(identifier, until_seconds, "")
    await callback.message.edit_text(result)
    
    # Теперь user_id известен, вызываем set_warning_expiry
    await set_warning_expiry(user_id=user_id, expiry_time=until_seconds)
    
    await state.clear()


@dp.callback_query(F.data == "unwarn")
async def unwarn_func(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Unwarn.waiting_for_message)
    await callback.message.answer("Введите @username или ID пользователя для снятия предупреждения:")

@dp.message(Unwarn.waiting_for_message)
async def process_unmute(message: Message, state: FSMContext):
    identifier = message.text.strip()
    username = identifier[1:]
    warning_count = await load_warnings_count(username=username)
    print(warning_count, username)

    if warning_count == 0:
        await message.answer("У этого пользователя нет предупреждений")
    
    else:
        result = await unwarn_user_by_id_or_username(identifier)
        await message.answer(result)

        await state.clear()

# Обработчик для показа черного списка
@dp.callback_query(F.data == "black_list")
async def show_blacklist(callback: CallbackQuery):
    blacklist = await load_blacklist()
    if not blacklist:
        await callback.message.answer("Черный список пуст.")
    else:
        text = "Черный список:\n"
        for uname, data in blacklist.items():
            until = data.get("until", 0)
            reason = data.get("reason", "Не указана")
            if until > 0:
                until_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(until))
                text += f"@{uname} (ID: {data['id']}) - до {until_str}, причина: {reason}\n"
            else:
                text += f"@{uname} (ID: {data['id']}) - постоянный, причина: {reason}\n"
        await callback.message.answer(text)

# Обработчик для отслеживания новых участников в группе
@dp.chat_member(F.chat.id == GROUP_ID)
async def track_new_member(update: ChatMemberUpdated):
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    # Проверяем, что пользователь только что присоединился (статус изменился на "member")
    if old_status != "member" and new_status == "member":
        user = update.new_chat_member.user
        username = user.username
        user_id = user.id

        if username:
            users = await load_users()
            users[username] = {"id": user_id, "muted_until": 0, "muted_reason": ""}
            await save_users(users)
            print(f"Новый пользователь сохранен: @{username} -> {user_id}")
        else:
            print(f"Пользователь {user_id} без username — не сохранен.")

# Обработчик для добавления пользователей, которые пишут сообщения в группе, если их нет в базе данных
@dp.message(F.chat.id == GROUP_ID)
async def add_user_on_message(message: Message):
    user = message.from_user
    username = user.username
    user_id = user.id

    if username:
        users = await load_users()
        if username not in users:
            users[username] = {"id": user_id, "muted_until": 0, "muted_reason": ""}
        await save_users(users)
        print(f"Пользователь добавлен по сообщению: @{username} -> {user_id}")

async def main():
    await init_db()
    # Запускаем фоновые задачи для проверки истекших банов и мутов
    asyncio.create_task(check_expired_bans())
    asyncio.create_task(check_expired_mutes())
    asyncio.create_task(check_expired_warnings())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())