import os
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")

application = Application.builder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    referrer_id = args[0] if args else None
    print(f"/start вызван с args: {args}, referrer_id: {referrer_id}")
    web_app_url = 'https://dubnacoin.ru/'
    if referrer_id:
        web_app_url += f'?start_param={referrer_id}'
    print(f"Web App URL: {web_app_url}")
    keyboard = [
        [InlineKeyboardButton(text='Открыть DubnaCoin', web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Добро пожаловать! Нажмите кнопку ниже, чтобы открыть приложение.',
        reply_markup=reply_markup
    )

application.add_handler(CommandHandler('start', start))

if __name__ == '__main__':
    print("Запуск Telegram-бота...")
    application.run_polling()
