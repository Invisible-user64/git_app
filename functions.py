import json
import re

# Функция для загрузки пользователей из JSON (теперь с дополнительными данными)
def load_users():
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}  # Если файл не найден, возвращаем пустой словарь
    
# Функция для сохранения пользователей в JSON
def save_users(users):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

# Функция для загрузки черного списка из JSON
def load_blacklist():
    try:
        with open('black_list.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}  # Если файл не найден, возвращаем пустой словарь

# Функция для сохранения черного списка в JSON
def save_blacklist(blacklist):
    with open('black_list.json', 'w', encoding='utf-8') as f:
        json.dump(blacklist, f, ensure_ascii=False, indent=4)


time_designation = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Функция для парсинга времени
def parse_time(time_str: str) -> int:
    """
    Парсит строку времени в формате Nt (например, 1h, 30m) и возвращает секунды.
    Если строка пустая или '0', возвращает 0 (постоянный бан).
    """
    if not time_str.strip() or time_str.strip() == '0':
        return 0
    match = re.match(r'^(\d+)([smhd])$', time_str.strip().lower())
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        return num * time_designation.get(unit, 1)
    return 0  # Если формат неверный, считаем постоянным

# Функция для форматирования времени в читаемый вид
def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        return f"{seconds // 60} мин"
    elif seconds < 86400:
        return f"{seconds // 3600} ч"
    else:
        return f"{seconds // 86400} д"
    
# Исправленная функция: ID извлекается из JSON (без API)
def get_user_id_by_username_in_group(username: str) -> int | None:
    """
    Получить ID пользователя по username из JSON.
    """
    users = load_users()
    user_data = users.get(username)
    if user_data and isinstance(user_data, dict):
        user_id = user_data.get("id")
        if user_id:
            print(f"ID найден в JSON: @{username} -> {user_id}")
            return user_id
    print(f"ID не найден в JSON для @{username}")
    return None
