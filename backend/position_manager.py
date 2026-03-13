"""
Position Manager — Handles the full trade lifecycle:
- Places 3 limit orders at 66/44/10 levels
- Monitors fills via price tracking or Binance API
- Detects 20% ROI and executes close sequence
- Cancels remaining limit orders on close
- Supports demo mode (passive price tracking)
"""

import time
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional
from config import config
from signal_engine import Signal

logger = logging.getLogger(__name__)


@dataclass
class LimitOrder:
    order_id: str
    level: str  # "66%", "44%", "10%"
    price: float
    capital: float
    units: float
    status: str = "pending"  # pending, filled, cancelled
    fill_time: Optional[float] = None
    binance_order_id: Optional[str] = None


@dataclass
class Trade:
    trade_id: str
    symbol: str
    signal_type: str
    direction: str
    candle_high: float
    candle_low: float
    capital_total: float
    open_time: float
    orders: list[LimitOrder] = field(default_factory=list)
    status: str = "pending"  # pending, partial, active, tp_hit, closed
    avg_entry: Optional[float] = None
    total_units: Optional[float] = None
    total_cap_used: Optional[float] = None
    tp_price: Optional[float] = None
    close_price: Optional[float] = None
    close_time: Optional[float] = None
    realized_pnl: Optional[float] = None
    demo: bool = True

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "direction": self.direction,
            "candle_high": self.candle_high,
            "candle_low": self.candle_low,
            "capital_total": self.capital_total,
            "open_time": self.open_time,
            "status": self.status,
            "avg_entry": self.avg_entry,
            "total_units": self.total_units,
            "total_cap_used": self.total_cap_used,
            "tp_price": self.tp_price,
            "close_price": self.close_price,
            "close_time": self.close_time,
            "realized_pnl": self.realized_pnl,
            "demo": self.demo,
            "orders": [
                {
                    "order_id": o.order_id,
                    "level": o.level,
                    "price": o.price,
                    "capital": o.capital,
                    "units": o.units,
                    "status": o.status,
                    "fill_time": o.fill_time,
                }
                for o in self.orders
            ],
        }


class PositionManager:
    def __init__(self, binance_client=None):
        self.binance = binance_client
        self.active_trades: list[Trade] = []
        self.closed_trades: list[Trade] = []
        self.alerts: list[dict] = []

    def open_trade(self, signal: Signal, capital: float, size_multiplier: float = 1.0) -> Trade:
        adjusted_capital = capital * size_multiplier
        per_slot = adjusted_capital / 3

        H = signal.candle_high
        L = signal.candle_low
        rng = H - L

        if rng <= 0:
            logger.warning(f"Invalid candle range for {signal.symbol}")
            return None

        p66 = L + rng * 0.66
        p44 = L + rng * 0.44
        mid = L + rng * 0.5
        p10 = mid * 0.9

        trade = Trade(
            trade_id=str(uuid.uuid4())[:8],
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            direction=signal.direction,
            candle_high=H,
            candle_low=L,
            capital_total=adjusted_capital,
            open_time=time.time(),
            demo=config.DEMO_MODE,
            orders=[
                LimitOrder(
                    order_id=str(uuid.uuid4())[:8],
                    level="66%",
                    price=round(p66, 8),
                    capital=per_slot,
                    units=per_slot / p66,
                ),
                LimitOrder(
                    order_id=str(uuid.uuid4())[:8],
                    level="44%",
                    price=round(p44, 8),
                    capital=per_slot,
                    units=per_slot / p44,
                ),
                LimitOrder(
                    order_id=str(uuid.uuid4())[:8],
                    level="10%",
                    price=round(p10, 8),
                    capital=per_slot,
                    units=per_slot / p10,
                ),
            ],
        )

        # Place orders on Binance (live mode) or just log (demo)
        if not config.DEMO_MODE and self.binance:
            self._place_binance_orders(trade)
        else:
            logger.info(
                f"[DEMO] Trade opened: {trade.symbol} {trade.signal_type} "
                f"orders at ${p66:.2f} / ${p44:.2f} / ${p10:.2f}"
            )

        self.active_trades.append(trade)
        self._add_alert(
            "signal",
            trade.symbol,
            f"{'[DEMO] ' if trade.demo else ''}{signal.signal_type} — "
            f"limits placed: 66% ${p66:.4f} / 44% ${p44:.4f} / 10% ${p10:.4f}",
        )
        return trade

    def _place_binance_orders(self, trade: Trade):
        """Place actual limit orders on Binance."""
        if not self.binance:
            return
        try:
            from binance.enums import SIDE_BUY, ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC

            for order in trade.orders:
                result = self.binance.create_order(
                    symbol=trade.symbol,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_LIMIT,
                    timeInForce=TIME_IN_FORCE_GTC,
                    quantity=self._format_qty(trade.symbol, order.units),
                    price=self._format_price(trade.symbol, order.price),
                )
                order.binance_order_id = str(result["orderId"])
                logger.info(
                    f"Binance order placed: {trade.symbol} {order.level} "
                    f"id={order.binance_order_id}"
                )
        except Exception as e:
            logger.error(f"Failed to place Binance orders: {e}")

    def check_prices(self, prices: dict[str, float]) -> list[dict]:
        """
        Called on every price tick. Checks for fills and TP hits.
        Returns list of events that occurred.
        """
        events = []

        for trade in self.active_trades[:]:
            if trade.status in ("tp_hit", "closed"):
                continue

            current_price = prices.get(trade.symbol)
            if current_price is None:
                continue

            # ── Check for limit order fills (demo mode: price crosses level) ──
            for order in trade.orders:
                if order.status != "pending":
                    continue

                if trade.direction == "long" and current_price <= order.price:
                    order.status = "filled"
                    order.fill_time = time.time()
                    events.append(
                        {
                            "type": "fill",
                            "trade_id": trade.trade_id,
                            "symbol": trade.symbol,
                            "level": order.level,
                            "price": order.price,
                            "demo": trade.demo,
                        }
                    )
                    self._add_alert(
                        "fill",
                        trade.symbol,
                        f"{'[DEMO] ' if trade.demo else ''}"
                        f"{order.level} filled at ${order.price:.4f}",
                    )
                    logger.info(
                        f"{'[DEMO] ' if trade.demo else ''}"
                        f"{trade.symbol} {order.level} FILLED at ${order.price:.4f}"
                    )

            # ── Recalculate position ──
            self._recalc_trade(trade)

            # ── Check for TP hit ──
            if trade.tp_price and trade.total_units and trade.total_units > 0:
                if trade.direction == "long" and current_price >= trade.tp_price:
                    self._close_trade(trade, current_price)
                    events.append(
                        {
                            "type": "tp_hit",
                            "trade_id": trade.trade_id,
                            "symbol": trade.symbol,
                            "pnl": trade.realized_pnl,
                            "demo": trade.demo,
                        }
                    )

        return events

    def _recalc_trade(self, trade: Trade):
        """Recalculate avg entry and TP from filled orders."""
        filled = [o for o in trade.orders if o.status == "filled"]
        if not filled:
            trade.status = "pending"
            trade.avg_entry = None
            trade.tp_price = None
            trade.total_units = None
            trade.total_cap_used = None
            return

        total_cap = sum(o.capital for o in filled)
        total_units = sum(o.units for o in filled)
        avg_entry = total_cap / total_units
        tp = avg_entry * (1 + config.ROI_TARGET)

        trade.avg_entry = round(avg_entry, 8)
        trade.tp_price = round(tp, 8)
        trade.total_units = total_units
        trade.total_cap_used = total_cap
        trade.status = "active" if len(filled) == len(trade.orders) else "partial"

    def _close_trade(self, trade: Trade, close_price: float):
        """
        Execute close sequence:
        1. Market sell all held units
        2. Cancel all remaining limit orders
        3. Log P&L
        """
        trade.status = "tp_hit"
        trade.close_price = close_price
        trade.close_time = time.time()
        trade.realized_pnl = round(
            trade.total_units * close_price - trade.total_cap_used, 4
        )

        # Cancel remaining pending orders
        cancelled_count = 0
        for order in trade.orders:
            if order.status == "pending":
                order.status = "cancelled"
                cancelled_count += 1
                if not config.DEMO_MODE and self.binance and order.binance_order_id:
                    self._cancel_binance_order(trade.symbol, order.binance_order_id)

        # Market sell (live mode)
        if not config.DEMO_MODE and self.binance:
            self._market_sell(trade)

        roi_pct = (trade.realized_pnl / trade.total_cap_used * 100) if trade.total_cap_used else 0

        self._add_alert(
            "tp",
            trade.symbol,
            f"{'[DEMO] ' if trade.demo else ''}"
            f"TP HIT +{roi_pct:.1f}% → +${trade.realized_pnl:.2f} | "
            f"Cancelled {cancelled_count} pending orders",
        )

        logger.info(
            f"{'[DEMO] ' if trade.demo else ''}"
            f"{trade.symbol} CLOSED at ${close_price:.4f} "
            f"P&L: ${trade.realized_pnl:.2f} ({roi_pct:.1f}%) "
            f"Cancelled {cancelled_count} orders"
        )

        # Move to closed
        self.active_trades.remove(trade)
        self.closed_trades.append(trade)

    def _cancel_binance_order(self, symbol: str, order_id: str):
        try:
            self.binance.cancel_order(symbol=symbol, orderId=int(order_id))
            logger.info(f"Cancelled Binance order {order_id} on {symbol}")
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")

    def _market_sell(self, trade: Trade):
        try:
            from binance.enums import SIDE_SELL, ORDER_TYPE_MARKET

            result = self.binance.create_order(
                symbol=trade.symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=self._format_qty(trade.symbol, trade.total_units),
            )
            logger.info(f"Market sell executed: {trade.symbol} {result}")
        except Exception as e:
            logger.error(f"Market sell failed: {e}")

    def _format_qty(self, symbol: str, qty: float) -> str:
        if symbol.endswith("USDT"):
            base = symbol.replace("USDT", "")
            if base in ("BTC",):
                return f"{qty:.6f}"
            elif base in ("ETH", "BNB"):
                return f"{qty:.4f}"
            else:
                return f"{qty:.2f}"
        return f"{qty:.4f}"

    def _format_price(self, symbol: str, price: float) -> str:
        if price >= 1000:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        else:
            return f"{price:.6f}"

    def _add_alert(self, alert_type: str, symbol: str, message: str):
        alert = {
            "id": str(uuid.uuid4())[:8],
            "type": alert_type,
            "symbol": symbol,
            "message": message,
            "time": time.time(),
        }
        self.alerts.insert(0, alert)
        self.alerts = self.alerts[:100]

    def get_state(self) -> dict:
        active = [t.to_dict() for t in self.active_trades]
        closed = [t.to_dict() for t in self.closed_trades[-50:]]

        # Aggregate P&L
        realized_pnl = sum(t.realized_pnl or 0 for t in self.closed_trades)

        return {
            "active_trades": active,
            "closed_trades": closed,
            "alerts": self.alerts[:30],
            "realized_pnl": round(realized_pnl, 2),
            "active_count": len(self.active_trades),
            "closed_count": len(self.closed_trades),
            "demo_mode": config.DEMO_MODE,
        }
