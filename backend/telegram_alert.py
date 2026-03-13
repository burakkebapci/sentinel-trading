"""
Telegram Alert Module — Sends formatted alerts to a Telegram chat.
"""

import logging
import httpx
from config import config

logger = logging.getLogger(__name__)


class TelegramAlert:
    def __init__(self):
        self.enabled = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
        self.base_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
        if self.enabled:
            logger.info("Telegram alerts enabled")
        else:
            logger.info("Telegram alerts disabled (no token/chat_id)")

    async def send(self, message: str):
        if not self.enabled:
            logger.info(f"[TG-disabled] {message}")
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": config.TELEGRAM_CHAT_ID,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                    timeout=10,
                )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def send_signal(self, signal_type: str, symbol: str, levels: dict, demo: bool = True):
        prefix = "🔵 DEMO" if demo else "🟢 LIVE"
        msg = (
            f"<b>{prefix} | {signal_type} on {symbol}</b>\n\n"
            f"📊 Entry Levels:\n"
            f"  66%: <code>${levels.get('p66', 0):.4f}</code>\n"
            f"  44%: <code>${levels.get('p44', 0):.4f}</code>\n"
            f"  10%: <code>${levels.get('p10', 0):.4f}</code>\n\n"
            f"📈 Avg Entry: <code>${levels.get('avg_entry', 0):.4f}</code>\n"
            f"🎯 TP (+20%): <code>${levels.get('tp', 0):.4f}</code>\n"
            f"🚫 Stop: None"
        )
        await self.send(msg)

    async def send_fill(self, symbol: str, level: str, price: float, demo: bool = True):
        prefix = "🔵" if demo else "🟢"
        await self.send(
            f"{prefix} <b>{symbol}</b> — {level} level <b>FILLED</b> at <code>${price:.4f}</code>"
        )

    async def send_tp_hit(self, symbol: str, pnl: float, roi: float, demo: bool = True):
        prefix = "🔵 DEMO" if demo else "🟢 LIVE"
        await self.send(
            f"🎯 <b>{prefix} | {symbol} TP HIT</b>\n"
            f"💰 P&L: <code>+${pnl:.2f}</code> (+{roi:.1f}%)\n"
            f"✅ Position closed + pending orders cancelled"
        )

    async def send_gate_block(self, symbol: str, signal_type: str, gate_mode: str):
        await self.send(
            f"🚫 <b>{symbol}</b> {signal_type} <b>BLOCKED</b>\n"
            f"Gate: {gate_mode} consensus vs conflicting signal"
        )
