import subprocess
import sys

def run_balance_module():
    subprocess.run([sys.executable, 'modules/balance.py'])

def run_transfer_module():
    subprocess.run([sys.executable, 'modules/transfer.py'])

def run_volume_spot_module():
    subprocess.run([sys.executable, 'modules/volume_spot.py'])

def run_swap_module():
    subprocess.run([sys.executable, 'modules/swap.py'])

def run_leverage_swap_module():
    subprocess.run([sys.executable, 'modules/leverage_swap.py'])

def run_withdraw_module():
    subprocess.run([sys.executable, 'modules/withdraw.py'])

def run_network_module():
    subprocess.run([sys.executable, 'modules/network.py'])

def run_upgrade_to_uta_module():
    subprocess.run([sys.executable, 'modules/upgrade_to_uta.py'])

def run_get_address_module():
    subprocess.run([sys.executable, 'modules/get_address.py'])

def main():
    while True:
        print("Выберите модуль для запуска:")
        print("1. Баланс")
        print("2. Перевод между счетами")
        print("3. Торговый объем на споте")
        print("4. Свап в любой паре на споте")
        print("5. Свап в любой паре на МАРЖЕ")
        print("6. Вывод с биржи")
        print("7. Узнать доступные сети для вывода")
        print("8. Узнать адрес для депозита")
        print("9. Обновление аккаунтов до UTA")
        print("10. Выход")

        choice = input("Введите номер модуля: ")

        if choice == '1':
            run_balance_module()
        elif choice == '2':
            run_transfer_module()
        elif choice == '3':
            run_volume_spot_module()
        elif choice == '4':
            run_swap_module()
        elif choice == '5':
            run_leverage_swap_module()
        elif choice == '6':
            run_withdraw_module()
        elif choice == '7':
            run_network_module()
        elif choice == '8':
            run_get_address_module()   
        elif choice == '9':
            run_upgrade_to_uta_module()
        elif choice == '10':
            print("Выход из программы.")
            break
        else:
            print("Неверный ввод. Пожалуйста, введите корректный номер модуля.")

if __name__ == "__main__":
    main()
