# import json
# from datetime import datetime
#
# file_path = "addresses_0.jsonl"
# output_file = "inactive_since_2021.jsonl"
#
# # Время отсечения — 1 января 2021
# cutoff = int(datetime(2021, 6, 1).timestamp() * 1000)  # в миллисекундах
#
# filtered_wallets = []
#
# with open(file_path, "r") as f:
#     for line in f:
#         wallet = json.loads(line.strip())
#         last_op = wallet.get("latestOperationTime", 0)
#         if last_op < cutoff:
#             filtered_wallets.append(wallet)
#
# # Сохраняем результат
# with open(output_file, "w") as f:
#     for wallet in filtered_wallets:
#         f.write(json.dumps(wallet) + "\n")
#
# print(f"Найдено {len(filtered_wallets)} кошельков, которые не использовались с 2021 года.")
#
#
# import json
# from datetime import datetime
#
# # Текущая цена TRX в USD (ОБНОВИ ЭТО ЗНАЧЕНИЕ!)
# TRX_PRICE_USD = 0.29  # Проверь актуальную цену на CoinMarketCap
#
# # Диапазоны в USD (минимальное и максимальное значение)
# RANGES = {
#     "1000$": (900, 1100),
#     "2000$": (1800, 2200),
#     "5000$": (4500, 5500),
#     "10.000$": (9000, 11000),
#     "25.000$": (24000, 26000),
#     "50.000$": (48000, 52000),
#     "70.000$": (68000, 72000),
#     "80.000$": (78000, 82000),
#     "100.000$": (98000, 102000)
# }
#
#
# def calculate_usd_balance(balance_sun, trx_price):
#     """Конвертирует баланс из SUN в USD"""
#     balance_trx = balance_sun / 1_000_000
#     return balance_trx * trx_price
#
#
# def filter_wallets(json_file_path, output_file="filtered_wallets.txt"):
#     """Фильтрует кошельки по заданным диапазонам"""
#
#     # Читаем JSON файл
#     try:
#         with open(json_file_path, 'r', encoding='utf-8') as f:
#             # Если файл содержит по одному JSON объекту на строку
#             wallets = []
#             for line in f:
#                 line = line.strip()
#                 if line:  # Пропускаем пустые строки
#                     wallet = json.loads(line)
#                     wallets.append(wallet)
#     except Exception as e:
#         print(f"Ошибка при чтении файла: {e}")
#         return
#
#     print(f"Загружено {len(wallets)} кошельков")
#     print(f"Используется цена TRX: ${TRX_PRICE_USD:.4f}")
#     print("-" * 60)
#
#     # Группируем кошельки по диапазонам
#     results = {range_name: [] for range_name in RANGES.keys()}
#
#     for wallet in wallets:
#         balance_sun = wallet.get("balance", 0)
#         usd_balance = calculate_usd_balance(balance_sun, TRX_PRICE_USD)
#
#         # Проверяем каждый диапазон
#         for range_name, (min_val, max_val) in RANGES.items():
#             if min_val <= usd_balance <= max_val:
#                 results[range_name].append({
#                     "address": wallet.get("address", "N/A"),
#                     "balance_trx": balance_sun / 1_000_000,
#                     "balance_usd": usd_balance,
#                     "tag": wallet.get("addressTag", ""),
#                     "total_transactions": wallet.get("totalTransactionCount", 0)
#                 })
#                 break  # Кошелек попадает только в один диапазон
#
#     # Выводим результаты и сохраняем в файл
#     with open(output_file, 'w', encoding='utf-8') as out_f:
#         out_f.write(f"Отчет сгенерирован: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
#         out_f.write(f"Цена TRX: ${TRX_PRICE_USD:.4f}\n")
#         out_f.write("=" * 60 + "\n\n")
#
#         total_found = 0
#         for range_name, wallets_in_range in results.items():
#             out_f.write(f"\n{'=' * 60}\n")
#             out_f.write(f"ДИАПАЗОН: {range_name}\n")
#             out_f.write(f"Найдено кошельков: {len(wallets_in_range)}\n")
#             out_f.write(f"{'=' * 60}\n\n")
#
#             if wallets_in_range:
#                 # Сортируем по балансу (от большего к меньшему)
#                 wallets_in_range.sort(key=lambda x: x["balance_usd"], reverse=True)
#
#                 for wallet in wallets_in_range:
#                     total_found += 1
#                     line = f"Адрес: {wallet['address']}\n"
#                     line += f"Баланс: {wallet['balance_trx']:,.2f} TRX (${wallet['balance_usd']:,.2f})\n"
#                     if wallet['tag']:
#                         line += f"Тег: {wallet['tag']}\n"
#                     line += f"Транзакций: {wallet['total_transactions']:,}\n"
#                     line += "-" * 40 + "\n"
#                     out_f.write(line)
#             else:
#                 out_f.write("Кошельков не найдено\n")
#
#         out_f.write(f"\n{'=' * 60}\n")
#         out_f.write(f"ИТОГО: Найдено {total_found} кошельков\n")
#
#     # Выводим сводку в консоль
#     print("\nРЕЗУЛЬТАТЫ ФИЛЬТРАЦИИ:")
#     print(f"{'Диапазон':<15} | {'Кол-во':<10} | {'Примерный баланс'}")
#     print("-" * 50)
#
#     total_all = 0
#     for range_name, wallets_in_range in results.items():
#         count = len(wallets_in_range)
#         total_all += count
#         if count > 0:
#             avg_balance = sum(w["balance_usd"] for w in wallets_in_range) / count
#             print(f"{range_name:<15} | {count:<10} | ${avg_balance:,.2f} в среднем")
#         else:
#             print(f"{range_name:<15} | {count:<10} | ---")
#
#     print("-" * 50)
#     print(f"{'ВСЕГО':<15} | {total_all:<10}")
#     print(f"\nДетальные результаты сохранены в файл: {output_file}")
#
#
# # Использование
# if __name__ == "__main__":
#     # УКАЖИ ПУТЬ К СВОЕМУ ФАЙЛУ
#     input_file = "inactive_since_2021.jsonl"  # Замени на путь к своему файлу
#
#     # ОБНОВИ ЦЕНУ TRX ПЕРЕД ЗАПУСКОМ!
#     # Можно получить через API:
#     # import requests
#     # response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=tron&vs_currencies=usd')
#     # TRX_PRICE_USD = response.json()['tron']['usd']
#
#     filter_wallets(input_file)
import pprint

# import json
# from datetime import datetime
#
# # Пример для первого кошелька
# timestamp_ms = 1549536747000  # из поля latestOperationTime
#
# # Конвертируем в дату
# timestamp_seconds = timestamp_ms / 1000
# date = datetime.fromtimestamp(timestamp_seconds)
#
# print(f"Timestamp: {timestamp_ms}")
# print(f"Дата: {date}")
# print(f"Форматированно: {date.strftime('%Y-%m-%d %H:%M:%S')}")

#
#
# import requests
#
# API_KEY = "268513cb-8366-4e15-8dbb-072be5cd6c61"
# url = "https://tron-mainnet.nownodes.io/wallet/getblockbynum"
# headers = {"api-key": API_KEY}
#
# block_num = 1000000  # пример номера блока
# response = requests.post(url, headers=headers, json={"num": block_num})
# # block = response.json()
# pprint.pprint(response)
# #
# # for tx in block.get("transactions", []):
# #     contracts = tx.get("raw_data", {}).get("contract", [])
# #     for contract in contracts:
# #         param = contract.get("parameter", {}).get("value", {})
# #         from_addr = param.get("owner_address")
# #         to_addr = param.get("to_address")
# #         print("From:", from_addr, "To:", to_addr)


import requests
import json
import os
import time

# --- Константы и Настройки ---
CONFIG_FILE = "config.json"


def load_config():
    """Загружает конфигурацию из config.json."""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def load_progress(progress_file, start_block):
    """Загружает последний обработанный блок из файла прогресса."""
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            try:
                data = json.load(f)
                return data.get('last_processed_block', start_block)
            except json.JSONDecodeError:
                return start_block
    return start_block


def save_progress(progress_file, block_num):
    """Сохраняет текущий прогресс."""
    with open(progress_file, 'w') as f:
        json.dump({'last_processed_block': block_num}, f)


def extract_addresses_from_block(block_data):
    """Извлекает уникальные адреса отправителей и получателей из блока."""
    addresses = set()
    
    # 1. Транзакции, упакованные в блок
    for tx in block_data.get('transactions', []):
        raw_data = tx.get('raw_data', {})
        
        # 2. Контракты внутри транзакции
        for contract in raw_data.get('contract', []):
            value = contract.get('parameter', {}).get('value', {})
            
            # TransferContract (TRX переводы)
            owner_address = value.get('owner_address')
            to_address = value.get('to_address')
            
            if owner_address:
                addresses.add(owner_address)
            if to_address:
                addresses.add(to_address)
            
            # TriggerSmartContract (USDT/Token переводы и другие контракты)
            # Извлекаем только owner_address (инициатора)
            if contract.get('type') == 'TriggerSmartContract':
                contract_owner = value.get('owner_address')
                if contract_owner:
                    addresses.add(contract_owner)
            
            # Примечание: Адреса получателей токенов (из поля 'data') требуют
            # дополнительного декодирования HEX, что мы пока опустим
            # для экономии времени и сосредоточимся на простых TransferContract и owner_address.
    
    return addresses


def main():
    cfg = load_config()
    RPC_URL = cfg['RPC_URL']
    API_KEY = cfg['API_KEY']
    START_BLOCK = cfg['START_BLOCK']
    PROGRESS_FILE = cfg['PROGRESS_FILE']
    ADDRESSES_FILE = cfg['ADDRESSES_FILE']
    BATCH_SIZE = cfg['BATCH_SIZE']  # Количество блоков, запрашиваемых за один цикл
    
    # Загрузка прогресса
    start_num = load_progress(PROGRESS_FILE, START_BLOCK)
    current_block = start_num
    
    headers = {
        'api-key': API_KEY,
        'Content-Type': 'application/json'
    }
    
    print(f"🚀 Индексатор запущен. Начинаем с блока: {current_block}")
    
    # Открываем файл для добавления уникальных адресов (режим 'a' - append)
    # Мы будем записывать адреса, а позже использовать Python set()
    # или базу данных для их дедупликации.
    
    while True:
        # Использование BATCH_SIZE для экономии запросов не работает напрямую с getblockbynum,
        # так как он принимает ОДИН номер блока. BATCH_SIZE здесь означает,
        # сколько блоков мы обработаем за ОДИН цикл, прежде чем сохранить прогресс.
        
        # Начинаем цикл запросов
        batch_addresses = set()
        
        # Определяем последний блок в сети (для остановки)
        try:
            r = requests.post(f"{RPC_URL}getnowblock", headers=headers)
            r.raise_for_status()
            latest_block_num = r.json()['block_header']['raw_data']['number']
        except Exception as e:
            print(f"❌ Ошибка при получении последнего блока: {e}")
            time.sleep(5)
            continue
        
        if current_block > latest_block_num:
            print(f"✅ Достигнут последний блок ({latest_block_num}). Завершение индексации.")
            break
        
        print(
            f"--- Обработка пакета: {current_block} - {min(current_block + BATCH_SIZE - 1, latest_block_num)} / {latest_block_num} ---")
        
        for i in range(BATCH_SIZE):
            block_to_process = current_block + i
            if block_to_process > latest_block_num:
                break
            
            # 1. Запрос к NOWNodes для получения ОДНОГО блока (трата одного запроса)
            try:
                data = json.dumps({'num': block_to_process})
                r = requests.post(f"{RPC_URL}getblockbynum", headers=headers, data=data)
                r.raise_for_status()
                block_data = r.json()
                
                # 2. Извлечение адресов
                new_addresses = extract_addresses_from_block(block_data)
                batch_addresses.update(new_addresses)
                
                print(f"Обработан блок {block_to_process}. Найдено {len(new_addresses)} новых адресов.")
            
            except requests.exceptions.HTTPError as errh:
                print(f"❌ HTTP Error: {errh} (Блок: {block_to_process})")
            except Exception as e:
                print(f"❌ Непредвиденная ошибка: {e} (Блок: {block_to_process})")
        
        # 3. Сохранение адресов в файл
        if batch_addresses:
            with open(ADDRESSES_FILE, 'a') as f:
                for addr in batch_addresses:
                    f.write(addr + '\n')
            print(f"💾 Сохранено {len(batch_addresses)} адресов в {ADDRESSES_FILE}.")
        
        # 4. Обновление прогресса
        current_block += BATCH_SIZE
        save_progress(PROGRESS_FILE, current_block)
        
        # Пауза, чтобы не превысить лимит (если он есть)
        time.sleep(1)


if __name__ == "__main__":
    main()