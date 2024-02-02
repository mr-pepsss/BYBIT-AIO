import requests
import json
import random
import time
import hmac
import hashlib
from urllib.parse import urlencode
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import ACCOUNT_DELAY_RANGE

# Перечисление цветов для вывода текста в консоли
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
ENDC = "\033[0m"

def color_text(text, color_code):
    return f"{color_code}{text}{ENDC}"

def print_green(text):
    colored_text = color_text(text, GREEN)
    print(colored_text)

def print_red(text):
    colored_text = color_text(text, RED)
    print(colored_text)

def print_yellow(text):
    colored_text = color_text(text, YELLOW)
    print(colored_text)

# Функция для загрузки информации об аккаунтах
def load_accounts(filename='accounts.txt'):
    accounts = []
    with open(filename, 'r') as file:
        for line in file:
            parts = line.strip().split(':')
            if len(parts) < 7:
                continue
            account_id, api_key, api_secret, proxy_ip, proxy_port, proxy_login, proxy_password = parts[:7]
            
            # Очистка API ключей от лишних символов и форматирование
            api_key = api_key.strip()
            api_secret = api_secret.strip()
            
            proxy_ip = proxy_ip.strip()
            proxy_port = proxy_port.strip()
            proxy_login = proxy_login.strip()
            proxy_password = proxy_password.strip()
            
            proxy = {
                "http": f"http://{proxy_login}:{proxy_password}@{proxy_ip}:{proxy_port}",
                "https": f"http://{proxy_login}:{proxy_password}@{proxy_ip}:{proxy_port}"
            }
            accounts.append((account_id, api_key, api_secret, proxy))
    return accounts

# Генерация подписи для запроса
def generate_signature(api_key, api_secret, timestamp, recv_window, params, method='POST'):
    sign_str = f"{timestamp}{api_key}{recv_window}"
    if method == 'POST':
        sign_str += params
    else:
        sign_str += urlencode(sorted(params.items()))
    signature = hmac.new(api_secret.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

# Функция для получения текущей информации об аккаунте
def get_account_info(api_key, api_secret, proxy):
    endpoint = "https://api.bybit.com/v5/account/info"
    
    # Генерация значений для заголовков
    timestamp = int(time.time() * 1000)
    recv_window = 5000  # Вы можете настроить этот параметр по вашему усмотрению
    
    # Создание заголовков
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": generate_signature(api_key, api_secret, timestamp, recv_window, {}, method='GET'),
        "X-BAPI-TIMESTAMP": str(timestamp),
        "X-BAPI-RECV-WINDOW": str(recv_window)
    }
    
    try:
        # Выполнение HTTP-запроса
        response = requests.get(endpoint, proxies=proxy, headers=headers)
        data = response.json()
        
        if "unifiedMarginStatus" in data["result"]:
            return data["result"]
        else:
            print_red("Поле 'unifiedMarginStatus' отсутствует в ответе от API.")
            return None
    
    except Exception as e:
        print_red(f"Произошла ошибка при выполнении запроса: {str(e)}")
        return None

# Обновленная функция для обновления аккаунта до UTA
def upgrade_account_to_uta_if_needed(api_key, api_secret, proxy):
    account_info = get_account_info(api_key, api_secret, proxy)
    
    if account_info:
        unified_margin_status = account_info["unifiedMarginStatus"]
        
        if unified_margin_status == 4:
            print_green("Аккаунт уже находится в режиме UTA. Обновление не требуется.")
        else:
            print(f"Текущий статус аккаунта: {unified_margin_status}")
            upgrade_account_to_uta(api_key, api_secret, proxy)
    else:
        print_red("Не удалось получить информацию об аккаунте.")

# Функция для обновления аккаунта до UTA
def upgrade_account_to_uta(api_key, api_secret, proxy):
    endpoint = "https://api.bybit.com/v5/account/upgrade-to-uta"
    
    # Генерация значений для заголовков
    timestamp = int(time.time() * 1000)
    recv_window = 5000  # Вы можете настроить этот параметр по вашему усмотрению
    payload = "{}"
    
    # Создание заголовков
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": generate_signature(api_key, api_secret, timestamp, recv_window, payload, method='POST'),
        "X-BAPI-TIMESTAMP": str(timestamp),
        "X-BAPI-RECV-WINDOW": str(recv_window),
        "Content-Type": "application/json"
    }
    
    try:
        # Выполнение HTTP-запроса
        response = requests.post(endpoint, proxies=proxy, headers=headers, data=payload)
        data = response.json()
        
        # Проверка наличия поля unifiedUpdateStatus
        if "unifiedUpdateStatus" in data["result"]:
            unified_update_status = data["result"]["unifiedUpdateStatus"]
            if unified_update_status == "SUCCESS":
                print_green("Аккаунт успешно обновлен до UTA.")
            elif unified_update_status == "PROCESS":
                print_yellow("Обновление аккаунта в процессе. Проверьте статус позже.")
            else:
                print_red(f"Ошибка при обновлении аккаунта. Статус: {unified_update_status}")
                if "unifiedUpdateMsg" in data["result"]:
                    error_msgs = data["result"]["unifiedUpdateMsg"]["msg"]
                    for error_msg in error_msgs:
                        print_red(error_msg)
        else:
            print_red("Поле 'unifiedUpdateStatus' отсутствует в ответе от API.")
    
    except Exception as e:
        print_red(f"Произошла ошибка при выполнении запроса: {str(e)}")

# Функция для ожидания завершения обновления аккаунта
def wait_for_account_upgrade(api_key, api_secret, proxy):
    max_attempts = 30  # Максимальное количество попыток проверки статуса
    interval_seconds = 10  # Интервал между попытками в секундах
    
    for attempt in range(max_attempts):
        account_info = get_account_info(api_key, api_secret, proxy)
        if account_info:
            unified_margin_status = account_info["unifiedMarginStatus"]
            if unified_margin_status == 4:
                print_green("Аккаунт успешно обновлен до UTA.")
                return
            elif unified_margin_status == "PROCESS":
                print_yellow("Обновление аккаунта в процессе. Проверьте статус позже.")
            else:
                print_red(f"Ошибка при обновлении аккаунта. Статус: {unified_margin_status}")
                if "unifiedUpdateMsg" in account_info:
                    error_msgs = account_info["unifiedUpdateMsg"]["msg"]
                    for error_msg in error_msgs:
                        print_red(error_msg)
        else:
            print_red("Не удалось получить информацию об аккаунте.")
        
        if attempt < max_attempts - 1:
            time.sleep(interval_seconds)
        else:
            print_red("Достигнут лимит попыток. Проверьте статус аккаунта вручную.")


def main():
    accounts = load_accounts()  # Загрузка информации о всех аккаунтах
    
    for account_id, api_key, api_secret, proxy in accounts:
        print(f"Обновление аккаунта {account_id}...")
        upgrade_account_to_uta_if_needed(api_key, api_secret, proxy)
        wait_for_account_upgrade(api_key, api_secret, proxy)

        # Генерация случайной задержки
        delay = random.randint(*ACCOUNT_DELAY_RANGE)
        print(f"Задержка перед следующим аккаунтом: {delay} секунд")
        time.sleep(delay)

        print("\n")

if __name__ == "__main__":
    main()
