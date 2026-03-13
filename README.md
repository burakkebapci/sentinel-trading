# Sentinel — Crypto Sentiment Trading System

Real-time crypto sentiment trading signal system that combines technical analysis (C10/C20 momentum indicators) with AI-powered Twitter sentiment analysis to execute trades on Binance.

## Architecture

```
Twitter/X API → Claude AI Analysis → Sentiment Gate
                                          ↓
Binance WebSocket → Signal Engine → Position Manager → Telegram Alerts
                                          ↓
                                   React Dashboard (Live UI)
```

## Features

- **C10/C20 Signal Detection**: RSI-based momentum indicators ported from Pine Script
- **Sentiment Gate**: AI-powered tweet analysis blocks trades against market consensus
- **3-Level Entry System**: Limit orders at 66%, 44%, 10% of signal candle range
- **20% ROI Target**: Auto-close on TP hit + cancel remaining limit orders
- **Demo Mode**: Passive price tracking with simulated fills (no real capital)
- **Live Dashboard**: Real-time React UI with trade tracking, P&L, alerts
- **Telegram Alerts**: Instant notifications for signals, fills, TP hits, gate blocks

## Entry Logic

When a signal fires (C10L, C20L, etc.):
1. Capture signal candle High and Low
2. Calculate entry levels:
   - **66% level**: `low + (high - low) × 0.66`
   - **44% level**: `low + (high - low) × 0.44`
   - **10% level**: `(low + (high - low) × 0.5) × 0.9`
3. Place 3 equal GTC limit orders (1/3 capital each)
4. No stop loss

## Close Logic

Whenever unrealized P&L reaches +20% on filled orders:
1. Market sell all held units
2. Query all open orders on the symbol
3. Cancel every remaining unfilled limit order
4. Log trade to P&L history + alert Telegram

## Setup

### Backend
```bash
cd backend
cp .env.example .env  # Fill in your API keys
pip install -r requirements.txt
python main.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Environment Variables
```
BINANCE_API_KEY=        # Binance API key
BINANCE_API_SECRET=     # Binance API secret
ANTHROPIC_API_KEY=      # Claude API key for sentiment analysis
TELEGRAM_BOT_TOKEN=     # Telegram bot token
TELEGRAM_CHAT_ID=       # Telegram chat ID for alerts
DEMO_MODE=true          # true = paper trading, false = live
```

## ⚠️ Disclaimer

This is experimental trading software. Use at your own risk. Always start in DEMO_MODE=true. The authors are not responsible for any financial losses.
