import sqlite3
import os
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

DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def check_init_data(init_data):
    try:
        token = os.environ.get('BOT_TOKEN')
        secret_key = hashlib.sha256(token.encode()).digest()

        init_data_dict = dict([param.split('=') for param in init_data.split('&') if '=' in param])
        hash_ = init_data_dict.pop('hash', None)
        if not hash_:
            return False
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(init_data_dict.items())])
        hmac_string = hmac.new(secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256).hexdigest()
        return hmac_string == hash_
    except Exception as e:
        print(f'Ошибка проверки init_data: {e}')
        return False

# Главная страница мини-приложения
@app.route('/')
def index():
    init_data = request.args.get('tgWebAppData')
    referrer_id = request.args.get('ref')  # Получаем ID пригласившего пользователя

    if init_data and check_init_data(init_data):
        try:
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
    # Fetch user's current level
    user_stat = conn.execute("SELECT Level FROM Statistic WHERE User_id = ?", (user_id,)).fetchone()
    level = user_stat['Level']
    
    # Determine the coin reward based on level
    if level <= 1:
        coins_reward = 1
    else:
        coins_reward = 2 ** (level - 1)  # Level 2: 2^1=2, Level 3: 2^2=4, etc.

    # Update the coins and clicks
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
            # Deduct coins and increase level
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

    elif item == 'skin_1000':
        cost = 1000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
            conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", ('skin_1000.png', user_id))
            conn.commit()
            message = 'Скин за 1000 куплен!'
        else:
            message = 'Недостаточно монет для покупки скина.'

    elif item == 'skin_2000':
        cost = 2000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
            conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", ('skin_2000.png', user_id))
            conn.commit()
            message = 'Скин за 2000 куплен!'
        else:
            message = 'Недостаточно монет для покупки скина.'

    elif item == 'skin_3000':
        cost = 3000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
            conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", ('skin_3000.png', user_id))
            conn.commit()
            message = 'Скин за 3000 куплен!'
        else:
            message = 'Недостаточно монет для покупки скина.'

    elif item == 'skin_4000':
        cost = 4000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
            conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", ('skin_4000.png', user_id))
            conn.commit()
            message = 'Скин за 4000 куплен!'
        else:
            message = 'Недостаточно монет для покупки скина.'

    elif item == 'skin_5000':
        cost = 5000
        if coins >= cost:
            conn.execute("UPDATE Statistic SET Coins = Coins - ? WHERE User_id = ?", (cost, user_id))
            conn.execute("UPDATE Users SET Current_skin = ? WHERE ID = ?", ('skin_5000.png', user_id))
            conn.commit()
            message = 'Скин за 5000 куплен!'
        else:
            message = 'Недостаточно монет для покупки скина.'
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
        time.sleep(10)  # Every 10 seconds


# Запуск автокликера в отдельном потоке
def start_autoclicker():
    thread = threading.Thread(target=autoclicker)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    # Проверяем, существует ли база данных
    if not os.path.exists(DATABASE):
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Users (
                ID INTEGER PRIMARY KEY,
                Username VARCHAR,
                Name VARCHAR,
                Email VARCHAR,
                Password VARCHAR,
                Current_skin VARCHAR DEFAULT 'default.png'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS User_Roles (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                User_id INTEGER,
                Role_id INTEGER,
                FOREIGN KEY (User_id) REFERENCES Users(ID),
                FOREIGN KEY (Role_id) REFERENCES Roles(ID)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Roles (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Role_name VARCHAR
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Statistic (
                Statistic_id INTEGER PRIMARY KEY AUTOINCREMENT,
        User_id INTEGER,
        Clicks INTEGER DEFAULT 0,
        Coins INTEGER DEFAULT 0,
        Autoclicker INTEGER DEFAULT 0,
        Level INTEGER DEFAULT 1,
        Level_Cost INTEGER DEFAULT 1000,
        FOREIGN KEY (User_id) REFERENCES Users(ID)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Improvements (
                Improvement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                Improvement_name VARCHAR,
                Cost INTEGER,
                Effect VARCHAR,
                User_id INTEGER,
                FOREIGN KEY (User_id) REFERENCES Users(ID)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Skins (
                Skin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                Skin_name VARCHAR,
                Price INTEGER,
                User_id INTEGER,
                FOREIGN KEY (User_id) REFERENCES Users(ID)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Errors (
                Error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                User_id INTEGER,
                Error_message VARCHAR,
                FOREIGN KEY (User_id) REFERENCES Users(ID)
            )
        ''')
        # Добавляем таблицу для друзей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Friends (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                User_id INTEGER,
                Friend_id INTEGER,
                FOREIGN KEY (User_id) REFERENCES Users(ID),
                FOREIGN KEY (Friend_id) REFERENCES Users(ID)
            )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Errors (
                Error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                User_id INTEGER,
                Error_message TEXT,
                Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (User_id) REFERENCES Users(ID)
            )
        ''')
        conn.commit()
        conn.close()
    #except Exception as e:
        #print(f"Ошибка при инициализации базы данных: {e}")
    start_autoclicker()
    print("Запуск Flask-приложения...")
    app.run(host='0.0.0.0', port=8000)