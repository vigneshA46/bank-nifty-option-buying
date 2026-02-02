from datetime import datetime, time as dtime
import time
import pytz
from dhanhq import marketfeed
import threading
from dotenv import load_dotenv
import os
import requests
import pandas as pd
from io import StringIO

load_dotenv()

INTERVAL=1
ACCESS_TOKEN=os.getenv("ACCESS_TOKEN")
CLIENT_ID=os.getenv("CLIENT_ID")
BASE_URL = "https://api.dhan.co/v2"
FNO_MASTER_URL = f"{BASE_URL}/instrument/NSE_FNO"
IDX_INTRADAY_URL=f"{BASE_URL}/charts/intraday"
GSHEET_URL=os.getenv("SHEETS")

IST = pytz.timezone("Asia/Kolkata")

HEADERS = {
    "Accept":"application/json",
    "Content-Type": "application/json",
    "access-token": ACCESS_TOKEN,
    "client-id": "1107425275"
}

# ================= STRATEGY CONFIG =================

TSL_TRIGGER = 40
SL_GAP = 15
TRAIL_STEP = 10

TICK_ENTRY_BUFFER = 25
TICK_EXIT_BUFFER = 25

MAX_LOT = 5
TARGET_PNL = 100

current_lot = 1
trading_enabled = True

cumulative_pnl = 0
max_profit = 0
max_dd = 0
total_trades = 0
ce_trades = 0
pe_trades = 0
engine_start_time = datetime.now(IST).strftime("%H:%M:%S")


def log_trade_sheet(
    symbol, opt_type, sec_id, side,
    entry, exitp, lots, qty, pnl, cum_pnl,
    entry_reason, exit_reason,
    marked_line, tsl, sl
):
    payload = {
        "type": "TRADE",
        "row": [
            datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            opt_type,
            sec_id,
            side,
            entry,
            exitp,
            lots,
            qty,
            round(pnl, 2),
            round(cum_pnl, 2),
            entry_reason,
            exit_reason,
            marked_line,
            tsl,
            sl
        ]
    }

    try:
        requests.post(GSHEET_URL, json=payload, timeout=3)
    except Exception as e:
        print("❌ Sheet Trade Log Error:", e)



def log_day_sheet(
    trade_date, atm, start_time, end_time,
    total_trades, ce_trades, pe_trades,
    day_pnl, max_profit, max_dd,
    exit_reason, notes=""
):
    payload = {
        "type": "LOGGER",
        "row": [
            trade_date,
            "banknifty_option_buying",
            atm,
            start_time,
            end_time,
            total_trades,
            ce_trades,
            pe_trades,
            round(day_pnl, 2),
            round(max_profit, 2),
            round(max_dd, 2),
            exit_reason,
            notes
        ]
    }

    try:
        requests.post(GSHEET_URL, json=payload, timeout=3)
    except Exception as e:
        print("❌ Sheet Day Log Error:", e)



def wait_for_start():
    print("⏳ Waiting for 09:16:00 ...")
    while True:
        now = datetime.now(IST).time()
        if now >= dtime(9, 16):
            print("✅ Market Start Triggered")
            break
        time.sleep(1)

def calculate_atm(price, step=100):
    return int(round(price / step) * step)

def fetch_index_intraday(trade_date: str):
    payload = {
        "securityId": "25",
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "interval": INTERVAL,
        "fromDate": f"{trade_date} 09:14:00",
        "toDate": f"{trade_date} 09:16:00"
    }

    r = requests.post(IDX_INTRADAY_URL, headers=HEADERS, json=payload)
    r.raise_for_status()
    data = r.json()

    df = pd.DataFrame({
        "timestamp": data["timestamp"],
        "open": data["open"],
        "high": data["high"],
        "low": data["low"],
        "close": data["close"]
    })

    dt = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df["datetime"] = dt.dt.tz_convert(IST)
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df

def find_option_security(df, strike, option_type, trade_date):
    trade_date = pd.to_datetime(trade_date)

    opt = df[
        (df["INSTRUMENT"] == "OPTIDX") &
        (df["UNDERLYING_SYMBOL"] == "BANKNIFTY") &
        (df["STRIKE_PRICE"] == strike) &
        (df["OPTION_TYPE"] == option_type) &
        (df["SM_EXPIRY_DATE"] >= trade_date)
    ]

    if opt.empty:
        raise ValueError(f"❌ No {option_type} found for strike {strike}")

    return opt.sort_values("SM_EXPIRY_DATE").iloc[0]


def get_banknifty_atm(trade_date):
    df = fetch_index_intraday(trade_date)

    first_candle = df.iloc[0]
    close_price = first_candle["close"]

    atm = calculate_atm(close_price)

    print(f"📌 BANKNIFTY Close @09:15 = {close_price}")
    print(f"🎯 ATM Strike = {atm}")

    return atm


def discover_options(atm, trade_date):
    df = load_fno_master()

    ce = find_option_security(df, atm, "CE", trade_date)
    pe = find_option_security(df, atm, "PE", trade_date)

    print(f"✅ CE -> {ce['SECURITY_ID']} {ce['DISPLAY_NAME']}")
    print(f"✅ PE -> {pe['SECURITY_ID']} {pe['DISPLAY_NAME']}")

    return ce, pe



def build_feed_instruments(ce, pe):
    instruments = [
        (marketfeed.NSE_FNO, str(ce["SECURITY_ID"]), marketfeed.Quote),
        (marketfeed.NSE_FNO, str(pe["SECURITY_ID"]), marketfeed.Quote),
    ]
    return instruments

def start_market_feed(instruments, client_id, access_token):
    dhan_context = DhanContext(client_id, access_token)
    market_feed = marketfeed(CLIENT_ID , ACCESS_TOKEN, instruments, version="v2")

    print("🚀 Connecting to Dhan Market Feed...")
    market_feed.run_forever()

    return market_feed


def load_fno_master():
    print("dowloading FNO master")
    r = requests.get(FNO_MASTER_URL)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text), header=None, low_memory=False)

    df.columns = [
        "EXCH_ID","SEGMENT","SECURITY_ID","ISIN","INSTRUMENT",
        "UNDERLYING_SECURITY_ID","UNDERLYING_SYMBOL","SYMBOL_NAME",
        "DISPLAY_NAME","INSTRUMENT_TYPE","SERIES","LOT_SIZE",
        "SM_EXPIRY_DATE","STRIKE_PRICE","OPTION_TYPE","TICK_SIZE",
        "EXPIRY_FLAG","BRACKET_FLAG","COVER_FLAG","ASM_GSM_FLAG",
        "ASM_GSM_CATEGORY","BUY_SELL_INDICATOR",
        "BUY_CO_MIN_MARGIN_PER","BUY_CO_SL_RANGE_MAX_PERC",
        "BUY_CO_SL_RANGE_MIN_PERC","BUY_BO_MIN_MARGIN_PER",
        "BUY_BO_PROFIT_RANGE_MAX_PERC","BUY_BO_PROFIT_RANGE_MIN_PERC",
        "MTF_LEVERAGE","RESERVED"
    ]

    df["STRIKE_PRICE"] = pd.to_numeric(df["STRIKE_PRICE"], errors="coerce")
    df["SM_EXPIRY_DATE"] = pd.to_datetime(df["SM_EXPIRY_DATE"], errors="coerce")
    print("result of FNO master ")
    print(df)
    return df


def normalize_tick(tick):
    if tick.get("type") != "Quote Data":
        return None

    return {
        "security_id": tick["security_id"],
        "price": float(tick["LTP"]),
        "avg": float(tick["avg_price"]),
        "time": tick["LTT"]
    }



class CandleBuilder:
    def __init__(self):
        self.current_minute = None
        self.ohlc = None

    def update(self, price, tick_time):
        now = datetime.now(IST)
        t = datetime.strptime(tick_time, "%H:%M:%S").replace(
        year=now.year, month=now.month, day=now.day
        )
        minute = t.replace(second=0)

        closed = None

        if self.current_minute != minute:
            closed = self.ohlc
            self.current_minute = minute
            self.ohlc = {
                "open": price,
                "high": price,
                "low": price,
                "close": price
            }
        else:
            self.ohlc["high"] = max(self.ohlc["high"], price)
            self.ohlc["low"] = min(self.ohlc["low"], price)
            self.ohlc["close"] = price

        return closed


class OptionState:
    def __init__(self, name):
        self.name = name

        self.marked_price = None

        self.position = False
        self.entry_price = None
        self.lots = 0

        self.tsl = None
        self.sl = None
        self.tsl_active = False

        self.pending_entry = False
        self.reentry_allowed = True

        self.pnl = 0

def execute_entry(state, price):
    global current_lot

    lots = min(current_lot, MAX_LOT)
    current_lot = min(current_lot + 1, MAX_LOT)

    state.position = True
    state.entry_price = price
    state.lots = lots

    state.tsl_active = False
    state.tsl = None
    state.sl = None
    state.entry_reason = "TICK_25" if price >= state.marked_price + TICK_ENTRY_BUFFER else "CANDLE_BREAK"

    print(f"🟢 ENTRY {state.name} @ {price} | Lots {lots}")

def execute_exit(state, price, reason):
    global cumulative_pnl, total_trades, ce_trades, pe_trades, max_profit, max_dd, current_lot

    pnl = (price - state.entry_price) * state.lots
    cumulative_pnl += pnl
    state.pnl += pnl
    total_trades += 1
    if state.name.endswith("CE"):
        ce_trades += 1
    else:
        pe_trades += 1

    max_profit = max(max_profit, cumulative_pnl)
    max_dd = min(max_dd, cumulative_pnl)

    log_trade_sheet(
        symbol="BANKNIFTY",
        opt_type="CE" if "CE" in state.name else "PE",
        sec_id=state.name,
        side="BUY",
        entry=state.entry_price,
        exitp=price,
        lots=state.lots,
        qty=state.lots * 15,
        pnl= pnl,
        cum_pnl=cumulative_pnl,
        entry_reason=state.entry_reason,
        exit_reason=reason,
        marked_line=state.marked_price,
        tsl=state.tsl,
        sl=state.sl
    )


    print(f"🔴 EXIT {state.name} @ {price} | PNL {pnl:.2f} | Reason {reason}")
    print(f"💰 CUM PNL = {cumulative_pnl:.2f}")

    if reason == "TSL_SL":
        current_lot = 1

    state.position = False
    state.entry_price = None
    state.lots = 0
    state.tsl_active = False
    state.tsl = None
    state.sl = None
    state.pending_entry = False

    if reason == "TSL_SL":
        state.reentry_allowed = False

def process_strategy(sec, price, avg, candle, state):
    global trading_enabled

    if not trading_enabled:
        return

    # ---------------- MARK FIRST CANDLE ----------------
    if state.marked_price is None and candle:
        state.marked_price = candle["close"]
        print(f"📌 MARKED {sec} @ {state.marked_price}")
        return

    # ---------------- REENTRY RESET ----------------
    if not state.reentry_allowed and price < state.marked_price:
        state.reentry_allowed = True
        print(f"🔁 REENTRY ENABLED {sec}")

    # ---------------- ENTRY LOGIC ----------------
    if not state.position and state.reentry_allowed:

        # Tick +25 entry
        if price >= state.marked_price + TICK_ENTRY_BUFFER:
            execute_entry(state, price)
            return

        # Candle based entry
        if candle and candle["close"] > state.marked_price:
            if avg > state.marked_price and avg < candle["close"]:
                state.pending_entry = True

        # Execute pending entry on FIRST TICK of next candle
        if state.pending_entry and not state.position:
            execute_entry(state, price)
            state.pending_entry = False
            return

    # ---------------- POSITION MANAGEMENT ----------------
    if state.position:

        # Activate TSL
        if not state.tsl_active and price >= state.entry_price + TSL_TRIGGER:
            state.tsl_active = True
            state.tsl = state.entry_price + TSL_TRIGGER
            state.sl = state.tsl - SL_GAP

            print(f"🟡 TSL ACTIVE {sec} | TSL {state.tsl} SL {state.sl}")

        # Trail
        if state.tsl_active:
            if price - state.tsl >= TRAIL_STEP:
                state.tsl += TRAIL_STEP
                state.sl = state.tsl - SL_GAP

        # Tick exit
        if price <= state.marked_price - TICK_EXIT_BUFFER:
            execute_exit(state, price, "MARK_-25")
            return

        if state.tsl_active and price <= state.sl:
            execute_exit(state, price, "TSL_SL")
            return

        # Candle exit
        if candle and candle["close"] < state.marked_price:
            execute_exit(state, candle["close"], "CANDLE_BREAK")
            return


def universal_risk_check(feed):
    global trading_enabled

    now = datetime.now(IST).time()

    if cumulative_pnl >= TARGET_PNL:
        print("🏁 TARGET HIT. STOPPING.")
        trading_enabled = False
        feed.disconnect()
        log_day_sheet(
        trade_date,
        atm ,
        engine_start_time,
        datetime.now(IST).strftime("%H:%M:%S"),
        total_trades,
        ce_trades,
        pe_trades,
        cumulative_pnl,
        max_profit,
        max_dd,
        exit_reason="TARGET_HIT"
    )


    if now >= dtime(15,20):
        print("⏰ TIME EXIT. STOPPING.")
        trading_enabled = False
        feed.disconnect()
        log_day_sheet(
        trade_date,
        atm ,
        engine_start_time,
        datetime.now(IST).strftime("%H:%M:%S"),
        total_trades,
        ce_trades,
        pe_trades,
        cumulative_pnl,
        max_profit,
        max_dd,
        exit_reason="TIME_EXIT"
    )


if __name__ == "__main__":  

    trade_date = datetime.now(IST).strftime("%Y-%m-%d")

    wait_for_start()

    atm = get_banknifty_atm(trade_date)

    ce, pe = discover_options(atm, trade_date)

    ce_security = ce["SECURITY_ID"]
    pe_security = pe["SECURITY_ID"]   # <-- FIXED
    print("security ids")
    print(ce_security, pe_security)

    feed = marketfeed.DhanFeed(
        CLIENT_ID,
        ACCESS_TOKEN,
        [
            (marketfeed.NSE_FNO, str(ce_security), marketfeed.Quote),
            (marketfeed.NSE_FNO, str(pe_security), marketfeed.Quote),
            
        ],
        version="v2"
    )

    print("✅ Live Feed Started")

    # ---------------- INIT ONCE ----------------
    builders = {}
    states = {}

    for sec in [ce_security,pe_security]:
        sec = str(sec)
        builders[sec] = CandleBuilder()
        states[sec] = OptionState(sec)

    # ---------------- START FEED ----------------
    threading.Thread(target=feed.run_forever, daemon=True).start()

    # ---------------- MAIN LOOP ----------------
    while True:

        tick = feed.get_data()
        if not tick:
            continue

        nt = normalize_tick(tick)
        if not nt:
            continue

        sec = str(nt["security_id"])
        price = nt["price"]
        avg = nt["avg"]
        ttime = nt["time"]

        candle = builders[sec].update(price, ttime)

        process_strategy(sec, price, avg, candle, states[sec])

        universal_risk_check(feed)

        if candle:
            print(f"🕯 Candle Closed {sec} -> {candle}")
