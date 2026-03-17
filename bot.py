import logging
import sqlite3
import os
import html
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8606821173:AAHDM_tM89RbEvFD5skzfnPDXQhVm1TVDPM"
TOPIC_ID = 4
CHAT_ID = -1003300908374
ADMIN_IDS = [639212691]  # ID админа

# Определяем путь для базы данных (приоритет: /data на BotHost)
if os.path.exists('/data'):
    DB_PATH = '/data/nicknames.db'
    logger.info(f"✅ Используется постоянное хранилище: {DB_PATH}")
    # Создаем директорию /data если её нет (хотя она должна существовать)
    os.makedirs('/data', exist_ok=True)
else:
    DB_PATH = 'nicknames.db'
    logger.info(f"⚠️ Используется локальное хранилище: {DB_PATH}")
    # Для локального файла директория не требуется

# Проверяем, можем ли писать в выбранное место
try:
    # Получаем директорию для записи
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:  # Если директория указана (не пустая)
        os.makedirs(db_dir, exist_ok=True)
        test_file = os.path.join(db_dir, 'test_write.tmp')
    else:  # Если файл в текущей директории
        test_file = 'test_write.tmp'
    
    # Пробуем создать тестовый файл
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    logger.info(f"✅ Есть доступ на запись в {db_dir or 'текущую директорию'}")
except Exception as e:
    logger.error(f"❌ Нет доступа на запись: {e}")
    # В крайнем случае используем текущую директорию
    DB_PATH = 'nicknames.db'
    logger.info(f"⚠️ Переключено на локальное хранилище: {DB_PATH}")

# ==================== КЛАСС ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ ====================
class NicknameDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Таблица пользователей
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        nickname TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица для логов действий админа
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id INTEGER,
                        action TEXT,
                        target_user_id INTEGER,
                        old_nickname TEXT,
                        new_nickname TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                logger.info(f"✅ База данных инициализирована в {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации БД: {e}")
            raise
    
    def update_user(self, user_id, username, first_name, last_name):
        """Обновляет или добавляет пользователя при активности"""
        with sqlite3.connect(self.db_path) as conn:
            # Проверяем, существует ли пользователь
            cursor = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,)
            )
            exists = cursor.fetchone()
            
            if exists:
                # Обновляем существующего
                conn.execute("""
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, 
                        is_active = 1, last_seen = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (username, first_name, last_name, user_id))
                logger.info(f"🔄 Обновлен пользователь {user_id}")
            else:
                # Добавляем нового
                conn.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, is_active)
                    VALUES (?, ?, ?, ?, 1)
                """, (user_id, username, first_name, last_name))
                logger.info(f"➕ Добавлен новый пользователь {user_id}")
    
    def set_nickname(self, user_id, nickname, admin_id=None):
        """Устанавливает никнейм пользователю"""
        with sqlite3.connect(self.db_path) as conn:
            # Получаем старый никнейм для лога
            cursor = conn.execute(
                "SELECT nickname FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            old_nickname = result[0] if result else None
            
            # Обновляем никнейм
            conn.execute("""
                UPDATE users 
                SET nickname = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (nickname, user_id))
            
            # Логируем действие админа
            if admin_id:
                conn.execute("""
                    INSERT INTO admin_logs (admin_id, action, target_user_id, old_nickname, new_nickname)
                    VALUES (?, ?, ?, ?, ?)
                """, (admin_id, 'set_nickname', user_id, old_nickname, nickname))
            
            logger.info(f"🏷️ Никнейм установлен для {user_id}: {nickname}")
            return True
    
    def remove_nickname(self, user_id, admin_id=None):
        """Удаляет никнейм пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            # Получаем старый никнейм для лога
            cursor = conn.execute(
                "SELECT nickname FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            old_nickname = result[0] if result else None
            
            if old_nickname:
                conn.execute("""
                    UPDATE users 
                    SET nickname = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (user_id,))
                
                # Логируем действие админа
                if admin_id:
                    conn.execute("""
                        INSERT INTO admin_logs (admin_id, action, target_user_id, old_nickname)
                        VALUES (?, ?, ?, ?)
                    """, (admin_id, 'remove_nickname', user_id, old_nickname))
                
                logger.info(f"🗑️ Никнейм удален у {user_id}")
                return True
            return False
    
    def get_user_by_username(self, username):
        """Ищет пользователя по username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, username, first_name, last_name, nickname FROM users WHERE username = ? AND is_active = 1",
                (username.lower(),)
            )
            return cursor.fetchone()
    
    def get_user_by_id(self, user_id):
        """Получает пользователя по ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, username, first_name, last_name, nickname FROM users WHERE user_id = ?",
                (user_id,)
            )
            return cursor.fetchone()
    
    def get_active_users(self):
        """Получает всех активных пользователей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_id, username, first_name, last_name, nickname 
                FROM users 
                WHERE is_active = 1 
                ORDER BY 
                    CASE WHEN nickname IS NOT NULL THEN 0 ELSE 1 END,
                    first_name
            """)
            return cursor.fetchall()
    
    def deactivate_user(self, user_id):
        """Помечает пользователя как неактивного (вышел из группы)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE users 
                SET is_active = 0 
                WHERE user_id = ?
            """, (user_id,))
            logger.info(f"👋 Пользователь {user_id} помечен как неактивный")
    
    def get_stats(self):
        """Возвращает статистику по базе"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            active = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE nickname IS NOT NULL AND is_active = 1")
            with_nicknames = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE nickname IS NULL AND is_active = 1")
            without_nicknames = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 0")
            inactive = cursor.fetchone()[0]
            
            return {
                'total': total,
                'active': active,
                'with_nicknames': with_nicknames,
                'without_nicknames': without_nicknames,
                'inactive': inactive
            }

# Создаем экземпляр базы данных
db = NicknameDatabase()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id in ADMIN_IDS

async def show_users_list(message):
    """Показывает список всех активных пользователей"""
    users = db.get_active_users()
    
    if not users:
        await message.reply_text(
            "📭 Список пользователей пуст. Напишите что-нибудь в чат, чтобы появиться в списке!",
            parse_mode='HTML'
        )
        return
    
    # Формируем сообщение со списком
    response = "📋 <b>Активные участники:</b>\n\n"
    
    for i, (user_id, username, first_name, last_name, nickname) in enumerate(users, 1):
        # Формируем имя для отображения
        if first_name and last_name:
            profile_name = f"{first_name} {last_name}"
        elif first_name:
            profile_name = first_name
        elif last_name:
            profile_name = last_name
        else:
            profile_name = f"Пользователь {user_id}"
        
        safe_profile_name = html.escape(profile_name)
        
        # Создаем кликабельную ссылку
        if username:
            # Если есть username - показываем @username
            user_display = f"@{html.escape(username)}"
        else:
            # Если нет username - ссылка на профиль
            user_display = f"<a href='tg://user?id={user_id}'>{safe_profile_name}</a>"
        
        # Добавляем никнейм если есть
        if nickname:
            safe_nickname = html.escape(nickname)
            response += f"{i}. {user_display} — <i>{safe_nickname}</i>\n"
        else:
            response += f"{i}. {user_display} — (нет никнейма)\n"
    
    # Добавляем статистику
    stats = db.get_stats()
    response += f"\n👥 <b>Всего:</b> {stats['active']} | "
    response += f"<b>С никнеймами:</b> {stats['with_nicknames']}"
    
    await message.reply_text(response, parse_mode='HTML')
    logger.info(f"📊 Показан список пользователей ({len(users)} активных)")

# ==================== КОМАНДЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 <b>Привет! Я бот для хранения никнеймов.</b>\n\n"
        "📋 <b>Команды для всех:</b>\n"
        "• /list — показать список всех участников\n"
        "• /greate_name ВашНик — задать свой никнейм\n"
        "• /edit_name НовыйНик — изменить свой никнейм\n"
        "• /remove_name — удалить свой никнейм\n"
        "• /help — показать это сообщение\n\n"
        "✨ Также можно написать <b>\"Привет. Я твой_никнейм\"</b> "
        "и я автоматически сохраню его!",
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await start_command(update, context)

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    await show_users_list(update.message)

async def greate_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Задать свой никнейм"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите никнейм после команды.\nПример: /greate_name СуперКодер"
        )
        return
    
    nickname = ' '.join(context.args).strip()
    
    if len(nickname) > 50:
        await update.message.reply_text("❌ Никнейм слишком длинный (максимум 50 символов)")
        return
    
    if len(nickname) < 2:
        await update.message.reply_text("❌ Никнейм слишком короткий (минимум 2 символа)")
        return
    
    # Сохраняем никнейм
    db.set_nickname(user.id, nickname)
    
    await update.message.reply_text(
        f"✅ Никнейм успешно сохранен! Теперь ты <b>{html.escape(nickname)}</b>",
        parse_mode='HTML'
    )

async def edit_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить свой никнейм"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите новый никнейм.\nПример: /edit_name НовыйНик"
        )
        return
    
    nickname = ' '.join(context.args).strip()
    
    if len(nickname) > 50:
        await update.message.reply_text("❌ Никнейм слишком длинный (максимум 50 символов)")
        return
    
    if len(nickname) < 2:
        await update.message.reply_text("❌ Никнейм слишком короткий (минимум 2 символа)")
        return
    
    # Проверяем, есть ли у пользователя никнейм
    user_data = db.get_user_by_id(user.id)
    if not user_data or not user_data[4]:
        await update.message.reply_text(
            "❌ У тебя еще нет никнейма. Используй /greate_name для создания."
        )
        return
    
    # Обновляем никнейм
    db.set_nickname(user.id, nickname)
    
    await update.message.reply_text(
        f"✅ Никнейм изменен! Теперь ты <b>{html.escape(nickname)}</b>",
        parse_mode='HTML'
    )

async def remove_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить свой никнейм"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    if db.remove_nickname(user.id):
        await update.message.reply_text("✅ Твой никнейм удален.")
    else:
        await update.message.reply_text("❌ У тебя нет никнейма для удаления.")

# ==================== АДМИН-КОМАНДЫ ====================
async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по админ-командам"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    await update.message.reply_text(
        "🔐 <b>Админ-команды:</b>\n\n"
        "• /set_nick @username Ник — установить никнейм пользователю\n"
        "• /set_nick_id ID Ник — установить никнейм по ID\n"
        "• /remove_nick @username — удалить никнейм\n"
        "• /remove_nick_id ID — удалить никнейм по ID\n"
        "• /stats — статистика по базе\n"
        "• /admin_help — это сообщение",
        parse_mode='HTML'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    stats = db.get_stats()
    
    response = (
        "📊 <b>Статистика базы данных:</b>\n\n"
        f"👥 <b>Всего в базе:</b> {stats['total']}\n"
        f"✅ <b>Активных:</b> {stats['active']}\n"
        f"📝 <b>С никнеймами:</b> {stats['with_nicknames']}\n"
        f"❌ <b>Без никнеймов:</b> {stats['without_nicknames']}\n"
        f"👋 <b>Покинули группу:</b> {stats['inactive']}\n\n"
        f"📁 <b>Файл БД:</b> {DB_PATH}"
    )
    
    await update.message.reply_text(response, parse_mode='HTML')

async def set_nick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить никнейм пользователю по @username"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /set_nick @username Никнейм"
        )
        return
    
    username = context.args[0].lstrip('@').lower()
    nickname = ' '.join(context.args[1:]).strip()
    
    # Ищем пользователя в базе
    user = db.get_user_by_username(username)
    
    if not user:
        await update.message.reply_text(
            f"❌ Пользователь @{username} не найден в базе. "
            "Он должен хотя бы раз написать в чат."
        )
        return
    
    user_id, db_username, first_name, last_name, old_nick = user
    
    # Устанавливаем никнейм
    db.set_nickname(user_id, nickname, update.effective_user.id)
    
    await update.message.reply_text(
        f"✅ Никнейм <b>{html.escape(nickname)}</b> установлен для @{username}",
        parse_mode='HTML'
    )

async def set_nick_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить никнейм пользователю по ID"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /set_nick_id ID Никнейм"
        )
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    nickname = ' '.join(context.args[1:]).strip()
    
    # Проверяем, есть ли пользователь в базе
    user = db.get_user_by_id(user_id)
    
    if not user:
        await update.message.reply_text(
            f"❌ Пользователь с ID {user_id} не найден в базе."
        )
        return
    
    # Устанавливаем никнейм
    db.set_nickname(user_id, nickname, update.effective_user.id)
    
    await update.message.reply_text(
        f"✅ Никнейм <b>{html.escape(nickname)}</b> установлен для ID: {user_id}",
        parse_mode='HTML'
    )

async def remove_nick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить никнейм пользователя по @username"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /remove_nick @username"
        )
        return
    
    username = context.args[0].lstrip('@').lower()
    
    user = db.get_user_by_username(username)
    
    if not user:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
        return
    
    user_id = user[0]
    
    if db.remove_nickname(user_id, update.effective_user.id):
        await update.message.reply_text(f"✅ Никнейм удален у @{username}")
    else:
        await update.message.reply_text(f"❌ У @{username} нет никнейма.")

async def remove_nick_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить никнейм пользователя по ID"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда только для администраторов.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /remove_nick_id ID"
        )
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    if db.remove_nickname(user_id, update.effective_user.id):
        await update.message.reply_text(f"✅ Никнейм удален у ID: {user_id}")
    else:
        await update.message.reply_text(f"❌ У пользователя {user_id} нет никнейма.")

# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных сообщений"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    message = update.message
    user = update.effective_user
    text = message.text
    
    # Игнорируем команды
    if text and text.startswith('/'):
        return
    
    # Обновляем/добавляем пользователя в базу
    db.update_user(
        user_id=user.id,
        username=user.username.lower() if user.username else None,
        first_name=user.first_name or "",
        last_name=user.last_name or ""
    )
    
    # Проверяем формат "Привет. Я <никнейм>"
    if text and text.startswith("Привет. Я "):
        nickname = text.replace("Привет. Я ", "").strip()
        
        if nickname and 2 <= len(nickname) <= 50:
            # Сохраняем никнейм
            db.set_nickname(user.id, nickname)
            
            # Подтверждаем сохранение
            await message.reply_text(
                f"✅ Привет, <b>{html.escape(nickname)}</b>! Твой никнейм сохранен.",
                parse_mode='HTML'
            )
            
            # Показываем список
            await show_users_list(message)
            return
    
    # Напоминание для незарегистрированных
    user_data = db.get_user_by_id(user.id)
    if not user_data or not user_data[4]:  # нет никнейма
        await message.reply_text(
            "👋 Кстати, ты еще не задал себе никнейм!\n"
            "Напиши <b>\"Привет. Я твой_никнейм\"</b> или используй /greate_name",
            parse_mode='HTML'
        )

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выхода пользователя из группы"""
    message = update.message
    
    if not message or message.chat.id != CHAT_ID:
        return
    
    if message.left_chat_member:
        left_user = message.left_chat_member
        db.deactivate_user(left_user.id)
        
        # Получаем информацию о пользователе для уведомления
        user_data = db.get_user_by_id(left_user.id)
        nickname = user_data[4] if user_data else None
        
        if nickname:
            await message.chat.send_message(
                f"👋 <b>{html.escape(nickname)}</b> покинул группу",
                message_thread_id=TOPIC_ID,
                parse_mode='HTML'
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}")

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    """Запуск бота"""
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Фильтр для нужного чата
    chat_filter = filters.Chat(chat_id=CHAT_ID)
    
    # ===== Команды для всех =====
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("greate_name", greate_name_command))
    application.add_handler(CommandHandler("edit_name", edit_name_command))
    application.add_handler(CommandHandler("remove_name", remove_name_command))
    
    # ===== Админ-команды =====
    application.add_handler(CommandHandler("admin_help", admin_help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("set_nick", set_nick_command))
    application.add_handler(CommandHandler("set_nick_id", set_nick_id_command))
    application.add_handler(CommandHandler("remove_nick", remove_nick_command))
    application.add_handler(CommandHandler("remove_nick_id", remove_nick_id_command))
    
    # ===== Обработчики сообщений =====
    application.add_handler(
        MessageHandler(chat_filter & filters.TEXT & ~filters.COMMAND, handle_message)
    )
    
    # ===== Обработчик выхода =====
    application.add_handler(
        MessageHandler(
            chat_filter & filters.StatusUpdate.LEFT_CHAT_MEMBER,
            handle_left_member
        )
    )
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Информация о запуске
    logger.info("=" * 50)
    logger.info("🚀 Бот для никнеймов запущен!")
    logger.info(f"📁 База данных: {DB_PATH}")
    logger.info(f"👤 Админ ID: {ADMIN_IDS}")
    logger.info(f"💬 Чат ID: {CHAT_ID}")
    logger.info(f"📌 Топик ID: {TOPIC_ID}")
    logger.info("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
