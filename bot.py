import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8606821173:AAHDM_tM89RbEvFD5skzfnPDXQhVm1TVDPM"
TOPIC_ID = 4  # ID топика из ссылки
CHAT_ID = -1003300908374  # ID чата

class NicknameDatabase:
    def __init__(self, db_path="nicknames.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nicknames (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    nickname TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("База данных инициализирована")
    
    def save_nickname(self, user_id, username, first_name, last_name, nickname):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO nicknames (user_id, username, first_name, last_name, nickname)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, nickname))
            logger.info(f"Сохранен никнейм для user_id {user_id}: {nickname}")
            return True
    
    def get_nickname(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT nickname FROM nicknames WHERE user_id = ?", 
                (user_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_all_nicknames(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_id, username, first_name, last_name, nickname, created_at 
                FROM nicknames 
                ORDER BY created_at DESC
            """)
            return cursor.fetchall()
    
    def delete_user(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM nicknames WHERE user_id = ? RETURNING nickname",
                (user_id,)
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Удален пользователь {user_id} с никнеймом {result[0]}")
                return result[0]
            return None

# Создаем экземпляр базы данных
db = NicknameDatabase()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Привет! Я бот для хранения никнеймов.\n\n"
        "📋 **Доступные команды:**\n"
        "• `/list_name` - показать список всех никнеймов\n"
        "• `/greate_name ВашНик` - задать свой никнейм\n"
        "• `/help` - показать это сообщение\n\n"
        "✨ Также ты можешь написать **\"Привет. Я твой_никнейм\"** "
        "и я автоматически сохраню его и покажу весь список!",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await start_command(update, context)

async def list_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list_name - показывает список всех никнеймов"""
    
    # Проверяем, что команда из нужного чата и топика
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    await show_nicknames_list(update.message)

async def greate_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /greate_name - задает никнейм пользователю"""
    
    # Проверяем, что команда из нужного чата и топика
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    user = update.effective_user
    
    # Проверяем, указан ли никнейм в команде
    if not context.args:
        await update.message.reply_text(
            "❌ Пожалуйста, укажите никнейм после команды.\n"
            "Пример: `/greate_name СуперКодер`",
            parse_mode='Markdown'
        )
        return
    
    # Объединяем аргументы в один никнейм
    nickname = ' '.join(context.args).strip()
    
    # Проверяем длину никнейма
    if len(nickname) > 50:
        await update.message.reply_text("❌ Никнейм слишком длинный (максимум 50 символов)")
        return
    
    if len(nickname) < 2:
        await update.message.reply_text("❌ Никнейм слишком короткий (минимум 2 символа)")
        return
    
    # Сохраняем никнейм
    db.save_nickname(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name or "",
        nickname=nickname
    )
    
    await update.message.reply_text(
        f"✅ Никнейм успешно сохранен!\n"
        f"Теперь ты **{nickname}**",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.id} установил никнейм: {nickname}")

async def show_nicknames_list(message):
    """Вспомогательная функция для показа списка никнеймов"""
    all_nicknames = db.get_all_nicknames()
    
    if not all_nicknames:
        await message.reply_text(
            "📭 Список никнеймов пуст. Будь первым!\n"
            "Используй `/greate_name ВашНик` или напиши **\"Привет. Я твой_никнейм\"**",
            parse_mode='Markdown'
        )
        return
    
    # Формируем сообщение со списком
    response = "📋 **Список всех никнеймов:**\n\n"
    
    for i, (uid, username, first_name, last_name, nick, created_at) in enumerate(all_nicknames, 1):
        # Формируем информацию о пользователе
        if username:
            user_info = f"@{username}"
        else:
            full_name = f"{first_name} {last_name}".strip()
            user_info = full_name if full_name else f"ID: {uid}"
        
        # Добавляем в список
        response += f"{i}. **{user_info}** → *{nick}*\n"
    
    response += f"\n👥 **Всего пользователей:** {len(all_nicknames)}"
    
    await message.reply_text(response, parse_mode='Markdown')
    logger.info(f"Показан список никнеймов ({len(all_nicknames)} записей)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных сообщений (не команд)"""
    
    # Проверяем, что сообщение из нужного чата и топика
    if update.effective_chat.id != CHAT_ID or update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    message = update.message
    user = update.effective_user
    text = message.text
    
    # Игнорируем команды (они обрабатываются отдельно)
    if text and text.startswith('/'):
        return
    
    # 🔥 НОВОЕ: Проверяем формат "Привет. Я <никнейм>"
    if text and text.startswith("Привет. Я "):
        nickname = text.replace("Привет. Я ", "").strip()
        
        if nickname:
            # Проверяем длину никнейма
            if len(nickname) > 50:
                await message.reply_text("❌ Никнейм слишком длинный (максимум 50 символов)")
                return
            if len(nickname) < 2:
                await message.reply_text("❌ Никнейм слишком короткий (минимум 2 символа)")
                return
            
            # Сохраняем никнейм
            db.save_nickname(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name or "",
                nickname=nickname
            )
            
            # Подтверждаем сохранение
            await message.reply_text(
                f"✅ Привет, **{nickname}**! Твой никнейм сохранен.",
                parse_mode='Markdown'
            )
            
            # Показываем весь список никнеймов
            await show_nicknames_list(message)
            
            logger.info(f"Пользователь {user.id} зарегистрировался через фразу: {nickname}")
            return
    
    # Для остальных обычных сообщений
    logger.info(f"Обычное сообщение от {user.id} в топике: {text}")
    
    # Напоминание для незарегистрированных
    if not db.get_nickname(user.id):
        await message.reply_text(
            "👋 Кстати, ты еще не задал себе никнейм!\n"
            "Напиши **\"Привет. Я твой_никнейм\"** или используй команду `/greate_name ТвойНик`",
            parse_mode='Markdown'
        )

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выхода пользователя из группы"""
    message = update.message
    
    if not message or message.chat.id != CHAT_ID:
        return
    
    if message.left_chat_member:
        left_user = message.left_chat_member
        deleted_nickname = db.delete_user(left_user.id)
        
        if deleted_nickname:
            logger.info(f"Пользователь {deleted_nickname} покинул группу")
            # Отправляем уведомление в топик
            await message.chat.send_message(
                f"👋 **{deleted_nickname}** покинул группу и удален из списка",
                message_thread_id=TOPIC_ID,
                parse_mode='Markdown'
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция"""
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Фильтр для нужного чата
    chat_filter = filters.Chat(chat_id=CHAT_ID)
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list_name", list_name_command))
    application.add_handler(CommandHandler("greate_name", greate_name_command))
    
    # Обработчик для обычных сообщений (включая фразу "Привет. Я ...")
    application.add_handler(
        MessageHandler(
            chat_filter & filters.TEXT & ~filters.COMMAND, 
            handle_message
        )
    )
    
    # Обработчик для событий выхода из группы
    application.add_handler(
        MessageHandler(
            chat_filter & filters.StatusUpdate.LEFT_CHAT_MEMBER,
            handle_left_member
        )
    )
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Информация о запуске
    logger.info("=" * 50)
    logger.info("Бот успешно запущен!")
    logger.info(f"Чат ID: {CHAT_ID}")
    logger.info(f"Топик ID: {TOPIC_ID}")
    logger.info("Доступные команды: /start, /help, /list_name, /greate_name")
    logger.info("Также поддерживается фраза: 'Привет. Я никнейм'")
    logger.info("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
