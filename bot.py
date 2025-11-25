import asyncio
import re
import aiosqlite
import time  # Добавлен импорт для работы с временем
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, ChatMemberUpdated, ChatPermissions
from aiogram.fsm.context import FSMContext
from functions import load_users, save_users, load_blacklist, parse_time, get_user_id_by_username_in_group, init_db, check_expired_bans, check_expired_mutes, check_expired_warnings
from functions import load_warnings_count, set_warning_expiry, check_forbidden_words, ban_user_by_id_or_username, unban_user_by_id_or_username, mute_user_by_id_or_username, unmute_user_by_id_or_username, warn_user_by_id_or_username, unwarn_user_by_id_or_username
from keyboards import cmd_start_kb, cmds_kb
from FSM import Ban, Unban, Mute, Unmute, Warn, Unwarn

from config import TOKEN, ADMIN_ID, GROUP_ID, DB_NAME

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(F.chat.id == GROUP_ID)
async def moderation(message: Message):
    text = message.text
    username = f"@{message.from_user.username}"
    if check_forbidden_words(text=text):
        await ban_user_by_id_or_username(identifier=username, until_date=0, reason="Было произнесенно запретное слово")

# Новый обработчик для проверки группы
#@dp.message(Command("groupinfo"), F.chat.id == GROUP_ID)
#async def group_info(message: Message):
#    try:
#        chat = await bot.get_chat(GROUP_ID)
#        await message.answer(f"ID группы: {chat.id}\nТип: {chat.type}\nНазвание: {chat.title}")
#    except Exception as e:
#        await message.answer(f"Ошибка: {e}")

@dp.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    if message.from_user.id in ADMIN_ID:
        await message.answer("Команды:\n/warn\n/unwarn\n/mute\n/unmute\n/ban\n/unban\n/blacklist", reply_markup=cmds_kb)
    else:
        await message.answer("У вас нет прав доступа!")

@dp.message(Command("ban"), F.chat.type == "private")
async def cmd_ban(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        args = command.args
        
        if not args:
            await message.answer("Укажите аргументы: /ban <username/ID> <длительность> <причина>")
            return
        
        identifier = None
        ban_until_or_reason = None
        reason = None

        parts = args.split(maxsplit=2)
        length = len(parts)
        if length == 1:
            identifier = parts[0]
        elif length == 2:
            identifier = parts[0]
            ban_until_or_reason = parts[1]
        else:
            identifier = parts[0]
            ban_until_or_reason = parts[1]
            reason = parts[2]

        if identifier.startswith("@") or identifier.isdigit():
            if ban_until_or_reason == None and reason == None:
                result = await ban_user_by_id_or_username(identifier, 0, "")
                await message.answer(result) 
            elif ban_until_or_reason[0].isdigit() and reason == None:
                until_date = parse_time(ban_until_or_reason)
                result = await ban_user_by_id_or_username(identifier, until_date, "")
                await message.answer(result)
            elif not ban_until_or_reason[0].isdigit() and reason == None:
                result = await ban_user_by_id_or_username(identifier, 0, ban_until_or_reason)
                await message.answer(result)
            else:
                until_date = parse_time(ban_until_or_reason)
                result = await ban_user_by_id_or_username(identifier, until_date, reason)
                await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")

@dp.message(Command("unban"), F.chat.type == "private")
async def cmd_unban(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        identifier = command.args
        
        if not identifier:
            await message.answer("Укажите аргументы: /unban <username/ID>")
            return
        
        if identifier.startswith("@") or identifier.isdigit():
            result = await unban_user_by_id_or_username(identifier)
            await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")


@dp.message(Command("mute"), F.chat.type == "private")
async def cmd_mute(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        args = command.args
        
        if not args:
            await message.answer("Укажите аргументы: /mute <username/ID> <длительность> <причина>")
            return
        
        identifier = None
        mute_until_or_reason = None
        reason = None

        parts = args.split(maxsplit=2)
        length = len(parts)
        if length == 1:
            identifier = parts[0]
        elif length == 2:
            identifier = parts[0]
            mute_until_or_reason = parts[1]
        else:
            identifier = parts[0]
            mute_until_or_reason = parts[1]
            reason = parts[2]

        if identifier.startswith("@") or identifier.isdigit():
            if mute_until_or_reason == None and reason == None:
                result = await mute_user_by_id_or_username(identifier, 0, "")
                await message.answer(result) 
            elif mute_until_or_reason[0].isdigit() and reason == None:
                until_date = parse_time(mute_until_or_reason)
                result = await mute_user_by_id_or_username(identifier, until_date, "")
                await message.answer(result)
            elif not mute_until_or_reason[0].isdigit() and reason == None:
                result = await mute_user_by_id_or_username(identifier, 0, mute_until_or_reason)
                await message.answer(result)
            else:
                until_date = parse_time(mute_until_or_reason)
                result = await mute_user_by_id_or_username(identifier, until_date, reason)
                await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")

@dp.message(Command("unmute"), F.chat.type == "private")
async def cmd_unmute(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        identifier = command.args
        
        if not identifier:
            await message.answer("Укажите аргументы: /unmute <username/ID>")
            return
        
        if identifier.startswith("@") or identifier.isdigit():
            result = await unmute_user_by_id_or_username(identifier)
            await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")

@dp.message(Command("warn"), F.chat.type == "private")
async def cmd_warn(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        args = command.args
        
        if not args:
            await message.answer("Укажите аргументы: /warn <username/ID> <длительность> <причина>")
            return
        
        identifier = None
        warn_until_or_reason = None
        reason = None

        parts = args.split(maxsplit=2)
        length = len(parts)
        if length == 1:
            identifier = parts[0]
        elif length == 2:
            identifier = parts[0]
            warn_until_or_reason = parts[1]
        else:
            identifier = parts[0]
            warn_until_or_reason = parts[1]
            reason = parts[2]

        if identifier.startswith("@") or identifier.isdigit():
            if warn_until_or_reason == None and reason == None:
                result = await warn_user_by_id_or_username(identifier, 0, "")
                await message.answer(result) 
            elif warn_until_or_reason[0].isdigit() and reason == None:
                until_date = parse_time(warn_until_or_reason)
                result = await warn_user_by_id_or_username(identifier, until_date, "")
                if identifier.startswith("@"):
                    await set_warning_expiry(username=identifier[1:], expiry_time=until_date)
                else:
                    await set_warning_expiry(user_id=identifier, expiry_time=until_date)
                await message.answer(result)
            elif not warn_until_or_reason[0].isdigit() and reason == None:
                result = await warn_user_by_id_or_username(identifier, 0, warn_until_or_reason)
                await message.answer(result)
            else:
                until_date = parse_time(warn_until_or_reason)
                result = await warn_user_by_id_or_username(identifier, until_date, reason)
                if identifier.startswith("@"):
                    await set_warning_expiry(username=identifier[1:], expiry_time=until_date)
                else:
                    await set_warning_expiry(user_id=identifier, expiry_time=until_date)
                await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")

@dp.message(Command("unwarn"), F.chat.type == "private")
async def cmd_unwarn(message: Message, command: CommandObject):
    if message.from_user.id in ADMIN_ID:

        identifier = command.args
        
        if not identifier:
            await message.answer("Укажите аргументы: /unwarn <username/ID>")
            return
        
        if identifier.startswith("@") or identifier.isdigit():
            result = await unwarn_user_by_id_or_username(identifier)
            await message.answer(result)     
        else:
            await message.answer("Вы не указали корректный username или ID")

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