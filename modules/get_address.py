import csv
import random
import requests
import json
import hmac
import hashlib
import time
from threading import Thread, Lock
from urllib.parse import urlencode
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import COIN, CHAIN, ACCOUNT_DELAY_RANGE


def get_server_time(proxy):
    url = 'https://api.bybit.com/v5/market/time'
    try:
        response = requests.get(url, proxies=proxy)
        if response.status_code == 200:
            data = response.json()
            return int(data['result']['timeSecond']) * 1000
        else:
            raise Exception(f"Ошибка запроса: {response.status_code}")
    except Exception as e:
        raise Exception(f"Не удалось получить время сервера: {str(e)}")

def generate_signature(api_key, api_secret, timestamp, recv_window, params, method='GET'):
    sign_str = f"{timestamp}{api_key}{recv_window}"
    if method == 'POST':
        sign_str += params
    else:
        sign_str += urlencode(sorted(params.items()))
    signature = hmac.new(api_secret.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

def get_deposit_address(api_key, api_secret, proxy):
    server_time = get_server_time(proxy)
    recv_window = "20000"
    params = {"coin": COIN, "chainType": CHAIN}

    signature = generate_signature(api_key, api_secret, server_time, recv_window, params)
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": str(server_time),
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    url = "https://api.bybit.com/v5/asset/deposit/query-address?" + urlencode(sorted(params.items()))
    response = requests.get(url, headers=headers, proxies=proxy)
    response_data = response.json()
    if response_data['retCode'] == 0:
        address_info = response_data['result']['chains'][0]
        return address_info['addressDeposit']
    else:
        return "Не удалось получить адрес депозита"

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

def process_account(account_id, api_key, api_secret, proxy):
    try:
        address = get_deposit_address(api_key, api_secret, proxy)
        # Добавляем вывод сети
        return f"Адрес депозита для аккаунта {account_id} в сети {CHAIN}: {address}"
    except Exception as e:
        return f"Ошибка при получении адреса для аккаунта {account_id}: {str(e)}"


def thread_function(account_id, api_key, api_secret, proxy, results, lock):
    try:
        address = get_deposit_address(api_key, api_secret, proxy)
        result = f"Адрес депозита для аккаунта {account_id} для токена {COIN} в сети {CHAIN}: {address}"
    except Exception as e:
        result = f"Ошибка при получении адреса для аккаунта {account_id}: {str(e)}"
    with lock:
        results[account_id] = result

def main():
    accounts = load_accounts('accounts.txt')
    results = {}
    lock = Lock()
    threads = []

    for account_data in accounts:
        account_id, api_key, api_secret, proxy = account_data
        thread = Thread(target=thread_function, args=(account_id, api_key, api_secret, proxy, results, lock))
        threads.append(thread)
        thread.start()
        time.sleep(random.randint(*ACCOUNT_DELAY_RANGE))

    for thread in threads:
        thread.join()

    # Запись результатов в CSV файл и сортировка по account_id перед выводом
    with open('deposit_addresses.csv', mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Account ID', 'Chain', 'Token', 'Deposit Address'])  # Добавлен столбец "Token"
        # Сортировка результатов по целочисленному значению account_id
        for account_id in sorted(results.keys(), key=int):
            result = results[account_id]
            chain = CHAIN
            token = COIN  # Получаем токен из конфигурации
            if "в сети" in result:
                address = result.split(': ')[-1]
            else:
                address = "Error or no address"
            writer.writerow([account_id, chain, token, address])  # Записываем токен вместе с другими данными
            print(result)  # Вывод отсортированных результатов

if __name__ == "__main__":
    main()
