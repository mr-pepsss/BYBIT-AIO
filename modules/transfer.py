import requests
import json
import hmac
import hashlib
import time
import threading
import random
import uuid
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import CHOSEN_TOKEN, FROM_ACCOUNT_TYPE, TO_ACCOUNT_TYPE, ACCOUNT_DELAY_RANGE, TRANSFER_AMOUNT

# ANSI escape codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
ENDC = "\033[0m"

def print_green(text):
    print(f"{GREEN}{text}{ENDC}")

def print_red(text):
    print(f"{RED}{text}{ENDC}")

def print_yellow(text):
    print(f"{YELLOW}{text}{ENDC}")

BASE_URL = "https://api.bybit.com/"

print_yellow(f"Перевожу {CHOSEN_TOKEN} с {FROM_ACCOUNT_TYPE} на {TO_ACCOUNT_TYPE}")

def get_server_time(my_proxies) -> int:
    response = requests.get(BASE_URL + "v3/public/time", proxies=my_proxies)
    if response.status_code != 200:
        raise Exception(f"Failed to get server time: {response.text}")

    content = response.json()
    if 'retCode' not in content or content['retCode'] != 0 or 'result' not in content or 'timeSecond' not in content['result']:
        raise Exception(f"Unexpected response structure: {content}")

    return int(content['result']['timeSecond'])

def generate_signed_headers(api_key, api_secret, payload, my_proxies) -> dict:
    time_stamp = str(get_server_time(my_proxies) * 1000)
    
    if isinstance(payload, dict):  
        param_str = time_stamp + api_key + '10000' + "&".join([f"{key}={value}" for key, value in payload.items()])
    else:  
        param_str = time_stamp + api_key + '10000' + payload
        
    hash = hmac.new(bytes(api_secret, "utf-8"), param_str.encode("utf-8"), hashlib.sha256)
    signature = hash.hexdigest()
    
    return {
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': signature,
        'X-BAPI-TIMESTAMP': time_stamp,
        'X-BAPI-RECV-WINDOW': '10000',
        'Content-Type': 'application/json'
    }

def get_balance(api_key, api_secret, account_type, my_proxies) -> float:
    endpoint = "asset/v3/private/transfer/account-coin/balance/query"
    params = {
        'accountType': account_type,
        'coin': CHOSEN_TOKEN
    }

    headers = generate_signed_headers(api_key, api_secret, params, my_proxies)
    response = requests.get(BASE_URL + endpoint, headers=headers, params=params, proxies=my_proxies)
    content = response.json()
    
    if response.status_code != 200 or content.get('retCode') != 0:
        raise Exception(f"Failed to get balance: {content.get('retMsg')}")

    return float(content['result']['balance']['walletBalance'])

def main(credentials, lock: threading.Lock):
    API_KEY = credentials['api_key']
    API_SECRET = credentials['api_secret']
    PROXY_DATA = credentials['proxy'].split(":")
    PROXY_IP = PROXY_DATA[0]
    PROXY_PORT = PROXY_DATA[1]
    PROXY_LOGIN = PROXY_DATA[2]
    PROXY_PASSWORD = PROXY_DATA[3]
    ACC_NUM = credentials['id']

    proxy_data = f"{PROXY_IP}:{PROXY_PORT}:{PROXY_LOGIN}:{PROXY_PASSWORD}"
    my_proxies = {
        'http': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}",
        'https': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}"
    }

    with lock:
        print(f"Запуск аккаунта номер {ACC_NUM}")

    try:
        token_balance = get_balance(API_KEY, API_SECRET, FROM_ACCOUNT_TYPE, my_proxies)
    except Exception as e:
        with lock:
            print_red(f"Ошибка при получении баланса на аккаунте номер {ACC_NUM}: {str(e)}")
        return

    # Проверка, задан ли фиксированный объем перевода
    if TRANSFER_AMOUNT is None:
        transfer_amount = token_balance - 0.0001  # оставляем небольшой остаток для избежания ошибок точности
    else:
        transfer_amount = min(TRANSFER_AMOUNT, token_balance - 0.0001)  # не переводим больше, чем есть на балансе

    transfer_amount = round(transfer_amount, 4)  # Округление до 4 знаков после запятой

    with lock:
        print_yellow(f"Текущий баланс {CHOSEN_TOKEN} на аккаунте номер {ACC_NUM} в {FROM_ACCOUNT_TYPE}: {token_balance:.8f}")
        print_yellow(f"Сумма для перевода: {transfer_amount:.8f} {CHOSEN_TOKEN}")

    if transfer_amount > 0:
        transfer_data = {
            "transferId": str(uuid.uuid4()).replace('-', ''),
            "coin": CHOSEN_TOKEN,
            "amount": str(transfer_amount),
            "fromAccountType": FROM_ACCOUNT_TYPE,
            "toAccountType": TO_ACCOUNT_TYPE
        }

        payload = json.dumps(transfer_data)
        headers = generate_signed_headers(API_KEY, API_SECRET, payload, my_proxies)
        transfer_response = requests.post(BASE_URL + "asset/v3/private/transfer/inter-transfer", headers=headers, data=payload, proxies=my_proxies)
        transfer_content = transfer_response.json()

        with lock:
            if transfer_content.get("retCode") == 0:
                print_green(f"Перевод на аккаунте номер {ACC_NUM} успешно выполнен. Сумма: {transfer_amount:.8f} {CHOSEN_TOKEN}.")
            else:
                print_red(f"Ошибка перевода на аккаунте номер {ACC_NUM}. Сообщение: {transfer_content.get('retMsg')}")

def load_credentials_from_file(filename: str) -> list:
    credentials = []
    with open(filename, 'r') as file:
        for index, line in enumerate(file.readlines()):
            parts = line.strip().split(":")
            if len(parts) < 7:
                print_red(f"Ошибка в строке {index + 1}: не хватает данных!")
                continue
            account_info = {
                'id': int(parts[0]),
                'api_key': parts[1],
                'api_secret': parts[2],
                'proxy': ':'.join(parts[3:7]),
            }
            credentials.append(account_info)
    return credentials

if __name__ == '__main__':
    filename = "accounts.txt"
    credentials = load_credentials_from_file(filename)
    
    lock = threading.Lock()
    threads = []

    for cred in credentials:
        t = threading.Thread(target=main, args=(cred, lock))
        threads.append(t)
        t.start()

        # Добавляем задержку между запуском потоков
        delay = random.randint(*ACCOUNT_DELAY_RANGE)
        print(f"Выбрана задержка перед следующим аккаунтом: {delay} секунд")
        time.sleep(delay)

    for t in threads:
        t.join()
