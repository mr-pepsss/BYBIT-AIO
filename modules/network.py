import requests
import hmac
import time
import hashlib

def load_first_account_credentials(filename='accounts.txt'):
    with open(filename, 'r') as file:
        line = file.readline()
        parts = line.strip().split(':')
        if len(parts) < 7:
            raise ValueError("Недостаточно данных в файле accounts.txt")
        api_key = parts[1]
        api_secret = parts[2]
        proxy = ':'.join(parts[3:7])  # Соединяем ip, port, login и pass в одну строку
        return api_key, api_secret, proxy

def generate_signature(secret, params):
    sorted_params = sorted(params.items(), key=lambda d: d[0])
    query_string = "&".join(["{}={}".format(k, v) for k, v in sorted_params])
    return hmac.new(bytes(secret, 'latin-1'), msg=bytes(query_string, 'latin-1'), digestmod=hashlib.sha256).hexdigest().upper()

def get_coin_chains(coin_ticker, api_key, api_secret, proxy):
    url = "http://api.bybit.com/v5/asset/coin/query-info"
    
    params = {
        "coin": coin_ticker,
        "api_key": api_key,
        "timestamp": str(int(time.time() * 1000))
    }
    
    params["sign"] = generate_signature(api_secret, params)
    
    ip, port, login, password = proxy.split(":")
    proxies = {
        "http": f"http://{login}:{password}@{ip}:{port}",
        "https": f"http://{login}:{password}@{ip}:{port}"
    }
    
    try:
        response = requests.get(url, params=params, proxies=proxies)
        response.raise_for_status()

        data = response.json()

        if "result" in data and "rows" in data["result"]:
            for coin_info in data['result']["rows"]:
                if coin_info["coin"] == coin_ticker:
                    chains = coin_info["chains"]
                    for chain in chains:
                        print(chain['chain'])
        else:
            print("Ошибка при получении данных")
            print(f"Response: {data}")
    
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при отправке запроса: {e}")

if __name__ == "__main__":
    API_KEY, API_SECRET, PROXY = load_first_account_credentials()
    coin_ticker = input("Введите тикер токена: ").upper()
    get_coin_chains(coin_ticker, API_KEY, API_SECRET, PROXY)
