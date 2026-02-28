import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

logging.basicConfig(level=logging.INFO)

# База
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


# 🔹 Отправка поста
async def send_post(post_id, app):
    cursor.execute("SELECT text, button_text, button_url FROM posts WHERE id=?", (post_id,))
    row = cursor.fetchone()

    if not row:
        return

    text, button_text, button_url = row

    if button_text and button_url:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(button_text, url=button_url)]
        ])
        await app.bot.send_message(chat_id=CHANNEL_ID, text=text, reply_markup=keyboard)
    else:
        await app.bot.send_message(chat_id=CHANNEL_ID, text=text)

    cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()


# 🔹 Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат:\n\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка\n\n"
        "/list — список\n"
        "/delete ID — удалить"
    )


# 🔹 Планирование
async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        parts = text.split("\n", 1)

        if len(parts) < 2:
            await update.message.reply_text("❌ После даты должен быть текст.")
            return

        date_line = parts[0].strip()
        rest = parts[1].strip()

        run_date = datetime.strptime(date_line, "%d.%m.%Y %H:%M")

        if run_date <= datetime.now():
            await update.message.reply_text("❌ Нельзя ставить в прошлое.")
            return

        button_text = None
        button_url = None

        if "КНОПКА:" in rest:
            content, button_part = rest.split("КНОПКА:", 1)
            post_text = content.strip()

            btn = button_part.strip().split("|")
            if len(btn) != 2:
                await update.message.reply_text("❌ Неверный формат кнопки.")
                return

            button_text = btn[0].strip()
            button_url = btn[1].strip()
        else:
            post_text = rest.strip()

        cursor.execute(
            "INSERT INTO posts (text, run_date, button_text, button_url) VALUES (?, ?, ?, ?)",
            (post_text, run_date.isoformat(), button_text, button_url),
        )
        conn.commit()

        post_id = cursor.lastrowid

        scheduler.add_job(
            send_post,
            "date",
            run_date=run_date,
            args=[post_id, context.application],
        )

        await update.message.reply_text(f"✅ Пост #{post_id} запланирован.")

    except Exception as e:
        logging.error(f"Ошибка планирования: {e}")
        await update.message.reply_text("❌ Ошибка формата.")


# 🔹 Список
async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, run_date FROM posts")
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("Нет запланированных постов.")
        return

    msg = "\n".join([f"#{r[0]} — {r[1]}" for r in rows])
    await update.message.reply_text(msg)


# 🔹 Удаление
async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        post_id = int(context.args[0])
        cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()
        await update.message.reply_text("Удалено.")
    except:
        await update.message.reply_text("Ошибка удаления.")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_posts))
    app.add_handler(CommandHandler("delete", delete_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    scheduler.start()

    app.run_polling()


if __name__ == "__main__":
    main()
