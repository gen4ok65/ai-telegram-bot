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

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

logging.basicConfig(level=logging.INFO)

# ---------- БАЗА ----------
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


# ---------- ОТПРАВКА ПОСТА ----------
async def send_post(context: ContextTypes.DEFAULT_TYPE):
    post_id = context.job.data

    cursor.execute("SELECT text, button_text, button_url FROM posts WHERE id=?", (post_id,))
    row = cursor.fetchone()

    if row:
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


# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат планирования:\n\n"
        "01.03.2026 22:30\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка\n\n"
        "/list — список\n"
        "/delete ID — удалить\n"
        "/test — проверка канала"
    )


# ---------- /test ----------
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text="✅ Проверка отправки в канал работает!"
        )
        await update.message.reply_text("Сообщение отправлено в канал.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


# ---------- ПЛАНИРОВАНИЕ ----------
async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        lines = text.split("\n")

        date_line = lines[0].strip()
        run_date = datetime.strptime(date_line, "%d.%m.%Y %H:%M")

        if run_date <= datetime.now():
            await update.message.reply_text("Дата должна быть в будущем.")
            return

        button_text = None
        button_url = None

        if "КНОПКА:" in text:
            content, button_line = text.split("КНОПКА:")
            post_text = content.split("\n", 1)[1].strip()

            btn = button_line.strip().split("|")
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
        logging.error(f"Ошибка планирования: {e}")
        await update.message.reply_text("❌ Ошибка формата.")


# ---------- СПИСОК ----------
async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, run_date FROM posts")
    rows = cursor.fetchall()

    if rows:
        msg = "\n".join([f"#{r[0]} — {r[1]}" for r in rows])
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Нет запланированных постов.")


# ---------- УДАЛЕНИЕ ----------
async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        post_id = int(context.args[0])
        cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()
        await update.message.reply_text("Удалено.")
    except:
        await update.message.reply_text("Ошибка удаления.")


# ---------- MAIN ----------
async def main():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # сброс webhook и конфликтов
    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("list", list_posts))
    app.add_handler(CommandHandler("delete", delete_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
