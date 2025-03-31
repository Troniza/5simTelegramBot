import json
import sqlite3
import threading
import time
import logging
import os
from config import DB_CONFIG

class BackupManager:
    def __init__(self, backup_interval=5):
        self.backup_interval = backup_interval
        self.backup_file = 'data/users_backup.json'
        self.running = False
        self.thread = None
        logging.basicConfig(level=logging.INFO)

    def start(self):
        """شروع فرآیند پشتیبان‌گیری خودکار"""
        self.running = True
        self.thread = threading.Thread(target=self._backup_loop)
        self.thread.daemon = True
        self.thread.start()
        logging.info("Backup manager started")

    def stop(self):
        """توقف فرآیند پشتیبان‌گیری"""
        self.running = False
        if self.thread:
            self.thread.join()
        logging.info("Backup manager stopped")

    def _backup_loop(self):
        """حلقه اصلی پشتیبان‌گیری"""
        while self.running:
            try:
                self.create_backup()
                time.sleep(self.backup_interval)
            except Exception as e:
                logging.error(f"Error in backup loop: {e}")
                time.sleep(self.backup_interval)

    def create_backup(self):
        """ایجاد فایل پشتیبان از اطلاعات کاربران"""
        try:
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, balance FROM users')
            users_data = {str(user_id): balance for user_id, balance in cursor.fetchall()}
            conn.close()

            with open(self.backup_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Backup created successfully. Users count: {len(users_data)}")
            return True
        except Exception as e:
            logging.error(f"Error creating backup: {e}")
            return False

    def restore_backup(self):
        """بازیابی اطلاعات کاربران از فایل پشتیبان"""
        try:
            # بررسی وجود فایل پشتیبان
            if not os.path.exists(self.backup_file):
                logging.warning("No backup file found")
                return False

            # خواندن اطلاعات از فایل پشتیبان
            with open(self.backup_file, 'r', encoding='utf-8') as f:
                users_data = json.load(f)

            if not users_data:
                logging.warning("Backup file is empty")
                return False

            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            
            try:
                # شروع تراکنش
                cursor.execute('BEGIN TRANSACTION')
                
                # ایجاد جدول users اگر وجود نداشته باشد
                cursor.execute('''CREATE TABLE IF NOT EXISTS users
                    (user_id INTEGER PRIMARY KEY,
                     balance INTEGER DEFAULT 0)''')

                # بروزرسانی موجودی کاربران
                for user_id, balance in users_data.items():
                    cursor.execute('''INSERT OR REPLACE INTO users (user_id, balance)
                        VALUES (?, ?)''', (int(user_id), balance))

                # تایید تراکنش
                conn.commit()
                logging.info(f"Backup restored successfully. Users count: {len(users_data)}")
                return True
                
            except Exception as e:
                # برگرداندن تغییرات در صورت خطا
                conn.rollback()
                logging.error(f"Error in database operations: {e}")
                return False
                
            finally:
                conn.close()
                
        except FileNotFoundError:
            logging.warning("No backup file found")
            return False
        except json.JSONDecodeError:
            logging.error("Invalid JSON format in backup file")
            return False
        except Exception as e:
            logging.error(f"Error restoring backup: {e}")
            return False 