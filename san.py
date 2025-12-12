import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import threading

# === НАСТРОЙКИ ===
ACCESS_TOKEN = "ory_at_t4axr0lstK769pREYxgt3JapM-UrrdA-GKp2umCPxmc.8k7wYUkAs4ient9Wr64CHHB9d8qy3uPbGTbZT_RpjTs"
ENDPOINT = "https://graphql.bitquery.io"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
CACHE_DIR = "cache_months"
RESULTS_FILE = "wallets_results.json"
CHECKED_ADDRESSES_FILE = "checked_addresses.json"
PAGE_SIZE = 5000
MAX_RETRIES = 3

# === НОВЫЕ НАСТРОЙКИ ПАРАЛЛЕЛИЗМА ===
REQUESTS_PER_SECOND = 5  # ⚡ НАСТРАИВАЙ ЗДЕСЬ! (1-50 запросов в секунду)
MAX_CONCURRENT = 5  # Максимум одновременных запросов

# ВАЖНО: Период ВНУТРИ которого ищем трансферы (включая активность)
TRANSFER_PERIOD_START = datetime(2020, 9, 1, tzinfo=timezone.utc)
TRANSFER_PERIOD_END = datetime(2020, 9, 29, tzinfo=timezone.utc)

# Граница последней активности (последняя активность должна быть ДО этой даты)
ACTIVITY_CUTOFF = datetime(2021, 1, 1, tzinfo=timezone.utc)

# Диапазон баланса (теперь проверяем АКТУАЛЬНЫЙ баланс)
MIN_BALANCE = 1000
MAX_BALANCE = 100000

os.makedirs(CACHE_DIR, exist_ok=True)


# === RATE LIMITER ===
class RateLimiter:
    def __init__(self, rate):
        self.rate = rate
        self.interval = 1.0 / rate
        self.last_request = 0
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request
            
            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                time.sleep(sleep_time)
            
            self.last_request = time.time()


rate_limiter = RateLimiter(REQUESTS_PER_SECOND)


def graphql_query(query, variables=None, retry=0):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    payload = {"query": query, "variables": variables or {}}
    
    try:
        response = requests.post(ENDPOINT, json=payload, headers=headers, timeout=90)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ HTTP {response.status_code}: {response.text[:200]}")
            
            if response.status_code in [401, 403]:
                raise Exception("Ошибка авторизации!")
            
            if retry < MAX_RETRIES and response.status_code >= 500:
                wait = 2 ** retry * 5
                print(f"⏳ Повтор через {wait}с...")
                time.sleep(wait)
                return graphql_query(query, variables, retry + 1)
            
            return None
    
    except requests.exceptions.Timeout:
        if retry < MAX_RETRIES:
            print("⏳ Таймаут, повтор...")
            time.sleep(5)
            return graphql_query(query, variables, retry + 1)
        return None


def generate_monthly_ranges(start, end):
    """Генерирует периоды по месяцам"""
    ranges = []
    current = start
    
    while current < end:
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1, day=1)
        else:
            next_month = current.replace(month=current.month + 1, day=1)
        
        month_end = min(next_month - timedelta(seconds=1), end)
        
        ranges.append({
            "start": current.strftime("%Y-%m-%d"),
            "end": month_end.strftime("%Y-%m-%d"),
            "label": current.strftime("%Y-%m")
        })
        
        current = next_month
    
    return ranges


def fetch_transfers_for_period(since, till, label):
    """Получает трансферы за период с кэшированием"""
    cache_file = os.path.join(CACHE_DIR, f"transfers_{label}.json")
    
    if os.path.exists(cache_file):
        print(f" ✅ Кэш: {label}")
        with open(cache_file, "r") as f:
            return json.load(f)
    
    print(f"\n🔍 Загружаем: {label} ({since} → {till})")
    
    query = """
    query GetUSDTTransfers($offset: Int!, $limit: Int!, $currency: String!, $since: ISO8601DateTime!, $till: ISO8601DateTime!) {
      tron(network: tron) {
        transfers(
          options: {limit: $limit, offset: $offset, asc: "block.timestamp.time"}
          date: {since: $since, till: $till}
          currency: {is: $currency}
          amount: {gt: 0}
        ) {
          sender: sender {
            address
          }
          receiver: receiver {
            address
          }
          amount
          block {
            timestamp {
              time(format: "%Y-%m-%d %H:%M:%S")
            }
          }
        }
      }
    }
    """
    
    all_transfers = []
    offset = 0
    
    while True:
        variables = {
            "offset": offset,
            "limit": PAGE_SIZE,
            "currency": USDT_CONTRACT,
            "since": since,
            "till": till
        }
        
        data = graphql_query(query, variables)
        
        if not data:
            print(f" ❌ Ошибка на offset={offset}")
            break
        
        if data.get('errors'):
            errors = data['errors']
            if any('Memory limit' in str(e.get('message', '')) for e in errors):
                print(f" ⚠️ Memory limit! Пропускаем {label}")
                return []
            print(f" ❌ Ошибки: {errors[0].get('message', '')[:100]}")
            break
        
        transfers = data.get("data", {}).get("tron", {}).get("transfers", [])
        
        if not transfers:
            break
        
        all_transfers.extend(transfers)
        
        if offset % 25000 == 0 and offset > 0:
            print(f" → {len(all_transfers)} трансферов")
        
        if len(transfers) < PAGE_SIZE:
            break
        
        offset += PAGE_SIZE
        time.sleep(0.2)
    
    print(f" ✓ Получено: {len(all_transfers)}")
    
    with open(cache_file, "w") as f:
        json.dump(all_transfers, f)
    
    return all_transfers


def load_checked_addresses():
    """Загружает уже проверенные адреса"""
    if os.path.exists(CHECKED_ADDRESSES_FILE):
        with open(CHECKED_ADDRESSES_FILE, "r") as f:
            return json.load(f)
    return {}


# THREAD-SAFE сохранение
checked_lock = threading.Lock()


def save_checked_address(address, data):
    """Сохраняет проверенный адрес (thread-safe)"""
    with checked_lock:
        checked = load_checked_addresses()
        checked[address] = data
        
        with open(CHECKED_ADDRESSES_FILE, "w") as f:
            json.dump(checked, f, indent=2)


def get_wallet_info_sync(address, currency=USDT_CONTRACT):
    """
    Синхронная проверка одного кошелька с rate limiting
    """
    query = """
    query GetInfo($address: String!, $currency: String!) {
      tron(network: tron) {
        address(address: {is: $address}) {
          balances(currency: {is: $currency}) {
            value
          }
        }
        lastTransfer: transfers(
          options: {desc: "block.timestamp.time", limit: 1}
          any: [{sender: {is: $address}}, {receiver: {is: $address}}]
        ) {
          block {
            timestamp {
              time(format: "%Y-%m-%d %H:%M:%S")
            }
          }
        }
      }
    }
    """
    try:
        # Rate limiting
        rate_limiter.wait()
        
        variables = {"address": address, "currency": currency}
        data = graphql_query(query, variables)
        
        if not data or "data" not in data or not data["data"].get("tron"):
            return {"balance": 0.0, "last_activity": None}
        
        tron_data = data["data"]["tron"]
        
        address_data = tron_data.get("address")
        
        if isinstance(address_data, list):
            address_data = address_data[0] if address_data else {}
        
        balances_list = address_data.get("balances", []) if address_data else []
        balance = float(balances_list[0]["value"]) if balances_list else 0.0
        
        last_transfers = tron_data.get("lastTransfer", [])
        last_time_str = last_transfers[0]["block"]["timestamp"]["time"] if last_transfers else None
        
        result = {"balance": balance, "last_activity": last_time_str}
        
        save_checked_address(address, result)
        
        return result
    
    except Exception as e:
        error_result = {"balance": 0.0, "last_activity": None, "error": str(e)}
        save_checked_address(address, error_result)
        return error_result


def check_wallets_parallel(potentially_abandoned):
    """
    Параллельная проверка кошельков с настраиваемым rate limiting
    """
    checked = load_checked_addresses()
    
    print(f"\n📂 Загружено ранее проверенных: {len(checked)}")
    print(f"⚡ Скорость: {REQUESTS_PER_SECOND} req/sec, макс. параллельных: {MAX_CONCURRENT}")
    
    final_results = {}
    addresses_to_check = list(potentially_abandoned.keys())
    
    # Обрабатываем уже проверенные
    for addr in list(checked.keys()):
        if addr in potentially_abandoned:
            info = checked[addr]
            
            if "error" in info:
                continue
            
            if info["last_activity"]:
                try:
                    last_dt = datetime.strptime(info["last_activity"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    
                    if last_dt < ACTIVITY_CUTOFF and MIN_BALANCE <= info["balance"] <= MAX_BALANCE and info[
                        "balance"] > 0:
                        final_results[addr] = {
                            "balance": round(info["balance"], 2),
                            "last_activity_in_period": last_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        }
                except:
                    pass
    
    print(f"✅ Из кэша найдено подходящих: {len(final_results)}")
    
    # Непроверенные адреса
    unchecked = [addr for addr in addresses_to_check if addr not in checked]
    
    if not unchecked:
        print("✅ Все адреса уже проверены!")
        return final_results
    
    print(f"\n🔍 Осталось проверить: {len(unchecked)}")
    print(f"⏱️  Примерное время: {len(unchecked) / REQUESTS_PER_SECOND / 60:.1f} минут")
    
    start_time = time.time()
    processed = 0
    
    # ThreadPoolExecutor для параллелизма
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(get_wallet_info_sync, addr): addr for addr in unchecked}
        
        for future in futures:
            addr = futures[future]
            processed += 1
            
            try:
                info = future.result()
                
                if "error" in info:
                    continue
                
                if info["last_activity"]:
                    try:
                        last_dt = datetime.strptime(info["last_activity"], "%Y-%m-%d %H:%M:%S").replace(
                            tzinfo=timezone.utc)
                        
                        if last_dt < ACTIVITY_CUTOFF and MIN_BALANCE <= info["balance"] <= MAX_BALANCE and info[
                            "balance"] > 0:
                            final_results[addr] = {
                                "balance": round(info["balance"], 2),
                                "last_activity_in_period": last_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                            }
                    except:
                        pass
                
                # Прогресс и статистика
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(unchecked) - processed) / rate if rate > 0 else 0
                
                print(f"\r[{processed}/{len(unchecked)}] Найдено: {len(final_results)} | "
                      f"Скорость: {rate:.1f} req/s | ETA: {eta / 60:.1f} мин", end="", flush=True)
                
                # Сохраняем промежуточные результаты каждые 100 адресов
                if processed % 100 == 0:
                    with open(RESULTS_FILE, "w") as f:
                        json.dump(final_results, f, indent=2)
            
            except Exception as e:
                print(f"\n⚠️ Ошибка обработки {addr[:10]}: {e}")
    
    print()  # Новая строка
    
    elapsed = time.time() - start_time
    print(f"\n✅ Проверено за {elapsed / 60:.1f} минут (средняя скорость: {processed / elapsed:.1f} req/s)")
    
    return final_results


def main():
    if os.path.exists(RESULTS_FILE):
        print(f"✅ Результаты уже есть: {RESULTS_FILE}")
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    
    print("=" * 60)
    print("🎯 ПОИСК ЗАБРОШЕННЫХ USDT КОШЕЛЬКОВ")
    print("=" * 60)
    print(f"📅 Период сбора: {TRANSFER_PERIOD_START.date()} → {TRANSFER_PERIOD_END.date()}")
    print(f"⏰ Граница активности: до {ACTIVITY_CUTOFF.date()}")
    print(f"💰 Диапазон баланса: {MIN_BALANCE:,} - {MAX_BALANCE:,} USDT (АКТУАЛЬНЫЙ баланс)")
    print(f"⚡ Параллельная проверка: {REQUESTS_PER_SECOND} req/sec")
    print("=" * 60)
    
    periods = generate_monthly_ranges(TRANSFER_PERIOD_START, TRANSFER_PERIOD_END)
    print(f"\n📊 Будет обработано периодов: {len(periods)}")
    
    all_transfers = []
    
    for i, period in enumerate(periods, 1):
        print(f"\n[{i}/{len(periods)}] {period['label']}")
        
        transfers = fetch_transfers_for_period(
            period['start'],
            period['end'],
            period['label']
        )
        
        if transfers:
            all_transfers.extend(transfers)
    
    print(f"\n{'=' * 60}")
    print(f"✅ Всего собрано: {len(all_transfers):,} трансферов")
    print(f"{'=' * 60}")
    
    if not all_transfers:
        print("❌ Нет данных")
        return {}
    
    print("\n📊 Анализируем данные...")
    
    balances = {}
    last_activity = {}
    
    for i, t in enumerate(all_transfers):
        try:
            sender = t["sender"]["address"]
            receiver = t["receiver"]["address"]
            amount = float(t["amount"])
            timestamp_str = t["block"]["timestamp"]["time"]
            
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            ts = dt.timestamp()
            
            balances[sender] = balances.get(sender, 0) - amount
            balances[receiver] = balances.get(receiver, 0) + amount
            
            last_activity[sender] = max(last_activity.get(sender, 0), ts)
            last_activity[receiver] = max(last_activity.get(receiver, 0), ts)
            
            if i % 100000 == 0 and i > 0:
                print(f" → Обработано {i:,} / {len(all_transfers):,}")
        
        except Exception as e:
            continue
    
    print(f"✓ Уникальных адресов: {len(balances):,}")
    
    print(f"\n🔍 Фильтр #1: Рассчитанный баланс {MIN_BALANCE:,}-{MAX_BALANCE:,} USDT...")
    
    filtered_by_balance = {}
    
    for addr, bal in balances.items():
        if MIN_BALANCE <= bal <= MAX_BALANCE:
            filtered_by_balance[addr] = bal
    
    print(f"✓ Подходят по балансу: {len(filtered_by_balance):,}")
    
    if not filtered_by_balance:
        print("❌ Нет кошельков в диапазоне")
        return {}
    
    print(f"\n🔍 Фильтр #2: Последняя активность ДО {ACTIVITY_CUTOFF.date()}...")
    
    cutoff_ts = ACTIVITY_CUTOFF.timestamp()
    potentially_abandoned = {}
    
    for addr, bal in filtered_by_balance.items():
        last_ts = last_activity.get(addr, 0)
        
        if last_ts < cutoff_ts:
            potentially_abandoned[addr] = {
                "balance": round(bal, 2),
                "last_activity_in_period": datetime.fromtimestamp(
                    last_ts, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC")
            }
    
    print(f"✓ Неактивны в период: {len(potentially_abandoned):,}")
    
    if not potentially_abandoned:
        print("❌ Все кошельки активны")
        return {}
    
    print(f"\n🔍 Фильтр #3: Параллельная проверка АКТУАЛЬНОГО баланса...")
    
    # ПАРАЛЛЕЛЬНАЯ ПРОВЕРКА
    final_results = check_wallets_parallel(potentially_abandoned)
    
    print(f"\n{'=' * 60}")
    print(f"✅ НАЙДЕНО ЗАБРОШЕННЫХ КОШЕЛЬКОВ: {len(final_results):,}")
    print(f"{'=' * 60}")
    
    with open(RESULTS_FILE, "w") as f:
        json.dump(final_results, f, indent=2, sort_keys=True)
    
    print(f"💾 Результаты сохранены: {RESULTS_FILE}")
    
    return final_results


if __name__ == "__main__":
    try:
        results = main()
        
        if results:
            print(f"\n📊 СТАТИСТИКА:")
            print(f"Всего кошельков: {len(results):,}")
            
            balances = [v["balance"] for v in results.values()]
            total_usdt = sum(balances)
            
            print(f"Общая сумма: {total_usdt:,.2f} USDT")
            print(f"Средний баланс: {total_usdt / len(balances):,.2f} USDT")
            print(f"Мин баланс: {min(balances):,.2f} USDT")
            print(f"Макс баланс: {max(balances):,.2f} USDT")
            
            print(f"\n📋 Первые 5 кошельков:")
            for addr, data in list(results.items())[:5]:
                print(f"\n 🔑 {addr}")
                print(f" 💰 {data['balance']:,.2f} USDT")
                print(f" ⏰ {data['last_activity_in_period']}")
        else:
            print("\n❌ Результатов нет")
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано (Ctrl+C)")
        print("💡 Прогресс сохранён в кэше, можно продолжить позже")
    except Exception as e:
        print(f"\n💥 Ошибка: {e}")
        import traceback
        
        traceback.print_exc()