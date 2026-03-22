import logging
import sqlite3
import os
import html
import asyncio
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

# Определяем путь для базы данных
DATA_DIR = '/app/data'
DB_PATH = os.path.join(DATA_DIR, 'nicknames.db')

try:
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"✅ Используется постоянное хранилище: {DB_PATH}")
    test_file = os.path.join(DATA_DIR, 'test_write.tmp')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    logger.info(f"✅ Есть доступ на запись в {DATA_DIR}")
except Exception as e:
    logger.error(f"❌ Ошибка доступа к {DATA_DIR}: {e}")
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        tag TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Добавляем колонку tag если её нет (для совместимости)
                try:
                    conn.execute("ALTER TABLE users ADD COLUMN tag TEXT")
                    logger.info("✅ Добавлена колонка tag")
                except sqlite3.OperationalError:
                    pass
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id INTEGER,
                        action TEXT,
                        target_user_id INTEGER,
                        old_tag TEXT,
                        new_tag TEXT,
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
            cursor = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,)
            )
            exists = cursor.fetchone()
            
            if exists:
                conn.execute("""
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, 
                        is_active = 1, last_seen = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (username, first_name, last_name, user_id))
                logger.info(f"🔄 Обновлен пользователь {user_id}")
            else:
                conn.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, is_active)
                    VALUES (?, ?, ?, ?, 1)
                """, (user_id, username, first_name, last_name))
                logger.info(f"➕ Добавлен новый пользователь {user_id}")
    
    def set_tag(self, user_id, tag, admin_id=None):
        """Устанавливает тег пользователю"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT tag FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            old_tag = result[0] if result else None
            
            conn.execute("""
                UPDATE users 
                SET tag = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (tag, user_id))
            
            if admin_id:
                conn.execute("""
                    INSERT INTO admin_logs (admin_id, action, target_user_id, old_tag, new_tag)
                    VALUES (?, ?, ?, ?, ?)
                """, (admin_id, 'set_tag', user_id, old_tag, tag))
            
            logger.info(f"🏷️ Тег установлен для {user_id}: {tag}")
            return True
    
    def remove_tag(self, user_id, admin_id=None):
        """Удаляет тег пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT tag FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            old_tag = result[0] if result else None
            
            if old_tag:
                conn.execute("""
                    UPDATE users 
                    SET tag = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (user_id,))
                
                if admin_id:
                    conn.execute("""
                        INSERT INTO admin_logs (admin_id, action, target_user_id, old_tag)
                        VALUES (?, ?, ?)
                    """, (admin_id, 'remove_tag', user_id, old_tag))
                
                logger.info(f"🗑️ Тег удален у {user_id}")
                return True
            return False
    
    def get_user_by_username(self, username):
        """Ищет пользователя по username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, username, first_name, last_name, tag FROM users WHERE username = ? AND is_active = 1",
                (username.lower(),)
            )
            return cursor.fetchone()
    
    def get_user_by_id(self, user_id):
        """Получает пользователя по ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, username, first_name, last_name, tag FROM users WHERE user_id = ?",
                (user_id,)
            )
            return cursor.fetchone()
    
    def get_active_users(self):
        """Получает всех активных пользователей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_id, username, first_name, last_name, tag 
                FROM users 
                WHERE is_active = 1 
                ORDER BY 
                    CASE WHEN tag IS NOT NULL THEN 0 ELSE 1 END,
                    first_name
            """)
            return cursor.fetchall()
    
    def deactivate_user(self, user_id):
        """Помечает пользователя как неактивного"""
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
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE tag IS NOT NULL AND is_active = 1")
            with_tags = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 0")
            inactive = cursor.fetchone()[0]
            
            return {
                'total': total,
                'active': active,
                'with_tags': with_tags,
                'inactive': inactive
            }

db = NicknameDatabase()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def set_telegram_title(application, chat_id, user_id, title):
    """Устанавливает кастомное отображаемое имя в Telegram"""
    try:
        await application.bot.set_chat_member_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=title[:128]
        )
        logger.info(f"✅ Установлен тег для {user_id}: {title}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка установки тега для {user_id}: {e}")
        return False

async def remove_telegram_title(application, chat_id, user_id):
    """Удаляет кастомное отображаемое имя"""
    try:
        await application.bot.set_chat_member_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=""
        )
        logger.info(f"✅ Удален тег для {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления тега для {user_id}: {e}")
        return False

async def scan_topic_history(application, chat_id, topic_id, limit=5000):
    """Сканирует историю сообщений в топике"""
    try:
        count = 0
        added = 0
        offset_id = 0
        
        logger.info(f"🔍 Начинаю сканирование истории топика {topic_id}")
        
        while count < limit:
            try:
                messages = await application.bot.get_chat_history(
                    chat_id=chat_id,
                    limit=min(100, limit - count)
                )
            except Exception as e:
                logger.error(f"Ошибка при получении сообщений: {e}")
                break
            
            if not messages:
                break
            
            for msg in messages:
                if msg.message_thread_id != topic_id:
                    continue
                    
                count += 1
                user = msg.from_user
                
                if user and not user.is_bot:
                    db.update_user(
                        user_id=user.id,
                        username=user.username.lower() if user.username else None,
                        first_name=user.first_name or "",
                        last_name=user.last_name or ""
                    )
                    added += 1
            
            logger.info(f"📊 Обработано {count} сообщений, добавлено {added} пользователей")
            
            if messages:
                offset_id = messages[-1].message_id
            
            if len(messages) < 100:
                break
            
            await asyncio.sleep(0.5)
        
        return count, added
        
    except Exception as e:
        logger.error(f"❌ Ошибка сканирования: {e}")
        return 0, 0

async def show_users_list(message, application=None):
    """Показывает список всех активных пользователей с их тегами"""
    users = db.get_active_users()
    
    if not users:
        await message.reply_text(
            "📭 Список пользователей пуст. Используйте /scan_history для сбора участников.",
            parse_mode='HTML'
        )
        return
    
    response = "📋 <b>Активные участники:</b>\n\n"
    
    for i, (user_id, username, first_name, last_name, tag) in enumerate(users, 1):
        # Формируем имя
        if first_name and last_name:
            profile_name = f"{first_name} {last_name}"
        elif first_name:
            profile_name = first_name
        elif last_name:
            profile_name = last_name
        else:
            profile_name = f"Пользователь {user_id}"
        
        safe_name = html.escape(profile_name)
        
        if username:
            display = f"{safe_name} (@{html.escape(username)})"
        else:
            display = f"<a href='tg://user?id={user_id}'>{safe_name}</a>"
        
        if tag:
            safe_tag = html.escape(tag)
            response += f"{i}. {display} — <b>{safe_tag}</b>\n"
        else:
            response += f"{i}. {display} — (нет тега)\n"
    
    stats = db.get_stats()
    response += f"\n👥 <b>Всего:</b> {stats['active']} | <b>С тегами:</b> {stats['with_tags']}"
    
    await message.reply_text(response, parse_mode='HTML')
    logger.info(f"📊 Показан список ({len(users)} активных)")

# ==================== КОМАНДЫ ДЛЯ ВСЕХ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    await update.message.reply_text(
        "👋 <b>Привет! Я бот для управления тегами.</b>\n\n"
        "📋 <b>Команды:</b>\n"
        "• /list — показать список участников с тегами\n"
        "• /set_tag ВашТег — установить свой тег\n"
        "• /remove_tag — удалить свой тег\n"
        "• /help — справка\n\n"
        "✨ Также можно написать <b>\"Привет. Я твой_тег\"</b>",
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    await show_users_list(update.message, context.application)

async def set_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить свой тег"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Укажите тег. Пример: /set_tag СуперКодер")
        return
    
    tag = ' '.join(context.args).strip()
    
    if len(tag) > 50:
        await update.message.reply_text("❌ Тег слишком длинный (максимум 50 символов)")
        return
    
    if len(tag) < 2:
        await update.message.reply_text("❌ Тег слишком короткий (минимум 2 символа)")
        return
    
    db.set_tag(user.id, tag)
    success = await set_telegram_title(context.application, CHAT_ID, user.id, tag)
    
    if success:
        await update.message.reply_text(f"✅ Тег <b>{html.escape(tag)}</b> установлен!", parse_mode='HTML')
    else:
        await update.message.reply_text(
            f"✅ Тег сохранен в базе, но не применен в Telegram.\n"
            f"⚠️ Проверьте права бота (нужно 'Изменение тегов участников').",
            parse_mode='HTML'
        )

async def remove_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить свой тег"""
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    if db.remove_tag(user.id):
        await remove_telegram_title(context.application, CHAT_ID, user.id)
        await update.message.reply_text("✅ Твой тег удален.")
    else:
        await update.message.reply_text("❌ У тебя нет тега.")

# ==================== АДМИН-КОМАНДЫ ====================
async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    await update.message.reply_text(
        "🔐 <b>Админ-команды:</b>\n\n"
        "• /scan_history — собрать участников из истории\n"
        "• /set_tag_n N тег — установить тег по номеру в списке\n"
        "• /set_tag_user @username тег — установить тег по username\n"
        "• /set_tag_id ID тег — установить тег по ID\n"
        "• /remove_tag_n N — удалить тег по номеру\n"
        "• /remove_tag_user @username — удалить тег\n"
        "• /remove_tag_id ID — удалить тег\n"
        "• /sync_tags — синхронизировать все теги\n"
        "• /stats — статистика\n"
        "• /admin_help — это сообщение",
        parse_mode='HTML'
    )

async def set_tag_by_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить тег по номеру в списке /list"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /set_tag_n N тег")
        return
    
    try:
        num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер должен быть числом.")
        return
    
    tag = ' '.join(context.args[1:]).strip()
    
    users = db.get_active_users()
    if num < 1 or num > len(users):
        await update.message.reply_text(f"❌ Номер от 1 до {len(users)}")
        return
    
    user_id = users[num-1][0]
    db.set_tag(user_id, tag, update.effective_user.id)
    await set_telegram_title(context.application, CHAT_ID, user_id, tag)
    
    await update.message.reply_text(f"✅ Тег <b>{html.escape(tag)}</b> установлен для #{num}", parse_mode='HTML')

async def remove_tag_by_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить тег по номеру в списке"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /remove_tag_n N")
        return
    
    try:
        num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер должен быть числом.")
        return
    
    users = db.get_active_users()
    if num < 1 or num > len(users):
        await update.message.reply_text(f"❌ Номер от 1 до {len(users)}")
        return
    
    user_id = users[num-1][0]
    
    if db.remove_tag(user_id, update.effective_user.id):
        await remove_telegram_title(context.application, CHAT_ID, user_id)
        await update.message.reply_text(f"✅ Тег удален у #{num}")
    else:
        await update.message.reply_text(f"❌ У #{num} нет тега.")

async def set_tag_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить тег по username"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /set_tag_user @username тег")
        return
    
    username = context.args[0].lstrip('@').lower()
    tag = ' '.join(context.args[1:]).strip()
    
    user = db.get_user_by_username(username)
    if not user:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
        return
    
    db.set_tag(user[0], tag, update.effective_user.id)
    await set_telegram_title(context.application, CHAT_ID, user[0], tag)
    
    await update.message.reply_text(f"✅ Тег <b>{html.escape(tag)}</b> установлен для @{username}", parse_mode='HTML')

async def set_tag_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить тег по ID"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /set_tag_id ID тег")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    tag = ' '.join(context.args[1:]).strip()
    
    user = db.get_user_by_id(user_id)
    if not user:
        await update.message.reply_text(f"❌ Пользователь с ID {user_id} не найден.")
        return
    
    db.set_tag(user_id, tag, update.effective_user.id)
    await set_telegram_title(context.application, CHAT_ID, user_id, tag)
    
    await update.message.reply_text(f"✅ Тег <b>{html.escape(tag)}</b> установлен для ID: {user_id}", parse_mode='HTML')

async def remove_tag_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить тег по username"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /remove_tag_user @username")
        return
    
    username = context.args[0].lstrip('@').lower()
    user = db.get_user_by_username(username)
    
    if not user:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
        return
    
    if db.remove_tag(user[0], update.effective_user.id):
        await remove_telegram_title(context.application, CHAT_ID, user[0])
        await update.message.reply_text(f"✅ Тег удален у @{username}")
    else:
        await update.message.reply_text(f"❌ У @{username} нет тега.")

async def remove_tag_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить тег по ID"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /remove_tag_id ID")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    if db.remove_tag(user_id, update.effective_user.id):
        await remove_telegram_title(context.application, CHAT_ID, user_id)
        await update.message.reply_text(f"✅ Тег удален у ID: {user_id}")
    else:
        await update.message.reply_text(f"❌ У пользователя {user_id} нет тега.")

async def sync_tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Синхронизирует теги для всех пользователей"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    msg = await update.message.reply_text("🔄 Синхронизация тегов...")
    
    users = db.get_active_users()
    success_count = 0
    fail_count = 0
    
    for user_id, username, first_name, last_name, tag in users:
        if tag:
            if await set_telegram_title(context.application, CHAT_ID, user_id, tag):
                success_count += 1
            else:
                fail_count += 1
        await asyncio.sleep(0.3)
    
    await msg.edit_text(
        f"✅ <b>Синхронизация завершена!</b>\n\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Ошибок: {fail_count}\n"
        f"👥 Всего с тегами: {len([u for u in users if u[4]])}",
        parse_mode='HTML'
    )

async def scan_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сканирует историю"""
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    msg = await update.message.reply_text("📜 Сканирую историю...")
    
    total_msgs, added_users = await scan_topic_history(
        context.application, CHAT_ID, TOPIC_ID, limit=5000
    )
    
    stats = db.get_stats()
    await msg.edit_text(
        f"✅ <b>Сканирование завершено!</b>\n\n"
        f"📨 Просмотрено: {total_msgs} сообщений\n"
        f"👥 Добавлено: {added_users} пользователей\n"
        f"📊 Всего в базе: {stats['total']}\n"
        f"✅ Активных: {stats['active']}\n"
        f"🏷️ С тегами: {stats['with_tags']}",
        parse_mode='HTML'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 <b>Статистика:</b>\n\n"
        f"👥 Всего: {stats['total']}\n"
        f"✅ Активных: {stats['active']}\n"
        f"🏷️ С тегами: {stats['with_tags']}\n"
        f"👋 Покинули: {stats['inactive']}\n"
        f"📁 Файл: {DB_PATH}",
        parse_mode='HTML'
    )

# ==================== ОБРАБОТЧИКИ ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    message = update.message
    user = update.effective_user
    text = message.text
    
    if text and text.startswith('/'):
        return
    
    db.update_user(
        user_id=user.id,
        username=user.username.lower() if user.username else None,
        first_name=user.first_name or "",
        last_name=user.last_name or ""
    )
    
    if text and text.startswith("Привет. Я "):
        tag = text.replace("Привет. Я ", "").strip()
        
        if tag and 2 <= len(tag) <= 50:
            db.set_tag(user.id, tag)
            await set_telegram_title(context.application, CHAT_ID, user.id, tag)
            await message.reply_text(f"✅ Привет, <b>{html.escape(tag)}</b>!", parse_mode='HTML')
            await show_users_list(message, context.application)
            return

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.id != CHAT_ID:
        return
    
    if message.left_chat_member:
        left_user = message.left_chat_member
        db.deactivate_user(left_user.id)
        
        user_data = db.get_user_by_id(left_user.id)
        tag = user_data[4] if user_data else None
        
        if tag:
            await message.chat.send_message(
                f"👋 <b>{html.escape(tag)}</b> покинул группу",
                message_thread_id=TOPIC_ID,
                parse_mode='HTML'
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Ошибка: {context.error}")

# ==================== ГЛАВНАЯ ====================
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    chat_filter = filters.Chat(chat_id=CHAT_ID)
    
    # Команды для всех
    application.add_handler(CommandHandler("start", start_command, filters=chat_filter))
    application.add_handler(CommandHandler("help", help_command, filters=chat_filter))
    application.add_handler(CommandHandler("list", list_command, filters=chat_filter))
    application.add_handler(CommandHandler("set_tag", set_tag_command, filters=chat_filter))
    application.add_handler(CommandHandler("remove_tag", remove_tag_command, filters=chat_filter))
    
    # Админ-команды
    application.add_handler(CommandHandler("admin_help", admin_help_command, filters=chat_filter))
    application.add_handler(CommandHandler("scan_history", scan_history_command, filters=chat_filter))
    application.add_handler(CommandHandler("set_tag_n", set_tag_by_number_command, filters=chat_filter))
    application.add_handler(CommandHandler("set_tag_user", set_tag_user_command, filters=chat_filter))
    application.add_handler(CommandHandler("set_tag_id", set_tag_id_command, filters=chat_filter))
    application.add_handler(CommandHandler("remove_tag_n", remove_tag_by_number_command, filters=chat_filter))
    application.add_handler(CommandHandler("remove_tag_user", remove_tag_user_command, filters=chat_filter))
    application.add_handler(CommandHandler("remove_tag_id", remove_tag_id_command, filters=chat_filter))
    application.add_handler(CommandHandler("sync_tags", sync_tags_command, filters=chat_filter))
    application.add_handler(CommandHandler("stats", stats_command, filters=chat_filter))
    
    application.add_handler(
        MessageHandler(chat_filter & filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(
        MessageHandler(
            filters.Chat(chat_id=CHAT_ID) & filters.StatusUpdate.LEFT_CHAT_MEMBER,
            handle_left_member
        )
    )
    
    application.add_error_handler(error_handler)
    
    logger.info("=" * 50)
    logger.info("🚀 Бот для тегов запущен!")
    logger.info(f"📁 База: {DB_PATH}")
    logger.info(f"👤 Админ: {ADMIN_IDS}")
    logger.info(f"💬 Чат: {CHAT_ID}, Топик: {TOPIC_ID}")
    logger.info("🏷️ Режим: управление тегами (отображаемыми именами)")
    logger.info("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
