import requests
import time
import hmac
import json
import hashlib
import random
import uuid
import threading
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CHOSEN_TOKEN_WITHDRAW, DESIRED_NETWORK, ACCOUNT_DELAY_RANGE, WITHDRAW_AMOUNT

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

def get_server_time(my_proxies) -> int:
    response = requests.get(BASE_URL + "v3/public/time", proxies=my_proxies)
    if response.status_code != 200:
        raise Exception(f"Не удалось получить время сервера: {response.text}")

    content = response.json()
    if 'retCode' not in content or content['retCode'] != 0 or 'result' not in content or 'timeSecond' not in content['result']:
        raise Exception(f"Неожиданная структура ответа: {content}")

    return int(content['result']['timeSecond'])

def generate_signed_headers(api_key, api_secret, payload, my_proxies, request_type="GET") -> dict:
    time_stamp = str(get_server_time(my_proxies) * 1000)
    
    if request_type == "GET":
        param_str = time_stamp + api_key + '10000' + "&".join([f"{key}={value}" for key, value in payload.items()])
    else:
        param_str = time_stamp + api_key + '10000' + json.dumps(payload)
        
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
        'coin': CHOSEN_TOKEN_WITHDRAW
    }

    headers = generate_signed_headers(api_key, api_secret, params, my_proxies, request_type="GET")
    
    response = requests.get(BASE_URL + endpoint, headers=headers, params=params, proxies=my_proxies)
    
    content = response.json()
    
    if response.status_code != 200 or content.get('retCode') != 0:
        raise Exception(f"Не удалось получить баланс: {content.get('retMsg')}")

    return float(content['result']['balance']['walletBalance'])

def withdraw_from_bybit(api_key, api_secret, coin, chain, address, amount, my_proxies, tag=None):
    """
    Вывести активы из аккаунта Bybit.
    """
    # Конечная точка
    endpoint = "v5/asset/withdraw/create"
    
    # Текущее время
    timestamp = int(time.time() * 1000)
    
    # Данные запроса
    data = {
        "coin": coin,
        "chain": chain,
        "address": address,
        "amount": str(amount),
        "timestamp": timestamp,
        "forceChain": 1,  # Принудительное вывод на цепь
        "accountType": "FUND",  # Кошелек финансирования
        "feeType": 1  # Система автоматически удержит комиссию
    }
    
    if tag:
        data["tag"] = tag
    
    # Создать подписанные заголовки
    headers = generate_signed_headers(api_key, api_secret, data, my_proxies, request_type="POST")
    # Отправить запрос
    response = requests.post(BASE_URL + endpoint, headers=headers, data=json.dumps(data), proxies=my_proxies)
    
    content = response.json()
    
    if response.status_code != 200 or content.get('retCode') != 0:
        raise Exception(f"Не удалось вывести средства: {content.get('retMsg')}")

    return content['result']['id']  # Вернуть идентификатор вывода

def main(credentials, lock: threading.Lock):
    API_KEY = credentials['api_key']
    API_SECRET = credentials['api_secret']
    PROXY_DATA = credentials['proxy'].split(":")
    PROXY_IP = PROXY_DATA[0]
    PROXY_PORT = PROXY_DATA[1]
    PROXY_LOGIN = PROXY_DATA[2]
    PROXY_PASSWORD = PROXY_DATA[3]
    ACC_NUM = credentials['id']
    WITHDRAW_ADDRESS = credentials['withdraw_address']
    TAG = credentials['tag']

    proxy_data = f"{PROXY_IP}:{PROXY_PORT}:{PROXY_LOGIN}:{PROXY_PASSWORD}"

    my_proxies = {
        'http': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}",
        'https': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}"
    }

    with lock:
        print(f"Работаю с номером аккаунта {ACC_NUM}")

    with lock:
        print(f"Подключение через прокси: {proxy_data}")

    try:
        token_balance = get_balance(API_KEY, API_SECRET, "FUND", my_proxies)  # Получить баланс из FUND
    except Exception as e:
        with lock:
            print_red(f"Ошибка получения баланса на аккаунте номер {ACC_NUM}: {str(e)}")
        return

    # Проверка, задан ли фиксированный объем вывода
    if WITHDRAW_AMOUNT is None:
        withdraw_amount = token_balance - 0.0001  # оставляем небольшой остаток для избежания ошибок точности
    else:
        withdraw_amount = min(WITHDRAW_AMOUNT, token_balance - 0.0001)  # не выводим больше, чем есть на балансе

    withdraw_amount = round(withdraw_amount, 4)  # Округление до 4 знаков после запятой

    with lock:
        print_yellow(f"Текущий баланс {CHOSEN_TOKEN_WITHDRAW} на аккаунте номер {ACC_NUM} в FUND: {token_balance:.8f}")
        print_yellow(f"Сумма для вывода: {withdraw_amount:.8f} {CHOSEN_TOKEN_WITHDRAW}")

    if withdraw_amount > 0:
        try:
            # Попытка вывода
            transaction_id = withdraw_from_bybit(API_KEY, API_SECRET, CHOSEN_TOKEN_WITHDRAW, DESIRED_NETWORK, WITHDRAW_ADDRESS, withdraw_amount, my_proxies, tag=TAG)
            with lock:
                print_green(f"Вывод на аккаунте номер {ACC_NUM} прошел успешно. Сумма: {withdraw_amount:.8f} {CHOSEN_TOKEN_WITHDRAW}. Идентификатор транзакции: {transaction_id}")
        except Exception as e:
            with lock:
                print_red(f"Ошибка вывода на аккаунте номер {ACC_NUM}. Сообщение: {str(e)}")

def load_credentials_from_file(filename: str) -> list:
    credentials = []
    with open(filename, 'r') as file:
        for index, line in enumerate(file.readlines()):
            parts = line.strip().split(":")
            if len(parts) < 9:  
                print_red(f"Ошибка в строке {index + 1}: недостаточно данных!")
                continue
            account_info = {
                'id': int(parts[0]),
                'api_key': parts[1],
                'api_secret': parts[2],
                'proxy': ':'.join(parts[3:7]),
                'withdraw_address': parts[7],
                'tag': parts[8] if len(parts) > 8 else None
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

        # Задержка перед запуском следующего потока
        delay = random.randint(*ACCOUNT_DELAY_RANGE)
        print(f"Задержка перед следующим аккаунтом: {delay} секунд")
        time.sleep(delay)

    for t in threads:
        t.join()
