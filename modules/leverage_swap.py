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
import sys
import os

# Добавление пути к корневой директории проекта в sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import (TOKEN_1, TOKEN_2, TRADE_DIRECTION, EXCHANGE_AMOUNT, 
                    MAX_RETRIES, DELAY_BETWEEN_RETRIES, LEV, ACCOUNT_DELAY_RANGE)

SYMBOL_TO_TRADE = TOKEN_1 + TOKEN_2


# ANSI escape codes
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
def get_coin_balance(api_key, api_secret, proxy, coin, accountType="UNIFIED", memberId=None): # вместо UNIFIED Может быть SPOT
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
    response = requests.get(url, headers=headers, proxies=proxy)
    return response.text

# Функция для обрезания числа до заданного количества знаков после запятой без округления
def format_number(number, decimal_places):
    return str(number)[:str(number).index('.') + 1 + decimal_places]

def create_unique_order_link_id():
    current_milliseconds = int(round(time.time() * 1000))
    random_number = random.randint(100, 999)
    return f"order_{current_milliseconds}_{random_number}"

def toggle_margin_trade(api_key, api_secret, spotMarginMode, proxy):
    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"
    params = {
        "spotMarginMode": spotMarginMode  # "1" для включения, "0" для выключения
    }

    params_json = json.dumps(params, separators=(',', ':'))

    signature = generate_signature(api_key, api_secret, timestamp, recv_window, params_json, method='POST')

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    url = "https://api.bybit.com/v5/spot-margin-trade/switch-mode"
    response = requests.post(url, headers=headers, data=params_json, proxies=proxy)

    return response.text

def set_leverage(api_key, api_secret, leverage, proxy):
    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"
    params = {
        "leverage": leverage
    }

    params_json = json.dumps(params, separators=(',', ':'))

    signature = generate_signature(api_key, api_secret, timestamp, recv_window, params_json, method='POST')

    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    url = "https://api.bybit.com/v5/spot-margin-trade/set-leverage"
    response = requests.post(url, headers=headers, data=params_json, proxies=proxy)

    return response.text


# Функция для размещения рыночного ордера
def place_market_order(api_key, api_secret, symbol, side, quantity, proxy, decimal_places, is_leverage=1):
    timestamp = str(int(time.time() * 1000))
    recv_window = "20000"

    formatted_quantity = format_number(float(quantity), decimal_places)
    print_green(f"Отправляемый запрос с количеством: {formatted_quantity}")

    order_link_id = create_unique_order_link_id()

    params = {
        "category": "spot",
        "symbol": symbol,
        "side": side.upper(),
        "orderType": "Market",
        "qty": formatted_quantity,
        "orderLinkId": order_link_id,
        "isLeverage": is_leverage  # Указываем, что это маржинальный ордер
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

    return response.text


# Функция для размещения рыночного ордера с повторными попытками
def attempt_place_market_order(api_key, api_secret, symbol, side, quantity, proxy, decimal_places, account_id):
    retries = 0
    while retries < MAX_RETRIES:
        # Получаем баланс валюты для торговли
        if TRADE_DIRECTION == "SELL":
            coin_to_check = TOKEN_1
        else:
            coin_to_check = TOKEN_2
        
        balance_info_text = get_coin_balance(api_key, api_secret, proxy, coin_to_check)
        balance_info = json.loads(balance_info_text)
        if 'result' in balance_info and 'balance' in balance_info['result']:
            balance = float(balance_info['result']['balance']['walletBalance'])
            print_yellow(f"Доступный баланс для {coin_to_check}: {balance}")
        else:
            print_red("Не удалось получить баланс.")
            return None

        # Рассчитываем количество для торговли
        if EXCHANGE_AMOUNT is None:
            # Используем весь доступный баланс с учетом кредитного плеча
            quantity = balance * LEV
        else:
            quantity = EXCHANGE_AMOUNT

        formatted_quantity = format_number(quantity, decimal_places)
        print_green(f"Используемое количество для торговли на попытке {retries + 1}: {formatted_quantity}")
        
        order_response_text = place_market_order(api_key, api_secret, SYMBOL_TO_TRADE, TRADE_DIRECTION, formatted_quantity, proxy, decimal_places, 1) # is_leverage всегда 1, т.к. уже учли в quantity

        order_response = json.loads(order_response_text)
        if order_response['retCode'] == 0:
            print_green(f"Свап успешный для аккаунта {account_id}")
            return order_response_text
        else:
            print_red(f"Ошибка при свапе для аккаунта {account_id}: {order_response['retMsg']}")
            retries += 1
            if retries < MAX_RETRIES:
                print_yellow(f"Повторная попытка через {DELAY_BETWEEN_RETRIES} секунд...")
                time.sleep(DELAY_BETWEEN_RETRIES)
    return None


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

def process_account(account_id, api_key, api_secret, proxy):
    print_yellow(f"Работаем с аккаунтом: {account_id}")

    # Включение маржинальной торговли
    try:
        toggle_margin_response = toggle_margin_trade(api_key, api_secret, "1", proxy)  # "1" для включения
        toggle_margin_result = json.loads(toggle_margin_response)
        if toggle_margin_result['retCode'] != 0:
            print_red(f"Не удалось включить маржинальную торговлю для аккаунта {account_id}: {toggle_margin_result['retMsg']}")
            return
        else:
            print_green(f"Маржинальная торговля включена для аккаунта {account_id}")
    except Exception as e:
        print_red(f"Ошибка при включении маржинальной торговли для аккаунта {account_id}: {str(e)}")
        return

    # Установка кредитного плеча
    leverage = LEV  # Пример значения кредитного плеча
    try:
        leverage_response_text = set_leverage(api_key, api_secret, leverage, proxy)
        leverage_response = json.loads(leverage_response_text)
        if leverage_response['retCode'] != 0:
            print_red(f"Ошибка при установке кредитного плеча для аккаунта {account_id}: {leverage_response['retMsg']}")
            return
        else:
            print_green(f"Кредитное плечо успешно установлено для аккаунта {account_id}")
    except Exception as e:
        print_red(f"Ошибка при установке кредитного плеча для аккаунта {account_id}: {str(e)}")
        return

    # Проверка баланса и размещение ордера
    coin_to_check = TOKEN_1 if TRADE_DIRECTION == "SELL" else TOKEN_2
    print(f"Проверяем токен: {coin_to_check}")

    try:
        balance_info_text = get_coin_balance(api_key, api_secret, proxy, coin_to_check, 'UNIFIED')
        balance_info = json.loads(balance_info_text)
        if 'result' in balance_info and 'balance' in balance_info['result']:
            balance = balance_info['result']['balance']['walletBalance']
            print(f"Баланс токена на аккаунте {account_id}: {coin_to_check}: {balance}")

            if float(balance) < 1 / (10 ** 2):  # Проверка минимального баланса для торговли
                print_red(f"Недостаточный баланс для торговли на аккаунте {account_id}")
                return
            else:
                quantity = EXCHANGE_AMOUNT if EXCHANGE_AMOUNT is not None else balance
                print(f"Используемое количество для торговли: {quantity}")

                # Размещение ордера
                for attempt in range(MAX_RETRIES):
                    order_response_text = attempt_place_market_order(
                        api_key, api_secret, SYMBOL_TO_TRADE, TRADE_DIRECTION, quantity, proxy, 2, account_id  # Предполагается, что десятичные места равны 2
                    )
                    order_response = json.loads(order_response_text)
                    if order_response['retCode'] == 0:
                        print_green(f"Успешная торговля для аккаунта {account_id}")
                        break
                    else:
                        print_red(f"Попытка {attempt + 1}/{MAX_RETRIES} на аккаунте {account_id} не удалась: {order_response['retMsg']}")
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(DELAY_BETWEEN_RETRIES)
        else:
            print_red(f"Не удалось получить баланс для аккаунта {account_id}: {balance_info_text}")
    except Exception as e:
        print_red(f"Ошибка при получении баланса для аккаунта {account_id}: {str(e)}")


def main():
    accounts = load_accounts()
    threads = []
    
    for account_id, api_key, api_secret, proxy in accounts:
        thread = Thread(target=process_account, args=(account_id, api_key, api_secret, proxy))
        threads.append(thread)
        thread.start()
        # Генерируем случайную задержку в пределах ACCOUNT_DELAY_RANGE
        random_delay = random.randint(*ACCOUNT_DELAY_RANGE)
        time.sleep(random_delay)
    
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
