import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования - ИСПРАВЛЕНО: asctime, а не asime
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8606821173:AAHDM_tM89RbEvFD5skzfnPDXQhVm1TVDPM"
TOPIC_ID = 5108  # ID топика
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений в топике"""
    
    # Проверяем, что сообщение из нужного чата
    if update.effective_chat.id != CHAT_ID:
        return
    
    # Проверяем, что сообщение из нужного топика
    if update.effective_message.message_thread_id != TOPIC_ID:
        return
    
    message = update.message
    if not message:
        return
        
    user = update.effective_user
    if not user:
        return
        
    text = message.text
    
    logger.info(f"Сообщение в топике от {user.id}: {text}")
    
    # Обработка команды регистрации
    if text and text.startswith("Привет. Я "):
        nickname = text.replace("Привет. Я ", "").strip()
        
        if nickname:
            # Сохраняем никнейм
            db.save_nickname(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name or "",
                nickname=nickname
            )
            
            # Получаем всех пользователей и показываем список
            all_nicknames = db.get_all_nicknames()
            response = "📋 **Список всех никнеймов:**\n\n"
            
            for uid, username, first_name, last_name, nick, created_at in all_nicknames:
                # Формируем информацию о пользователе
                if username:
                    user_info = f"@{username}"
                else:
                    full_name = f"{first_name} {last_name}".strip()
                    user_info = full_name if full_name else f"ID: {uid}"
                
                # Добавляем в список
                response += f"• **{user_info}**: {nick}\n"
            
            response += f"\n👥 **Всего пользователей:** {len(all_nicknames)}"
            
            await message.reply_text(response, parse_mode='Markdown')
            logger.info(f"Зарегистрирован новый пользователь: {nickname}")
    
    # Обработка обычных сообщений (не команд и не регистрация)
    elif text and not text.startswith("/") and not text.startswith("Привет. Я "):
        saved_nickname = db.get_nickname(user.id)
        
        if saved_nickname:
            try:
                # Пытаемся удалить оригинальное сообщение
                await message.delete()
                
                # Отправляем новое с никнеймом
                new_text = f"<b>{saved_nickname}</b>:\n{text}"
                await message.chat.send_message(
                    text=new_text,
                    message_thread_id=TOPIC_ID,
                    parse_mode='HTML'
                )
                logger.info(f"Заменено сообщение от {user.id} на никнейм {saved_nickname}")
                
            except Exception as e:
                logger.error(f"Ошибка при замене сообщения: {e}")
                # Если не удалось удалить, просто отвечаем
                await message.reply_text(
                    f"⚠️ {saved_nickname}, у бота нет прав удалять сообщения. "
                    "Пожалуйста, дайте мне права администратора с возможностью удалять сообщения."
                )
        else:
            # Если пользователь не зарегистрирован
            await message.reply_text(
                "👋 Привет! Чтобы я мог запомнить твой никнейм, напиши 'Привет. Я твой_никнейм'"
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
    
    # Обработчик для всех текстовых сообщений
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
    logger.info(f"Токен бота: {BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}")
    logger.info("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
