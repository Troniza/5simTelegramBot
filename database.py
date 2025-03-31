import sqlite3
from config import DB_CONFIG
import logging
from datetime import datetime

def setup_databases():
    setup_users_database()
    setup_admin_database()
    setup_orders_database()

def setup_users_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()

        # جدول کاربران
        cursor.execute('''CREATE TABLE IF NOT EXISTS users
            (user_id INTEGER PRIMARY KEY,
             username TEXT,
             first_name TEXT,
             last_name TEXT,
             join_date DATETIME DEFAULT CURRENT_TIMESTAMP,
             balance INTEGER DEFAULT 0,
             is_blocked INTEGER DEFAULT 0)''')

        # حذف جدول قدیمی اگر وجود دارد
        cursor.execute('DROP TABLE IF EXISTS transactions')
        
        # ایجاد جدول جدید با ساختار صحیح
        cursor.execute('''CREATE TABLE transactions
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             amount INTEGER,
             type TEXT,
             description TEXT,
             ref_id TEXT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users(user_id))''')

        # جدول پرداخت‌های کارت به کارت
        cursor.execute('''CREATE TABLE IF NOT EXISTS card_payments
            (payment_id TEXT PRIMARY KEY,
             user_id INTEGER,
             amount INTEGER,
             status TEXT DEFAULT 'pending',
             receipt TEXT,
             admin_response TEXT,
             created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users(user_id))''')

        conn.commit()
        conn.close()
        logging.info("Users database setup completed")
        return True
    except Exception as e:
        logging.error(f"Error in setup_users_database: {e}")
        return False

def setup_admin_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()

        # جدول تنظیمات کارت بانکی
        cursor.execute('''CREATE TABLE IF NOT EXISTS card_info
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             card_number TEXT,
             card_holder TEXT,
             updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # جدول تنظیمات عمومی
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings
            (key TEXT PRIMARY KEY,
             value TEXT,
             updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        conn.commit()
        conn.close()
        logging.info("Admin database setup completed")
    except Exception as e:
        logging.error(f"Error in setup_admin_database: {e}")

def setup_orders_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()

        # جدول سفارش‌ها
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             service TEXT,
             country TEXT,
             phone_number TEXT,
             price INTEGER,
             status TEXT,
             order_id TEXT UNIQUE,
             created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users(user_id))''')

        conn.commit()
        conn.close()
        logging.info("Orders database setup completed")
    except Exception as e:
        logging.error(f"Error in setup_orders_database: {e}")

def get_user_balance(user_id):
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        return 0
    except Exception as e:
        logging.error(f"Error in get_user_balance: {e}")
        return 0

def add_balance(user_id, amount):
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        
        # بررسی وجود کاربر
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user is None:
            # ایجاد کاربر جدید
            cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, amount))
            new_balance = amount
        else:
            # بروزرسانی موجودی
            new_balance = user[0] + amount
            cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Balance updated for user {user_id}. New balance: {new_balance}")
        return new_balance
    except Exception as e:
        logging.error(f"Error in add_balance: {e}", exc_info=True)
        return None

def save_transaction(user_id, amount, type_trans, description, ref_id=None):
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        
        # ثبت تراکنش
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description, ref_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, type_trans, description, ref_id))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Transaction saved successfully: user_id={user_id}, amount={amount}, type={type_trans}")
        return True
        
    except sqlite3.Error as e:
        logging.error(f"Database error in save_transaction: {e}")
        return False
    except Exception as e:
        logging.error(f"Error in save_transaction: {e}")
        return False

def get_card_info():
    try:
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()
        cursor.execute('SELECT card_number, card_holder FROM card_info ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logging.error(f"Error in get_card_info: {e}")
        return None

def add_test_transaction():
    try:
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('''INSERT INTO transactions 
                    (user_id, amount, type, description)
                    VALUES (?, ?, ?, ?)''',
                 (123456, 100000, 'purchase', 'تست تراکنش'))
        conn.commit()
        conn.close()
        logging.info("تراکنش تست با موفقیت اضافه شد")
    except Exception as e:
        logging.error(f"خطا در اضافه کردن تراکنش تست: {e}")

def save_user_phone(user_id, phone):
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, phone) 
            VALUES (?, ?)
            ON CONFLICT (user_id) 
            DO UPDATE SET phone = ?
        """, (user_id, phone, phone))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error saving phone number: {e}")
        return False 