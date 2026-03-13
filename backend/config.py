import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
    TRADE_CAPITAL = float(os.getenv("TRADE_CAPITAL", "1000"))
    ROI_TARGET = float(os.getenv("ROI_TARGET", "0.20"))
    SENTIMENT_THRESHOLD = float(os.getenv("SENTIMENT_THRESHOLD", "0.3"))
    MIN_MOMENTUM = float(os.getenv("MIN_MOMENTUM", "1.0"))
    WATCHED_SYMBOLS = [
        s.strip()
        for s in os.getenv(
            "WATCHED_SYMBOLS",
            "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT",
        ).split(",")
    ]
    TWITTER_ACCOUNTS = [
        s.strip()
        for s in os.getenv(
            "TWITTER_ACCOUNTS", "@CryptoWhale,@WhalePanda,@AltcoinDaily"
        ).split(",")
    ]
    KLINE_INTERVAL = "15m"
    RSI_PERIOD = 14
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9


config = Config()
