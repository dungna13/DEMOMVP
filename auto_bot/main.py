import logging
import asyncio
import threading
from auto_bot.engine import engine
from auto_bot.telegram_bot import run_bot

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Entry point"""
    logger.info("CleanBot Initializing...")
    
    # Start Telegram Bot (Thread)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Engine (Async)
    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        logger.info("Shutting down...")

if __name__ == "__main__":
    main()
