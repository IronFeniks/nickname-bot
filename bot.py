import logging
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация - ЗАМЕНИТЕ НА СВОИ ЗНАЧЕНИЯ
BOT_TOKEN = "8606821173:AAHDM_tM89RbEvFD5skzfnPDXQhVm1TVDPM"  # Ваш токен
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

db = NicknameDatabase()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.effective_chat.id != CHAT_ID or 
        update.effective_message.message_thread_id != TOPIC_ID):
        return
    
    message = update.message
    user = update.effective_user
    text = message.text
    
    logger.info(f"Сообщение в топике от {user.id}: {text}")
    
    if text and text.startswith("Привет. Я "):
        nickname = text.replace("Привет. Я ", "").strip()
        
        if nickname:
            db.save_nickname(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name or "",
                nickname=nickname
            )
            
            all_nicknames = db.get_all_nicknames()
            response = "📋 **Список никнеймов:**\n\n"
            for uid, username, first_name, last_name, nick, _ in all_nicknames:
                if username:
                    user_info = f"@{username}"
                else:
                    full_name = f"{first_name} {last_name}".strip()
                    user_info = full_name if full_name else f"ID: {uid}"
                response += f"• **{user_info}**: {nick}\n"
            
            response += f"\nВсего: {len(all_nicknames)} пользователей"
            await message.reply_text(response, parse_mode='Markdown')
    
    else:
        saved_nickname = db.get_nickname(user.id)
        
        if saved_nickname:
            try:
                await message.delete()
                
                if text:
                    new_text = f"<b>{saved_nickname}</b>:\n{text}"
                elif message.caption:
                    new_text = f"<b>{saved_nickname}</b>:\n{message.caption}"
                else:
                    new_text = f"<b>{saved_nickname}</b>:"
                
                if message.photo:
                    await message.chat.send_photo(
                        photo=message.photo[-1].file_id,
                        caption=new_text,
                        message_thread_id=TOPIC_ID,
                        parse_mode='HTML'
                    )
                elif message.video:
                    await message.chat.send_video(
                        video=message.video.file_id,
                        caption=new_text,
                        message_thread_id=TOPIC_ID,
                        parse_mode='HTML'
                    )
                elif message.text or not message:
                    await message.chat.send_message(
                        text=new_text,
                        message_thread_id=TOPIC_ID,
                        parse_mode='HTML'
                    )
                    
                logger.info(f"Заменено имя на {saved_nickname}")
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        else:
            if text and not text.startswith("Привет. Я "):
                await message.reply_text(
                    "👋 Напиши 'Привет. Я твой_никнейм' чтобы я запомнил тебя"
                )

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if message.chat.id != CHAT_ID:
        return
    
    if message.left_chat_member:
        left_user = message.left_chat_member
        deleted_nickname = db.delete_user(left_user.id)
        
        if deleted_nickname:
            logger.info(f"Пользователь {deleted_nickname} покинул группу")
            await message.chat.send_message(
                f"👋 **{deleted_nickname}** покинул группу и удален из списка",
                message_thread_id=TOPIC_ID,
                parse_mode='Markdown'
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    chat_filter = filters.Chat(chat_id=CHAT_ID)
    topic_filter = filters.Message(message_thread_id=TOPIC_ID)
    
    application.add_handler(
        MessageHandler(chat_filter & topic_filter, handle_message)
    )
    
    application.add_handler(
        MessageHandler(
            filters.Chat(chat_id=CHAT_ID) & filters.StatusUpdate.LEFT_CHAT_MEMBER,
            handle_left_member
        )
    )
    
    application.add_error_handler(error_handler)
    
    logger.info("Бот запущен...")
    logger.info(f"Чат ID: {CHAT_ID}, Топик ID: {TOPIC_ID}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
