import sqlite3
import logging

class OperatorConfig:
    def __init__(self):
        self.setup_database()
        
    def setup_database(self):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            
            # حذف جدول قبلی اگر وجود دارد
            cursor.execute('DROP TABLE IF EXISTS operator_settings')
            
            # ایجاد جدول تنظیمات اپراتور با ساختار جدید
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS operator_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    country TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    UNIQUE(service, country)
                )
            ''')
            
            # تنظیمات به‌روز شده
            default_settings = [
                # تلگرام
                ('telegram', 'cyprus', 'virtual4', 'قبرس 🇨🇾'),
                ('telegram', 'paraguay', 'virtual4', 'پاراگوئه 🇵🇾'),
                ('telegram', 'maldives', 'virtual4', 'مالدیو 🇲🇻'),
                ('telegram', 'suriname', 'virtual4', 'سورینام 🇸🇷'),
                ('telegram', 'slovenia', 'virtual4', 'اسلوونی 🇸🇮'),
                ('telegram', 'canada', 'virtual8', 'کانادا 🇨🇦'),
                
                # واتساپ
                ('whatsapp', 'georgia', 'virtual4', 'گرجستان 🇬🇪'),
                ('whatsapp', 'cameroon', 'virtual4', 'کامرون 🇨🇲'),
                ('whatsapp', 'laos', 'virtual4', 'لائوس 🇱🇦'),
                ('whatsapp', 'benin', 'virtual4', 'بنین 🇧🇯'),
                ('whatsapp', 'dominican_republic', 'virtual4', 'جمهوری دومینیکن 🇩🇴'),
                
                # اینستاگرام
                ('instagram', 'poland', 'virtual53', 'لهستان 🇵🇱'),
                ('instagram', 'philippines', 'virtual38', 'فیلیپین 🇵🇭'),
                ('instagram', 'netherlands', 'virtual52', 'هلند 🇳🇱'),
                ('instagram', 'estonia', 'virtual38', 'استونی 🇪🇪'),
                ('instagram', 'vietnam', 'virtual4', 'ویتنام 🇻🇳'),
                
                # گوگل
                ('google', 'cambodia', 'virtual4', 'کامبوج 🇰🇭'),
                ('google', 'philippines', 'virtual58', 'فیلیپین 🇵🇭'),
                ('google', 'indonesia', 'virtual4', 'اندونزی 🇮🇩'),
                ('google', 'ethiopia', 'virtual4', 'اتیوپی 🇪🇹'),
                ('google', 'russia', 'mts', 'روسیه 🇷🇺')
            ]
            
            # اضافه کردن تنظیمات جدید
            cursor.executemany('''
                INSERT OR REPLACE INTO operator_settings (service, country, operator, country_name)
                VALUES (?, ?, ?, ?)
            ''', default_settings)
            
            conn.commit()
            conn.close()
            logging.info("Operator settings database updated successfully")
            
        except Exception as e:
            logging.error(f"Error in setup_database: {e}")
            
    def get_operator_info(self, service, country):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT operator, country_name FROM operator_settings 
                WHERE service = ? AND country = ?
            ''', (service, country))
            result = cursor.fetchone()
            conn.close()
            return result if result else (None, None)
        except Exception as e:
            logging.error(f"Error in get_operator_info: {e}")
            return None, None
            
    def set_operator(self, service, country, operator, country_name):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO operator_settings (service, country, operator, country_name)
                VALUES (?, ?, ?, ?)
            ''', (service, country, operator, country_name))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error in set_operator: {e}")
            return False
            
    def get_all_settings(self):
        try:
            conn = sqlite3.connect('admin.db')
            cursor = conn.cursor()
            cursor.execute('SELECT service, country, operator, country_name FROM operator_settings')
            settings = cursor.fetchall()
            conn.close()
            return settings
        except Exception as e:
            logging.error(f"Error in get_all_settings: {e}")
            return [] 