import os
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")

# Создание экземпляра приложения бота
application = Application.builder().token(BOT_TOKEN).build()

# Асинхронный обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    web_app_url = 'https://dubnacoin.ru/'  # Замените на URL вашего веб-приложения
    keyboard = [
        [InlineKeyboardButton(text='Открыть DubnaCoin', web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Добро пожаловать! Нажмите кнопку ниже, чтобы открыть приложение.', reply_markup=reply_markup)

# Регистрация обработчика команды /start
application.add_handler(CommandHandler('start', start))

if __name__ == '__main__':
    print("Запуск Telegram-бота...")
    application.run_polling()
