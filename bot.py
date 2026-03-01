import os
import sqlite3
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("posts.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    run_date TEXT,
    button_text TEXT,
    button_url TEXT
)
""")
conn.commit()


async def send_post(context: ContextTypes.DEFAULT_TYPE):
    post_id = context.job.data
    cursor.execute("SELECT text, button_text, button_url FROM posts WHERE id=?", (post_id,))
    row = cursor.fetchone()

    if not row:
        return

    text, button_text, button_url = row

    if button_text and button_url:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(button_text, url=button_url)]
        ])
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text
        )

    cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()


def restore_jobs(app):
    now = datetime.now()
    cursor.execute("SELECT id, run_date FROM posts")
    rows = cursor.fetchall()

    for post_id, run_date_str in rows:
        run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")
        if run_date > now:
            app.job_queue.run_once(send_post, run_date, data=post_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат:\n\n"
        "01.03.2026 22:30\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка"
    )


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=CHANNEL_ID, text="✅ Тестовое сообщение")
    await update.message.reply_text("Отправлено.")


async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        lines = text.split("\n")
        run_date = datetime.strptime(lines[0].strip(), "%d.%m.%Y %H:%M")

        if run_date <= datetime.now():
            await update.message.reply_text("Дата должна быть в будущем.")
            return

        button_text = None
        button_url = None

        if "КНОПКА:" in text:
            content, button_line = text.split("КНОПКА:")
            post_text = content.split("\n", 1)[1].strip()
            btn = button_line.strip().split("|")
            if len(btn) == 2:
                button_text = btn[0].strip()
                button_url = btn[1].strip()
        else:
            post_text = text.split("\n", 1)[1].strip()

        cursor.execute(
            "INSERT INTO posts (text, run_date, button_text, button_url) VALUES (?, ?, ?, ?)",
            (post_text, run_date.strftime("%Y-%m-%d %H:%M:%S"), button_text, button_url),
        )
        conn.commit()

        post_id = cursor.lastrowid
        context.job_queue.run_once(send_post, run_date, data=post_id)

        await update.message.reply_text("✅ Запланировано.")

    except:
        await update.message.reply_text("Ошибка формата.")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    restore_jobs(app)

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
    )


if __name__ == "__main__":
    main()
