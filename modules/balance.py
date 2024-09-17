import requests
import random
import json
import hmac
import hashlib
import time
from threading import Thread, Lock
from urllib.parse import urlencode
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import TOKEN, THRESHOLD, ACCOUNT_TYPE, ACCOUNT_DELAY_RANGE

# ANSI escape codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m" 
ENDC = "\033[0m"

def color_text(text, color_code):
    return f"{color_code}{text}{ENDC}"

def get_server_time(proxy):
    url = 'https://api.bybit.com/v5/market/time'
    try:
        # Проверка корректности прокси перед запросом
        if proxy.get("http", "").startswith("http://") or proxy.get("https", "").startswith("https://"):
            response = requests.get(url, proxies=proxy)
        else:
            raise ValueError("Неверный формат прокси URL")

        if response.status_code == 200:
            data = response.json()
            return int(data['result']['timeSecond']) * 1000
        else:
            raise Exception(f"Ошибка запроса: {response.status_code}")
    except requests.exceptions.InvalidURL as e:
        print(f"Ошибка в формате URL: {e}")
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе: {e}")
    except Exception as e:
        print(f"Произошла ошибка: {e}")
    return None

def generate_signature(api_key, api_secret, timestamp, recv_window, params, method='GET'):
    sign_str = f"{timestamp}{api_key}{recv_window}"
    if method == 'POST':
        sign_str += params
    else:
        sign_str += urlencode(sorted(params.items()))
    signature = hmac.new(api_secret.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

def get_coin_balance(api_key, api_secret, proxy, coin, accountType=ACCOUNT_TYPE):
    timestamp = get_server_time(proxy)
    if not timestamp:
        return None
    recv_window = "20000"
    params = {"accountType": accountType, "coin": coin}

    signature = generate_signature(api_key, api_secret, timestamp, recv_window, params, 'GET')
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": str(timestamp),
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    url = "https://api.bybit.com/v5/asset/transfer/query-account-coin-balance?" + urlencode(params)
    
    try:
        response = requests.get(url, headers=headers, proxies=proxy)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе баланса: {e}")
        return None

def load_accounts(filename='accounts.txt'):
    accounts = []
    with open(filename, 'r') as file:
        for line in file:
            parts = line.strip().split(':')
            if len(parts) < 7:
                continue
            account_id, api_key, api_secret, proxy_ip, proxy_port, proxy_login, proxy_password = parts[:7]
            
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

def write_to_file(lock, filename, text):
    with lock:
        with open(filename, 'a') as file:
            file.write(text + "\n")

def process_account(results, lock, account_id, api_key, api_secret, proxy):
    balance_info_text = get_coin_balance(api_key, api_secret, proxy, TOKEN)
    
    # Обработка случая, если запрос вернул None
    if balance_info_text is None:
        balance_output = f"{color_text(f'Не удалось получить баланс для аккаунта {account_id}: Проблема с запросом', RED)}"
        balance = 0
    else:
        balance_info = json.loads(balance_info_text)

        if 'result' in balance_info and 'balance' in balance_info['result']:
            balance = float(balance_info['result']['balance']['walletBalance'])
            color = RED if THRESHOLD is not None and balance < THRESHOLD else GREEN
            balance_output = f"{color_text(f'Баланс {TOKEN} на аккаунте {account_id}: {balance}', color)}"
        else:
            balance_output = f"{color_text(f'Не удалось получить баланс для аккаунта {account_id}: {balance_info_text}', RED)}"
            balance = 0  # Если баланс получить не удалось, считаем его нулевым

    with lock:
        results[account_id] = {"text": balance_output, "value": balance}

def main():
    accounts = load_accounts()
    output_filename = "balances.txt"
    lock = Lock()
    results = {}

    threads = []
    for account_data in accounts:
        account_id = account_data[0]  # Получение ID аккаунта
        thread = Thread(target=process_account, args=(results, lock, account_id) + account_data[1:])
        threads.append(thread)
        thread.start()
        random_delay = random.randint(*ACCOUNT_DELAY_RANGE)
        time.sleep(random_delay)

    for thread in threads:
        thread.join()

    total_balance = 0
    with open(output_filename, 'w') as file:
        for account_data in accounts:
            account_id = account_data[0]  # Получение ID аккаунта
            result = results.get(account_id, {"text": f"Нет данных для аккаунта {account_id}", "value": 0})
            output = result["text"]
            print(output)
            file.write(f"{output.strip(RED).strip(GREEN).strip(ENDC)}\n")  # Удаление ANSI кодов при записи в файл
            total_balance += result["value"]  # Подсчет общего баланса

        # Вывод и запись общего баланса желтым цветом
        total_balance_output = color_text(f"Общий баланс всех аккаунтов: {total_balance}", YELLOW)
        print(total_balance_output)
        file.write(f"\n{total_balance_output.strip(ENDC)}")  # Запись в файл без ANSI кодов

if __name__ == "__main__":
    main()
