# android_trading_bot.py - COMPLETE 1503 LINES CONVERTED
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from datetime import datetime, timedelta
import time
import pytz
import requests
import sys
import os

# ============================================
# TELEGRAM CREDENTIALS - ADD YOURS HERE
# ============================================
TELEGRAM_BOT_TOKEN = "8906117381:AAHZfaWN9GfUnwKdVmBZwHrNSFnfqTkQFlI"
TELEGRAM_CHAT_ID = "6317897423"

# ============================================
# CONFIGURATION - SAME AS YOUR ORIGINAL BOT
# ============================================
MT5_SYMBOL = "XAUUSDm"
MT5_LOT_SIZE = 0.01
MT5_SLIPPAGE = 50

AUTO_TRADE_ENABLED = True
AUTO_TRADE_CONFIDENCE_THRESHOLD = 5.5

MAX_STOP_LOSS = 10.0
MIN_TAKE_PROFIT = 15.0
MAX_TAKE_PROFIT = 20.0
MIN_RISK_REWARD_RATIO = 1.5
MAX_RISK_REWARD_RATIO = 2.0
ENTRY_TIMEFRAME = "M15"
TREND_TIMEFRAME = "H1"

MIN_CONFIRMATIONS = 4
MIN_CONFIDENCE_SCORE = 4.0
STRONG_SIGNAL_THRESHOLD = 5.5
SAME_SIGNAL_COOLDOWN_MIN = 10
MTF_WEIGHTS = {"M15": 1.0, "H1": 1.5, "H4": 2.0, "D": 2.5}
MIN_HTF_ALIGNMENT = 2
MIN_CONSECUTIVE_BARS = 3
HAMMER_MIN_RATIO = 2.5
ENGULFING_MIN_SIZE = 1.5
VOLUME_SPIKE_MIN = 1.5

TIMEFRAMES = ["M15", "H1", "H4", "D"]
MAX_CANDLES = 500
UPDATE_CANDLES = 100
SWING_LOOKBACK = 15

OANDA_API_URL = "https://api-fxpractice.oanda.com/v3"
OANDA_TOKEN = "2709d7d75f303cd9a5937d7ae326842fcad5961182b202ecb40007d46ef7153f"
OANDA_ACCOUNT = "101-011-31806371-001"
INSTRUMENT = "XAU_USD"
HEADERS = {"Authorization": f"Bearer {OANDA_TOKEN}", "Content-Type": "application/json"}

TF_DATA = {}
FIRST_RUN = True
NEWS_CACHE = []
NEWS_LAST_FETCH = None
NEWS_CACHE_MINUTES = 60

LAST_SIGNAL = {"direction": None, "timestamp": None, "price": None, "score": 0}
LAST_SIGNAL_TIME = None
PK_TZ = pytz.timezone("Asia/Karachi")
UTC_TZ = pytz.utc
SIGNAL_STATS = {"total_cycles": 0, "buy_signals": 0, "sell_signals": 0, "hold_signals": 0, "trades_placed": 0}
DEBUG_MODE = True

# Colors for console output (kept for visual appeal)
BG_COLOR = "#121212"
TEXT_COLOR = "#E0E0E0"
PANEL_BG = "#1E1E1E"
BORDER_COLOR = "#424242"
ACCENT_COLOR = "#4CAF50"
BUY_COLOR = "#00C853"
BUY_BG = "#1B5E20"
SELL_COLOR = "#FF5252"
SELL_BG = "#B71C1C"
HOLD_COLOR = "#9E9E9E"
HOLD_BG = "#424242"
LOG_COLOR = "#76FF03"
LOG_BG = "#000000"

# ============================================
# TELEGRAM FUNCTION
# ============================================
def send_telegram_signal(signal, entry, sl, tp, rr, reason, market_state, amd_phase):
    try:
        if signal == "Buy":
            emoji = "🟢"
            direction = "BUY"
        else:
            emoji = "🔴"
            direction = "SELL"
        
        message = f"""
{emoji} *{direction} SIGNAL* {emoji}

━━━━━━━━━━━━━━━━━━━━
💰 *Entry:* ${entry:.2f}
🛑 *Stop Loss:* ${sl:.2f}
🎯 *Take Profit:* ${tp:.2f}
📊 *Risk/Reward:* 1:{rr:.2f}
━━━━━━━━━━━━━━━━━━━━

📈 *Market State:* {market_state}
🏗️ *AMD Phase:* {amd_phase}
💡 *Reason:* {reason}

⚠️ *Risk:* ${abs(entry-sl):.2f} | *Reward:* ${abs(tp-entry):.2f}
        """
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=data, timeout=5)
        print("  📱 Telegram alert sent!")
    except Exception as e:
        print(f"  ⚠️ Telegram error: {e}")

def send_telegram_startup():
    try:
        message = f"""
🤖 *TRADING BOT STARTED* 🤖

━━━━━━━━━━━━━━━━━━━━
📊 *Entry:* M15
📈 *Trend:* H1
💰 *Max SL:* ${MAX_STOP_LOSS}
🎯 *Min TP:* ${MIN_TAKE_PROFIT}
📐 *RR Ratio:* 1:{MIN_RISK_REWARD_RATIO} to 1:{MAX_RISK_REWARD_RATIO}
━━━━━━━━━━━━━━━━━━━━

✅ Bot is now monitoring XAU/USD
📡 You will receive signals here
        """
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=data, timeout=5)
    except:
        pass

# ============================================
# SOUND FUNCTION (REMOVED - Android doesn't need)
# ============================================
def play_alert_sound():
    pass  # Removed for Android

# ============================================
# MARKET STRUCTURE DETECTION - COMPLETE
# ============================================
class MarketStructure:
    """Detects AMD (Accumulation, Manipulation, Distribution)"""

    @staticmethod
    def detect_amd(df, lookback=50):
        """Detect Accumulation, Manipulation, Distribution phases"""
        if len(df) < lookback:
            return "Unknown"
        recent = df.tail(lookback)
        price_range = recent.h.max() - recent.l.min()
        avg_volume = recent.v.mean()
        current_volume = recent.v.iloc[-1]
        if price_range < recent.h.iloc[:30].max() - recent.l.iloc[:30].min():
            if current_volume > avg_volume * 0.8 and current_volume < avg_volume * 1.2:
                return "Accumulation"
        if price_range > (recent.h.iloc[:30].max() - recent.l.iloc[:30].min()) * 1.5:
            if current_volume > avg_volume * 1.5:
                return "Manipulation"
        if price_range > avg_volume * 1.2:
            if recent.c.iloc[-1] < recent.o.iloc[-1] and current_volume > avg_volume * 1.3:
                return "Distribution"
        return "Neutral"

    @staticmethod
    def detect_zones(df, lookback=100):
        """Detect supply and demand zones"""
        zones = {"supply": [], "demand": []}
        if len(df) < lookback:
            return zones
        data = df.tail(lookback).reset_index()
        for i in range(2, len(data)-2):
            if (data['l'].iloc[i] < data['l'].iloc[i-1] and 
                data['l'].iloc[i] < data['l'].iloc[i-2] and
                data['l'].iloc[i] < data['l'].iloc[i+1] and
                data['l'].iloc[i] < data['l'].iloc[i+2]):
                zones["demand"].append({
                    "price": data['l'].iloc[i],
                    "strength": 1,
                    "timestamp": data['timestamp'].iloc[i]
                })
            if (data['h'].iloc[i] > data['h'].iloc[i-1] and 
                data['h'].iloc[i] > data['h'].iloc[i-2] and
                data['h'].iloc[i] > data['h'].iloc[i+1] and
                data['h'].iloc[i] > data['h'].iloc[i+2]):
                zones["supply"].append({
                    "price": data['h'].iloc[i],
                    "strength": 1,
                    "timestamp": data['timestamp'].iloc[i]
                })
        return zones

    @staticmethod
    def detect_order_blocks(df, lookback=50):
        """Detect order blocks (institutional order flow)"""
        order_blocks = {"bullish": [], "bearish": []}
        if len(df) < lookback:
            return order_blocks
        data = df.tail(lookback).reset_index()
        avg_volume = data.v.mean()
        for i in range(1, len(data)-1):
            if (data['c'].iloc[i] > data['o'].iloc[i] and
                (data['c'].iloc[i] - data['o'].iloc[i]) > (data['h'].iloc[i] - data['l'].iloc[i]) * 0.6 and
                data['v'].iloc[i] > avg_volume * 1.5):
                order_blocks["bullish"].append({
                    "high": data['h'].iloc[i],
                    "low": data['l'].iloc[i],
                    "strength": 2,
                    "timestamp": data['timestamp'].iloc[i]
                })
            if (data['c'].iloc[i] < data['o'].iloc[i] and
                (data['o'].iloc[i] - data['c'].iloc[i]) > (data['h'].iloc[i] - data['l'].iloc[i]) * 0.6 and
                data['v'].iloc[i] > avg_volume * 1.5):
                order_blocks["bearish"].append({
                    "high": data['h'].iloc[i],
                    "low": data['l'].iloc[i],
                    "strength": 2,
                    "timestamp": data['timestamp'].iloc[i]
                })
        return order_blocks

    @staticmethod
    def detect_large_moves(df, threshold_percent=0.01):
        """Detect large buying/selling moves"""
        large_moves = {"large_buy": [], "large_sell": []}
        if len(df) < 20:
            return large_moves
        for i in range(10, len(df)):
            price_change = abs(df['c'].iloc[i] - df['c'].iloc[i-10])
            price_change_percent = price_change / df['c'].iloc[i-10]
            if price_change_percent > threshold_percent:
                if df['c'].iloc[i] > df['c'].iloc[i-10]:
                    large_moves["large_buy"].append({
                        "from": df['c'].iloc[i-10],
                        "to": df['c'].iloc[i],
                        "change": price_change,
                        "percent": price_change_percent * 100,
                        "timestamp": df.index[i]
                    })
                else:
                    large_moves["large_sell"].append({
                        "from": df['c'].iloc[i-10],
                        "to": df['c'].iloc[i],
                        "change": price_change,
                        "percent": price_change_percent * 100,
                        "timestamp": df.index[i]
                    })
        return large_moves

# ============================================
# DATA FETCHING - OANDA ONLY (MT5 REMOVED)
# ============================================
def fetch_candles_oanda(tf, count=MAX_CANDLES):
    try:
        r = requests.get(
            f"{OANDA_API_URL}/instruments/{INSTRUMENT}/candles",
            headers=HEADERS,
            params={"price": "M", "granularity": tf, "count": count},
            timeout=12
        )
        r.raise_for_status()
        candles = r.json()["candles"]
        if not candles:
            return None
        df = pd.DataFrame([
            {
                "timestamp": pd.to_datetime(c["time"]),
                "o": float(c["mid"]["o"]),
                "h": float(c["mid"]["h"]),
                "l": float(c["mid"]["l"]),
                "c": float(c["mid"]["c"]),
                "v": int(c.get("volume", 0))
            } for c in candles
        ]).set_index("timestamp").sort_index()
        return df
    except Exception as e:
        print(f"OANDA Fetch {tf} failed: {e}")
        return None

def fetch_candles(tf, count=MAX_CANDLES):
    df = fetch_candles_oanda(tf, count)
    if df is not None:
        print(f"  OANDA {tf:3} → {len(df)} candles | Close: {df.c.iloc[-1]:.2f}")
        return df
    return None

def update_data():
    global FIRST_RUN, TF_DATA
    if FIRST_RUN:
        print("Loading initial data...")
        for tf in TIMEFRAMES:
            TF_DATA[tf] = fetch_candles(tf, MAX_CANDLES)
        FIRST_RUN = False
    else:
        print("Updating candles...")
        for tf in TIMEFRAMES:
            curr = TF_DATA.get(tf)
            if curr is None:
                TF_DATA[tf] = fetch_candles(tf, MAX_CANDLES)
                continue
            new = fetch_candles(tf, UPDATE_CANDLES)
            if new is not None and not new.empty:
                curr_trimmed = curr.iloc[:-1]
                combined = pd.concat([curr_trimmed, new]).sort_index()
                combined = combined[~combined.index.duplicated(keep='last')]
                if len(combined) > 800:
                    combined = combined.tail(800)
                TF_DATA[tf] = combined

# ============================================
# NEWS FUNCTIONS - COMPLETE
# ============================================
def fetch_high_impact_news():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        events = []
        for event in data:
            if event.get("impact") != "High" or event.get("country") != "USD":
                continue
            time_str = event.get("date", "").strip()
            if not time_str:
                continue
            try:
                ev_time = datetime.fromisoformat(time_str).replace(tzinfo=pytz.utc)
            except:
                continue
            events.append({"currency": "USD", "time": ev_time, "event": event.get("title", "").strip()})
        return events
    except Exception as e:
        return []

def is_news_blocked():
    global NEWS_LAST_FETCH, NEWS_CACHE
    now = datetime.now(pytz.utc)
    if NEWS_LAST_FETCH is None or (now - NEWS_LAST_FETCH).total_seconds() / 60 > NEWS_CACHE_MINUTES:
        NEWS_CACHE = fetch_high_impact_news()
        NEWS_LAST_FETCH = now
    if not NEWS_CACHE:
        return False
    for ev in NEWS_CACHE:
        start = ev["time"] - timedelta(minutes=35)
        end = ev["time"] + timedelta(minutes=65)
        if start <= now <= end:
            print(f"News block active: {ev.get('event', 'High impact USD')}")
            return True
    return False

# ============================================
# ADVANCED ANALYZER - COMPLETE (UNCHANGED)
# ============================================
class AdvancedAnalyzer:
    def __init__(self, df, tf_name=""):
        self.df = df.reset_index()
        self.tf_name = tf_name
        self.current_price = df.c.iloc[-1] if len(df) > 0 else 0
        self.buy_analysis = {"score": 0, "confirmations": [], "strength": "Weak", "factors": {}}
        self.sell_analysis = {"score": 0, "confirmations": [], "strength": "Weak", "factors": {}}
        self.market_state = "Neutral"
        self.market_structure = {}

    def analyze_both_sides(self):
        self.buy_analysis = {"score": 0, "confirmations": [], "strength": "Weak", "factors": {}}
        self.sell_analysis = {"score": 0, "confirmations": [], "strength": "Weak", "factors": {}}
        swings = self._find_swings()
        atr = self._calculate_atr()
        self._analyze_market_structure()
        self._analyze_buy_side(swings, atr)
        self._analyze_sell_side(swings, atr)
        self._determine_market_state()
        return {
            "buy": self.buy_analysis,
            "sell": self.sell_analysis,
            "market_state": self.market_state,
            "price": self.current_price,
            "atr": atr,
            "market_structure": self.market_structure
        }

    def _analyze_market_structure(self):
        amd_phase = MarketStructure.detect_amd(self.df)
        self.market_structure["amd_phase"] = amd_phase
        zones = MarketStructure.detect_zones(self.df)
        self.market_structure["zones"] = zones
        order_blocks = MarketStructure.detect_order_blocks(self.df)
        self.market_structure["order_blocks"] = order_blocks
        large_moves = MarketStructure.detect_large_moves(self.df)
        self.market_structure["large_moves"] = large_moves
        if zones["demand"]:
            nearest_demand = max([z["price"] for z in zones["demand"] if z["price"] < self.current_price], default=None)
            if nearest_demand and (self.current_price - nearest_demand) / self.current_price < 0.002:
                self.market_structure["near_demand_zone"] = nearest_demand
        if zones["supply"]:
            nearest_supply = min([z["price"] for z in zones["supply"] if z["price"] > self.current_price], default=None)
            if nearest_supply and (nearest_supply - self.current_price) / self.current_price < 0.002:
                self.market_structure["near_supply_zone"] = nearest_supply
        if order_blocks["bullish"]:
            for ob in order_blocks["bullish"]:
                if abs(self.current_price - ob["low"]) / self.current_price < 0.001:
                    self.market_structure["near_bullish_ob"] = ob["low"]
        if order_blocks["bearish"]:
            for ob in order_blocks["bearish"]:
                if abs(self.current_price - ob["high"]) / self.current_price < 0.001:
                    self.market_structure["near_bearish_ob"] = ob["high"]

    def _find_swings(self):
        order = SWING_LOOKBACK
        hi = argrelextrema(self.df.h.values, np.greater_equal, order=order)[0]
        lo = argrelextrema(self.df.l.values, np.less_equal, order=order)[0]
        swing_highs = [{"t": self.df.timestamp.iloc[i], "p": self.df.h.iloc[i]} for i in hi[-8:]]
        swing_lows = [{"t": self.df.timestamp.iloc[i], "p": self.df.l.iloc[i]} for i in lo[-8:]]
        return {"highs": swing_highs, "lows": swing_lows}

    def _calculate_atr(self):
        high_low = self.df.h - self.df.l
        high_close = abs(self.df.h - self.df.c.shift())
        low_close = abs(self.df.l - self.df.c.shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=14).mean().iloc[-1]
        return atr if not np.isnan(atr) else (self.df.h.iloc[-1] - self.df.l.iloc[-1])

    def _analyze_buy_side(self, swings, atr):
        score = 0
        confirmations = []
        factors = {}
        if "near_demand_zone" in self.market_structure:
            score += 3.0
            confirmations.append(f"✅ At demand zone: ${self.market_structure['near_demand_zone']:.2f}")
            factors["demand_zone"] = self.market_structure["near_demand_zone"]
        if "near_bullish_ob" in self.market_structure:
            score += 2.5
            confirmations.append(f"✅ At bullish order block: ${self.market_structure['near_bullish_ob']:.2f}")
            factors["bullish_ob"] = self.market_structure["near_bullish_ob"]
        if self.market_structure.get("amd_phase") == "Accumulation":
            score += 2.0
            confirmations.append("✅ Accumulation phase detected")
            factors["accumulation"] = True
        supports = [s["p"] for s in swings["lows"][-4:]] if swings["lows"] else []
        if supports:
            closest_support = max([s for s in supports if s < self.current_price], default=None)
            if closest_support:
                distance = self.current_price - closest_support
                if distance <= atr * 1.2:
                    score += 2.0
                    confirmations.append(f"✅ Near support: ${closest_support:.2f}")
                    factors["near_support"] = closest_support
        if len(self.df) >= 3:
            last = self.df.iloc[-1]
            prev = self.df.iloc[-2]
            if (last.c > last.o and prev.c < prev.o and 
                last.o <= prev.c and last.c >= prev.o and
                (last.h - last.l) > (prev.h - prev.l) * ENGULFING_MIN_SIZE):
                score += 2.5
                confirmations.append("✅ Bullish engulfing")
                factors["bullish_engulfing"] = True
        if len(self.df) >= 2:
            last = self.df.iloc[-1]
            body_size = abs(last.c - last.o)
            lower_wick = min(last.o, last.c) - last.l
            upper_wick = last.h - max(last.o, last.c)
            if (lower_wick > body_size * HAMMER_MIN_RATIO and 
                last.c > last.o and upper_wick < body_size * 0.3):
                score += 2.0
                confirmations.append("✅ Hammer reversal")
                factors["hammer"] = True
        if len(self.df) >= MIN_CONSECUTIVE_BARS:
            bullish_count = 0
            for i in range(-MIN_CONSECUTIVE_BARS, 0):
                if self.df.c.iloc[i] > self.df.o.iloc[i]:
                    bullish_count += 1
            if bullish_count >= MIN_CONSECUTIVE_BARS - 1:
                score += 1.5 * bullish_count
                confirmations.append(f"✅ {bullish_count} consecutive bullish bars")
                factors["consecutive_bullish"] = bullish_count
        if len(self.df) >= 20:
            avg_volume = self.df.v.rolling(20).mean().iloc[-1]
            if self.df.v.iloc[-1] > avg_volume * VOLUME_SPIKE_MIN and self.df.c.iloc[-1] > self.df.o.iloc[-1]:
                score += 1.5
                confirmations.append("✅ High volume on up move")
                factors["volume_spike_bullish"] = True
        if len(self.df) >= 14:
            gains = self.df.c.diff()
            gains = gains.where(gains > 0, 0)
            losses = -self.df.c.diff()
            losses = losses.where(losses > 0, 0)
            avg_gain = gains.rolling(14).mean().iloc[-1]
            avg_loss = losses.rolling(14).mean().iloc[-1]
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))
            if rsi < 35 and self.df.c.iloc[-1] > self.df.c.iloc[-2]:
                score += 1.5
                confirmations.append(f"✅ RSI bounce from {rsi:.1f}")
                factors["rsi_oversold"] = rsi
        if len(swings["highs"]) >= 2 and len(swings["lows"]) >= 2:
            if (swings["highs"][-1]["p"] > swings["highs"][-2]["p"] and 
                swings["lows"][-1]["p"] > swings["lows"][-2]["p"]):
                score += 2.0
                confirmations.append("✅ Higher highs & higher lows")
                factors["bullish_structure"] = True
        strength = "Weak"
        if score >= STRONG_SIGNAL_THRESHOLD:
            strength = "Strong"
        elif score >= MIN_CONFIDENCE_SCORE:
            strength = "Moderate"
        self.buy_analysis = {
            "score": round(score, 2),
            "confirmations": confirmations[:5],
            "strength": strength,
            "factors": factors
        }

    def _analyze_sell_side(self, swings, atr):
        score = 0
        confirmations = []
        factors = {}
        if "near_supply_zone" in self.market_structure:
            score += 3.0
            confirmations.append(f"✅ At supply zone: ${self.market_structure['near_supply_zone']:.2f}")
            factors["supply_zone"] = self.market_structure["near_supply_zone"]
        if "near_bearish_ob" in self.market_structure:
            score += 2.5
            confirmations.append(f"✅ At bearish order block: ${self.market_structure['near_bearish_ob']:.2f}")
            factors["bearish_ob"] = self.market_structure["near_bearish_ob"]
        if self.market_structure.get("amd_phase") == "Distribution":
            score += 2.0
            confirmations.append("✅ Distribution phase detected")
            factors["distribution"] = True
        resistances = [r["p"] for r in swings["highs"][-4:]] if swings["highs"] else []
        if resistances:
            closest_resistance = min([r for r in resistances if r > self.current_price], default=None)
            if closest_resistance:
                distance = closest_resistance - self.current_price
                if distance <= atr * 1.2:
                    score += 2.0
                    confirmations.append(f"✅ Near resistance: ${closest_resistance:.2f}")
                    factors["near_resistance"] = closest_resistance
        if len(self.df) >= 3:
            last = self.df.iloc[-1]
            prev = self.df.iloc[-2]
            if (last.c < last.o and prev.c > prev.o and 
                last.o >= prev.c and last.c <= prev.o and
                (last.h - last.l) > (prev.h - prev.l) * ENGULFING_MIN_SIZE):
                score += 2.5
                confirmations.append("✅ Bearish engulfing")
                factors["bearish_engulfing"] = True
        if len(self.df) >= 2:
            last = self.df.iloc[-1]
            body_size = abs(last.c - last.o)
            upper_wick = last.h - max(last.o, last.c)
            lower_wick = min(last.o, last.c) - last.l
            if (upper_wick > body_size * HAMMER_MIN_RATIO and 
                last.c < last.o and lower_wick < body_size * 0.3):
                score += 2.0
                confirmations.append("✅ Shooting star reversal")
                factors["shooting_star"] = True
        if len(self.df) >= MIN_CONSECUTIVE_BARS:
            bearish_count = 0
            for i in range(-MIN_CONSECUTIVE_BARS, 0):
                if self.df.c.iloc[i] < self.df.o.iloc[i]:
                    bearish_count += 1
            if bearish_count >= MIN_CONSECUTIVE_BARS - 1:
                score += 1.5 * bearish_count
                confirmations.append(f"✅ {bearish_count} consecutive bearish bars")
                factors["consecutive_bearish"] = bearish_count
        if len(self.df) >= 20:
            avg_volume = self.df.v.rolling(20).mean().iloc[-1]
            if self.df.v.iloc[-1] > avg_volume * VOLUME_SPIKE_MIN and self.df.c.iloc[-1] < self.df.o.iloc[-1]:
                score += 1.5
                confirmations.append("✅ High volume on down move")
                factors["volume_spike_bearish"] = True
        if len(self.df) >= 14:
            gains = self.df.c.diff()
            gains = gains.where(gains > 0, 0)
            losses = -self.df.c.diff()
            losses = losses.where(losses > 0, 0)
            avg_gain = gains.rolling(14).mean().iloc[-1]
            avg_loss = losses.rolling(14).mean().iloc[-1]
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))
            if rsi > 65 and self.df.c.iloc[-1] < self.df.c.iloc[-2]:
                score += 1.5
                confirmations.append(f"✅ RSI rejection from {rsi:.1f}")
                factors["rsi_overbought"] = rsi
        if len(swings["highs"]) >= 2 and len(swings["lows"]) >= 2:
            if (swings["highs"][-1]["p"] < swings["highs"][-2]["p"] and 
                swings["lows"][-1]["p"] < swings["lows"][-2]["p"]):
                score += 2.0
                confirmations.append("✅ Lower highs & lower lows")
                factors["bearish_structure"] = True
        strength = "Weak"
        if score >= STRONG_SIGNAL_THRESHOLD:
            strength = "Strong"
        elif score >= MIN_CONFIDENCE_SCORE:
            strength = "Moderate"
        self.sell_analysis = {
            "score": round(score, 2),
            "confirmations": confirmations[:5],
            "strength": strength,
            "factors": factors
        }

    def _determine_market_state(self):
        buy_score = self.buy_analysis["score"]
        sell_score = self.sell_analysis["score"]
        if buy_score >= STRONG_SIGNAL_THRESHOLD and sell_score < MIN_CONFIDENCE_SCORE:
            self.market_state = "Strongly Bullish"
        elif sell_score >= STRONG_SIGNAL_THRESHOLD and buy_score < MIN_CONFIDENCE_SCORE:
            self.market_state = "Strongly Bearish"
        elif buy_score >= MIN_CONFIDENCE_SCORE and sell_score >= MIN_CONFIDENCE_SCORE:
            if buy_score > sell_score + 1.0:
                self.market_state = "Bullish Bias"
            elif sell_score > buy_score + 1.0:
                self.market_state = "Bearish Bias"
            else:
                self.market_state = "Neutral/Conflict"
        elif buy_score >= MIN_CONFIDENCE_SCORE:
            self.market_state = "Bullish"
        elif sell_score >= MIN_CONFIDENCE_SCORE:
            self.market_state = "Bearish"
        else:
            self.market_state = "Neutral"

# ============================================
# MARKET ANALYSIS - COMPLETE
# ============================================
def analyze_market():
    market_analysis = {}
    for tf in TIMEFRAMES:
        df = TF_DATA.get(tf)
        if df is None or len(df) < 50:
            continue
        analyzer = AdvancedAnalyzer(df, tf)
        analysis = analyzer.analyze_both_sides()
        market_analysis[tf] = analysis
        if DEBUG_MODE:
            print(f"\n[{tf}] MARKET ANALYSIS:")
            print(f"  Price: ${analysis['price']:.2f}")
            print(f"  Market State: {analysis['market_state']}")
            print(f"  AMD Phase: {analysis['market_structure'].get('amd_phase', 'Unknown')}")
            print(f"  BUY Score: {analysis['buy']['score']} ({analysis['buy']['strength']})")
            print(f"  SELL Score: {analysis['sell']['score']} ({analysis['sell']['strength']})")
            if analysis['buy']['confirmations']:
                print(f"  Buy: {', '.join(analysis['buy']['confirmations'][:3])}")
            if analysis['sell']['confirmations']:
                print(f"  Sell: {', '.join(analysis['sell']['confirmations'][:3])}")

    htf_bias = 0
    htf_alignment_count = 0
    for tf, weight in MTF_WEIGHTS.items():
        if tf in market_analysis and tf != ENTRY_TIMEFRAME:
            state = market_analysis[tf]["market_state"]
            if "Bullish" in state:
                htf_bias += weight
                htf_alignment_count += 1
            elif "Bearish" in state:
                htf_bias -= weight
                htf_alignment_count += 1

    if ENTRY_TIMEFRAME in market_analysis:
        market_analysis[ENTRY_TIMEFRAME]["htf_bias"] = htf_bias
        market_analysis[ENTRY_TIMEFRAME]["htf_alignment_count"] = htf_alignment_count

    print(f"\n📊 TREND CONFIRMATION ({TREND_TIMEFRAME}):")
    print(f"  HTF Bias: {htf_bias:.1f}")
    print(f"  Aligned TFs: {htf_alignment_count}/{len(TIMEFRAMES)-1}")
    return market_analysis

def get_signal(market_analysis):
    global LAST_SIGNAL

    if not market_analysis or ENTRY_TIMEFRAME not in market_analysis:
        return "Hold", ["No market analysis available"], {}, {}

    now = datetime.now(pytz.utc)

    if LAST_SIGNAL["direction"] and LAST_SIGNAL["timestamp"]:
        minutes_since = (now - LAST_SIGNAL["timestamp"]).total_seconds() / 60
        if minutes_since < SAME_SIGNAL_COOLDOWN_MIN:
            return "Hold", [f"Cooldown ({int(SAME_SIGNAL_COOLDOWN_MIN - minutes_since)} min)"], {}, market_analysis
        else:
            LAST_SIGNAL["direction"] = None
            LAST_SIGNAL["timestamp"] = None

    m15_analysis = market_analysis[ENTRY_TIMEFRAME]
    h1_analysis = market_analysis.get(TREND_TIMEFRAME, {})

    buy_score = m15_analysis["buy"]["score"]
    sell_score = m15_analysis["sell"]["score"]
    market_state = m15_analysis["market_state"]
    htf_bias = m15_analysis.get("htf_bias", 0)
    htf_alignment = m15_analysis.get("htf_alignment_count", 0)

    h1_trend = h1_analysis.get("market_state", "Neutral")
    h1_buy_score = h1_analysis.get("buy", {}).get("score", 0)
    h1_sell_score = h1_analysis.get("sell", {}).get("score", 0)

    h1_aligned_buy = "Bullish" in h1_trend or h1_buy_score > h1_sell_score
    h1_aligned_sell = "Bearish" in h1_trend or h1_sell_score > h1_buy_score

    if (buy_score >= STRONG_SIGNAL_THRESHOLD and sell_score < MIN_CONFIDENCE_SCORE and
        htf_bias > 0 and htf_alignment >= MIN_HTF_ALIGNMENT and
        "Bullish" in market_state and h1_aligned_buy):

        direction = "Buy"
        reason = f"STRONG BUY: Score {buy_score:.1f} | H1 Trend: {h1_trend}"
        analysis_details = {
            "type": "Strong Buy", "score": buy_score,
            "confirmations": m15_analysis["buy"]["confirmations"][:5],
            "authentic": True,
            "market_structure": m15_analysis.get("market_structure", {}),
            "h1_trend": h1_trend
        }
        LAST_SIGNAL = {"direction": "Buy", "timestamp": now, "price": m15_analysis["price"], "score": buy_score}
        return direction, [reason], analysis_details, market_analysis

    elif (sell_score >= STRONG_SIGNAL_THRESHOLD and buy_score < MIN_CONFIDENCE_SCORE and
          htf_bias < 0 and htf_alignment >= MIN_HTF_ALIGNMENT and
          "Bearish" in market_state and h1_aligned_sell):

        direction = "Sell"
        reason = f"STRONG SELL: Score {sell_score:.1f} | H1 Trend: {h1_trend}"
        analysis_details = {
            "type": "Strong Sell", "score": sell_score,
            "confirmations": m15_analysis["sell"]["confirmations"][:5],
            "authentic": True,
            "market_structure": m15_analysis.get("market_structure", {}),
            "h1_trend": h1_trend
        }
        LAST_SIGNAL = {"direction": "Sell", "timestamp": now, "price": m15_analysis["price"], "score": sell_score}
        return direction, [reason], analysis_details, market_analysis

    else:
        direction = "Hold"
        reasons = []
        if not h1_aligned_buy and not h1_aligned_sell:
            reasons.append(f"H1 trend conflict: {h1_trend}")
        elif buy_score < MIN_CONFIDENCE_SCORE and sell_score < MIN_CONFIDENCE_SCORE:
            reasons.append(f"Insufficient confirmations (B:{buy_score:.1f}/S:{sell_score:.1f})")
        elif htf_alignment < MIN_HTF_ALIGNMENT:
            reasons.append(f"HTF alignment insufficient ({htf_alignment}/{MIN_HTF_ALIGNMENT})")
        else:
            reasons.append("No clear edge")
        reason = " | ".join(reasons)
        analysis_details = {"type": "Hold"}
        return direction, [reason], analysis_details, market_analysis

# ============================================
# RISK MANAGEMENT - COMPLETE
# ============================================
def calculate_sl_tp(signal, df, market_analysis, is_test_signal=False):
    if len(df) < 1:
        return None, None, None, None

    price = df.c.iloc[-1]

    if is_test_signal:
        if signal == "Buy":
            entry = price
            sl = entry - 10.00
            tp = entry + 18.00
        else:
            entry = price
            sl = entry + 10.00
            tp = entry - 18.00
        return round(sl, 2), round(tp, 2), 0.01, None

    if signal == "Buy":
        entry = price
        market_struct = market_analysis.get(ENTRY_TIMEFRAME, {}).get("market_structure", {})
        nearest_support = market_struct.get("near_demand_zone", None)

        if nearest_support and (entry - nearest_support) <= MAX_STOP_LOSS:
            sl = nearest_support - 0.50
        else:
            sl = entry - min(MAX_STOP_LOSS, entry * 0.002)

        if entry - sl > MAX_STOP_LOSS:
            sl = entry - MAX_STOP_LOSS

        risk = entry - sl
        tp = entry + (risk * 1.7)

        tp_distance = tp - entry
        if tp_distance < MIN_TAKE_PROFIT:
            tp = entry + MIN_TAKE_PROFIT
        elif tp_distance > MAX_TAKE_PROFIT:
            tp = entry + MAX_TAKE_PROFIT

        final_risk = entry - sl
        final_reward = tp - entry
        final_ratio = final_reward / final_risk if final_risk > 0 else 0

        if final_ratio > MAX_RISK_REWARD_RATIO and final_reward > 0:
            adjusted_risk = final_reward / MAX_RISK_REWARD_RATIO
            if adjusted_risk <= MAX_STOP_LOSS:
                sl = entry - adjusted_risk
                final_risk = adjusted_risk
                final_ratio = final_reward / final_risk

        print(f"\n📊 RISK MANAGEMENT:")
        print(f"  Entry: ${entry:.2f}")
        print(f"  Stop Loss: ${sl:.2f} (Risk: ${final_risk:.2f})")
        print(f"  Take Profit: ${tp:.2f} (Reward: ${final_reward:.2f})")
        print(f"  Risk/Reward: 1:{final_ratio:.2f}")

        if final_ratio < MIN_RISK_REWARD_RATIO or final_ratio > MAX_RISK_REWARD_RATIO:
            print(f"  ❌ Rejected: RR ratio {final_ratio:.2f} not in range {MIN_RISK_REWARD_RATIO}-{MAX_RISK_REWARD_RATIO}")
            return None, None, None, None
        if final_risk > MAX_STOP_LOSS:
            print(f"  ❌ Rejected: Risk ${final_risk:.2f} > ${MAX_STOP_LOSS}")
            return None, None, None, None

        return round(sl, 2), round(tp, 2), MT5_LOT_SIZE, None

    elif signal == "Sell":
        entry = price
        market_struct = market_analysis.get(ENTRY_TIMEFRAME, {}).get("market_structure", {})
        nearest_resistance = market_struct.get("near_supply_zone", None)

        if nearest_resistance and (nearest_resistance - entry) <= MAX_STOP_LOSS:
            sl = nearest_resistance + 0.50
        else:
            sl = entry + min(MAX_STOP_LOSS, entry * 0.002)

        if sl - entry > MAX_STOP_LOSS:
            sl = entry + MAX_STOP_LOSS

        risk = sl - entry
        tp = entry - (risk * 1.7)

        tp_distance = entry - tp
        if tp_distance < MIN_TAKE_PROFIT:
            tp = entry - MIN_TAKE_PROFIT
        elif tp_distance > MAX_TAKE_PROFIT:
            tp = entry - MAX_TAKE_PROFIT

        final_risk = sl - entry
        final_reward = entry - tp
        final_ratio = final_reward / final_risk if final_risk > 0 else 0

        if final_ratio > MAX_RISK_REWARD_RATIO and final_reward > 0:
            adjusted_risk = final_reward / MAX_RISK_REWARD_RATIO
            if adjusted_risk <= MAX_STOP_LOSS:
                sl = entry + adjusted_risk
                final_risk = adjusted_risk
                final_ratio = final_reward / final_risk

        print(f"\n📊 RISK MANAGEMENT:")
        print(f"  Entry: ${entry:.2f}")
        print(f"  Stop Loss: ${sl:.2f} (Risk: ${final_risk:.2f})")
        print(f"  Take Profit: ${tp:.2f} (Reward: ${final_reward:.2f})")
        print(f"  Risk/Reward: 1:{final_ratio:.2f}")

        if final_ratio < MIN_RISK_REWARD_RATIO or final_ratio > MAX_RISK_REWARD_RATIO:
            print(f"  ❌ Rejected: RR ratio {final_ratio:.2f} not in range {MIN_RISK_REWARD_RATIO}-{MAX_RISK_REWARD_RATIO}")
            return None, None, None, None
        if final_risk > MAX_STOP_LOSS:
            print(f"  ❌ Rejected: Risk ${final_risk:.2f} > ${MAX_STOP_LOSS}")
            return None, None, None, None

        return round(sl, 2), round(tp, 2), MT5_LOT_SIZE, None

    return None, None, None, None

# ============================================
# MAIN CYCLE - COMPLETE (NO MT5, NO GUI)
# ============================================
def run_cycle():
    global SIGNAL_STATS
    SIGNAL_STATS["total_cycles"] += 1

    now_pk = datetime.now(PK_TZ)
    print(f"\n{'='*60}")
    print(f"[{now_pk:%Y-%m-%d %H:%M:%S PKT}] CYCLE #{SIGNAL_STATS['total_cycles']}")
    print(f"{'='*60}")

    if is_news_blocked():
        print("→ Trading paused – high-impact news")
        SIGNAL_STATS["hold_signals"] += 1
        return

    print("\n📡 FETCHING MARKET DATA...")
    update_data()

    if ENTRY_TIMEFRAME not in TF_DATA or TF_DATA[ENTRY_TIMEFRAME] is None or len(TF_DATA[ENTRY_TIMEFRAME]) < 50:
        print(f"→ Insufficient {ENTRY_TIMEFRAME} data")
        SIGNAL_STATS["hold_signals"] += 1
        return

    print("\n🔍 ANALYZING MARKET CONDITIONS...")
    market_analysis = analyze_market()

    if not market_analysis:
        print("→ Market analysis failed")
        SIGNAL_STATS["hold_signals"] += 1
        return

    print("\n🎯 GENERATING TRADING SIGNAL...")
    signal, reasons, analysis_details, full_analysis = get_signal(market_analysis)

    if signal in ["Buy", "Sell"]:
        df_entry = TF_DATA[ENTRY_TIMEFRAME]
        sl, tp, lot_size, _ = calculate_sl_tp(signal, df_entry, market_analysis, is_test_signal=False)

        if sl is None or tp is None:
            print("→ Signal filtered - Failed risk management checks")
            SIGNAL_STATS["hold_signals"] += 1
            return

        entry = df_entry.c.iloc[-1]
        rr = abs(tp-entry)/abs(entry-sl)

        print(f"\n{'='*50}")
        print(f"🎯 {signal.upper()} SIGNAL!")
        print(f"{'='*50}")
        print(f"  Entry: ${entry:.2f}")
        print(f"  SL: ${sl:.2f} (Risk: ${abs(entry-sl):.2f})")
        print(f"  TP: ${tp:.2f} (Reward: ${abs(tp-entry):.2f})")
        print(f"  RR: {rr:.2f}:1")
        print(f"  H1 Trend: {analysis_details.get('h1_trend', 'N/A')}")

        market_struct = analysis_details.get("market_structure", {})
        if market_struct.get("amd_phase"):
            print(f"  AMD Phase: {market_struct.get('amd_phase')}")
        if market_struct.get("near_demand_zone"):
            print(f"  Demand Zone: ${market_struct.get('near_demand_zone'):.2f}")
        if market_struct.get("near_supply_zone"):
            print(f"  Supply Zone: ${market_struct.get('near_supply_zone'):.2f}")

        print(f"  Reason: {reasons[0]}")
        if "confirmations" in analysis_details and analysis_details["confirmations"]:
            print(f"  Confirmations:")
            for conf in analysis_details["confirmations"][:3]:
                print(f"    • {conf}")
        print(f"{'='*50}")

        # Send Telegram Alert
        market_state = market_analysis[ENTRY_TIMEFRAME]["market_state"]
        amd_phase = market_struct.get("amd_phase", "Unknown")
        send_telegram_signal(signal, entry, sl, tp, rr, reasons[0], market_state, amd_phase)

        # Save to file
        with open("/storage/emulated/0/signals.txt", "a") as f:
            f.write(f"[{now_pk}] {signal} | Entry: ${entry:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f} | RR: 1:{rr:.2f}\n")

        SIGNAL_STATS[signal.lower() + "_signals"] += 1
    else:
        SIGNAL_STATS["hold_signals"] += 1
        print(f"\n→ Signal: {signal} | {reasons[0]}")

    print(f"\n📊 STATS: Cycles: {SIGNAL_STATS['total_cycles']} | "
          f"Buy: {SIGNAL_STATS['buy_signals']} | "
          f"Sell: {SIGNAL_STATS['sell_signals']} | "
          f"Hold: {SIGNAL_STATS['hold_signals']}")
    print(f"{'='*60}\n")

def force_signal_manual():
    print("\n" + "="*60)
    print("🧪 TEST SIGNAL - FOLLOWING COMPULSORY RULES")
    print("="*60)

    if ENTRY_TIMEFRAME not in TF_DATA or TF_DATA[ENTRY_TIMEFRAME] is None:
        print("⚠️ No data available")
        return

    df = TF_DATA[ENTRY_TIMEFRAME]
    current_price = df.c.iloc[-1]

    global SIGNAL_STATS
    if SIGNAL_STATS["total_cycles"] % 2 == 0:
        signal = "Buy"
        sl = current_price - 10.00
        tp = current_price + 18.00
    else:
        signal = "Sell"
        sl = current_price + 10.00
        tp = current_price - 18.00

    analysis_details = {
        "type": "TEST SIGNAL",
        "score": STRONG_SIGNAL_THRESHOLD,
        "authentic": True,
        "confirmations": ["✅ Test Mode", f"✅ Max SL: ${MAX_STOP_LOSS}", f"✅ Min TP: ${MIN_TAKE_PROFIT}-${MAX_TAKE_PROFIT}"],
        "h1_trend": "Test Mode",
        "market_structure": {"amd_phase": "Test Mode"}
    }

    rr = abs(tp-current_price)/abs(current_price-sl)

    print(f"\n🎯 TEST {signal.upper()} SIGNAL")
    print(f"  Entry: ${current_price:.2f}")
    print(f"  SL: ${sl:.2f} (Risk: $10.00)")
    print(f"  TP: ${tp:.2f} (Reward: $18.00)")
    print(f"  RR: 1:1.8")

    # Send Telegram for test signal too
    send_telegram_signal(signal, current_price, sl, tp, rr, "Manual test signal", "Test Mode", "Test Mode")

    SIGNAL_STATS[signal.lower() + "_signals"] += 1
    play_alert_sound()

# ============================================
# BOT WORKER - NO GUI VERSION
# ============================================
class BotWorker:
    def __init__(self):
        self.running = True

    def run(self):
        while self.running:
            try:
                run_cycle()
            except Exception as e:
                print(f"❌ Cycle error: {e}")
            time.sleep(60)

    def stop(self):
        self.running = False

# ============================================
# MAIN ENTRY POINT - NO GUI
# ============================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🎯 XAU/USD TRADING BOT - ANDROID VERSION")
    print("="*70)
    print(f"📊 ENTRY: {ENTRY_TIMEFRAME} | TREND: {TREND_TIMEFRAME}")
    print(f"💰 MAX SL: ${MAX_STOP_LOSS} | MIN TP: ${MIN_TAKE_PROFIT}-${MAX_TAKE_PROFIT}")
    print(f"📈 RR RATIO: 1:{MIN_RISK_REWARD_RATIO} to 1:{MAX_RISK_REWARD_RATIO}")
    print("🏗️ MARKET STRUCTURE: AMD | Zones | Order Blocks | Large Moves")
    print("")
    print("🤖 Telegram notifications ENABLED")
    print("⚠️ Signals will be sent to your Telegram")
    print("="*70)

    # Test connection
    print("\n📡 Testing OANDA connection...")
    test_df = fetch_candles("M15", 10)
    if test_df is not None:
        print("✅ OANDA API connected successfully")
        send_telegram_startup()
        print("✅ Telegram notification sent")
    else:
        print("❌ OANDA API connection failed. Check your internet.")

    print("\n🤖 Bot is running... You will receive signals on Telegram")
    print("Press Ctrl+C to stop\n")

    worker = BotWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        print("\n\n⏹️ Bot stopped by user")
        print("\n📊 FINAL STATISTICS:")
        print(f"Total Cycles: {SIGNAL_STATS['total_cycles']}")
        print(f"Buy Signals: {SIGNAL_STATS['buy_signals']}")
        print(f"Sell Signals: {SIGNAL_STATS['sell_signals']}")
        print(f"Total Signals: {SIGNAL_STATS['buy_signals'] + SIGNAL_STATS['sell_signals']}")