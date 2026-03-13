"""
Sentinel Trading — Main Server
FastAPI backend with WebSocket for live dashboard updates.
"""

import asyncio
import json
import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import config
from signal_engine import SignalEngine
from sentiment import SentimentAnalyzer
from position_manager import PositionManager
from telegram_alert import TelegramAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("sentinel")

# ── Core components ──
signal_engine = SignalEngine()
sentiment = SentimentAnalyzer()
positions = PositionManager()
telegram = TelegramAlert()

# ── State ──
live_prices: dict[str, float] = {}
connected_clients: list[WebSocket] = []
binance_client = None


async def init_binance():
    """Initialize Binance client and load historical candles."""
    global binance_client

    if not config.DEMO_MODE and config.BINANCE_API_KEY:
        try:
            from binance.client import Client

            binance_client = Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
            positions.binance = binance_client
            logger.info("Binance client connected (LIVE mode)")
        except Exception as e:
            logger.warning(f"Binance client failed: {e}. Falling back to demo.")
    else:
        logger.info("Running in DEMO mode — no Binance connection")

    # Load initial candle data for all symbols
    for symbol in config.WATCHED_SYMBOLS:
        try:
            await load_candles(symbol)
        except Exception as e:
            logger.warning(f"Failed to load candles for {symbol}: {e}")


async def load_candles(symbol: str):
    """Load historical candles via Binance REST API."""
    import httpx
    import pandas as pd

    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": config.KLINE_INTERVAL,
        "limit": 200,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=15)
        data = resp.json()

    if not data or not isinstance(data, list):
        return

    df = pd.DataFrame(
        data,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ],
    )
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float}
    )
    df["timestamp"] = df["timestamp"].astype(float)

    signal_engine.update_candles(symbol, df)
    if len(df) > 0:
        live_prices[symbol] = float(df.iloc[-1]["close"])

    logger.info(f"Loaded {len(df)} candles for {symbol}")


async def price_stream():
    """Stream live prices from Binance WebSocket or poll REST."""
    import httpx

    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.binance.com/api/v3/ticker/price", timeout=10
                )
                tickers = resp.json()

            for t in tickers:
                sym = t["symbol"]
                if sym in config.WATCHED_SYMBOLS:
                    price = float(t["price"])
                    live_prices[sym] = price

            # Check positions against new prices
            events = positions.check_prices(live_prices)

            # Send telegram alerts for events
            for event in events:
                if event["type"] == "fill":
                    await telegram.send_fill(
                        event["symbol"], event["level"],
                        event["price"], event["demo"]
                    )
                elif event["type"] == "tp_hit":
                    pnl = event.get("pnl", 0)
                    roi = (pnl / config.TRADE_CAPITAL * 100) if config.TRADE_CAPITAL else 0
                    await telegram.send_tp_hit(
                        event["symbol"], pnl, roi, event["demo"]
                    )

            # Broadcast to connected WebSocket clients
            await broadcast_state()

        except Exception as e:
            logger.error(f"Price stream error: {e}")

        await asyncio.sleep(2)


async def candle_updater():
    """Periodically refresh candles and check for new signals."""
    while True:
        for symbol in config.WATCHED_SYMBOLS:
            try:
                await load_candles(symbol)
                signals = signal_engine.detect_signals(symbol)

                for sig in signals:
                    gate = sentiment.check_gate(sig.direction)

                    if gate["passed"]:
                        trade = positions.open_trade(
                            sig, config.TRADE_CAPITAL, gate["size_multiplier"]
                        )
                        if trade and sig.entry_levels:
                            await telegram.send_signal(
                                sig.signal_type, sig.symbol,
                                sig.entry_levels, trade.demo
                            )
                    else:
                        await telegram.send_gate_block(
                            sig.symbol, sig.signal_type, sentiment.gate_mode
                        )
                        positions._add_alert(
                            "gate", sig.symbol,
                            f"{sig.signal_type} BLOCKED — {gate['reason']}"
                        )
            except Exception as e:
                logger.error(f"Candle update error for {symbol}: {e}")

        await asyncio.sleep(60)  # Check every minute


async def broadcast_state():
    """Send current state to all connected WebSocket clients."""
    if not connected_clients:
        return

    state = build_state()
    message = json.dumps(state)

    disconnected = []
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        connected_clients.remove(ws)


def build_state() -> dict:
    """Build complete state for frontend."""
    pairs = []
    for symbol in config.WATCHED_SYMBOLS:
        price = live_prices.get(symbol, 0)
        buf = signal_engine.candle_buffers.get(symbol)
        change_24h = 0
        if buf is not None and len(buf) > 0:
            first_price = float(buf.iloc[0]["close"])
            if first_price > 0:
                change_24h = ((price - first_price) / first_price) * 100

        # Find active signal for this pair
        active_signal = None
        for trade in positions.active_trades:
            if trade.symbol == symbol:
                active_signal = trade.signal_type
                break

        pairs.append({
            "symbol": symbol,
            "price": price,
            "change_24h": round(change_24h, 2),
            "signal": active_signal,
        })

    return {
        "timestamp": time.time(),
        "demo_mode": config.DEMO_MODE,
        "pairs": pairs,
        "prices": live_prices,
        "sentiment": sentiment.get_state(),
        "positions": positions.get_state(),
    }


# ── FastAPI App ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("SENTINEL TRADING ENGINE STARTING")
    logger.info(f"Mode: {'DEMO' if config.DEMO_MODE else 'LIVE'}")
    logger.info(f"Symbols: {len(config.WATCHED_SYMBOLS)}")
    logger.info(f"Capital per trade: ${config.TRADE_CAPITAL}")
    logger.info(f"ROI target: {config.ROI_TARGET:.0%}")
    logger.info("=" * 50)

    await init_binance()

    price_task = asyncio.create_task(price_stream())
    candle_task = asyncio.create_task(candle_updater())

    yield

    price_task.cancel()
    candle_task.cancel()


app = FastAPI(title="Sentinel Trading", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
async def get_state():
    return JSONResponse(build_state())


@app.get("/api/trades")
async def get_trades():
    return JSONResponse(positions.get_state())


@app.get("/api/sentiment")
async def get_sentiment():
    return JSONResponse(sentiment.get_state())


@app.post("/api/sentiment/gate")
async def set_gate(mode: str = "neutral"):
    if mode in ("bullish", "neutral", "bearish"):
        sentiment.gate_mode = mode
        return {"ok": True, "gate_mode": mode}
    return {"ok": False, "error": "Invalid mode"}


@app.post("/api/demo/toggle")
async def toggle_demo():
    config.DEMO_MODE = not config.DEMO_MODE
    logger.info(f"Demo mode toggled to: {config.DEMO_MODE}")
    return {"demo_mode": config.DEMO_MODE}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")

    try:
        # Send initial state
        await ws.send_text(json.dumps(build_state()))

        while True:
            # Keep connection alive, handle incoming messages
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "set_gate":
                    sentiment.gate_mode = msg.get("mode", "neutral")
                elif msg.get("type") == "toggle_demo":
                    config.DEMO_MODE = not config.DEMO_MODE
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if ws in connected_clients:
            connected_clients.remove(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
