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
ENDC = "\033[0m"

def color_text(text, color_code):
    return f"{color_code}{text}{ENDC}"

def get_server_time(proxy):
    url = 'https://api.bybit.com/v5/market/time'
    try:
        response = requests.get(url, proxies=proxy)
        if response.status_code == 200:
            data = response.json()
            return int(data['result']['timeSecond']) * 1000
        raise Exception(f"Ошибка запроса: {response.status_code}")
    except Exception as e:
        raise

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
    response = requests.get(url, headers=headers, proxies=proxy)
    return response.text

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

def process_account(results, lock, account_id, api_key, api_secret, proxy, threshold=THRESHOLD):
    balance_info_text = get_coin_balance(api_key, api_secret, proxy, TOKEN)
    balance_info = json.loads(balance_info_text)

    if 'result' in balance_info and 'balance' in balance_info['result']:
        balance = float(balance_info['result']['balance']['walletBalance'])
        color = RED if threshold is not None and balance < threshold else GREEN
        balance_output = color_text(f"Баланс {TOKEN} на аккаунте {account_id}: {balance}", color)
    else:
        balance_output = color_text(f"Не удалось получить баланс для аккаунта {account_id}: {balance_info_text}", RED)

    with lock:
        results[account_id] = balance_output

def main():
    accounts = load_accounts()
    output_filename = "balances.txt"
    lock = Lock()
    results = {}

    threads = []
    for account_id, api_key, api_secret, proxy in accounts:
        thread = Thread(target=process_account, args=(results, lock, account_id, api_key, api_secret, proxy))
        threads.append(thread)
        thread.start()
        # Генерируем случайную задержку в пределах ACCOUNT_DELAY_RANGE
        random_delay = random.randint(*ACCOUNT_DELAY_RANGE)
        time.sleep(random_delay)

    for thread in threads:
        thread.join()

    # Вывод и запись результатов в упорядоченном виде
    with open(output_filename, 'w') as file:
        for account_id, api_key, api_secret, proxy in accounts:
            output = results.get(account_id, f"Нет данных для аккаунта {account_id}")
            print(output)
            file.write(output.strip(RED).strip(GREEN).strip(ENDC) + "\n")  # Удаление ANSI кодов при записи в файл

if __name__ == "__main__":
    main()
