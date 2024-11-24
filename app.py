import os
import sqlite3
import threading
import time
import logging
import json
import hashlib
import hmac
import urllib.parse
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from itsdangerous import URLSafeSerializer, BadSignature
from telegram import WebAppData
from urllib.parse import parse_qsl
from operator import itemgetter

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

# Настройка логирования
app.logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError('BOT_TOKEN is not set')

# Инициализируем сериализатор для токенов
SECRET_KEY = app.secret_key
serializer = URLSafeSerializer(SECRET_KEY)

@app.route('/process_init_data', methods=['POST'])
def process_init_data():
    try:
        data = request.get_json()
        init_data = data.get('initData')
        referrer_id = data.get('referrer_id')
        app.logger.info(f"Received init_data: {init_data}")
        app.logger.info(f"Received referrer_id: {referrer_id}")

        # Проверяем init_data
        is_valid, result = check_init_data(init_data, BOT_TOKEN)
        if not is_valid:
            app.logger.error(f"Invalid init data: {result}")
            return jsonify({'success': False, 'error': result}), 403
        app.logger.info(f"Результат проверки init_data: {is_valid}")

        # Получаем данные пользователя
        user_data_json = result.get('user')
        if not user_data_json:
            app.logger.error('Данные пользователя отсутствуют в initData.')
            return jsonify({'success': False, 'error': 'Данные пользователя отсутствуют'}), 403

        user_data = json.loads(user_data_json)
        user_id = user_data.get('id')
        username = user_data.get('username', '')
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        name = f"{first_name} {last_name}".strip()

        conn = get_db_connection()
        user_db = conn.execute('SELECT * FROM Users WHERE ID = ?', (user_id,)).fetchone()
        if user_db is None:
            conn.execute("INSERT INTO Users (ID, Username, Name) VALUES (?, ?, ?)", (user_id, username, name))
            conn.execute("INSERT INTO Statistic (User_id) VALUES (?)", (user_id,))
            conn.commit()
            app.logger.info(f"New user added: {user_id} - {username}")

        # Обработка реферальной ссылки
        if referrer_id and referrer_id != str(user_id):
            existing_friend = conn.execute('''
                SELECT * FROM Friends WHERE User_id = ? AND Friend_id = ?
            ''', (referrer_id, user_id)).fetchone()
            if not existing_friend:
                conn.execute('INSERT INTO Friends (User_id, Friend_id) VALUES (?, ?)', (referrer_id, user_id))
                conn.execute('UPDATE Statistic SET Coins = Coins + 100 WHERE User_id = ?', (referrer_id,))
                conn.commit()
                app.logger.info(f"Referral added: {referrer_id} invited {user_id}")

        # Получаем актуальные данные пользователя
        coins_row = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
        level_row = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
        coins = coins_row['Coins'] if coins_row else 0
        level = level_row['Level'] if level_row else 1

        current_skin_row = conn.execute("SELECT Current_skin FROM Users WHERE ID = ?", (user_id,)).fetchone()
        current_skin = current_skin_row['Current_skin'] if current_skin_row else 'default.png'
        if not current_skin:
            current_skin = 'default.png'
        conn.close()

        # Генерируем токен
        token = serializer.dumps({'user_id': user_id})

        return jsonify({
            'success': True,
            'coins': coins,
            'level': level,
            'current_skin': current_skin,
            'username': username,
            'token': token
        })
    except Exception as e:
        app.logger.error(f'Error processing init_data: {e}')
        return jsonify({'success': False, 'error': 'Server error'}), 500

# Ваша рабочая функция check_init_data
# def check_init_data(init_data):
#     try:
#         app.logger.info(f'Проверка init_data: {init_data}')
#         web_app_data = WebAppData.from_webapp(init_data=init_data, bot_token=BOT_TOKEN)
#         app.logger.info('initData verification successful')
#         return True, web_app_data
#     except Exception as e:
#         app.logger.error(f'Ошибка проверки init_data: {e}')
#         return False, None

def check_init_data(init_data, bot_token):
    try:
        # Парсим init_data с URL-декодированием значений
        parsed_data = dict(parse_qsl(init_data))
        
        # Извлекаем хэш из данных
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            return False, 'Параметр hash отсутствует в init_data.'
        
        # Удаляем 'hash' из данных
        # Сортируем параметры по ключу
        data_check_arr = [f"{k}={v}" for k, v in sorted(parsed_data.items(), key=itemgetter(0))]
        data_check_string = '\n'.join(data_check_arr)
        
        # Вычисляем секретный ключ
        secret_key = hmac.new(
            key=b'WebAppData',
            msg=bot_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        # Вычисляем хэш
        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Сравниваем вычисленный хэш с хэшем, полученным от Telegram
        if not hmac.compare_digest(computed_hash, received_hash):
            return False, 'Хэш не совпадает.'
        
        # Проверяем актуальность auth_date
        auth_date = int(parsed_data.get('auth_date', '0'))
        current_time = int(time.time())
        if current_time - auth_date > 86400:
            return False, 'auth_date слишком старый.'
        
        # Возвращаем успешный результат и данные
        return True, parsed_data
    except Exception as e:
        return False, f'Ошибка при проверке initData: {e}'

@app.route('/')
def index():
    return render_template('index.html')



# Обновляем маршруты для использования токена вместо сессий

@app.route('/friends')
def friends():
    token = request.args.get('token')
    if not token:
        return redirect(url_for('index'))

    try:
        token_data = serializer.loads(token)
        user_id = token_data['user_id']
    except BadSignature:
        return redirect(url_for('index'))

    conn = get_db_connection()
    friends = conn.execute('''
        SELECT Users.ID, Users.Username, Users.Name
        FROM Friends
        JOIN Users ON Friends.Friend_id = Users.ID
        WHERE Friends.User_id = ?
    ''', (user_id,)).fetchall()
    conn.close()
    return render_template('friends.html', friends=friends, user_id=user_id, token=token)

@app.route('/click', methods=['POST'])
def click():
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({'error': 'Authentication token missing'}), 403

    try:
        token_data = serializer.loads(token)
        user_id = token_data['user_id']
    except BadSignature:
        return jsonify({'error': 'Invalid authentication token'}), 403

    conn = get_db_connection()
    user_stat = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    level = user_stat['Level']

    # Определяем количество монет за клик на основе уровня
    coins_reward = 2 ** (level - 1) if level > 1 else 1

    # Обновляем количество монет и кликов
    conn.execute("UPDATE Statistic SET Coins = Coins + ?, Clicks = Clicks + 1 WHERE User_id = ?", (coins_reward, user_id))
    conn.commit()
    coins = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Coins']
    conn.close()
    return jsonify({'coins': coins})

@app.route('/buy', methods=['POST'])
def buy():
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({'error': 'Authentication token missing'}), 403

    try:
        token_data = serializer.loads(token)
        user_id = token_data['user_id']
    except BadSignature:
        return jsonify({'error': 'Invalid authentication token'}), 403

    item = data.get('item')

    conn = get_db_connection()
    user_stat = conn.execute("SELECT * FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    coins = user_stat['Coins']

    if item == 'level_up':
        level = user_stat['Level']
        level_cost = user_stat['Level_Cost']

        if level >= 10:
            message = 'Вы достигли максимального уровня.'
        elif coins >= level_cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ?, Level = Level + 1, Level_Cost = Level_Cost + 1000 WHERE User_id = ?", (level_cost, user_id))
            conn.commit()
            message = f'Уровень увеличен до {level + 1}!'
        else:
            message = 'Недостаточно монет для увеличения уровня.'

    elif item == 'upgrade_autoclicker':
        cost = 2000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ?, Autoclicker = Autoclicker + 1 WHERE User_id = ?", (cost, user_id))
            conn.commit()
            message = 'Автокликер улучшен!'
        else:
            message = 'Недостаточно монет для улучшения автокликера.'

    elif item.startswith('skin_'):
        try:
            cost = int(item.split('_')[1])
            if coins >= cost:
                conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
                conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", (f'{item}.png', user_id))
                conn.commit()
                message = f'Скин за {cost} куплен!'
            else:
                message = 'Недостаточно монет для покупки скина.'
        except ValueError:
            message = 'Некорректный товар.'

    else:
        message = 'Неизвестный товар.'

    new_coins_row = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    new_coins = new_coins_row['Coins'] if new_coins_row else coins
    conn.close()
    return jsonify({'message': message, 'coins': new_coins})

@app.route('/shop')
def shop():
    token = request.args.get('token')
    if not token:
        return redirect(url_for('index'))

    try:
        token_data = serializer.loads(token)
        user_id = token_data['user_id']
    except BadSignature:
        return redirect(url_for('index'))

    conn = get_db_connection()
    user_stat = conn.execute("SELECT Coins, Level, Level_Cost FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    coins = user_stat['Coins']
    level = user_stat['Level']
    level_cost = user_stat['Level_Cost']
    conn.close()

    return render_template('shop.html', coins=coins, level=level, level_cost=level_cost, token=token)

@app.route('/report_error', methods=['POST'])
def report_error():
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({'success': False}), 403

    try:
        token_data = serializer.loads(token)
        user_id = token_data['user_id']
    except BadSignature:
        return jsonify({'success': False}), 403

    error_message = data.get('error_message')

    if not error_message:
        return jsonify({'success': False}), 400

    conn = get_db_connection()
    conn.execute("INSERT INTO Errors (User_id, Error_message) VALUES (?, ?)", (user_id, error_message))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Функция автокликера
def autoclicker():
    while True:
        try:
            conn = get_db_connection()
            users = conn.execute("SELECT User_id, Autoclicker, Level FROM Statistic WHERE Autoclicker > 0").fetchall()
            for user in users:
                user_id = user['User_id']
                autoclicker_level = user['Autoclicker']
                level = user['Level']
                coins_reward = autoclicker_level * (2 ** (level - 1)) if level > 1 else autoclicker_level * 1
                conn.execute("UPDATE Statistic SET Coins = Coins + ? WHERE User_id = ?", (coins_reward, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            app.logger.error(f"Ошибка в автокликере: {e}")
        time.sleep(10)  # Каждые 10 секунд

# Запуск автокликера в отдельном потоке
def start_autoclicker():
    thread = threading.Thread(target=autoclicker)
    thread.daemon = True
    thread.start()

start_autoclicker()

if __name__ == '__main__':
    app.run(debug=True)
