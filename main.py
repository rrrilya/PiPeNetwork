import requests
import schedule
import time
import json
import logging
import os

# Устанавливаем логирование
logging.basicConfig(level=logging.INFO)

# Константы
API_URL = "https://pipe-network-backend.pipecanary.workers.dev/api"
HEARTBEAT_INTERVAL = 5 * 60  # 5 минут
NODE_TEST_INTERVAL = 30  # 30 минут
TOKEN_FILE = "token.json"  # Файл для сохранения токена


# Функция для авторизации
def authorize():
    logging.info("Запуск процесса авторизации...")
    email = input("Введите ваш email: ")
    password = input("Введите ваш пароль: ")

    # Отправляем запрос на авторизацию
    try:
        logging.info("Отправка запроса на авторизацию...")
        response = requests.post(f"{API_URL}/login", json={"email": email, "password": password})
        response.raise_for_status()

        data = response.json()
        if "token" in data:
            token = data["token"]
            # Сохраняем токен в файл
            with open(TOKEN_FILE, "w") as token_file:
                json.dump({"token": token}, token_file)
            logging.info("Авторизация успешна! Токен сохранен.")
            return token
        else:
            logging.error("Не удалось получить токен. Проверьте правильность введенных данных.")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при авторизации: {e}")
        return None


# Функция для получения токена из файла
def get_token_from_file():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as token_file:
            data = json.load(token_file)
            logging.info("Токен успешно получен из файла.")
            return data.get("token")
    logging.info("Токен не найден в файле.")
    return None


# Функция для авторизации, если токен не найден
def get_authorized_token():
    token = get_token_from_file()
    if token:
        logging.info("Токен найден в файле.")
        return token
    logging.info("Токен не найден. Пожалуйста, выполните авторизацию.")
    return authorize()


def get_geo_location():
    try:
        # Получаем информацию о геолокации
        logging.info("Получение информации о геолокации...")
        response = requests.get("https://ipapi.co/json/")
        response.raise_for_status()
        data = response.json()
        logging.info(f"Геолокация получена: {data['city']}, {data['region']}, {data['country_name']}")
        return data['ip'], f"{data['city']}, {data['region']}, {data['country_name']}"
    except requests.exceptions.RequestException as e:
        logging.error(f"Geo-location error: {e}")
        return 'unknown', 'unknown'


def send_heartbeat(token):
    logging.info("Отправка heartbeat...")
    ip, location = get_geo_location()

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    payload = {
        'ip': ip,
        'location': location,
        'timestamp': int(time.time())
    }

    try:
        response = requests.post(f"{API_URL}/heartbeat", headers=headers, json=payload)
        if response.ok:
            logging.info("Heartbeat отправлен успешно.")
        else:
            logging.error(f"Не удалось отправить heartbeat: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при отправке heartbeat: {e}")


def test_node_latency(node):
    try:
        logging.info(f"Тестирование узла {node['node_id']} ({node['ip']})...")
        start_time = time.time()
        response = requests.get(f"http://{node['ip']}", timeout=5)
        latency = (time.time() - start_time) * 1000  # задержка в миллисекундах
        logging.info(f"Узел {node['node_id']} ({node['ip']}) имеет задержку: {latency}ms")
        return latency
    except requests.exceptions.RequestException:
        logging.warning(f"Узел {node['node_id']} ({node['ip']}) не доступен.")
        return -1  # Узел не доступен


def report_test_result(token, node, latency):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    payload = {
        'node_id': node['node_id'],
        'ip': node['ip'],
        'latency': latency,
        'status': 'online' if latency > 0 else 'offline'
    }

    try:
        logging.info(f"Отправка результатов тестирования узла {node['node_id']}...")
        response = requests.post(f"{API_URL}/test", headers=headers, json=payload)
        if response.ok:
            logging.info(f"Результаты тестирования для узла {node['node_id']} отправлены успешно.")
        else:
            logging.error(f"Не удалось отправить результаты для узла {node['node_id']}.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при отправке результатов для узла {node['node_id']}: {e}")


def run_node_tests(token):
    logging.info("Запуск тестов узлов...")
    try:
        # Получаем узлы для тестирования
        response = requests.get(f"{API_URL}/nodes", headers={'Authorization': f'Bearer {token}'})
        nodes = response.json()

        for node in nodes:
            latency = test_node_latency(node)
            report_test_result(token, node, latency)

        logging.info("Тестирование узлов завершено.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запуске тестов узлов: {e}")


# Функции для запуска периодических задач
def schedule_periodic_tasks(token):
    logging.info("Запуск планировщика задач...")
    # Запускаем heartbeat каждые 5 минут
    schedule.every(HEARTBEAT_INTERVAL).seconds.do(send_heartbeat, token)

    # Запускаем тестирование узлов каждые 30 минут
    schedule.every(NODE_TEST_INTERVAL).minutes.do(run_node_tests, token)

    while True:
        schedule.run_pending()
        time.sleep(1)  # Задержка, чтобы избежать излишней загрузки процессора


# Запуск задач при старте программы
if __name__ == "__main__":
    logging.info("Запуск программы тестирования узлов...")
    token = get_authorized_token()  # Получаем токен (если он есть)
    if token:
        schedule_periodic_tasks(token)
    else:
        logging.error("Программа не может продолжить без авторизации.")
