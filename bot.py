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

# ======================
# НАСТРОЙКИ
# ======================

TOKEN = os.environ["TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

logging.basicConfig(level=logging.INFO)

# ======================
# БАЗА ДАННЫХ
# ======================

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

# ======================
# ОТПРАВКА ПОСТА
# ======================

async def send_post(context: ContextTypes.DEFAULT_TYPE):
    post_id = context.job.data

    cursor.execute(
        "SELECT text, button_text, button_url FROM posts WHERE id=?",
        (post_id,)
    )
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

    except Exception as e:
        logging.error(f"Ошибка отправки поста: {e}")

# ======================
# /start
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Формат планирования:\n\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Текст поста\n\n"
        "КНОПКА: Текст | https://ссылка\n\n"
        "/list — список постов\n"
        "/delete ID — удалить пост"
    )

# ======================
# ПЛАНИРОВАНИЕ ПОСТА
# ======================

async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()

        # Разделяем дату и остальной текст
        parts = text.split("\n", 1)
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ После даты должен быть текст поста."
            )
            return

        date_line = parts[0].strip()
        rest = parts[1].strip()

        # Проверка даты
        try:
            run_date = datetime.strptime(date_line, "%d.%m.%Y %H:%M")
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты.\nПример: 01.03.2026 22:30"
            )
            return

        if run_date <= datetime.now():
            await update.message.reply_text(
                "❌ Нельзя ставить пост в прошлое."
            )
            return

        button_text = None
        button_url = None

        # Проверка кнопки
        if "КНОПКА:" in rest:
            content, button_part = rest.split("КНОПКА:", 1)
            post_text = content.strip()

            btn_parts = button_part.strip().split("|")
            if len(btn_parts) != 2:
                await update.message.reply_text(
                    "❌ Неверный формат кнопки.\n"
                    "Пример: КНОПКА: Текст | https://ссылка"
                )
                return

            button_text = btn_parts[0].strip()
            button_url = btn_parts[1].strip()

        else:
            post_text = rest.strip()

        if not post_text:
            await update.message.reply_text(
                "❌ Текст поста не может быть пустым."
            )
            return

        # Сохраняем в базу
        cursor.execute(
            "INSERT INTO posts (text, run_date, button_text, button_url) VALUES (?, ?, ?, ?)",
            (post_text, run_date, button_text, button_url)
        )
        conn.commit()

        post_id = cursor.lastrowid

        # Планируем задачу
        context.job_queue.run_once(
            send_post,
            when=run_date,
            data=post_id
        )

        await update.message.reply_text(
            f"✅ Пост #{post_id} запланирован на {run_date.strftime('%d.%m.%Y %H:%M')}"
        )

    except Exception as e:
        logging.error(f"Ошибка планирования: {e}")
        await update.message.reply_text("❌ Внутренняя ошибка.")

# ======================
# СПИСОК ПОСТОВ
# ======================

async def list_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, run_date FROM posts ORDER BY run_date")
    rows = cursor.fetchall()

    if rows:
        msg = "\n".join(
            [f"#{r[0]} — {r[1]}" for r in rows]
        )
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Нет запланированных постов.")

# ======================
# УДАЛЕНИЕ ПОСТА
# ======================

async def delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("Укажи ID: /delete 1")
            return

        post_id = int(context.args[0])

        cursor.execute("DELETE FROM posts WHERE id=?", (post_id,))
        conn.commit()

        await update.message.reply_text("Удалено.")

    except Exception:
        await update.message.reply_text("Ошибка удаления.")

# ======================
# ЗАПУСК
# ======================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_posts))
    app.add_handler(CommandHandler("delete", delete_post))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_post))

    app.run_polling()

if __name__ == "__main__":
    main()
