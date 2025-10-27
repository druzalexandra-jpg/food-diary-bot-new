import os
import re
import json
import gspread
from google.oauth2 import service_account
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# === Настройки ===
BOT_TOKEN = os.environ['BOT_TOKEN']
CREDENTIALS_JSON = os.environ['GOOGLE_CREDENTIALS_JSON']
SHEET_URL = os.environ['GOOGLE_SHEET_URL']

# === Подключение к Google Sheets ===
def get_worksheet():
    creds_dict = json.loads(CREDENTIALS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).sheet1
    return sheet

# === Поиск КБЖУ в Open Food Facts ===
def get_nutrition(product_name):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        'search_terms': product_name,
        'search_simple': 1,
        'json': 1,
        'page_size': 1
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        if data['products']:
            p = data['products'][0]
            nutriments = p.get('nutriments', {})
            return {
                'kcal': round(nutriments.get('energy-kcal', 0)),
                'proteins': round(nutriments.get('proteins', 0), 1),
                'fats': round(nutriments.get('fat', 0), 1),
                'carbs': round(nutriments.get('carbohydrates', 0), 1)
            }
    except Exception as e:
        print("Ошибка поиска:", e)
    return {'kcal': 0, 'proteins': 0, 'fats': 0, 'carbs': 0}

# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    
    # Парсинг: "овсянка 40г" или "яйцо 2 шт"
    match = re.search(r'([а-яa-z\s\-]+?)\s*(\d+)\s*(г|шт|ml|мл)', text)
    if not match:
        await update.message.reply_text("Напиши, пожалуйста, в формате: *продукт весг* (например, овсянка 40г)", parse_mode="Markdown")
        return

    product = match.group(1).strip()
    amount = int(match.group(2))
    unit = match.group(3)

    # Получаем данные по продукту
    nutr = get_nutrition(product)

    # Запись в таблицу
    try:
        sheet = get_worksheet()
        from datetime import datetime
        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            product,
            amount,
            nutr['kcal'],
            nutr['proteins'],
            nutr['fats'],
            nutr['carbs']
        ]
        sheet.append_row(row)
        await update.message.reply_text(
            f"✅ Записал: *{product} {amount}{unit}*\n"
            f"КБЖУ: {nutr['kcal']} ккал | Б: {nutr['proteins']}г | Ж: {nutr['fats']}г | У: {nutr['carbs']}г",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка записи: {str(e)}")

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой дневник питания 🍽️\n"
        "Просто пиши, что ешь: *овсянка 40г*, *курица 150г*, *яблоко 1 шт*\n"
        "В конце дня напиши /итог — подведу баланс!",
        parse_mode="Markdown"
    )

# === Команда /summary ===
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Скоро будет анализ за день! Пока просто записываю всё в таблицу.")

# === Запуск бота ===
if __name__ == '__main__':
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("summary", summary))  # ← Исправлено!
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен!")
    app.run_polling()
