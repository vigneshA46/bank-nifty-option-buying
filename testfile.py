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

GSHEET_URL = "https://script.google.com/macros/s/AKfycbyLk6BmJzhni-2qD-nwV1gNWTx9a4viId6_veR0_jZhI9u9Tv85CMrmzg3V-LhLYzk2/exec"



IDX_INTRADAY_URL="https://api.dhan.co/v2/charts/intraday"

ACCESS_TOKEN=os.getenv("ACCESS_TOKEN")
IDXHEADERS = {
    "Content-Type": "application/json",
    "access-token": ACCESS_TOKEN,
}




def fetch_index_intraday(trade_date: str):
    payload = {
        "securityId": "25",
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "interval": "1",
        "fromDate": f"{trade_date} 09:14:00",
        "toDate": f"{trade_date} 09:16:00"
    }

    r = requests.post(IDX_INTRADAY_URL, headers=IDXHEADERS, json=payload)
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


def log_trade_sheet():
    payload = {
    "sheet": "BankNiftyTrade",   # 👈 your tab name
    "row": [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "BANKNIFTY",
        "CE",
        "123456",
        "BUY",
        450.25,
        468.50,
        1,
        25,
        456.25,
        456.25,
        "TEST ENTRY",
        "TEST EXIT",
        58200,
        20,
        30
    ]
}

    try:
        r = requests.post(GSHEET_URL, json=payload, timeout=5)

        print("📤 Sheet Status:", r.status_code)
        print("📤 Sheet Response:", r.text)

    except Exception as e:
        print("❌ Sheet Trade Log Error:", e)




log_trade_sheet()