import sqlite3
import os
import logging
import threading
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask import session as login_session
from dotenv import load_dotenv
import hmac
import hashlib
import json

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')
app.logger.setLevel(logging.INFO)

DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def check_init_data(init_data):
    try:
        if not init_data:
            return False
        token = os.environ.get('BOT_TOKEN')
        if not token:
            app.logger.error('BOT_TOKEN is not set')
            return False
        secret_key = hashlib.sha256(token.encode('utf-8')).digest()
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_ = data.pop('hash', None)
        if not hash_:
            return False
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(data.items())])
        hmac_string = hmac.new(secret_key, msg=data_check_string.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
        return hmac_string == hash_
    except Exception as e:
        app.logger.error(f'Ошибка проверки init_data: {e}')
        return False


# Главная страница мини-приложения
@app.route('/')
def index():
    init_data = request.args.get('tgWebAppData')
    app.logger.info(f"Получено init_data: {init_data}")
    referrer_id = request.args.get('ref')  # Получаем ID пригласившего пользователя

    #if init_data and check_init_data(init_data):
    if True:
        try:
            if init_data:
                parsed_data = dict([pair.split('=') for pair in init_data.split('&') if '=' in pair])
                user_data_json = parsed_data.get('user', '{}')
                user_data = json.loads(user_data_json)
                user_id = user_data.get('id')
                username = user_data.get('username', '')
                first_name = user_data.get('first_name', '')
                last_name = user_data.get('last_name', '')
                name = f"{first_name} {last_name}".strip()
                login_session['user_id'] = user_id
                conn = get_db_connection()
                user = conn.execute('SELECT * FROM Users WHERE ID = ?', (user_id,)).fetchone()
                if not user_id:
                    return "User ID not found in init data", 400
                if user is None:
                    conn.execute("INSERT INTO Users (ID, Username, Name) VALUES (?, ?, ?)", (user_id, username, name))
                    conn.execute("INSERT INTO Statistic (User_id) VALUES (?)", (user_id,))
                    conn.commit()
                    coins = 0
                    current_skin = 'default.png'
                else:
                    coins = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Coins']
                    current_skin_row = conn.execute("SELECT Current_skin FROM Users WHERE ID = ?", (user_id,)).fetchone()
                    current_skin = current_skin_row['Current_skin'] if current_skin_row else 'default.png'
                    if not current_skin:
                        current_skin = 'default.png'
                # Обработка реферальной ссылки
                if referrer_id and referrer_id != str(user_id):
                    existing_friend = conn.execute('''
                        SELECT * FROM Friends WHERE User_id = ? AND Friend_id = ?
                    ''', (referrer_id, user_id)).fetchone()
                    if not existing_friend:
                        conn.execute('INSERT INTO Friends (User_id, Friend_id) VALUES (?, ?)', (referrer_id, user_id))
                        conn.execute('UPDATE Statistic SET Coins = Coins + 100 WHERE User_id = ?', (referrer_id,))
                        conn.commit()
                coins = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Coins']
                level = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Level']
                conn.close()
                return render_template('index.html', coins=coins, level=level, current_skin=current_skin)
            else:
                return "No init data received", 400
        except Exception as e:
            print(f"Ошибка при обработке index: {e}")
            return "Internal Server Error", 500
    else:
        return "Invalid init data", 403

# Страница друзей
@app.route('/friends')
def friends():
    user_id = login_session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Получаем список друзей
    friends = conn.execute('''
        SELECT Users.ID, Users.Username, Users.Name
        FROM Friends
        JOIN Users ON Friends.Friend_id = Users.ID
        WHERE Friends.User_id = ?
    ''', (user_id,)).fetchall()

    conn.close()
    return render_template('friends.html', friends=friends, user_id=user_id)

# Обработка клика по монете
@app.route('/click', methods=['POST'])
def click():
    user_id = login_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 403

    conn = get_db_connection()
    # Получаем текущий уровень пользователя
    user_stat = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    level = user_stat['Level']
    
    # Определяем количество монет за клик на основе уровня
    if level <= 1:
        coins_reward = 1
    else:
        coins_reward = 2 ** (level - 1)  # Уровень 2: 2^1=2, Уровень 3: 2^2=4 и т.д.

    # Обновляем количество монет и кликов
    conn.execute("UPDATE Statistic SET Coins = Coins + ?, Clicks = Clicks + 1 WHERE User_id = ?", (coins_reward, user_id))
    conn.commit()
    coins = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Coins']
    conn.close()
    return jsonify({'coins': coins})

# Обработка покупки товаров в магазине
@app.route('/buy', methods=['POST'])
def buy():
    user_id = login_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 403

    item = request.json.get('item')

    conn = get_db_connection()
    user_stat = conn.execute("SELECT * FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    coins = user_stat['Coins']

    if item == 'level_up':
        level = user_stat['Level']
        level_cost = user_stat['Level_Cost']

        if level >= 10:
            message = 'Вы достигли максимального уровня.'
        elif coins >= level_cost:
            # Списываем монеты и повышаем уровень
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

    # Обработка покупки скинов
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

    new_coins = conn.execute("SELECT Coins FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()['Coins']
    conn.close()
    return jsonify({'message': message, 'coins': new_coins})

# Страница магазина
@app.route('/shop')
def shop():
    user_id = login_session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))

    conn = get_db_connection()
    user_stat = conn.execute("SELECT Coins, Level, Level_Cost FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    coins = user_stat['Coins']
    level = user_stat['Level']
    level_cost = user_stat['Level_Cost']
    conn.close()

    return render_template('shop.html', coins=coins, level=level, level_cost=level_cost)

@app.route('/report_error', methods=['POST'])
def report_error():
    user_id = login_session.get('user_id')
    if not user_id:
        return jsonify({'success': False}), 403

    data = request.get_json()
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
                if level <= 1:
                    coins_reward = autoclicker_level * 1
                else:
                    coins_reward = autoclicker_level * (2 ** (level - 1))
                conn.execute("UPDATE Statistic SET Coins = Coins + ? WHERE User_id = ?", (coins_reward, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка в автокликере: {e}")
        time.sleep(10)  # Каждые 10 секунд

# Запуск автокликера в отдельном потоке
def start_autoclicker():
    thread = threading.Thread(target=autoclicker)
    thread.daemon = True
    thread.start()

# Перемещаем вызов start_autoclicker() за пределы блока if __name__ == '__main__'
start_autoclicker()

# Ваше приложение Flask готово к импорту Gunicorn
