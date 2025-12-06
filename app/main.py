import asyncio
import aiohttp
import requests
import json
import os
import time
from pathlib import Path

# --- Константы и Настройки ---
CONFIG_FILE = "config.json"


# --- Вспомогательные функции ---

def load_config():
    """Загружает конфигурацию из config.json."""
    print(f"🔄 Загружаем конфигурацию из {CONFIG_FILE}")
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            print(f"✅ Конфигурация загружена: {config}")
            return config
    except FileNotFoundError:
        print(f"❌ Файл {CONFIG_FILE} не найден!")
        # Создаем пример конфигурации
        example_config = {
            "API_KEY": "your_api_key_here",
            "RPC_URL": "https://trx.nownodes.io/wallet/",
            "START_BLOCK": 60000000,
            "PROGRESS_FILE": "index_progress.json",
            "ADDRESSES_FILE": "unique_addresses.txt",
            "BATCH_SIZE": 10,
            "TG_TOKEN": "your_token_here",
            "TG_CHAT_ID": "your_chat_id_here"
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(example_config, f, indent=2)
        print(f"📄 Создан пример конфигурации в {CONFIG_FILE}")
        print("⚠️ Пожалуйста, заполните его своими данными и перезапустите скрипт")
        exit(1)
    except json.JSONDecodeError:
        print(f"❌ Ошибка парсинга {CONFIG_FILE}")
        exit(1)


def load_progress(progress_file, start_block):
    """Загружает последний обработанный блок из файла прогресса."""
    print(f"🔄 Проверяем файл прогресса: {progress_file}")
    if os.path.exists(progress_file):
        print(f"✅ Файл прогресса существует")
        try:
            with open(progress_file, 'r') as f:
                data = json.load(f)
                last_block = data.get('last_processed_block', start_block)
                print(f"📊 Последний обработанный блок: {last_block}")
                return last_block
        except json.JSONDecodeError:
            print("⚠️ Файл прогресса поврежден, начинаем с START_BLOCK")
            return start_block
    else:
        print(f"📄 Файл прогресса не существует, начинаем с блока {start_block}")
        return start_block


def save_progress(progress_file, block_num):
    """Сохраняет текущий прогресс."""
    print(f"💾 Сохраняем прогресс: блок {block_num} в {progress_file}")
    try:
        with open(progress_file, 'w') as f:
            json.dump({'last_processed_block': block_num}, f, indent=2)
        print(f"✅ Прогресс сохранен")
    except Exception as e:
        print(f"❌ Ошибка сохранения прогресса: {e}")


# --- Функция для отправки логов в Telegram ---
async def tg_log_message(session, text, token, chat_id):
    """Асинхронно отправляет сообщение в Telegram."""
    if not token or not chat_id or token == "your_token_here":
        print(f"⚠️ Telegram настройки не указаны, пропускаем отправку")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        async with session.post(url, json=payload, timeout=10) as resp:
            if resp.status == 200:
                print(f"📨 Telegram сообщение отправлено")
            else:
                print(f"⚠️ Ошибка Telegram: статус {resp.status}")
    except Exception as e:
        print(f"❌ Ошибка отправки в TG: {e}")


def extract_addresses_from_block(block_data):
    """Извлекает уникальные адреса отправителей и получателей из блока."""
    addresses = set()
    if not block_data:
        return addresses
    
    transactions = block_data.get('transactions', [])
    print(f"🔍 Извлекаем адреса из блока, транзакций: {len(transactions)}")
    
    for tx in transactions:
        raw_data = tx.get('raw_data', {})
        contracts = raw_data.get('contract', [])
        
        for contract in contracts:
            value = contract.get('parameter', {}).get('value', {})
            
            owner_address = value.get('owner_address')
            to_address = value.get('to_address')
            
            if owner_address:
                addresses.add(owner_address)
            if to_address:
                addresses.add(to_address)
            
            if contract.get('type') == 'TriggerSmartContract':
                contract_owner = value.get('owner_address')
                if contract_owner:
                    addresses.add(contract_owner)
    
    print(f"✅ Найдено адресов в блоке: {len(addresses)}")
    return addresses


# --- Основная логика индексации (асинхронная) ---

async def fetch_block(session, url, headers, block_num):
    """Асинхронный запрос данных блока."""
    try:
        data = json.dumps({'num': block_num})
        print(f"🌐 Запрашиваем блок {block_num}")
        
        async with session.post(url, headers=headers, data=data, timeout=30) as resp:
            resp.raise_for_status()
            result = await resp.json()
            print(f"✅ Блок {block_num} получен")
            return result
    except asyncio.TimeoutError:
        print(f"⏰ Таймаут при запросе блока {block_num}")
        return None
    except Exception as e:
        print(f"❌ Ошибка запроса блока {block_num}: {e}")
        return None


async def main():
    print("=" * 50)
    print("🚀 ЗАПУСК ИНДЕКСАТОРА TRON")
    print("=" * 50)
    
    cfg = load_config()
    RPC_URL = cfg['RPC_URL'] + "getblockbynum"
    LATEST_BLOCK_URL = cfg['RPC_URL'] + "getnowblock"
    API_KEY = cfg['API_KEY']
    START_BLOCK = cfg['START_BLOCK']
    PROGRESS_FILE = cfg['PROGRESS_FILE']
    ADDRESSES_FILE = cfg['ADDRESSES_FILE']
    BATCH_SIZE = cfg['BATCH_SIZE']
    
    # Telegram
    TG_TOKEN = cfg['TG_TOKEN']
    TG_CHAT_ID = cfg['TG_CHAT_ID']
    
    # Проверяем API ключ
    if API_KEY == "your_api_key_here":
        print("❌ Пожалуйста, укажите ваш API ключ в config.json")
        return
    
    print(f"\n📊 Конфигурация:")
    print(f"  • API ключ: {'*' * 8}{API_KEY[-8:] if len(API_KEY) > 8 else ''}")
    print(f"  • RPC URL: {RPC_URL}")
    print(f"  • Стартовый блок: {START_BLOCK}")
    print(f"  • Файл прогресса: {PROGRESS_FILE}")
    print(f"  • Файл адресов: {ADDRESSES_FILE}")
    print(f"  • Размер пакета: {BATCH_SIZE}")
    
    # Загрузка прогресса
    start_num = load_progress(PROGRESS_FILE, START_BLOCK)
    current_block = start_num
    
    headers = {
        'api-key': API_KEY,
        'Content-Type': 'application/json'
    }
    
    total_found_addresses = 0
    
    # Создаем файл адресов если его нет
    if not os.path.exists(ADDRESSES_FILE):
        print(f"📄 Создаем новый файл для адресов: {ADDRESSES_FILE}")
        open(ADDRESSES_FILE, 'w').close()
    else:
        # Подсчитываем сколько уже есть адресов
        with open(ADDRESSES_FILE, 'r') as f:
            lines = f.readlines()
            total_found_addresses = len([line for line in lines if line.strip()])
        print(f"📊 В файле уже есть {total_found_addresses} адресов")
    
    async with aiohttp.ClientSession() as session:
        # 1. Отправляем стартовое сообщение в Telegram
        start_msg = f"🚀 *Индексатор Tron запущен.*\nНачало с блока: `{current_block}`\nВсего адресов: `{total_found_addresses}`"
        await tg_log_message(session, start_msg, TG_TOKEN, TG_CHAT_ID)
        
        while True:
            # Определяем последний блок в сети
            try:
                print(f"\n🔄 Проверяем последний блок в сети...")
                r = requests.post(LATEST_BLOCK_URL, headers=headers, timeout=10)
                r.raise_for_status()
                latest_data = r.json()
                latest_block_num = latest_data['block_header']['raw_data']['number']
                print(f"✅ Последний блок в сети: {latest_block_num}")
            except Exception as e:
                print(f"❌ Ошибка при получении последнего блока: {e}")
                await asyncio.sleep(5)
                continue
            
            if current_block > latest_block_num:
                print(f"✅ Достигнут последний блок: {latest_block_num}")
                end_msg = f"✅ *Индексация завершена.*\nДостигнут последний блок: `{latest_block_num}`.\nВсего найдено адресов: `{total_found_addresses}`"
                await tg_log_message(session, end_msg, TG_TOKEN, TG_CHAT_ID)
                break
            
            # --- Обработка пакета ---
            batch_addresses = set()
            blocks_processed_in_batch = 0
            
            print(f"\n{'=' * 50}")
            print(
                f"📦 Обработка пакета: {current_block} - {min(current_block + BATCH_SIZE - 1, latest_block_num)} / {latest_block_num}")
            print(f"{'=' * 50}")
            
            # Запускаем запросы блоков параллельно
            tasks = []
            for i in range(BATCH_SIZE):
                block_to_process = current_block + i
                if block_to_process > latest_block_num:
                    break
                tasks.append(fetch_block(session, RPC_URL, headers, block_to_process))
            
            results = await asyncio.gather(*tasks)
            
            for idx, block_data in enumerate(results):
                if block_data:
                    blocks_processed_in_batch += 1
                    new_addresses = extract_addresses_from_block(block_data)
                    batch_addresses.update(new_addresses)
            
            # 3. Сохранение адресов в файл и логгирование
            if batch_addresses:
                addresses_to_save = len(batch_addresses)
                total_found_addresses += addresses_to_save
                
                print(f"💾 Сохраняем {addresses_to_save} адресов в {ADDRESSES_FILE}")
                
                # Проверяем права на запись
                try:
                    with open(ADDRESSES_FILE, 'a') as f:
                        for addr in batch_addresses:
                            f.write(addr + '\n')
                    print(f"✅ Адреса успешно сохранены")
                    
                    # Формируем список найденных адресов для лога
                    address_list_for_log = "\n".join(list(batch_addresses)[:10])
                    
                    # Отправка лога в Telegram
                    log_message = (
                        f"🟢 *Пакет успешно обработан!*\n"
                        f"Блоки: `{current_block}` - `{current_block + blocks_processed_in_batch - 1}`\n"
                        f"Найдено новых адресов: `{addresses_to_save}`\n"
                        f"Всего найдено: `{total_found_addresses}`\n"
                        f"Первые адреса:\n"
                        f"```\n{address_list_for_log}\n```"
                    )
                    await tg_log_message(session, log_message, TG_TOKEN, TG_CHAT_ID)
                
                except Exception as e:
                    print(f"❌ Ошибка записи в файл: {e}")
                    print(f"  Путь к файлу: {os.path.abspath(ADDRESSES_FILE)}")
                    print(f"  Права на запись: {os.access(os.path.dirname(ADDRESSES_FILE), os.W_OK)}")
            else:
                print(f"⚪️ В пакете не найдено новых адресов")
                # Отправка лога о пустом пакете
                await tg_log_message(session,
                                     f"⚪️ Пакет обработан. Блоки `{current_block}` - `{current_block + blocks_processed_in_batch - 1}`. Найдено: *0* адресов.",
                                     TG_TOKEN, TG_CHAT_ID)
            
            # 4. Обновление прогресса
            current_block += blocks_processed_in_batch
            save_progress(PROGRESS_FILE, current_block)
            
            print(f"\n📊 Статистика:")
            print(f"  • Всего обработано блоков: {current_block - START_BLOCK}")
            print(f"  • Всего найдено адресов: {total_found_addresses}")
            print(f"  • Следующий блок: {current_block}")
            
            # Пауза перед следующим пакетом
            print(f"⏳ Ожидание 1 секунду...")
            await asyncio.sleep(1)


if __name__ == "__main__":
    print("Скрипт запущен...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Индексация прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        
        traceback.print_exc()