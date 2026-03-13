"""
Sentiment Analyzer — Uses Claude API to analyze tweets and produce
sentiment scores, timeframe classification, and catalyst detection.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


@dataclass
class TweetAnalysis:
    account: str
    text: str
    sentiment: float  # -1.0 to 1.0
    timeframe: str  # short-term, mid-term, long-term
    catalyst: bool
    related_symbol: Optional[str]
    confidence: float
    timestamp: float


class SentimentAnalyzer:
    def __init__(self):
        self.analyses: list[TweetAnalysis] = []
        self.aggregate_sentiment: float = 0.0
        self.gate_mode: str = "neutral"  # bullish, neutral, bearish
        self.confidence: float = 0.0
        self.client = None

        if config.ANTHROPIC_API_KEY:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
                logger.info("Anthropic client initialized")
            except Exception as e:
                logger.warning(f"Could not init Anthropic client: {e}")

    async def analyze_tweet(self, account: str, text: str) -> TweetAnalysis:
        if self.client:
            return await self._analyze_with_claude(account, text)
        return self._analyze_heuristic(account, text)

    async def _analyze_with_claude(self, account: str, text: str) -> TweetAnalysis:
        try:
            prompt = f"""Analyze this crypto tweet for trading signals.

Tweet by {account}: "{text}"

Respond in exactly this format (one value per line, no labels):
SENTIMENT: <float from -1.0 to 1.0>
TIMEFRAME: <short-term|mid-term|long-term>
CATALYST: <true|false>
SYMBOL: <BTCUSDT|ETHUSDT|etc or NONE>
CONFIDENCE: <float from 0.0 to 1.0>

Rules:
- Sentiment: -1.0 = extremely bearish, 0 = neutral, 1.0 = extremely bullish
- Timeframe: short-term = hours/days, mid-term = weeks, long-term = months
- Catalyst: true if this contains immediate actionable news (listing, hack, partnership, regulation)
- Symbol: the most relevant trading pair, or NONE if general market
- Confidence: how confident you are in the sentiment reading"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            lines = response.content[0].text.strip().split("\n")
            parsed = {}
            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    parsed[key.strip().upper()] = val.strip()

            analysis = TweetAnalysis(
                account=account,
                text=text,
                sentiment=float(parsed.get("SENTIMENT", "0")),
                timeframe=parsed.get("TIMEFRAME", "mid-term"),
                catalyst=parsed.get("CATALYST", "false").lower() == "true",
                related_symbol=parsed.get("SYMBOL")
                if parsed.get("SYMBOL") != "NONE"
                else None,
                confidence=float(parsed.get("CONFIDENCE", "0.5")),
                timestamp=time.time(),
            )

        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            analysis = self._analyze_heuristic(account, text)

        self._update_aggregate(analysis)
        return analysis

    def _analyze_heuristic(self, account: str, text: str) -> TweetAnalysis:
        """Fallback keyword-based analysis when Claude API is unavailable."""
        text_lower = text.lower()

        bullish_words = [
            "bullish", "moon", "breakout", "accumulate", "strong",
            "buy", "long", "ath", "surge", "rocket", "pump",
            "undervalued", "gem", "massive", "incredible", "unstoppable",
        ]
        bearish_words = [
            "bearish", "dump", "crash", "short", "weak",
            "sell", "drop", "breakdown", "overextended", "caution",
            "warning", "divergence", "exhausted", "pullback",
        ]
        catalyst_words = [
            "listing", "hack", "partnership", "regulation",
            "etf", "approval", "launch", "just", "breaking",
        ]

        bull_score = sum(1 for w in bullish_words if w in text_lower)
        bear_score = sum(1 for w in bearish_words if w in text_lower)
        total = bull_score + bear_score or 1
        sentiment = (bull_score - bear_score) / total * 0.8
        catalyst = any(w in text_lower for w in catalyst_words)

        # Detect symbol
        symbol = None
        symbol_map = {
            "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
            "eth": "ETHUSDT", "ethereum": "ETHUSDT",
            "sol": "SOLUSDT", "solana": "SOLUSDT",
            "bnb": "BNBUSDT", "xrp": "XRPUSDT",
            "ada": "ADAUSDT", "cardano": "ADAUSDT",
            "doge": "DOGEUSDT", "avax": "AVAXUSDT",
            "link": "LINKUSDT", "dot": "DOTUSDT",
            "near": "NEARUSDT", "matic": "MATICUSDT",
        }
        for keyword, sym in symbol_map.items():
            if keyword in text_lower or f"${keyword}" in text_lower:
                symbol = sym
                break

        analysis = TweetAnalysis(
            account=account,
            text=text,
            sentiment=round(max(-1, min(1, sentiment)), 2),
            timeframe="mid-term",
            catalyst=catalyst,
            related_symbol=symbol,
            confidence=0.5,
            timestamp=time.time(),
        )
        self._update_aggregate(analysis)
        return analysis

    def _update_aggregate(self, analysis: TweetAnalysis):
        self.analyses.append(analysis)
        # Keep last 100 analyses
        self.analyses = self.analyses[-100:]

        # Weighted average: recent tweets count more
        if len(self.analyses) == 0:
            return

        now = time.time()
        total_weight = 0.0
        weighted_sum = 0.0
        for a in self.analyses:
            age = now - a.timestamp
            weight = max(0.1, 1.0 - age / 3600)  # decay over 1 hour
            weighted_sum += a.sentiment * weight * a.confidence
            total_weight += weight * a.confidence

        if total_weight > 0:
            self.aggregate_sentiment = round(weighted_sum / total_weight, 3)

        # Update gate mode
        if self.aggregate_sentiment > config.SENTIMENT_THRESHOLD:
            self.gate_mode = "bullish"
        elif self.aggregate_sentiment < -config.SENTIMENT_THRESHOLD:
            self.gate_mode = "bearish"
        else:
            self.gate_mode = "neutral"

        # Confidence = agreement among recent analyses
        if len(self.analyses) >= 3:
            recent = self.analyses[-10:]
            signs = [1 if a.sentiment > 0 else -1 for a in recent]
            agreement = abs(sum(signs)) / len(signs)
            self.confidence = round(agreement, 2)

    def check_gate(self, signal_direction: str) -> dict:
        """
        Returns gate decision for a signal direction.
        Returns: {passed: bool, action: str, reason: str, size_multiplier: float}
        """
        if self.gate_mode == "neutral":
            return {
                "passed": True,
                "action": "reduced",
                "reason": f"Neutral sentiment ({self.aggregate_sentiment:.0%})",
                "size_multiplier": 0.5 if self.confidence > 0.6 else 1.0,
            }

        aligned = (
            (self.gate_mode == "bullish" and signal_direction == "long")
            or (self.gate_mode == "bearish" and signal_direction == "short")
        )

        if aligned:
            return {
                "passed": True,
                "action": "execute",
                "reason": f"{self.gate_mode} consensus aligned with {signal_direction}",
                "size_multiplier": 1.0,
            }

        # Conflicting
        if self.confidence > 0.7:
            return {
                "passed": False,
                "action": "blocked",
                "reason": f"High-confidence {self.gate_mode} blocks {signal_direction}",
                "size_multiplier": 0.0,
            }

        return {
            "passed": True,
            "action": "reduced",
            "reason": f"Low-confidence {self.gate_mode} vs {signal_direction}",
            "size_multiplier": 0.25,
        }

    def get_state(self) -> dict:
        return {
            "aggregate_sentiment": self.aggregate_sentiment,
            "gate_mode": self.gate_mode,
            "confidence": self.confidence,
            "total_analyses": len(self.analyses),
            "recent_analyses": [
                {
                    "account": a.account,
                    "text": a.text,
                    "sentiment": a.sentiment,
                    "timeframe": a.timeframe,
                    "catalyst": a.catalyst,
                    "related_symbol": a.related_symbol,
                    "timestamp": a.timestamp,
                }
                for a in self.analyses[-20:]
            ],
        }
