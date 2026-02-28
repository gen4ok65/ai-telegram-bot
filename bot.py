import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.environ["TOKEN"]
HANNEL_ID = os.getenv("CHANNEL_ID")

logging.basicConfig(level=logging.INFO)

# база данных
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

scheduler = AsyncIOScheduler()

async def send_post(context: ContextTypes.DEFAULT_TYPE):
    post_id = context.job.data

    cursor.execute("SELECT text, button_text, button_url FROM posts WHERE id=?", (post_id,))
    row = cursor.fetchone()

    if row:
        text, button_text, button_url = row

        if button_text and button_url:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(button_text, url=button_url)]
            ])
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, reply_markup=keyboard)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text)

        cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат:\n\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка\n\n"
        "/list — список\n"
        "/delete ID — удалить"
    )

async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        lines = text.split("\n")
        date_line = lines[0]
        run_date = datetime.strptime(date_line, "%d.%m.%Y %H:%M")

        button_text = None
        button_url = None

        if "КНОПКА:" in text:
            content, button_line = text.split("КНОПКА:")
            post_text = content.split("\n", 1)[1]
            btn = button_line.strip().split("|")
            button_text = btn[0].strip()
            button_url = btn[1].strip()
        else:
            post_text = text.split("\n", 1)[1]

        cursor.execute(
            "INSERT INTO posts (text, run_date, button_text, button_url) VALUES (?, ?, ?, ?)",
            (post_text, run_date, button_text, button_url),
        )
        conn.commit()
        post_id = cursor.lastrowid

        context.job_queue.run_once(
            send_post,
            when=run_date,
            data=post_id
        )

        await update.message.reply_text(f"✅ Пост #{post_id} запланирован.")

    except Exception:
        await update.message.reply_text("❌ Ошибка формата.")

async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, run_date FROM posts")
    rows = cursor.fetchall()

    if rows:
        msg = "\n".join([f"#{r[0]} — {r[1]}" for r in rows])
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Нет запланированных постов.")

async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        post_id = int(context.args[0])
        cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()
        await update.message.reply_text("Удалено.")
    except:
        await update.message.reply_text("Ошибка удаления.")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_posts))
    app.add_handler(CommandHandler("delete", delete_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
