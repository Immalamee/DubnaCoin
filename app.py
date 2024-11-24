import os
import sqlite3
import threading
import time
import logging
import json
import hashlib
import hmac
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv
from itsdangerous import URLSafeSerializer, BadSignature
from urllib.parse import parse_qsl, urlparse, parse_qs
from operator import itemgetter

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')

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

        is_valid, result = check_init_data(init_data, BOT_TOKEN)
        if not is_valid:
            app.logger.error(f"Invalid init data: {result}")
            return jsonify({'success': False, 'error': result}), 403
        app.logger.info(f"Результат проверки init_data: {is_valid}")

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
        is_new_user = False
        if user_db is None:
            conn.execute("INSERT INTO Users (ID, Username, Name) VALUES (?, ?, ?)", (user_id, username, name))
            conn.execute("INSERT INTO Statistic (User_id) VALUES (?)", (user_id,))
            conn.commit()
            app.logger.info(f"New user added: {user_id} - {username}")
            is_new_user = True

        # Обработка реферальной ссылки только при первом входе
        if is_new_user and referrer_id and referrer_id != str(user_id):
            app.logger.info(f"Processing referral: referrer_id={referrer_id}, user_id={user_id}")
            existing_friend = conn.execute('''
                SELECT * FROM Friends WHERE User_id = ? AND Friend_id = ?
            ''', (referrer_id, user_id)).fetchone()
            if not existing_friend:
                conn.execute('INSERT INTO Friends (User_id, Friend_id) VALUES (?, ?)', (referrer_id, user_id))
                conn.execute('UPDATE Statistic SET Coins = Coins + 100 WHERE User_id = ?', (referrer_id,))
                conn.commit()
                app.logger.info(f"Referral added: {referrer_id} invited {user_id}")
            else:
                app.logger.info(f"Referral already exists: {referrer_id} and {user_id}")
        else:
            app.logger.info("No valid referrer_id provided or self-invitation detected")

        coins_row = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
        level_row = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
        coins = coins_row['Coins'] if coins_row else 0
        level = level_row['Level'] if level_row else 1
        level_cost_row = conn.execute("SELECT Level_Cost FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
        level_cost = level_cost_row['Level_Cost'] if level_cost_row else 1000

        current_skin_row = conn.execute("SELECT Current_skin FROM Users WHERE ID = ?", (user_id,)).fetchone()
        current_skin = current_skin_row['Current_skin'] if current_skin_row else 'default.png'
        if not current_skin:
            current_skin = 'default.png'
        conn.close()

        token = serializer.dumps({'user_id': user_id})

        return jsonify({
            'success': True,
            'coins': coins,
            'level': level,
            'level_cost': level_cost,
            'current_skin': current_skin,
            'username': username,
            'token': token
        })
    except Exception as e:
        app.logger.error(f'Error processing init_data: {e}')
        return jsonify({'success': False, 'error': 'Server error'}), 500

def check_init_data(init_data, bot_token):
    try:
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        app.logger.info(f"Parsed init_data: {parsed_data}")

        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            return False, 'Параметр hash отсутствует в init_data.'

        data_check_arr = [f"{k}={v}" for k, v in sorted(parsed_data.items(), key=itemgetter(0))]
        data_check_string = '\n'.join(data_check_arr)
        app.logger.info(f"data_check_string:\n{data_check_string}")

        secret_key = hmac.new(
            key=b'WebAppData',
            msg=bot_token.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        app.logger.info(f"Вычисленный хэш: {computed_hash}")
        app.logger.info(f"Хэш из Telegram: {received_hash}")

        if not hmac.compare_digest(computed_hash, received_hash):
            return False, 'Хэш не совпадает.'

        auth_date = int(parsed_data.get('auth_date', '0'))
        current_time = int(time.time())
        if current_time - auth_date > 86400:
            return False, 'auth_date слишком старый.'

        return True, parsed_data
    except Exception as e:
        return False, f'Ошибка при проверке initData: {e}'

@app.route('/')
def index():
    token = request.args.get('token')
    return render_template('index.html', token=token)

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

    coins_reward = 2 ** (level - 1) if level > 1 else 1

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
    level = user_stat['Level']
    level_cost = user_stat['Level_Cost']
    autoclicker_level = user_stat['Autoclicker']

    if item == 'level_up':
        if level >= 10:
            message = 'Вы достигли максимального уровня.'
        elif coins >= level_cost:
            new_level = level + 1
            new_level_cost = level_cost + 1000
            conn.execute("UPDATE Statistic SET Coins = Coins - ?, Level = ?, Level_Cost = ? WHERE User_id = ?",
                         (level_cost, new_level, new_level_cost, user_id))
            conn.commit()
            message = f'Уровень увеличен до {new_level}!'
        else:
            message = 'Недостаточно монет для увеличения уровня.'

    elif item == 'upgrade_autoclicker':
        cost = (autoclicker_level + 1) * 2000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ?, Autoclicker = Autoclicker + 1 WHERE User_id = ?", (cost, user_id))
            conn.commit()
            message = f'Автокликер улучшен до уровня {autoclicker_level + 1}!'
        else:
            message = 'Недостаточно монет для улучшения автокликера.'

    elif item.startswith('skin_'):
        try:
            cost = int(item.split('_')[1])
            skin_filename = f'skin_{cost}.png'  # Формируем имя файла скина
            skin_path = os.path.join('static', 'images', skin_filename)
            if not os.path.exists(skin_path):
                message = 'Такого скина не существует.'
            elif coins >= cost:
                conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
                conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", (skin_filename, user_id))
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
    user_stat = conn.execute("SELECT Coins, Level, Level_Cost, Autoclicker FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    coins = user_stat['Coins']
    level = user_stat['Level']
    level_cost = user_stat['Level_Cost']
    autoclicker_level = user_stat['Autoclicker']
    conn.close()

    return render_template('shop.html', coins=coins, level=level, level_cost=level_cost, autoclicker_level=autoclicker_level, token=token)

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
        time.sleep(10)

def start_autoclicker():
    thread = threading.Thread(target=autoclicker)
    thread.daemon = True
    thread.start()

start_autoclicker()

if __name__ == '__main__':
    app.run(debug=True)
