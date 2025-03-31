import sqlite3
import logging
from datetime import datetime

class Wallet:
    def __init__(self):
        self.db_path = 'users.db'  # استفاده از همان دیتابیس users.db
        
    def ensure_user_exists(self, user_id):
        """اطمینان از وجود کاربر در جدول users"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
            exists = c.fetchone() is not None
            if not exists:
                c.execute('INSERT INTO users (user_id, balance) VALUES (?, 0)', (user_id, ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"خطا در بررسی وجود کاربر: {e}")
            return False
            
    def get_balance(self, user_id):
        try:
            # اطمینان از وجود کاربر
            self.ensure_user_exists(user_id)
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            conn.close()
            
            if result is None:
                self.create_wallet(user_id)
                return 0
                
            return result[0]
        except Exception as e:
            logging.error(f"خطا در دریافت موجودی: {e}")
            return 0
            
    def create_wallet(self, user_id):
        try:
            # اطمینان از وجود کاربر
            self.ensure_user_exists(user_id)
            
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # بررسی وجود کیف پول
            c.execute('SELECT 1 FROM wallet WHERE user_id = ?', (user_id,))
            if c.fetchone() is None:
                c.execute('''INSERT INTO wallet 
                            (user_id, balance, total_deposit, total_spent, last_transaction)
                            VALUES (?, 0, 0, 0, ?)''',
                         (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"خطا در ایجاد کیف پول: {e}")
            return False
            
    def add_balance(self, user_id, amount):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # بررسی وجود کاربر
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result is None:
                # اگر کاربر وجود ندارد، او را اضافه می‌کنیم
                cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, ?)', (user_id, amount))
            else:
                # بروزرسانی موجودی
                cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            
            # ثبت تراکنش
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description) 
                VALUES (?, ?, 'deposit', 'افزایش موجودی')
            ''', (user_id, amount))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logging.error(f"Error in add_balance: {e}")
            return False
            
    def reduce_balance(self, user_id, amount):
        try:
            current_balance = self.get_balance(user_id)
            if current_balance < amount:
                return False
                
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute('''UPDATE wallet 
                        SET balance = balance - ?,
                            total_spent = total_spent + ?,
                            last_transaction = ?
                        WHERE user_id = ?''',
                     (amount, amount, now, user_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"خطا در کاهش موجودی: {e}")
            return False
            
    def get_wallet_info(self, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # بررسی موجودی فعلی
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result is None:
                # اگر کاربر در دیتابیس نباشد، او را اضافه می‌کنیم
                cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
                conn.commit()
                balance = 0
            else:
                balance = result[0] or 0  # اگر None بود، 0 برگرداند
            
            # محاسبه کل واریزی‌ها
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) 
                FROM transactions 
                WHERE user_id = ? AND type = 'deposit'
            ''', (user_id,))
            total_deposit = cursor.fetchone()[0] or 0
            
            # بروزرسانی موجودی بر اساس تراکنش‌ها
            cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (total_deposit, user_id))
            conn.commit()
            
            # محاسبه کل برداشت‌ها
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) 
                FROM transactions 
                WHERE user_id = ? AND type = 'purchase'
            ''', (user_id,))
            total_spent = cursor.fetchone()[0] or 0
            
            # آخرین تراکنش
            cursor.execute('''
                SELECT timestamp 
                FROM transactions 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (user_id,))
            last_transaction = cursor.fetchone()
            last_transaction = last_transaction[0] if last_transaction else None
            
            conn.close()
            
            return {
                'balance': total_deposit - total_spent,  # محاسبه موجودی واقعی
                'total_deposit': total_deposit,
                'total_spent': total_spent,
                'last_transaction': last_transaction
            }
            
        except Exception as e:
            logging.error(f"Error in get_wallet_info: {e}")
            return None

    def deduct_balance(self, user_id, amount):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # بررسی موجودی کافی
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if not result or result[0] < amount:
                conn.close()
                return False
                
            # کسر از موجودی
            cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
            
            # ثبت تراکنش
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description) 
                VALUES (?, ?, 'purchase', 'خرید شماره مجازی')
            ''', (user_id, amount))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logging.error(f"Error in deduct_balance: {e}")
            return False 