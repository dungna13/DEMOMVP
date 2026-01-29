import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from .task_queue import queue

logger = logging.getLogger(__name__)

# Placeholder token (Replace with real one via Config later)
TOKEN = "YOUR_TOKEN_HERE" 

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
    if "YOUR_TOKEN" in TOKEN:
        logger.warning("No Token provided. Bot disabled.")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    
    logger.info("Bot Polling...")
    app.run_polling()
