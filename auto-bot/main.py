import logging

# Setup Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Entry point"""
    logger.info("CleanBot is constructing...")
    print("CleanBot System initialized.")

if __name__ == "__main__":
    main()
