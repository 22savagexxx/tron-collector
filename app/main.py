import requests
import time
from datetime import datetime
import json
import asyncio
import aiohttp
from aiohttp import ClientSession, ClientTimeout
import os

# === КОНФИГУРАЦИЯ ===
API_KEY = "8c23d239-2121-4540-8f0e-3aecad9fa365"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TG_TOKEN = "8369848164:AAEwtQ7jXSBUpzncTXpgjZ7FVOByd44GbnM"

TG_CHAT_ID = "700416664"
ADDRESSES_FILE = "unique_addresses.txt"
PROGRESS_FILE = "progress.txt"
RESULTS_LOG = "results.log"
MATCHING_FILE = "matching.txt"
CONCURRENCY_LIMIT = 7  # Уменьшено для стабильности
LOG_INTERVAL = 3  # секунды между логами в TG


# === ОТПРАВКА В ТЕЛЕГРАМ ===
def send_tg_message(message):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            print(f"TG Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}")


# === АСИНХРОННЫЕ ФУНКЦИИ ===
async def get_usdt_balance(session, address):
    """Получение баланса USDT"""
    url = f"https://api.trongrid.io/v1/accounts/{address}"
    headers = {"TRON-PRO-API-KEY": API_KEY} if API_KEY else {}
    
    for attempt in range(3):
        try:
            timeout = ClientTimeout(total=20)
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    # Пробуем получить текст ошибки
                    try:
                        error_data = await resp.json()
                        error_msg = error_data.get('error', f'HTTP {resp.status}')
                    except:
                        error_msg = f'HTTP {resp.status}'
                    
                    print(f"⚠️ Баланс: Ошибка {error_msg} для {address[:10]}...")
                    
                    # Обработка частых ошибок
                    if resp.status == 429:  # Too Many Requests
                        await asyncio.sleep(3)
                        continue
                    elif resp.status == 401:  # Unauthorized
                        print("❌ Ошибка авторизации API. Проверьте API_KEY!")
                        return -1
                    elif resp.status == 404:  # Not Found
                        return 0  # Адрес не существует
                    else:
                        await asyncio.sleep(2)
                        continue
                
                # Успешный ответ
                data = await resp.json()
                
                if "data" in data and data["data"]:
                    trc20_data = data["data"][0].get("trc20", [])
                    
                    # Ищем USDT
                    for token in trc20_data:
                        if USDT_CONTRACT in token:
                            usdt_amount = int(token[USDT_CONTRACT])
                            return usdt_amount / 1_000_000
                    return 0  # Адрес существует, но USDT нет
                else:
                    return 0  # Нет данных об адресе
        
        except asyncio.TimeoutError:
            print(f"⏰ Таймаут баланса для {address[:10]}..., попытка {attempt + 1}")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"❌ Ошибка получения баланса для {address[:10]}...: {str(e)[:50]}")
            await asyncio.sleep(2)
    
    return -1  # Все попытки исчерпаны


async def get_last_wallet_activity(session, address):
    """Получение последней активности кошелька"""
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions?limit=1&only_confirmed=true"
    headers = {"TRON-PRO-API-KEY": API_KEY} if API_KEY else {}
    
    for attempt in range(3):
        try:
            timeout = ClientTimeout(total=20)
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    try:
                        error_data = await resp.json()
                        error_msg = error_data.get('error', f'HTTP {resp.status}')
                    except:
                        error_msg = f'HTTP {resp.status}'
                    
                    print(f"⚠️ Активность: Ошибка {error_msg} для {address[:10]}...")
                    
                    if resp.status == 429:
                        await asyncio.sleep(3)
                        continue
                    elif resp.status == 401:
                        return "Ошибка API", None
                    elif resp.status == 404:
                        return "Нет активности", None
                    else:
                        await asyncio.sleep(2)
                        continue
                
                data = await resp.json()
                
                if data.get("data"):
                    # Получаем временную метку из первого элемента
                    transaction = data["data"][0]
                    if "block_timestamp" in transaction:
                        ts = transaction["block_timestamp"]
                        dt = datetime.fromtimestamp(ts / 1000)
                        
                        # Получаем тип транзакции
                        tx_type = "UNKNOWN"
                        if "raw_data" in transaction and "contract" in transaction["raw_data"]:
                            contracts = transaction["raw_data"]["contract"]
                            if contracts and len(contracts) > 0:
                                tx_type = contracts[0].get("type", "UNKNOWN")
                        
                        return dt.strftime('%Y-%m-%d %H:%M:%S UTC'), tx_type
                
                return "Нет активности", None
        
        except asyncio.TimeoutError:
            print(f"⏰ Таймаут активности для {address[:10]}..., попытка {attempt + 1}")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"❌ Ошибка получения активности для {address[:10]}...: {str(e)[:50]}")
            await asyncio.sleep(2)
    
    return "Ошибка API", None


# === ПРОВЕРКА АДРЕСА ===
async def check_address(session, address, semaphore):
    """Проверка одного адреса"""
    async with semaphore:
        # Нормализация адреса
        addr = address.strip()
        if addr.startswith('0x'):
            addr = '41' + addr[2:]  # Конвертируем 0x в 41
        elif not addr.startswith('T') and not addr.startswith('41'):
            addr = '41' + addr
        
        print(f"🔍 Проверяю: {addr}")
        
        # Получаем данные
        usdt = await get_usdt_balance(session, addr)
        last_act, tx_type = await get_last_wallet_activity(session, addr)
        
        # Формируем результат
        result = {
            "address": addr,
            "usdt_balance": usdt,
            "last_wallet_activity": last_act,
            "activity_type": tx_type,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Вывод в консоль
        if usdt == -1:
            print(f"   ❌ Ошибка получения данных")
        else:
            print(f"   💰 Баланс: {usdt:.2f} USDT | 📅 Активность: {last_act}")
        
        # Записываем ВЕСЬ результат
        with open(RESULTS_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
        
        # Проверяем условия совпадения
        try:
            # Условия: баланс > 100 USDT, была активность в 2021 году
            if (usdt > 100 and
                    last_act != "Нет активности" and
                    last_act != "Ошибка API" and
                    "2021" in last_act):
                with open(MATCHING_FILE, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
                
                print(f"✅ НАЙДЕНО СООТВЕТСТВИЕ!")
                print(f"   Адрес: {addr}")
                print(f"   Баланс: {usdt} USDT")
                print(f"   Последняя активность: {last_act}")
                print("-" * 50)
                
                return result
        except Exception as e:
            print(f"⚠️ Ошибка проверки условий: {e}")
        
        return None


# === ОСНОВНОЙ ЦИКЛ ===
async def main():
    """Основная асинхронная функция"""
    # Проверяем существование файла с адресами
    if not os.path.exists(ADDRESSES_FILE):
        print(f"❌ Файл {ADDRESSES_FILE} не найден!")
        send_tg_message(f"<b>Ошибка:</b> Файл {ADDRESSES_FILE} не найден!")
        return
    
    # Читаем адреса
    with open(ADDRESSES_FILE, 'r', encoding='utf-8') as f:
        addresses = [line.strip() for line in f if line.strip()]
    
    total = len(addresses)
    if total == 0:
        print("❌ Файл с адресами пуст!")
        send_tg_message("<b>Ошибка:</b> Файл с адресами пуст!")
        return
    
    # Восстанавливаем прогресс
    start_idx = 0
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                start_idx = int(f.read().strip())
            print(f"📌 Восстанавливаем прогресс: {start_idx}/{total}")
        except:
            print("⚠️ Не удалось прочитать файл прогресса")
    
    print(f"🚀 Начинаем проверку {total} адресов")
    print(f"📊 Начинаем с индекса: {start_idx}")
    print("-" * 50)
    
    # Создаем семафор для ограничения одновременных запросов
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    # Настраиваем HTTP клиент
    timeout = ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(
        limit=CONCURRENCY_LIMIT * 2,
        limit_per_host=CONCURRENCY_LIMIT,
        ttl_dns_cache=300
    )
    
    async with ClientSession(connector=connector, timeout=timeout) as session:
        matching_count = 0
        processed = start_idx
        last_log = time.time()
        start_time = time.time()
        
        # Основной цикл обработки
        for i in range(start_idx, total):
            try:
                # Создаем задачу для проверки адреса
                task = check_address(session, addresses[i], semaphore)
                result = await task
                
                if result:
                    matching_count += 1
                
                processed += 1
                
                # Сохраняем прогресс каждые 10 адресов
                if processed % 10 == 0:
                    with open(PROGRESS_FILE, 'w') as f:
                        f.write(str(processed))
                
                # Логируем в Telegram
                now = time.time()
                if now - last_log >= LOG_INTERVAL:
                    elapsed = now - start_time
                    speed = processed / elapsed if elapsed > 0 else 0
                    remaining = (total - processed) / speed if speed > 0 else 0
                    
                    msg = (
                        f"<b>Прогресс:</b> {processed}/{total} ({processed / total * 100:.1f}%)\n"
                        f"<b>Найдено:</b> {matching_count}\n"
                        f"<b>Скорость:</b> {speed:.1f} адр/сек\n"
                        f"<b>Осталось:</b> {remaining:.0f} сек"
                    )
                    send_tg_message(msg)
                    last_log = now
                
                # Небольшая задержка для стабильности API
                await asyncio.sleep(0.1)
            
            except KeyboardInterrupt:
                print("\n⏸️ Остановлено пользователем")
                break
            except Exception as e:
                print(f"❌ Критическая ошибка при обработке адреса {i}: {e}")
                await asyncio.sleep(1)
        
        # Финальное сообщение
        elapsed_total = time.time() - start_time
        speed_total = total / elapsed_total if elapsed_total > 0 else 0
        
        final_msg = (
            f"<b>✅ ПРОВЕРКА ЗАВЕРШЕНА!</b>\n"
            f"Обработано: {total} адресов\n"
            f"Найдено совпадений: {matching_count}\n"
            f"Средняя скорость: {speed_total:.1f} адр/сек\n"
            f"Общее время: {elapsed_total:.0f} сек"
        )
        
        send_tg_message(final_msg)
        print("\n" + "=" * 50)
        print("✅ ПРОВЕРКА ЗАВЕРШЕНА!")
        print(f"📊 Итого: {total} адресов")
        print(f"🎯 Найдено: {matching_count} совпадений")
        print(f"⏱️ Время: {elapsed_total:.0f} сек")
        print("=" * 50)
        
        # Очищаем файл прогресса
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)


# === ЗАПУСК ===
if __name__ == "__main__":
    print("=" * 50)
    print("🔍 TRON WALLET SCANNER")
    print("=" * 50)
    
    # Инициализация лог-файлов
    try:
        open(RESULTS_LOG, 'w').close()
        open(MATCHING_FILE, 'w').close()
        print("🗑️ Лог-файлы очищены")
    except:
        print("⚠️ Не удалось очистить лог-файлы")
    
    # Запуск
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⛔ Остановлено пользователем")
        send_tg_message("🛑 Скрипт остановлен вручную")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        send_tg_message(f"<b>❌ Критическая ошибка:</b>\n{str(e)[:200]}")