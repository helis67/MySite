import os
import asyncio
import sqlite3
import random
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

# ==================== КОНФИГ ====================
BOT_TOKEN = "2202254922:AAEDdDrPhvvy2cwVbcQcKXuBiE843R9qf9M/test"  # ВСТАВЬ СВОЙ ТОКЕН
ADMIN_USERNAME = "xid3r"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
# ... дальше весь код как был

# Хранилище игр
games: Dict[int, Dict] = {}

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('mafia.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            games INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            diamonds INTEGER DEFAULT 0,
            vip BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id: int, username: str = None):
    conn = sqlite3.connect('mafia.db')
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    if not user:
        cur.execute('INSERT INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
        conn.commit()
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
    conn.close()
    return {'user_id': user[0], 'username': user[1], 'games': user[2], 'wins': user[3], 'diamonds': user[4], 'vip': bool(user[5])}

def update_user(user_id: int, username: str = None, games: int = None, wins: int = None, diamonds: int = None, vip: bool = None):
    conn = sqlite3.connect('mafia.db')
    cur = conn.cursor()
    if games is not None:
        cur.execute('UPDATE users SET games = ? WHERE user_id = ?', (games, user_id))
    if wins is not None:
        cur.execute('UPDATE users SET wins = ? WHERE user_id = ?', (wins, user_id))
    if diamonds is not None:
        cur.execute('UPDATE users SET diamonds = ? WHERE user_id = ?', (diamonds, user_id))
    if vip is not None:
        cur.execute('UPDATE users SET vip = ? WHERE user_id = ?', (vip, user_id))
    if username:
        cur.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    conn.commit()
    conn.close()

def add_diamonds(user_id: int, amount: int):
    user = get_user(user_id, None)
    update_user(user_id, None, diamonds=user['diamonds'] + amount)

def get_user_mention(user_id: int, username: str = None) -> str:
    user = get_user(user_id, username)
    vip = "👑 " if user['vip'] else ""
    name = user['username'] or f"User{user_id}"
    return f"{vip}<a href='tg://user?id={user_id}'>{name}</a>"

def mention(user_id: int) -> str:
    return f"<a href='tg://user?id={user_id}'>игрок</a>"

# ==================== ЛОГИКА ИГРЫ ====================
def is_user_alive(game: Dict, user_id: int) -> bool:
    return game['alive'].get(user_id, False)

def get_alive_players(game: Dict) -> List[int]:
    return [uid for uid in game['players'] if game['alive'][uid]]

def check_winner(game: Dict) -> Optional[str]:
    alive_roles = [game['roles'][uid] for uid in game['players'] if game['alive'][uid]]
    mafia_alive = any(r == 'mafia' for r in alive_roles)
    civilians_alive = any(r in ('civilian', 'doctor', 'commissioner') for r in alive_roles)
    
    if not mafia_alive:
        return 'civilians'
    if not civilians_alive:
        return 'mafia'
    return None

async def end_game(chat_id: int, game_id: int, winner: str):
    game = games[game_id]
    
    if winner == 'civilians':
        text = "🏆 Мирные жители победили!"
        winning_roles = ('civilian', 'doctor', 'commissioner')
    else:
        text = "🔪 Мафия победила!"
        winning_roles = ('mafia',)
    
    for uid in game['players']:
        user = get_user(uid, None)
        role = game['roles'][uid]
        if role in winning_roles:
            add_diamonds(uid, 10)
            update_user(uid, None, wins=user['wins'] + 1, games=user['games'] + 1)
        else:
            update_user(uid, None, games=user['games'] + 1)
    
    roles_text = "\n".join([f"{get_user_mention(uid)} — {game['roles'][uid]}" for uid in game['players']])
    await bot.send_message(chat_id, f"{text}\n\n📋 Все роли:\n{roles_text}", parse_mode=ParseMode.HTML)
    
    del games[game_id]

# ==================== НОЧЬ ====================
async def start_night(game_id: int):
    game = games[game_id]
    chat_id = game['chat_id']
    
    game['phase'] = 'night'
    game['mafia_kill_target'] = None
    game['doctor_save_target'] = None
    game['commissioner_check_target'] = None
    
    await bot.send_message(chat_id, "🌙 Наступила ночь. Мафия, доктор и комиссар просыпаются.")
    
    mafia_ids = [uid for uid in game['players'] if game['roles'][uid] == 'mafia' and game['alive'][uid]]
    if mafia_ids:
        alive_players = get_alive_players(game)
        keyboard = InlineKeyboardMarkup(row_width=2)
        for uid in alive_players:
            if uid not in mafia_ids:
                keyboard.add(InlineKeyboardButton(text=get_user_mention(uid, None), callback_data=f"night_kill_{uid}"))
        for mafia_id in mafia_ids:
            try:
                await bot.send_message(mafia_id, "🔪 Кого убить?", reply_markup=keyboard, parse_mode=ParseMode.HTML)
            except:
                pass
    
    doctor_ids = [uid for uid in game['players'] if game['roles'][uid] == 'doctor' and game['alive'][uid]]
    if doctor_ids:
        alive_players = get_alive_players(game)
        keyboard = InlineKeyboardMarkup(row_width=2)
        for uid in alive_players:
            keyboard.add(InlineKeyboardButton(text=get_user_mention(uid, None), callback_data=f"night_save_{uid}"))
        keyboard.add(InlineKeyboardButton(text="❌ Никого", callback_data="night_save_none"))
        for doctor_id in doctor_ids:
            try:
                await bot.send_message(doctor_id, "💊 Кого спасти?", reply_markup=keyboard, parse_mode=ParseMode.HTML)
            except:
                pass
    
    com_ids = [uid for uid in game['players'] if game['roles'][uid] == 'commissioner' and game['alive'][uid]]
    if com_ids:
        alive_players = get_alive_players(game)
        keyboard = InlineKeyboardMarkup(row_width=2)
        for uid in alive_players:
            keyboard.add(InlineKeyboardButton(text=get_user_mention(uid, None), callback_data=f"night_check_{uid}"))
        for com_id in com_ids:
            try:
                await bot.send_message(com_id, "🔍 Кого проверить?", reply_markup=keyboard, parse_mode=ParseMode.HTML)
            except:
                pass
    
    await asyncio.sleep(30)
    await finish_night(game_id)

async def finish_night(game_id: int):
    game = games[game_id]
    if game['phase'] != 'night':
        return
    
    chat_id = game['chat_id']
    killed = game['mafia_kill_target']
    saved = game['doctor_save_target']
    
    if game['commissioner_check_target']:
        target = game['commissioner_check_target']
        role = game['roles'][target]
        is_mafia = role == 'mafia'
        com_ids = [uid for uid in game['players'] if game['roles'][uid] == 'commissioner' and game['alive'][uid]]
        for com_id in com_ids:
            try:
                if is_mafia:
                    await bot.send_message(com_id, f"🔍 {mention(target)} - МАФИЯ!", parse_mode=ParseMode.HTML)
                else:
                    await bot.send_message(com_id, f"🔍 {mention(target)} - МИРНЫЙ", parse_mode=ParseMode.HTML)
            except:
                pass
    
    night_killed = None
    if killed and killed != saved:
        night_killed = killed
        game['alive'][killed] = False
    
    game['night_killed'] = night_killed
    await start_day(game_id)

# ==================== ДЕНЬ ====================
async def start_day(game_id: int):
    game = games[game_id]
    chat_id = game['chat_id']
    killed = game.get('night_killed')
    
    if killed:
        await bot.send_message(chat_id, f"☠️ Ночью убит {mention(killed)}", parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(chat_id, "🕊️ Ночь прошла спокойно, никто не умер.")
    
    winner = check_winner(game)
    if winner:
        await end_game(chat_id, game_id, winner)
        return
    
    game['phase'] = 'day'
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳️ Начать голосование", callback_data="start_vote")]
    ])
    await bot.send_message(chat_id, "🌞 Наступил день. Обсуждайте, затем начните голосование.", reply_markup=keyboard)

async def start_vote(callback: CallbackQuery):
    game_id = callback.message.chat.id
    game = games.get(game_id)
    
    if not game or game['phase'] != 'day':
        await callback.answer("Сейчас нельзя голосовать!", show_alert=True)
        return
    
    if not is_user_alive(game, callback.from_user.id):
        await callback.answer("Вы мертвы!", show_alert=True)
        return
    
    game['phase'] = 'vote'
    game['votes'] = {}
    
    alive_players = get_alive_players(game)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for uid in alive_players:
        keyboard.add(InlineKeyboardButton(text=get_user_mention(uid, None), callback_data=f"vote_{uid}"))
    keyboard.add(InlineKeyboardButton(text="❌ Пропустить", callback_data="vote_skip"))
    
    await callback.message.delete()
    vote_msg = await bot.send_message(game['chat_id'], "🗳️ Голосование! Кого выгоняем?", reply_markup=keyboard, parse_mode=ParseMode.HTML)
    game['vote_message_id'] = vote_msg.message_id
    
    await asyncio.sleep(30)
    if game.get('phase') == 'vote':
        await finish_vote(game_id)

async def finish_vote(game_id: int):
    game = games[game_id]
    if game['phase'] != 'vote':
        return
    
    chat_id = game['chat_id']
    
    try:
        await bot.delete_message(chat_id, game['vote_message_id'])
    except:
        pass
    
    votes = game['votes']
    if not votes:
        await bot.send_message(chat_id, "❌ Никто не голосовал. Переход к ночи.")
        game['phase'] = 'night'
        await start_night(game_id)
        return
    
    vote_counts = {}
    for target in votes.values():
        if target is not None:
            vote_counts[target] = vote_counts.get(target, 0) + 1
    
    if not vote_counts:
        await bot.send_message(chat_id, "Все проголосовали за пропуск. Переход к ночи.")
        game['phase'] = 'night'
        await start_night(game_id)
        return
    
    max_votes = max(vote_counts.values())
    candidates = [uid for uid, cnt in vote_counts.items() if cnt == max_votes]
    
    if len(candidates) > 1:
        await bot.send_message(chat_id, f"🤝 Ничья между {len(candidates)} игроками. Никто не вылетает.")
        game['phase'] = 'night'
        await start_night(game_id)
        return
    
    eliminated = candidates[0]
    await bot.send_message(chat_id, f"⚖️ Вылетает {mention(eliminated)}!", parse_mode=ParseMode.HTML)
    
    game['phase'] = 'last_words'
    msg = await bot.send_message(chat_id, f"💬 {mention(eliminated)}, последнее слово (30 сек):", parse_mode=ParseMode.HTML)
    game['last_words_message_id'] = msg.message_id
    
    await asyncio.sleep(30)
    
    game['alive'][eliminated] = False
    await bot.send_message(chat_id, f"💀 {mention(eliminated)} покидает игру.", parse_mode=ParseMode.HTML)
    
    winner = check_winner(game)
    if winner:
        await end_game(chat_id, game_id, winner)
        return
    
    game['phase'] = 'night'
    await start_night(game_id)

# ==================== СТАРТ ИГРЫ ====================
async def start_game(chat_id: int, game_id: int):
    game = games[game_id]
    players = game['players']
    random.shuffle(players)
    
    n = len(players)
    if n >= 6:
        roles = ['mafia', 'mafia', 'doctor', 'commissioner'] + ['civilian'] * (n - 4)
    else:
        roles = ['civilian'] * n
    
    random.shuffle(roles)
    
    game['roles'] = {players[i]: roles[i] for i in range(n)}
    game['alive'] = {uid: True for uid in players}
    
    role_names = {
        'mafia': '🔪 Мафия',
        'doctor': '🩺 Доктор',
        'commissioner': '🕵️ Комиссар',
        'civilian': '👨 Мирный житель'
    }
    
    for uid, role in game['roles'].items():
        try:
            await bot.send_message(uid, f"Твоя роль: {role_names[role]}")
        except:
            pass
    
    await bot.send_message(chat_id, f"🎮 Игра началась! Игроков: {n}\nРоли в ЛС.")
    await start_night(game_id)

# ==================== КОМАНДЫ ====================
@dp.message(Command("mafia"))
async def cmd_mafia(message: Message):
    chat_id = message.chat.id
    
    if chat_id in games:
        await message.reply("Игра уже идёт!")
        return
    
    games[chat_id] = {
        'chat_id': chat_id,
        'players': [message.from_user.id],
        'roles': {},
        'alive': {},
        'phase': 'lobby',
        'mafia_kill_target': None,
        'doctor_save_target': None,
        'commissioner_check_target': None,
        'votes': {},
        'night_killed': None
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Присоединиться", callback_data="join_game")],
        [InlineKeyboardButton(text="▶️ Старт", callback_data="force_start")]
    ])
    
    await message.reply(f"🎲 Лобби. Игроков: 1\nАвтостарт через 30 сек (мин. 6)", reply_markup=keyboard)
    
    await asyncio.sleep(30)
    if chat_id in games and games[chat_id]['phase'] == 'lobby':
        if len(games[chat_id]['players']) >= 6:
            await start_game(chat_id, chat_id)
        else:
            await bot.send_message(chat_id, f"❌ Не хватает игроков ({len(games[chat_id]['players'])}/6). Лобби закрыто.")
            del games[chat_id]

@dp.callback_query(lambda c: c.data == "join_game")
async def join_game(callback: CallbackQuery):
    game_id = callback.message.chat.id
    game = games.get(game_id)
    
    if not game or game['phase'] != 'lobby':
        await callback.answer("Лобби закрыто!")
        return
    
    if callback.from_user.id in game['players']:
        await callback.answer("Вы уже в игре!")
        return
    
    game['players'].append(callback.from_user.id)
    await callback.message.edit_text(f"🎲 Лобби. Игроков: {len(game['players'])}\nАвтостарт через 30 сек (мин. 6)", reply_markup=callback.message.reply_markup)
    await callback.answer("Присоединились!")

@dp.callback_query(lambda c: c.data == "force_start")
async def force_start(callback: CallbackQuery):
    game_id = callback.message.chat.id
    game = games.get(game_id)
    
    if not game or game['phase'] != 'lobby':
        await callback.answer("Игра уже начата!")
        return
    
    if len(game['players']) < 6:
        await callback.answer(f"Нужно 6 игроков (сейчас {len(game['players'])})", show_alert=True)
        return
    
    await start_game(game_id, game_id)
    await callback.answer("Старт!")

@dp.callback_query(lambda c: c.data.startswith("night_"))
async def night_action(callback: CallbackQuery):
    game_id = callback.message.chat.id
    game = games.get(game_id)
    
    if not game or game['phase'] != 'night':
        await callback.answer("Сейчас не ночь!")
        return
    
    parts = callback.data.split('_')
    action = parts[1]
    target = parts[2] if len(parts) > 2 else None
    
    if action == 'kill':
        if game['roles'].get(callback.from_user.id) != 'mafia':
            await callback.answer("Вы не мафия!")
            return
        game['mafia_kill_target'] = int(target)
        await callback.answer("Цель выбрана!")
        await callback.message.delete()
    
    elif action == 'save':
        if game['roles'].get(callback.from_user.id) != 'doctor':
            await callback.answer("Вы не доктор!")
            return
        game['doctor_save_target'] = int(target) if target != 'none' else None
        await callback.answer("Цель спасения выбрана!")
        await callback.message.delete()
    
    elif action == 'check':
        if game['roles'].get(callback.from_user.id) != 'commissioner':
            await callback.answer("Вы не комиссар!")
            return
        game['commissioner_check_target'] = int(target)
        await callback.answer("Проверка начата!")
        await callback.message.delete()

@dp.callback_query(lambda c: c.data == "start_vote")
async def start_vote_callback(callback: CallbackQuery):
    await start_vote(callback)

@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def vote_callback(callback: CallbackQuery):
    game_id = callback.message.chat.id
    game = games.get(game_id)
    
    if not game or game['phase'] != 'vote':
        await callback.answer("Голосование не активно!")
        return
    
    if not is_user_alive(game, callback.from_user.id):
        await callback.answer("Вы мертвы!", show_alert=True)
        return
    
    if callback.data == "vote_skip":
        game['votes'][callback.from_user.id] = None
        await callback.answer("Пропуск")
    else:
        target = int(callback.data.split('_')[1])
        if not is_user_alive(game, target):
            await callback.answer("Этот игрок мёртв!", show_alert=True)
            return
        game['votes'][callback.from_user.id] = target
        await callback.answer("Голос принят!")
    
    await callback.message.delete()
    
    alive_count = len(get_alive_players(game))
    if len(game['votes']) >= alive_count:
        await finish_vote(game_id)

# ==================== ПРОФИЛЬ ====================
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    vip_status = "✅" if user['vip'] else "❌"
    text = f"👤 Профиль {get_user_mention(message.from_user.id, message.from_user.username)}\n\n"
    text += f"📊 Игр: {user['games']}\n"
    text += f"🏆 Побед: {user['wins']}\n"
    text += f"💎 Алмазов: {user['diamonds']}\n"
    text += f"👑 VIP: {vip_status}"
    await message.reply(text, parse_mode=ParseMode.HTML)

@dp.message(Command("shop"))
async def cmd_shop(message: Message):
    text = "🛒 Магазин\n\n👑 VIP статус — 500💎\nДает 👑 возле имени\n\n/buy vip"
    await message.reply(text)

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    args = message.text.split()
    if len(args) != 2 or args[1] != 'vip':
        await message.reply("Использование: /buy vip")
        return
    
    user = get_user(message.from_user.id, message.from_user.username)
    if user['diamonds'] >= 500:
        if user['vip']:
            await message.reply("VIP уже есть!")
            return
        update_user(message.from_user.id, None, diamonds=user['diamonds'] - 500, vip=True)
        await message.reply("👑 Вы купили VIP!")
    else:
        await message.reply(f"❌ Нужно 500 алмазов, у вас {user['diamonds']}")

@dp.message(Command("give"))
async def cmd_give(message: Message):
    if message.from_user.username != ADMIN_USERNAME:
        await message.reply("Нет прав!")
        return
    
    args = message.text.split()
    if len(args) != 3:
        await message.reply("Использование: /give @username количество")
        return
    
    username = args[1].lstrip('@')
    amount = int(args[2])
    
    conn = sqlite3.connect('mafia.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users WHERE username = ?', (username,))
    user = cur.fetchone()
    conn.close()
    
    if user:
        add_diamonds(user[0], amount)
        await message.reply(f"✅ Выдано {amount} алмазов @{username}")
    else:
        await message.reply("❌ Пользователь не найден")

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.reply("pong! Бот работает на Railway ✅")

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    print("🤖 Бот Мафия запущен на Railway!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
