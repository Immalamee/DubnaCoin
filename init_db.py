import sqlite3
import os

DATABASE = 'database.db'

def init_db():
    try:
        if not os.path.exists(DATABASE):
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()

            # Создание таблицы пользователей
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

            # Создание таблицы ролей пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS User_Roles (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    User_id INTEGER,
                    Role_id INTEGER,
                    FOREIGN KEY (User_id) REFERENCES Users(ID),
                    FOREIGN KEY (Role_id) REFERENCES Roles(ID)
                )
            ''')

            # Создание таблицы ролей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Roles (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Role_name VARCHAR
                )
            ''')

            # Создание таблицы статистики
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

            # Создание таблицы улучшений
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

            # Создание таблицы скинов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Skins (
                    Skin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Skin_name VARCHAR,
                    Price INTEGER,
                    User_id INTEGER,
                    FOREIGN KEY (User_id) REFERENCES Users(ID)
                )
            ''')

            # Создание таблицы ошибок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Errors (
                    Error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    User_id INTEGER,
                    Error_message TEXT,
                    Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (User_id) REFERENCES Users(ID)
                )
            ''')

            # Создание таблицы друзей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Friends (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT,
                    User_id INTEGER,
                    Friend_id INTEGER,
                    FOREIGN KEY (User_id) REFERENCES Users(ID),
                    FOREIGN KEY (Friend_id) REFERENCES Users(ID)
                )
            ''')

            conn.commit()
            conn.close()
            print("База данных успешно инициализирована.")
        else:
            print("База данных уже существует.")
    except Exception as e:
        print(f"Ошибка при инициализации базы данных: {e}")

if __name__ == '__main__':
    init_db()
