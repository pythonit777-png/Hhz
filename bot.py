import sqlite3
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties

# Настройки бота
BOT_TOKEN = "8373274074:AAHNwRWR88vshUmDS-WWIcYIPAWNQZLpf6M"
DATABASE_FILE = "subscriptions.db"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

class DatabaseManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    display_name TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_url TEXT NOT NULL,
                    is_private BOOLEAN NOT NULL,
                    original_input TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    expires_at TEXT,
                    duration TEXT,
                    hours INTEGER,
                    is_permanent BOOLEAN NOT NULL,
                    UNIQUE(chat_id, channel_id)
                )
            ''')
            conn.commit()
    
    def add_subscription(self, chat_id: int, display_name: str, channel_id: str, 
                        channel_url: str, is_private: bool, original_input: str,
                        expires_at: str = None, duration: str = None, 
                        hours: int = None, is_permanent: bool = False):
        """Добавляет подписку в базу данных"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO subscriptions 
                (chat_id, display_name, channel_id, channel_url, is_private, 
                 original_input, added_at, expires_at, duration, hours, is_permanent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, display_name, channel_id, channel_url, is_private,
                  original_input, datetime.now().isoformat(), expires_at, 
                  duration, hours, is_permanent))
            conn.commit()
    
    def remove_subscription(self, chat_id: int, channel_input: str):
        """Удаляет подписку из базу данных"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM subscriptions 
                WHERE chat_id = ? AND (original_input = ? OR channel_id = ?)
            ''', (chat_id, channel_input, channel_input))
            conn.commit()
    
    def get_active_subscriptions(self, chat_id: int):
        """Получает активные подписки для чата"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT display_name, channel_id, channel_url, is_private, 
                       original_input, expires_at, duration, hours, is_permanent
                FROM subscriptions 
                WHERE chat_id = ? AND (is_permanent = 1 OR expires_at > ? OR expires_at IS NULL)
            ''', (chat_id, datetime.now().isoformat()))
            
            rows = cursor.fetchall()
            subscriptions = []
            for row in rows:
                subscriptions.append({
                    'display_name': row[0],
                    'channel_id': row[1],
                    'channel_url': row[2],
                    'is_private': bool(row[3]),
                    'original_input': row[4],
                    'expires_at': row[5],
                    'duration': row[6],
                    'hours': row[7],
                    'is_permanent': bool(row[8])
                })
            return subscriptions
    
    def get_all_subscriptions(self, chat_id: int):
        """Получает все подписки для чата"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT display_name, channel_id, channel_url, is_private, 
                       original_input, expires_at, duration, hours, is_permanent
                FROM subscriptions 
                WHERE chat_id = ?
            ''', (chat_id,))
            
            rows = cursor.fetchall()
            subscriptions = []
            for row in rows:
                subscriptions.append({
                    'display_name': row[0],
                    'channel_id': row[1],
                    'channel_url': row[2],
                    'is_private': bool(row[3]),
                    'original_input': row[4],
                    'expires_at': row[5],
                    'duration': row[6],
                    'hours': row[7],
                    'is_permanent': bool(row[8])
                })
            return subscriptions
    
    def get_all_chats(self):
        """Получает список всех чатов с подписками"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT chat_id FROM subscriptions')
            return [row[0] for row in cursor.fetchall()]
    
    def cleanup_expired(self):
        """Очищает истекшие подписки"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM subscriptions 
                WHERE is_permanent = 0 AND expires_at <= ?
            ''', (datetime.now().isoformat(),))
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

class SubscriptionManager:
    def __init__(self, db_file):
        self.db = DatabaseManager(db_file)
    
    async def add_subscription(self, chat_id: int, channel_input: str, bot: Bot, duration: str = None):
        """Добавляет канал по юзернейму или ID"""
        channel_info = await self.get_channel_info(channel_input, bot)
        if not channel_info:
            return None
        
        # Парсим длительность
        hours = self.parse_duration(duration)
        expires_at = None if hours is None else (datetime.now() + timedelta(hours=hours)).isoformat()
        is_permanent = hours is None
        
        # Сохраняем в базу данных
        self.db.add_subscription(
            chat_id=chat_id,
            display_name=channel_info["display_name"],
            channel_id=channel_info["channel_id"],
            channel_url=channel_info["channel_url"],
            is_private=channel_info["is_private"],
            original_input=channel_info["original_input"],
            expires_at=expires_at,
            duration=duration,
            hours=hours,
            is_permanent=is_permanent
        )
        
        return {
            **channel_info,
            "expires_at": expires_at,
            "duration": duration,
            "hours": hours,
            "is_permanent": is_permanent
        }
    
    def parse_duration(self, duration: str):
        """Парсит длительность в часах"""
        if not duration:
            return None  # Навсегда
        
        # Убираем пробелы и приводим к нижнему регистру
        duration = duration.strip().lower()
        
        # Регулярное выражение для поиска чисел и единиц измерения
        match = re.match(r'^(\d+)([hd])$', duration)
        if not match:
            return None
        
        number = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'h':  # Часы
            return number
        elif unit == 'd':  # Дни
            return number * 24
        
        return None
    
    async def get_channel_info(self, channel_input: str, bot: Bot):
        """Получает информацию о канале"""
        try:
            # Если это ID приватного канала
            if channel_input.startswith('-100'):
                chat = await bot.get_chat(channel_input)
                # Создаем обычную инвайт-ссылку БЕЗ заявки
                invite_link = await bot.create_chat_invite_link(
                    chat_id=channel_input, 
                    name=f"Invite_{datetime.now().strftime('%H%M%S')}"
                )
                return {
                    "display_name": "chat",
                    "channel_id": channel_input,
                    "channel_url": invite_link.invite_link,
                    "is_private": True,
                    "original_input": channel_input
                }
            
            # Если это юзернейм
            if not channel_input.startswith('@'):
                channel_input = f"@{channel_input}"
            
            chat = await bot.get_chat(channel_input)
            return {
                "display_name": chat.username,
                "channel_id": str(chat.id),
                "channel_url": f"https://t.me/{chat.username}",
                "is_private": False,
                "original_input": channel_input
            }
            
        except Exception:
            return None
    
    def remove_subscription(self, chat_id: int, channel_input: str):
        """Удаляет подписку"""
        self.db.remove_subscription(chat_id, channel_input)
    
    def get_active_subscriptions(self, chat_id: int):
        """Получает активные подписки"""
        return self.db.get_active_subscriptions(chat_id)
    
    def get_all_subscriptions(self, chat_id: int):
        """Получает все подписки"""
        return self.db.get_all_subscriptions(chat_id)
    
    def get_chat_list(self):
        """Получает список чатов"""
        return self.db.get_all_chats()
    
    def cleanup_expired(self):
        """Очищает истекшие подписки"""
        return self.db.cleanup_expired()

# Инициализация менеджера подписок
sub_manager = SubscriptionManager(DATABASE_FILE)

def create_subscription_keyboard(subs):
    """Создает кнопки для подписки"""
    keyboard = []
    for i, sub in enumerate(subs, 1):
        button_text = f"Подписаться {i}"
        keyboard.append([InlineKeyboardButton(text=button_text, url=sub['channel_url'])])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_duration(hours):
    """Форматирует длительность в читаемый вид"""
    if hours is None:
        return "навсегда"
    
    if hours < 24:
        # Склонение для часов
        if hours == 1:
            return "1 час"
        elif 2 <= hours <= 4:
            return f"{hours} часа"
        else:
            return f"{hours} часов"
    else:
        days = hours // 24
        # Склонение для дней
        if days == 1:
            return "1 день"
        elif 2 <= days <= 4:
            return f"{days} дня"
        else:
            return f"{days} дней"

async def check_user_subscription(user_id: int, channel_id: str, bot: Bot) -> bool:
    """Проверяет подписку пользователя"""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def is_user_admin(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Проверяет, является ли пользователь администратором чата"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

async def check_subscriptions(message: Message):
    """Проверяет подписки и показывает сообщение с кнопками"""
    """Возвращает True если сообщение нужно удалить, False если нет"""
    chat_id = message.chat.id
    user = message.from_user
    
    # Админы могут писать без проверки подписок
    if await is_user_admin(chat_id, user.id, message.bot):
        return False
    
    active_subs = sub_manager.get_active_subscriptions(chat_id)
    
    if not active_subs:
        return False  # Не удаляем сообщение, т.к. нет подписок для проверки
    
    not_subscribed = []
    for sub in active_subs:
        if not await check_user_subscription(user.id, sub["channel_id"], message.bot):
            not_subscribed.append(sub)
    
    # Если пользователь подписан на все каналы - не удаляем сообщение
    if not not_subscribed:
        return False
    
    # Для приватных каналов создаем новую ссылку каждый раз (БЕЗ заявки)
    for sub in not_subscribed:
        if sub['is_private']:
            try:
                new_invite = await message.bot.create_chat_invite_link(
                    chat_id=sub["channel_id"],
                    name=f"Invite_{datetime.now().strftime('%H%M%S')}"
                )
                sub["channel_url"] = new_invite.invite_link
            except Exception:
                pass
    
    # Формируем сообщение с синим кликабельным ником
    user_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    
    message_text = f"<b>{user_link}</b>, чтобы писать в чат, необходимо подписаться на канал(ы):\n\n"
    
    channels_line = ""
    for sub in not_subscribed:
        if sub['is_private']:
            channels_line += f'<a href="{sub["channel_url"]}"><b>@chat</b></a> | '
        else:
            channels_line += f'<a href="{sub["channel_url"]}"><b>@{sub["display_name"]}</b></a> | '
    
    channels_line = channels_line.rstrip(" | ")
    message_text += f"{channels_line}"

    keyboard = create_subscription_keyboard(not_subscribed)
    
    await message.answer(
        message_text, 
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    
    return True  # Удаляем сообщение, т.к. пользователь не подписан

@router.message(CommandStart())
async def start_command(message: Message):
    """Команда /start"""
    await message.answer("Привет! Это бот для ОП для чатов. \nДля того чтобы ознакомиться с командами введите /help")
    await check_subscriptions(message)

@router.message(Command("help"))
async def help_command(message: Message):
    """Команда /help"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Если это личные сообщения с ботом - показываем полную справку
    if message.chat.type == ChatType.PRIVATE:
        help_text = """
🤖 <b>Бот для обязательных подписок</b>

Этот бот помогает настроить обязательные подписки на каналы в ваших чатах.

<b>Как использовать:</b>
1. Добавьте бота в группу или супергруппу
2. Сделайте бота администратором
3. Используйте команды для настройки подписок

<b>Команды для администраторов чата:</b>

<b>Добавление каналов:</b>
/setup @username - навсегда
/setup -1001234567890 - приватный канал навсегда
/setup @username 1h - на 1 час
/setup @username 24h - на 24 часа  
/setup @username 1d - на 1 день
/setup @username 7d - на 7 дней
/setup @username 30d - на 30 дней

<b>Управление:</b>
/unsetup @username - удалить канал
/listsubs - список подписок
/getchatid - получить ID чата
/cleanup - очистка истекших
/help - эта справка

<b>Формат времени:</b>
• 1h = 1 час
• 24h = 24 часа
• 1d = 1 день
• 7d = 7 дней

<b>Примечание:</b>
Для приватных каналов используйте ID канала (начинается с -100)
Бот автоматически создает инвайт-ссылки для приватных каналов
        """
        await message.answer(help_text)
        return
    
    # Если это группа/супергруппа - проверяем права администратора
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    help_text = """
🤖 <b>Команды для администраторов чата:</b>

<b>Добавление каналов:</b>
/setup @username - навсегда
/setup -1001234567890 - приватный канал навсегда
/setup @username 1h - на 1 час
/setup @username 24h - на 24 часа  
/setup @username 1d - на 1 день
/setup @username 7d - на 7 дней
/setup @username 30d - на 30 дней

<b>Управление:</b>
/unsetup @username - удалить канал
/listsubs - список подписок
/getchatid - получить ID чата
/cleanup - очистка истекших
/help - эта справка

<b>Формат времени:</b>
• 1h = 1 час
• 24h = 24 часа
• 1d = 1 день
• 7d = 7 дней
    """
    await message.answer(help_text)

# Используем фильтры Command для каждой команды отдельно
@router.message(Command("setup"))
async def setup_command(message: Message):
    """Добавление канала в обязательные подписки"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer(
            "Использование:\n"
            "/setup @username - навсегда\n"
            "/setup -1001234567890 - приватный канал\n"
            "/setup @username 1h - на 1 час\n"
            "/setup @username 1d - на 1 день\n"
            "/setup @username 7d - на 7 дней"
        )
        return
    
    channel_input = args[0]
    duration = args[1] if len(args) > 1 else None
    
    sub_info = await sub_manager.add_subscription(chat_id, channel_input, message.bot, duration)
    
    if not sub_info:
        await message.answer("❌ Не удалось добавить канал.")
        return
    
    duration_text = format_duration(sub_info['hours'])
    
    if sub_info['hours'] is None:
        response = f"✅ Канал добавлен {duration_text}"
    else:
        expires_at = datetime.fromisoformat(sub_info["expires_at"]).strftime("%d.%m.%Y %H:%M")
        response = f"✅ Канал добавлен на {duration_text} до {expires_at}"
    
    await message.answer(response)

@router.message(Command("unsetup"))
async def unsetup_command(message: Message):
    """Удаление канала из обязательных подписок"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer("Использование: /unsetup @username или /unsetup -1001234567890")
        return
    
    sub_manager.remove_subscription(chat_id, args[0])
    await message.answer("✅ Канал удален.")

@router.message(Command("listsubs"))
async def list_subscriptions_command(message: Message):
    """Показать список подписок"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    active_subs = sub_manager.get_active_subscriptions(chat_id)
    
    if not active_subs:
        await message.answer("📭 Нет подписок.")
        return
    
    response = "📋 <b>Активные подписки:</b>\n\n"
    for i, sub in enumerate(active_subs, 1):
        duration_text = format_duration(sub['hours'])
        channel_type = "🔒 Приватный" if sub['is_private'] else f"📢 Публичный (@{sub['display_name']})"
        
        if sub['hours'] is None:
            expires_text = "🔄 НАВСЕГДА"
        else:
            expires_at = datetime.fromisoformat(sub['expires_at']).strftime("%d.%m.%Y %H:%M")
            expires_text = f"⏰ до {expires_at}"
        
        response += f"{i}. {channel_type}\n"
        response += f"   📅 {duration_text}\n"
        response += f"   {expires_text}\n\n"
    
    await message.answer(response)

@router.message(Command("getchatid"))
async def get_chat_id_command(message: Message):
    """Получить ID чата"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    await message.answer(f"ID этого чата: <code>{chat_id}</code>")

@router.message(Command("cleanup"))
async def cleanup_command(message: Message):
    """Очистка истекших подписок"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_user_admin(chat_id, user_id, message.bot):
        await message.answer("❌ Эта команда доступна только администраторам чата.")
        return
    
    deleted_count = sub_manager.cleanup_expired()
    await message.answer(f"🧹 Очищено {deleted_count} истекших подписок.")

#@router.message(Command("chatlist"))
#async def chatlist_command(message: Message):
#    """Список чатов с подписками"""
#    chat_id = message.chat.id
#    user_id = message.from_user.id
#    
#    if not await is_user_admin(chat_id, user_id, message.bot):
#        await message.answer("❌ Эта команда доступна только администраторам чата.")
#        return
#    
#    chat_ids = sub_manager.get_chat_list()
#    
#    if not chat_ids:
#        await message.answer("📭 Нет чатов с подписками.")
#        return
#    
#    response = "📋 <b>Чаты с подписками:</b>\n\n"
#    for i, chat_id_item in enumerate(chat_ids, 1):
#        subs_count = len(sub_manager.get_all_subscriptions(chat_id_item))
#        response += f"{i}. Чат ID: <code>{chat_id_item}</code>\n"
#        response += f"   Подписок: {subs_count}\n\n"
#    
#    await message.answer(response)

@router.message()
async def handle_all_messages(message: Message):
    """Обработка всех сообщений"""
    # Пропускаем команды (они уже обработаны выше)
    if message.text and message.text.startswith('/'):
        return
    
    # Для обычных пользователей проверяем подписки
    should_delete = await check_subscriptions(message)
    
    # Удаляем сообщение только если пользователь НЕ подписан на все каналы
    if should_delete:
        try:
            await message.delete()
        except Exception:
            pass

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
