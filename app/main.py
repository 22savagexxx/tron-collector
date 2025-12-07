import requests
import time
import json
import os
from datetime import datetime

# Конфигурация
API_KEY = "51a153dc-3a84-4092-9855-65397c4342a8"
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
MIN_USDT = 10

# Telegram конфиг - ПРОВЕРЬТЕ ЭТИ ДАННЫЕ
TG_TOKEN = "8275156524:AAFWlDsud0qdJn7oKY-xCO1-y_LWIylOF_8"
TG_CHAT_ID = "700416664"  # Убедитесь что это правильный chat_id


def send_tg(message, retries=3):
    """Отправка сообщения в Telegram с повторными попытками"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠ Telegram конфиг не настроен")
        return False
    
    for attempt in range(retries):
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {
                "chat_id": TG_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                print(f"⚠ Telegram ошибка {response.status_code}: {response.text}")
                time.sleep(2)
        
        except Exception as e:
            print(f"⚠ Telegram ошибка: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    
    return False


def test_telegram():
    """Тест подключения к Telegram"""
    print("🔍 Тестирую подключение к Telegram...")
    test_msg = "✅ Бот подключен! Начинаю проверку адресов."
    if send_tg(test_msg):
        print("✅ Telegram подключен успешно")
        return True
    else:
        print("❌ Не удалось подключиться к Telegram")
        return False


def get_usdt_balance(address, retries=3):
    """Получает баланс USDT для адреса с повторными попытками"""
    for attempt in range(retries):
        try:
            url = f"https://api.trongrid.io/v1/accounts/{address}"
            headers = {"TRON-PRO-API-KEY": API_KEY} if API_KEY else {}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            if "data" in data and data["data"]:
                trc20_data = data["data"][0].get("trc20", [])
                for token in trc20_data:
                    if USDT_CONTRACT in token:
                        usdt_sun = int(token[USDT_CONTRACT])
                        return usdt_sun / 1_000_000
            return 0
        
        except Exception as e:
            if attempt == retries - 1:
                print(f"  ❌ Ошибка после {retries} попыток: {e}")
                return 0
            time.sleep(2)
    
    return 0


def main():
    print(f"🔍 Проверка USDT на адресах (минимум {MIN_USDT} USDT)")
    print("=" * 60)
    
    # Тестируем Telegram
    telegram_ok = test_telegram()
    
    # Файлы
    input_file = "unique_addresses.txt"
    output_file = "found_addresses.json"
    checkpoint_file = "checkpoint.txt"
    error_file = "error_addresses.txt"
    
    # Загружаем checkpoint (последний успешно обработанный индекс)
    last_index = 0
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r") as f:
                last_index = int(f.read().strip())
            print(f"🔄 Продолжаю с адреса #{last_index + 1}")
        except:
            pass
    
    # Загружаем ошибки
    error_addresses = set()
    if os.path.exists(error_file):
        with open(error_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    error_addresses.add(line)
    
    # Читаем все адреса
    with open(input_file, "r") as f:
        all_lines = f.readlines()
    
    # Загружаем найденные адреса
    found = []
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                found = json.load(f)
        except:
            pass
    
    total_addresses = len(all_lines)
    processed_count = 0
    found_count = len(found)
    error_count = len(error_addresses)
    
    # Стартовое сообщение
    if telegram_ok:
        start_msg = (f"🚀 <b>Начинаю проверку USDT</b>\n"
                     f"Адресов всего: {total_addresses}\n"
                     f"Продолжаю с: #{last_index + 1}\n"
                     f"Уже найдено: {found_count}")
        send_tg(start_msg)
    
    # Обрабатываем адреса
    for i in range(last_index, total_addresses):
        line = all_lines[i].strip()
        
        # Пропускаем пустые строки и комментарии
        if not line or line.startswith("#"):
            continue
        
        # Извлекаем адрес
        parts = line.split()
        address = parts[0].lower().replace('0x', '')
        
        # Пропускаем адреса с ошибками
        if address in error_addresses:
            print(f"[{i + 1}/{total_addresses}] {address[:10]}... ⚠ Пропускаем (была ошибка)")
            continue
        
        print(f"[{i + 1}/{total_addresses}] {address[:10]}...", end=" ")
        
        # Проверяем адрес
        usdt = get_usdt_balance(address)
        print(f"= {usdt:.6f} USDT")
        
        processed_count += 1
        
        # Сохраняем checkpoint ПОСЛЕ успешной проверки
        with open(checkpoint_file, "w") as f:
            f.write(str(i))
        
        # Обрабатываем результат
        if usdt == 0:
            # Возможно ошибка API, помечаем для повторной проверки
            if address not in error_addresses:
                error_addresses.add(address)
                with open(error_file, "a") as f:
                    f.write(address + "\n")
                error_count += 1
        
        # Если нашли достаточно USDT
        elif usdt >= MIN_USDT:
            # Проверяем, нет ли уже этого адреса
            if not any(r["address"] == address for r in found):
                result = {
                    "address": address,
                    "usdt": usdt,
                    "found_at": datetime.now().isoformat()
                }
                found.append(result)
                found_count += 1
                
                # Сохраняем сразу
                with open(output_file, "w") as f:
                    json.dump(found, f, indent=2)
                
                # Уведомление в Telegram
                if telegram_ok:
                    msg = (f"💰 <b>НАЙДЕН АДРЕС!</b>\n"
                           f"Адрес: <code>{address}</code>\n"
                           f"USDT: <b>{usdt:.6f}</b>\n"
                           f"Всего найдено: {found_count}")
                    send_tg(msg)
        
        # Логи в Telegram каждые 5 адресов
        if processed_count % 5 == 0 and telegram_ok:
            progress = (i + 1) / total_addresses * 100
            msg = (f"📊 <b>Прогресс:</b> {i + 1}/{total_addresses} ({progress:.1f}%)\n"
                   f"✅ Проверено: {processed_count}\n"
                   f"💰 Найдено: {found_count}\n"
                   f"⚠ Ошибок: {error_count}")
            send_tg(msg)
        
        # Пауза между запросами
        time.sleep(0.5)
    
    # ФИНАЛ - после завершения всех адресов
    print("\n" + "=" * 60)
    
    # Удаляем checkpoint
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
    
    # Обновляем исходный файл с отметками
    if processed_count > 0:
        print("📝 Обновляю файл с отметками...")
        updated_lines = []
        
        for line in all_lines:
            line = line.strip()
            if not line or line.startswith("#"):
                updated_lines.append(line)
                continue
            
            parts = line.split()
            address = parts[0].lower().replace('0x', '')
            
            # Отмечаем только успешно обработанные адреса
            if address in error_addresses:
                # Адреса с ошибками оставляем без отметки
                updated_lines.append(line)
            elif "# проверен" not in line:
                updated_lines.append(f"{line} # проверен")
            else:
                updated_lines.append(line)
        
        # Сохраняем обновленный файл
        with open(input_file, "w") as f:
            f.write("\n".join(updated_lines))
    
    # Финальное сообщение
    final_msg = (f"✅ <b>Проверка завершена!</b>\n"
                 f"📊 Всего адресов: {total_addresses}\n"
                 f"✅ Успешно проверено: {processed_count}\n"
                 f"💰 Найдено с USDT ≥ {MIN_USDT}: {found_count}\n"
                 f"⚠ Адресов с ошибками: {error_count}")
    
    print(final_msg)
    print(f"📁 Результаты: {output_file}")
    
    if telegram_ok:
        send_tg(final_msg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Проверка прервана пользователем")
        if TG_TOKEN and TG_CHAT_ID:
            send_tg("⚠ Проверка прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        if TG_TOKEN and TG_CHAT_ID:
            send_tg(f"❌ Скрипт упал с ошибкой: {str(e)[:100]}")