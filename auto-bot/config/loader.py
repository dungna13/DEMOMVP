import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Load secrets from .env file (if it exists)
env_path = Path(__file__).parent / "secrets.env"
load_dotenv(dotenv_path=env_path)

class Config:
    def __init__(self):
        self._load_settings()
        self._load_secrets()

    def _load_settings(self):
        """Load static settings from settings.yaml"""
        settings_path = Path(__file__).parent / "settings.yaml"
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found at {settings_path}")
        
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = yaml.safe_load(f)

    def _load_secrets(self):
        """Load secrets from environment variables"""
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.DB_URL = os.getenv("DB_URL", "sqlite:///./cleanbot.db")
        self.AI_API_KEY = os.getenv("AI_API_KEY")

    def get(self, key, default=None):
        """Get a setting value by key"""
        return self.settings.get(key, default)

# Singleton instance
config = Config()

if __name__ == "__main__":
    # Test the config loader
    print(f"Project: {config.get('project_name')}")
    print(f"Timezone: {config.get('timezone')}")
    print(f"Database: {config.DB_URL}")
    print(f"Telegram Token Present: {'Yes' if config.TELEGRAM_TOKEN else 'No'}")
