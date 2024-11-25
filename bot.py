import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),  
        logging.StreamHandler()          
    ]
)


application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    referrer_id = args[0] if args else None
    user_id = update.effective_user.id
    logging.info(f"/start вызван с args: {args}, referrer_id: {referrer_id}, user_id: {user_id}")
    if referrer_id:
        cursor.execute('''
            INSERT INTO Friends (User_id, Friend_id)
            VALUES (?, ?)
        ''', (referrer_id, user_id))
        connection.commit()
    web_app_url = 'https://dubnacoin.ru/'
    if referrer_id:
        web_app_url += f'?start_param={referrer_id}'
    logging.info(f"Web App URL: {web_app_url}")

    keyboard = [
        [InlineKeyboardButton(text='Открыть DubnaCoin', web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = await update.message.reply_text(
        'Добро пожаловать! Нажмите кнопку ниже, чтобы открыть приложение.',
        reply_markup=reply_markup
    )
    logging.info(f"Сообщение отправлено: {message.to_dict()}")


application.add_handler(CommandHandler('start', start))

if __name__ == '__main__':
    print("Запуск Telegram-бота...")
    application.run_polling()
