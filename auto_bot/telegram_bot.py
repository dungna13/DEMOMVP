import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from .task_queue import queue

logger = logging.getLogger(__name__)

# Load from Environment (Lazy)
# TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("CleanBot Online! Send /add <cmd> to add task.")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <command>")
        return
    
    cmd = " ".join(context.args)
    await queue.add_task(cmd)
    await update.message.reply_text(f"Queued: {cmd}")

def run_bot():
    """Run the bot (Blocking - meant for thread/process)"""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or "YOUR_TOKEN" in token:
        logger.warning("No Token provided. Bot disabled.")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    
    logger.info("Bot Polling...")
    app.run_polling()
