import requests
import time
import json
import os
from datetime import datetime

API_KEY = "51a153dc-3a84-4092-9855-65397c4342a8"
API_BASE = "https://api.trongrid.io/v1"

# Контракт USDT TRC20
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


def get_account_info(address_hex: str, retries=3):
    """Получает информацию об аккаунте с повторными попытками"""
    url = f"{API_BASE}/accounts/{address_hex}"
    headers = {"TRON-PRO-API-KEY": API_KEY} if API_KEY else {}
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                print(f"  ⚠ Ошибка для адреса {address_hex[:10]}...: {e}")
                return None
            time.sleep(2)
    
    return None


def get_usdt_balance(trc20_data: list) -> float:
    """Извлекает баланс USDT из данных trc20"""
    for token_data in trc20_data:
        if USDT_CONTRACT in token_data:
            balance_int = int(token_data[USDT_CONTRACT])
            return balance_int / 1_000_000  # USDT имеет 6 decimals
    return 0.0


def read_addresses_from_file(filename: str):
    """Читает адреса из файла, игнорируя уже проверенные"""
    addresses = []
    
    if not os.path.exists(filename):
        print(f"❌ Файл {filename} не найден!")
        return addresses
    
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            # Игнорируем пустые строки и комментарии
            if not line or line.startswith('#'):
                continue
            
            # Разбираем строку - адрес может быть с комментарием через пробел или запятую
            parts = line.split()
            if parts:
                address = parts[0].lower().replace('0x', '')
                if len(address) == 42:  # Проверяем длину Tron адреса
                    addresses.append(address)
                else:
                    print(f"  ⚠ Пропускаем некорректный адрес: {address}")
    
    return addresses


def save_checkpoint(address: str, result: dict, checkpoint_file: str):
    """Сохраняет контрольную точку (последний проверенный адрес)"""
    checkpoint_data = {
        "last_checked": address,
        "timestamp": datetime.now().isoformat(),
        "result": result
    }
    
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)


def load_checkpoint(checkpoint_file: str):
    """Загружает контрольную точку"""
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None


def mark_address_checked(address: str, checked_file: str):
    """Отмечает адрес как проверенный в отдельном файле"""
    try:
        # Загружаем существующие проверенные адреса
        if os.path.exists(checked_file):
            with open(checked_file, 'r', encoding='utf-8') as f:
                checked_addresses = set(json.load(f))
        else:
            checked_addresses = set()
        
        # Добавляем новый адрес
        checked_addresses.add(address)
        
        # Сохраняем обновленный список
        with open(checked_file, 'w', encoding='utf-8') as f:
            json.dump(list(checked_addresses), f, indent=2)
    
    except Exception as e:
        print(f"  ⚠ Ошибка при сохранении проверенного адреса: {e}")


def get_already_checked(checked_file: str):
    """Получает список уже проверенных адресов"""
    if os.path.exists(checked_file):
        try:
            with open(checked_file, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            pass
    return set()


def update_original_file_with_checkmarks(input_file: str, checked_file: str):
    """Обновляет оригинальный файл, добавляя отметки о проверке"""
    if not os.path.exists(checked_file):
        return
    
    try:
        # Загружаем проверенные адреса
        with open(checked_file, 'r', encoding='utf-8') as f:
            checked_addresses = set(json.load(f))
        
        # Читаем оригинальный файл
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Обновляем строки
        updated_lines = []
        for line in lines:
            original_line = line.strip()
            if not original_line or original_line.startswith('#'):
                updated_lines.append(line)
                continue
            
            # Извлекаем адрес из строки
            parts = original_line.split()
            if parts:
                address = parts[0].lower().replace('0x', '')
                
                # Если адрес проверен, добавляем комментарий
                if address in checked_addresses:
                    # Удаляем возможные старые отметки
                    clean_line = original_line.split('#')[0].strip()
                    updated_lines.append(f"{clean_line} # проверен\n")
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
        
        # Создаем резервную копию
        backup_file = f"{input_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        # Записываем обновленный файл
        with open(input_file, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)
        
        print(f"  📝 Создана резервная копия: {backup_file}")
    
    except Exception as e:
        print(f"  ⚠ Ошибка при обновлении файла: {e}")


def process_address(address: str, index: int, total: int):
    """Обрабатывает один адрес и возвращает результат"""
    print(f"[{index}/{total}] Проверка адреса: {address[:10]}...")
    
    result = {
        "address": address,
        "checked_at": datetime.now().isoformat(),
        "trx_balance": 0,
        "usdt_balance": 0,
        "has_usdt": False,
        "error": None
    }
    
    try:
        info = get_account_info(address)
        
        if not info:
            result["error"] = "API request failed"
            return result
        
        if "data" in info and len(info["data"]) > 0:
            acct = info["data"][0]
            
            # Баланс TRX
            trx_balance = int(acct.get("balance", 0)) / 1_000_000
            result["trx_balance"] = trx_balance
            
            # Ищем USDT в TRC20 токенах
            trc20_data = acct.get("trc20", [])
            usdt_balance = get_usdt_balance(trc20_data)
            result["usdt_balance"] = usdt_balance
            
            if usdt_balance > 0:
                result["has_usdt"] = True
            
            print(f"  ✓ TRX: {trx_balance:.6f}, USDT: {usdt_balance:.6f}")
        
        else:
            print(f"  ✗ Аккаунт не найден или пуст")
            result["error"] = "Account not found"
    
    except Exception as e:
        print(f"  ⚠ Ошибка обработки: {str(e)}")
        result["error"] = str(e)
    
    return result


def main():
    print("=" * 60)
    print("🔍 МАССОВАЯ ПРОВЕРКА USDT НА АДРЕСАХ TRON")
    print("=" * 60)
    
    # Файлы
    input_file = "unique_addresses.txt"
    checkpoint_file = "checkpoint.json"
    checked_file = "checked_addresses.json"
    output_file = f"usdt_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Загружаем адреса
    addresses = read_addresses_from_file(input_file)
    
    if not addresses:
        print("❌ Не найдено адресов в файле")
        return
    
    print(f"📄 Найдено {len(addresses)} адресов в файле")
    
    # Загружаем уже проверенные адреса
    already_checked = get_already_checked(checked_file)
    addresses_to_check = [addr for addr in addresses if addr not in already_checked]
    
    if already_checked:
        print(f"📊 Уже проверено: {len(already_checked)} адресов")
        print(f"📋 Осталось проверить: {len(addresses_to_check)} адресов")
    
    if not addresses_to_check:
        print("✅ Все адреса уже проверены!")
        return
    
    # Загружаем контрольную точку (если была прервана предыдущая проверка)
    checkpoint = load_checkpoint(checkpoint_file)
    if checkpoint:
        last_address = checkpoint.get("last_checked")
        print(f"📍 Найдена контрольная точка: {last_address[:10]}...")
        
        # Находим индекс с которого продолжить
        if last_address in addresses_to_check:
            start_index = addresses_to_check.index(last_address)
            addresses_to_check = addresses_to_check[start_index:]
            print(f"🔄 Продолжаем с адреса {start_index + 1}/{len(addresses)}")
    
    print("=" * 60)
    
    # Обрабатываем адреса
    results = []
    start_time = time.time()
    total_to_check = len(addresses_to_check)
    
    for i, address in enumerate(addresses_to_check, 1):
        # Обрабатываем адрес
        result = process_address(address, i, total_to_check)
        results.append(result)
        
        # Сохраняем контрольную точку
        save_checkpoint(address, result, checkpoint_file)
        
        # Отмечаем адрес как проверенный
        mark_address_checked(address, checked_file)
        
        # Пауза между запросами
        if i < total_to_check:
            time.sleep(0.3)  # 300ms пауза
    
    # Удаляем контрольную точку после успешного завершения
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("\n🗑 Контрольная точка удалена (проверка завершена)")
    
    # Обновляем оригинальный файл с отметками
    update_original_file_with_checkmarks(input_file, checked_file)
    
    # Анализируем результаты
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\n" + "=" * 60)
    print("📊 СТАТИСТИКА:")
    print("=" * 60)
    
    successful = sum(1 for r in results if not r.get("error"))
    with_usdt = sum(1 for r in results if r.get("has_usdt"))
    total_trx = sum(r.get("trx_balance", 0) for r in results)
    total_usdt = sum(r.get("usdt_balance", 0) for r in results)
    
    # Адреса с USDT > 10
    rich_addresses = [r for r in results if r.get("usdt_balance", 0) >= 10]
    
    print(f"✅ Успешно проверено: {successful}/{total_to_check}")
    print(f"💰 Всего TRX: {total_trx:.6f}")
    print(f"💵 Всего USDT: {total_usdt:.6f}")
    print(f"📊 Адресов с USDT: {with_usdt}")
    print(f"🏦 Адресов с USDT ≥ 10: {len(rich_addresses)}")
    print(f"⏱ Время выполнения: {total_time:.2f} сек.")
    print(f"📈 Среднее время на адрес: {total_time / total_to_check:.2f} сек.")
    
    # Сохраняем все результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Все результаты сохранены в: {output_file}")
    
    # Сохраняем адреса с USDT >= 10
    if rich_addresses:
        rich_file = f"rich_usdt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        rich_data = []
        for result in rich_addresses:
            rich_data.append({
                "address": result["address"],
                "trx_balance": result["trx_balance"],
                "usdt_balance": result["usdt_balance"],
                "checked_at": result["checked_at"]
            })
        
        with open(rich_file, 'w', encoding='utf-8') as f:
            json.dump(rich_data, f, indent=2, ensure_ascii=False)
        
        # Простой текстовый файл
        txt_file = f"rich_usdt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write(f"# Адреса с USDT ≥ 10\n")
            f.write(f"# Проверено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Найдено адресов: {len(rich_addresses)}\n\n")
            
            for i, addr in enumerate(rich_data, 1):
                f.write(f"{i}. {addr['address']} | TRX: {addr['trx_balance']:.2f} | USDT: {addr['usdt_balance']:.6f}\n")
        
        print(f"💰 Богатые адреса сохранены в: {rich_file}")
        print(f"📝 Текстовый список: {txt_file}")
        
        # Выводим топ адресов
        print("\n" + "=" * 60)
        print("🏆 АДРЕСА С USDT ≥ 10:")
        print("=" * 60)
        
        for i, addr in enumerate(rich_data, 1):
            print(f"{i}. {addr['address'][:10]}... | "
                  f"TRX: {addr['trx_balance']:.2f} | "
                  f"USDT: {addr['usdt_balance']:.6f}")
    
    print("\n" + "=" * 60)
    print("✅ ПРОВЕРКА ЗАВЕРШЕНА!")
    print("=" * 60)


if __name__ == "__main__":
    main()