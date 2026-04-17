import os
import sqlite3
import json
import threading
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
PORT = int(os.environ.get("PORT", 8443))
DB_PATH = "tasks.db"

app = Flask(__name__, static_folder="static")


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                due_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

def get_tasks():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, description, due_date, created_at FROM tasks ORDER BY due_date"
        ).fetchall()
    return [{"id": r[0], "description": r[1], "due_date": r[2], "created_at": r[3]} for r in rows]

def create_task(description, due_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO tasks (description, due_date, created_at) VALUES (?, ?, ?)",
            (description, due_date, datetime.utcnow().isoformat()),
        )


# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    return jsonify(get_tasks())

@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json()
    description = (data.get("description") or "").strip()
    due_date = (data.get("due_date") or "").strip()
    if not description or not due_date:
        return jsonify({"error": "description and due_date are required"}), 400
    create_task(description, due_date)
    return jsonify({"ok": True}), 201


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Telegram webhook ──────────────────────────────────────────────────────────

telegram_app = Application.builder().token(TOKEN).build()

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok"


# ── Bot handlers ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton(
            "Open Task Manager",
            web_app=WebAppInfo(url=WEBHOOK_URL),
        )
    ]]
    await update.message.reply_text(
        "Hi Ivan! Tap below to manage your tasks.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_tasks()
    if not rows:
        await update.message.reply_text("No tasks yet. Use /start to add one.")
        return
    lines = [f"• {t['description']} — {t['due_date']}" for t in rows]
    await update.message.reply_text("Your tasks:\n" + "\n".join(lines))

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("tasks", tasks_command))


# ── Startup ───────────────────────────────────────────────────────────────────

def run_bot():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_setup_webhook())

async def _setup_webhook():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    await telegram_app.start()

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
