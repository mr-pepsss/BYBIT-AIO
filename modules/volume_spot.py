import requests
import json
from threading import Thread
import time
import hmac
import hashlib
from requests.exceptions import RequestException
from urllib.parse import urlencode
import math
import random
import datetime
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from config import REPEATS, PAUSE_RANGE, MAX_RETRIES, DELAY_BETWEEN_RETRIES


# ANSI escape codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
ENDC = "\033[0m"

# Создание пути к файлу лога в папке 'logs'
log_folder = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(log_folder, exist_ok=True)  # Создает папку logs, если она не существует
log_filename = os.path.join(log_folder, datetime.datetime.now().strftime("Spot_volume_log_%Y-%m-%d_%H-%M-%S.txt"))

def color_text(text, color_code):
    return f"{color_code}{text}{ENDC}"

def log_to_file(message):
    """Записывает сообщение в файл лога."""
    with open(log_filename, "a") as log_file:
        log_file.write(message + "\n")

def print_green(text):
    colored_text = color_text(text, GREEN)
    print(colored_text)
    log_to_file(text)  # Записываем неформатированный текст в файл лога

def print_red(text):
    colored_text = color_text(text, RED)
    print(colored_text)
    log_to_file(text)  # Записываем неформатированный текст в файл лога

def print_yellow(text):
    colored_text = color_text(text, YELLOW)
    print(colored_text)
    log_to_file(text)  # Записываем неформатированный текст в файл лога

# Функция для получения текущего времени в формате timestamp
def get_server_time(proxy):
    url = 'https://api.bybit.com/v5/market/time'
    url = url.strip()  # Очистка URL-адреса от лишних символов
    try:
        response = requests.get(url, proxies=proxy)
        if response.status_code == 200:
            data = response.json()
            return int(data['result']['timeSecond']) * 1000
        raise Exception(f"Ошибка запроса: {response.status_code}")
    except Exception as e:
        raise

# Функция для подписи параметров запроса
def generate_signature(api_key, api_secret, timestamp, recv_window, params, method='GET'):
    sign_str = f"{timestamp}{api_key}{recv_window}"
    if method == 'POST':
        sign_str += params
    else:
        sign_str += urlencode(sorted(params.items()))
    signature = hmac.new(api_secret.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

# Функция для получения баланса монеты
def get_coin_balance(api_key, api_secret, proxy, coin, accountType="UNIFIED", memberId=None): # вместо UNIFIED может быть SPOT
    timestamp = get_server_time(proxy)
    recv_window = "20000"
    params = {"accountType": accountType, "coin": coin}
    if memberId:
        params["memberId"] = memberId

    signature = generate_signature(api_key, api_secret, timestamp, recv_window, params, 'GET')
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": str(timestamp),
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    url = "https://api.bybit.com/v5/asset/transfer/query-account-coin-balance?" + urlencode(params)
    
    #print_yellow(f"Отправляемый запрос на получение баланса: {url}")  # Логируем URL запроса
    response = requests.get(url, headers=headers, proxies=proxy)
    #print_yellow(f"Ответ API на запрос баланса: {response.text}")  # Логируем ответ API

    return response.text


def format_number(number, decimal_places):
    number_str = f"{number:.{decimal_places + 10}f}"  # Форматируем число с дополнительными знаками после запятой
    dot_index = number_str.find('.')
    if dot_index != -1:
        return number_str[:dot_index] + number_str[dot_index:dot_index + decimal_places + 1]
    return number_str

def create_unique_order_link_id():
    current_milliseconds = int(round(time.time() * 1000))
    random_number = random.randint(100, 999)
    return f"order_{current_milliseconds}_{random_number}"

# Функция для размещения рыночного ордера
def place_market_order(api_key, api_secret, symbol, side, quantity, proxy, decimal_places):
    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"

    formatted_quantity = format_number(quantity, decimal_places)

    print(f"Отправляемый запрос с количеством: {formatted_quantity}")

    order_link_id = create_unique_order_link_id()

    params = {
        "category": "spot",
        "symbol": symbol,
        "side": side.upper(),
        "orderType": "Market",
        "qty": formatted_quantity,
        "orderLinkId": order_link_id
    }

    params_json = json.dumps(params, separators=(',', ':'), sort_keys=True)

    signature = generate_signature(api_key, api_secret, timestamp, recv_window, params_json, method='POST')

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    url = "https://api.bybit.com/v5/order/create"
    response = requests.post(url, headers=headers, data=params_json, proxies=proxy)

    if response.status_code == 200:
        print_green("Ордер успешно размещен")
    else:
        print_red(f"Ошибка при размещении ордера: {response.status_code}")
        print(response.text)

    return response.text


def main(credentials, pause_range, account_balances):
    API_KEY = credentials['api_key']
    API_SECRET = credentials['api_secret']
    PROXY_DATA = credentials['proxy'].split(":")
    PROXY_IP = PROXY_DATA[0]
    PROXY_PORT = PROXY_DATA[1]
    PROXY_LOGIN = PROXY_DATA[2]
    PROXY_PASSWORD = PROXY_DATA[3]
    ACC_NUM = credentials['id']

    print_yellow(f"Запуск аккаунта номер {ACC_NUM}")
    
    my_proxies = {
        'http': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}",
        'https': f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_IP}:{PROXY_PORT}"
    }
    
    for i in range(1, REPEATS + 1):
        print_yellow(f"Повторение: {i}/{REPEATS}")

        try:
            # Получение баланса USDT
            response_text_usdt = get_coin_balance(API_KEY, API_SECRET, my_proxies, 'USDT')
            balance_data_usdt = json.loads(response_text_usdt)
            usdt_balance = 0.0
            if 'result' in balance_data_usdt and 'balance' in balance_data_usdt['result']:
                usdt_balance = float(balance_data_usdt['result']['balance']['walletBalance'])

            print(f"Полученный баланс USDT: {usdt_balance}")
            if usdt_balance > 0:
                print("Вызов функции place_market_order для USDT...")
                place_market_order(API_KEY, API_SECRET, "USDCUSDT", "BUY", usdt_balance, my_proxies, 2)  # Количество знаков после запятой для USDT

            # Получение баланса USDC
            response_text_usdc = get_coin_balance(API_KEY, API_SECRET, my_proxies, 'USDC')
            balance_data_usdc = json.loads(response_text_usdc)
            usdc_balance = 0.0
            if 'result' in balance_data_usdc and 'balance' in balance_data_usdc['result']:
                usdc_balance = float(balance_data_usdc['result']['balance']['walletBalance'])

            print(f"Полученный баланс USDC: {usdc_balance}")
            if usdc_balance > 0:
                print("Вызов функции place_market_order для USDC...")
                place_market_order(API_KEY, API_SECRET, "USDCUSDT", "SELL", usdc_balance, my_proxies, 2)  # Количество знаков после запятой для USDC

        except Exception as e:
            print_red(f"Ошибка: {e}")

        delay = random.randint(*PAUSE_RANGE)
        print(f"Выбрана задержка: {delay} секунд")
        time.sleep(delay)

    # В конце обработки каждого аккаунта обновляем баланс в account_balances
    final_balance_usdt = get_coin_balance(API_KEY, API_SECRET, my_proxies, 'USDT')
    final_balance_data = json.loads(final_balance_usdt)
    if 'result' in final_balance_data and 'balance' in final_balance_data['result']:
        account_balances[ACC_NUM] = float(final_balance_data['result']['balance']['walletBalance'])


def load_credentials_from_file(filename: str) -> list:
    credentials = []
    with open(filename, 'r') as file:
        for line in file.readlines():
            parts = line.strip().split(":")
            if len(parts) >= 6:  # Учет возможности отсутствия поля повторений
                account_info = {
                    'id': int(parts[0]),
                    'api_key': parts[1],
                    'api_secret': parts[2],
                    'proxy': ':'.join(parts[3:7])
                }
                credentials.append(account_info)
    return credentials


if __name__ == "__main__":
    credentials = load_credentials_from_file('accounts.txt')  # Загрузка учетных данных
    account_balances = {}  # Словарь для хранения балансов

    for cred in credentials:
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                main(cred, PAUSE_RANGE, account_balances)
                break
            except Exception as e:
                print_red(f"Ошибка: {e}")
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    print_yellow(f"Попытка {retry_count + 1} из {MAX_RETRIES}")
                    time.sleep(DELAY_BETWEEN_RETRIES)
                else:
                    print_red("Достигнуто максимальное количество попыток.")

    # Вывод баланса USDT каждого аккаунта
    for account_id, balance in account_balances.items():
        print_yellow(f"Баланс на аккаунте номер {account_id}: {balance} USDT")