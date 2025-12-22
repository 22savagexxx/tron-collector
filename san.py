import requests
import json
import os
import time
import sqlite3
import threading
import logging
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

# === НАСТРОЙКИ ===
ACCESS_TOKEN = "ory_at_n2Bt-9M9HNWphG8OAXYW2JAbMtCEgpEv6tl_xmqZz1M.OAzuu6d5wqRX0lwhubosG-yXgw5D7VxbnZBuhLLfpOk"
ENDPOINT = "https://graphql.bitquery.io"

# BSC USDT Contract (BSC-USD / BEP20)
USDT_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"

DB_FILE = "bsc_data.db"
RESULTS_FILE = "bsc_results.json"
CHECKED_ADDRESSES_FILE = "bsc_checked_cache.json"

PAGE_SIZE = 5000
MAX_RETRIES = 3
REQUESTS_PER_SECOND = 10  # Для платного тарифа
MAX_CONCURRENT = 10  # Для платного тарифа

# Период (BSC запустился в сентябре 2020)
TRANSFER_PERIOD_START = datetime(2020, 9, 1, tzinfo=timezone.utc)
TRANSFER_PERIOD_END = datetime(2021, 3, 1, tzinfo=timezone.utc)
ACTIVITY_CUTOFF = datetime(2021, 7, 1, tzinfo=timezone.utc)

MIN_BALANCE = 1000
MAX_BALANCE = 100000

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("bsc_debug.log"), logging.StreamHandler()]
)


class RateLimiter:
    def __init__(self, rate):
        self.interval = 1.0 / rate
        self.last_request = 0
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self.last_request = time.time()


rate_limiter = RateLimiter(REQUESTS_PER_SECOND)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS wallets')
    cursor.execute('''
        CREATE TABLE wallets (
            address TEXT PRIMARY KEY,
            balance REAL DEFAULT 0,
            last_ts INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX idx_filter ON wallets(balance, last_ts)')
    conn.commit()
    return conn


def graphql_query(query, variables=None, retry=0):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN.strip()}"}
    try:
        response = requests.post(ENDPOINT, json={"query": query, "variables": variables or {}}, headers=headers,
                                 timeout=90)
        if response.status_code == 200:
            res = response.json()
            if "errors" in res:
                logging.error(f"API Error: {res['errors']}")
                return None
            return res
        if retry < MAX_RETRIES and response.status_code >= 500:
            time.sleep(5)
            return graphql_query(query, variables, retry + 1)
    except Exception as e:
        logging.error(f"Connection error: {e}")
    return None


def fetch_and_process(conn, since, till):
    # BSC использует ту же структуру что и Ethereum в v1 API
    query = """
    query GetBSC($offset: Int!, $limit: Int!, $currency: String!, $since: ISO8601DateTime!, $till: ISO8601DateTime!) {
      ethereum(network: bsc) {
        transfers(
          options: {limit: $limit, offset: $offset, asc: "block.timestamp.time"}
          time: {since: $since, till: $till}
          currency: {is: $currency}
          amount: {gt: 0}
        ) {
          sender { address }
          receiver { address }
          amount
          block { timestamp { time(format: "%Y-%m-%d %H:%M:%S") } }
        }
      }
    }
    """
    offset = 0
    total = 0
    while True:
        vars = {"offset": offset, "limit": PAGE_SIZE, "currency": USDT_CONTRACT, "since": since, "till": till}
        data = graphql_query(query, vars)
        if not data: break
        transfers = data.get("data", {}).get("ethereum", {}).get("transfers", [])
        if not transfers: break
        
        cursor = conn.cursor()
        for t in transfers:
            try:
                s, r, amt = t["sender"]["address"], t["receiver"]["address"], float(t["amount"])
                ts = int(datetime.strptime(t["block"]["timestamp"]["time"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc).timestamp())
                cursor.execute(
                    'INSERT INTO wallets (address, balance, last_ts) VALUES (?, ?, ?) ON CONFLICT(address) DO UPDATE SET balance=balance-excluded.balance, last_ts=MAX(last_ts, excluded.last_ts)',
                    (s, amt, ts))
                cursor.execute(
                    'INSERT INTO wallets (address, balance, last_ts) VALUES (?, ?, ?) ON CONFLICT(address) DO UPDATE SET balance=balance+excluded.balance, last_ts=MAX(last_ts, excluded.last_ts)',
                    (r, amt, ts))
            except:
                continue
        conn.commit()
        
        total += len(transfers)
        logging.info(f"   BSC Загружено: {offset + len(transfers)}")
        if len(transfers) < PAGE_SIZE: break
        offset += PAGE_SIZE
        time.sleep(0.05)
    return total


def get_current_info_bsc(address):
    rate_limiter.wait()
    query = """
    query GetBSCInfo($address: String!, $currency: String!) {
      ethereum(network: bsc) {
        address(address: {is: $address}) {
          balances(currency: {is: $currency}) { value }
        }
        # Проверяем только ИСХОДЯЩИЕ транзакции (то есть активность владельца)
        lastTransfer: transfers(
          options: {desc: "block.timestamp.time", limit: 1}
          sender: {is: $address}
          currency: {is: $currency}
        ) {
          block { timestamp { time(format: "%Y-%m-%d %H:%M:%S") } }
        }
      }
    }
    """
    data = graphql_query(query, {"address": address, "currency": USDT_CONTRACT})
    try:
        eth = data["data"]["ethereum"]
        bal = float(eth["address"][0]["balances"][0]["value"]) if eth["address"] and eth["address"][0][
            "balances"] else 0.0
        
        # Если исходящих транзакций вообще не было, last_activity будет None
        last = eth["lastTransfer"][0]["block"]["timestamp"]["time"] if eth["lastTransfer"] else "1970-01-01 00:00:00"
        return {"balance": bal, "last_activity": last}
    except Exception as e:
        return {"balance": 0.0, "last_activity": None}


def main():
    db_conn = init_db()
    logging.info("🚀 BSC USDT Script Started")
    
    curr = TRANSFER_PERIOD_START
    while curr < TRANSFER_PERIOD_END:
        # Для BSC можно брать шаг в 2-3 дня
        nxt = min(curr + timedelta(days=2), TRANSFER_PERIOD_END)
        s_str, t_str = curr.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")
        logging.info(f"📅 Period: {s_str} - {t_str}")
        fetch_and_process(db_conn, s_str, t_str)
        curr = nxt
    
    logging.info("🔍 Filtering candidates in local DB...")
    cursor = db_conn.cursor()
    cursor.execute("SELECT address, balance, last_ts FROM wallets WHERE balance BETWEEN ? AND ? AND last_ts < ?",
                   (MIN_BALANCE, MAX_BALANCE, int(ACTIVITY_CUTOFF.timestamp())))
    candidates = cursor.fetchall()
    logging.info(f"✅ Candidates for API check: {len(candidates)}")
    
    if not candidates:
        logging.info("No candidates found. Done.")
        return
    
    final_results = {}
    if os.path.exists(CHECKED_ADDRESSES_FILE):
        with open(CHECKED_ADDRESSES_FILE, "r") as f:
            checked_cache = json.load(f)
    else:
        checked_cache = {}
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        future_to_addr = {executor.submit(get_current_info_bsc, c[0]): c[0] for c in candidates if
                          c[0] not in checked_cache}
        for i, future in enumerate(future_to_addr):
            addr, info = future_to_addr[future], future.result()
            checked_cache[addr] = info
            if info["last_activity"]:
                last_dt = datetime.strptime(info["last_activity"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if MIN_BALANCE <= info["balance"] <= MAX_BALANCE and last_dt < ACTIVITY_CUTOFF:
                    final_results[addr] = info
                    logging.info(f" ✨ FOUND BSC WALLET: {addr} | Balance: {info['balance']}")
            if i % 50 == 0:
                with open(CHECKED_ADDRESSES_FILE, "w") as f: json.dump(checked_cache, f)
    
    with open(RESULTS_FILE, "w") as f:
        json.dump(final_results, f, indent=2)
    logging.info(f"🎉 Process Finished. Found: {len(final_results)}")


if __name__ == "__main__":
    main()