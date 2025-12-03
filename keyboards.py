from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

cmd_start_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="Выдать придупреждение", callback_data="warn"),
           InlineKeyboardButton(text="Снять придупреждение", callback_data="unwarn")],
          [InlineKeyboardButton(text="Мут пользователя", callback_data="mute"),
           InlineKeyboardButton(text="Размут пользователя", callback_data="unmute")],
            [InlineKeyboardButton(text="Забанить пользователя", callback_data="ban"),
           InlineKeyboardButton(text="Разбанить пользователя", callback_data="unban")],
          [InlineKeyboardButton(text="Чёрный список", callback_data="black_list")],
          [InlineKeyboardButton(text="<<", callback_data="to_cmds")]
      ]
  )

cmds_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text=">>", callback_data="to_btns")]
      ]
  )

cmd_start_kb_for_user = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="Мои дела", callback_data="cases"),]
          ]
  )

apil_message_button = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Подать апелляцию", url="https://t.me/TheRulerAndTheJudgeBot")]])
