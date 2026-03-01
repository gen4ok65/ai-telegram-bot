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

logging.basicConfig(level=logging.INFO)

# ===== БАЗА =====
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


# ===== ОТПРАВКА =====
async def send_post(context: ContextTypes.DEFAULT_TYPE):
    post_id = context.job.data

    cursor.execute("SELECT text, button_text, button_url FROM posts WHERE id=?", (post_id,))
    row = cursor.fetchone()

    if not row:
        return

    text, button_text, button_url = row

    try:
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

        logging.info(f"Пост {post_id} отправлен")

    except Exception as e:
        logging.error(f"Ошибка отправки: {e}")


# ===== ВОССТАНОВЛЕНИЕ =====
def restore_jobs(app):
    now = datetime.now()
    cursor.execute("SELECT id, run_date FROM posts")
    rows = cursor.fetchall()

    for post_id, run_date_str in rows:
        run_date = datetime.strptime(run_date_str, "%Y-%m-%d %H:%M:%S")

        if run_date > now:
            app.job_queue.run_once(
                send_post,
                run_date,
                data=post_id
            )
            logging.info(f"Восстановлен пост {post_id}")


# ===== ОБРАБОТЧИК ОШИБОК =====
async def error_handler(update, context):
    logging.error(f"Ошибка: {context.error}")


# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат:\n\n"
        "01.03.2026 22:30\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка"
    )


# ===== /test =====
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text="✅ Тестовое сообщение"
    )
    await update.message.reply_text("Отправлено.")


# ===== ПЛАНИРОВАНИЕ =====
async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()

        # защита от мусорных сообщений
        if len(text) < 16:
            return

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

        context.job_queue.run_once(
            send_post,
            run_date,
            data=post_id
        )

        await update.message.reply_text(f"✅ Пост #{post_id} запланирован.")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Ошибка формата.")


# ===== MAIN =====
def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    restore_jobs(app)

    # КЛЮЧЕВАЯ СТРОКА ДЛЯ УСТРАНЕНИЯ КОНФЛИКТА
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
