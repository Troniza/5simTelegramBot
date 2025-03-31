import sqlite3
import json
from datetime import datetime
import logging

class AdminConfig:
    def __init__(self):
        self.setup_database()
    
    def setup_database(self):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            
            # جدول تنظیمات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # جدول تراکنش‌ها
            cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER,
                         amount INTEGER,
                         type TEXT,
                         description TEXT,
                         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            
            # جدول کانال‌های اجباری
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS required_channels (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    invite_link TEXT NOT NULL,
                    added_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # تنظیم مقادیر پیش‌فرض
            cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                         ('profit_percentage', '30'))
            cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                         ('ruble_rate', '0'))
            cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                         ('channel_lock', 'false'))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logging.error(f"Error in setup_database: {e}")
    
    def get_profit_percentage(self):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key = ?', ('profit_percentage',))
        result = c.fetchone()
        conn.close()
        return float(result[0]) if result else 30.0
    
    def set_profit_percentage(self, percentage):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('UPDATE settings SET value = ? WHERE key = ?',
                 (str(percentage), 'profit_percentage'))
        conn.commit()
        conn.close()
    
    def get_ruble_rate(self):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key = ?', ('ruble_rate',))
        result = c.fetchone()
        conn.close()
        return float(result[0]) if result else 0.0
    
    def set_ruble_rate(self, rate):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('UPDATE settings SET value = ? WHERE key = ?',
                 (str(rate), 'ruble_rate'))
        conn.commit()
        conn.close()
    
    def add_transaction(self, user_id, amount, type_trans, description):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('''INSERT INTO transactions 
                    (user_id, amount, type, description)
                    VALUES (?, ?, ?, ?)''',
                 (user_id, amount, type_trans, description))
        conn.commit()
        conn.close()
    
    def get_transactions(self, limit=10):
        conn = sqlite3.connect('admin.db')
        c = conn.cursor()
        c.execute('''SELECT * FROM transactions 
                    ORDER BY timestamp DESC LIMIT ?''', (limit,))
        transactions = c.fetchall()
        conn.close()
        return transactions
    
    def get_required_channels(self):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            
            # اضافه کردن logging برای دیباگ
            logging.info("Fetching channels from database...")
            
            cursor.execute('SELECT username, display_name, invite_link FROM required_channels')
            channels = cursor.fetchall()
            
            # اضافه کردن logging برای نمایش نتایج
            logging.info(f"Raw database result: {channels}")
            
            conn.close()
            
            # تبدیل نتایج به لیست
            channels_list = []
            for channel in channels:
                channels_list.append((
                    channel[0],  # username
                    channel[1],  # display_name
                    channel[2]   # invite_link
                ))
            
            logging.info(f"Returning {len(channels_list)} channels: {channels_list}")
            return channels_list
            
        except Exception as e:
            logging.error(f"Error in get_required_channels: {e}")
            return []
    
    def add_required_channel(self, username, display_name, invite_link):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            
            # حذف @ از ابتدای نام کاربری
            username = username.replace('@', '')
            
            logging.info(f"Adding channel: @{username}, {display_name}, {invite_link}")
            
            # بررسی وجود کانال قبل از اضافه کردن
            cursor.execute('SELECT username FROM required_channels WHERE username = ?', (username,))
            existing = cursor.fetchone()
            
            if existing:
                # اگر کانال وجود دارد، آپدیت می‌کنیم
                cursor.execute('''
                    UPDATE required_channels 
                    SET display_name = ?, invite_link = ?
                    WHERE username = ?
                ''', (display_name, invite_link, username))
                logging.info(f"Updated existing channel @{username}")
            else:
                # اگر کانال جدید است، اضافه می‌کنیم
                cursor.execute('''
                    INSERT INTO required_channels 
                    (username, display_name, invite_link) 
                    VALUES (?, ?, ?)
                ''', (username, display_name, invite_link))
                logging.info(f"Inserted new channel @{username}")
            
            conn.commit()
            
            # بررسی نتیجه
            cursor.execute('SELECT * FROM required_channels WHERE username = ?', (username,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                logging.info(f"Successfully added/updated channel @{username}")
                return True
            else:
                logging.error(f"Failed to add channel @{username}")
                return False
                
        except Exception as e:
            logging.error(f"Error in add_required_channel: {e}")
            return False
    
    def remove_required_channel(self, username):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            
            # حذف @ از ابتدای نام کاربری اگر وجود داشت
            username = username.replace('@', '')
            
            cursor.execute('DELETE FROM required_channels WHERE username = ?', (username,))
            conn.commit()
            
            # بررسی اینکه آیا کانال واقعاً حذف شده
            cursor.execute('SELECT * FROM required_channels WHERE username = ?', (username,))
            result = cursor.fetchone()
            
            conn.close()
            
            if not result:
                logging.info(f"Channel @{username} removed successfully")
                return True
            else:
                logging.error(f"Failed to remove channel @{username}")
                return False
                
        except Exception as e:
            logging.error(f"Error in remove_required_channel: {e}")
            return False
    
    def get_lock_status(self):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = "channel_lock"')
            result = cursor.fetchone()
            conn.close()
            
            return result[0].lower() == 'true' if result else False
            
        except Exception as e:
            logging.error(f"Error in get_lock_status: {e}")
            return False
    
    def set_lock_status(self, status):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                         ('channel_lock', str(status).lower()))
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logging.error(f"Error in set_lock_status: {e}")
            return False 