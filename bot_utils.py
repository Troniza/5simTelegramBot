import logging
import requests
import sqlite3
import os
import time
from dotenv import load_dotenv
from config import BOT_CONFIG

# بارگیری متغیرهای محیطی (برای سایر متغیرها)
load_dotenv()

# دریافت توکن ربات از فایل کانفیگ
BOT_TOKEN = BOT_CONFIG['token']
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message_to_bot(user_id, message_text):
    """
    ارسال پیام به کاربر از طریق ربات تلگرام
    
    Args:
        user_id: شناسه کاربر در دیتابیس یا شناسه تلگرام (اگر با عدد 1 شروع شود، شناسه تلگرام فرض می‌شود)
        message_text: متن پیام برای ارسال
    
    Returns:
        bool: نتیجه ارسال پیام (موفق یا ناموفق)
    """
    conn = None
    max_retries = 3  # تعداد تلاش‌های مجدد برای داده‌های قفل شده
    retry_count = 0
    
    # بررسی اینکه آیا user_id مستقیماً یک شناسه تلگرام است
    # معمولاً شناسه‌های تلگرام با 1 شروع می‌شوند و طول آنها 10 کاراکتر یا بیشتر است
    try:
        user_id_str = str(user_id)
        if user_id_str.startswith('1') and len(user_id_str) >= 9:
            # احتمالاً این یک شناسه تلگرام است، مستقیماً ارسال کنیم
            telegram_id = user_id
            return send_telegram_message(telegram_id, message_text)
    except:
        pass  # اگر خطایی رخ داد، به روال عادی ادامه می‌دهیم
    
    while retry_count < max_retries:
        try:
            # دریافت شناسه تلگرام کاربر از دیتابیس
            try:
                conn = sqlite3.connect('bot.db', timeout=10)  # افزایش تایم‌اوت برای قفل پایگاه داده
                cursor = conn.cursor()
                
                cursor.execute("SELECT telegram_id FROM users WHERE id = ?", (user_id,))
                result = cursor.fetchone()
                
                if conn:
                    conn.close()
                    conn = None
                
                if not result:
                    logging.warning(f"کاربر با شناسه {user_id} در دیتابیس یافت نشد")
                    return False
                    
                telegram_id = result[0]
                
                # ارسال پیام به تلگرام
                return send_telegram_message(telegram_id, message_text)
            
            except sqlite3.OperationalError as e:
                if "no such table: users" in str(e):
                    logging.warning(f"جدول users وجود ندارد. تلاش برای ارسال مستقیم...")
                    # ممکن است user_id همان telegram_id باشد، تلاش می‌کنیم
                    return send_telegram_message(user_id, message_text)
                elif "database is locked" in str(e):
                    retry_count += 1
                    if retry_count < max_retries:
                        logging.warning(f"پایگاه داده قفل شده است، تلاش مجدد {retry_count} از {max_retries}")
                        time.sleep(0.5)  # انتظار کوتاه قبل از تلاش مجدد
                        continue
                    else:
                        logging.error(f"پایگاه داده پس از {max_retries} تلاش همچنان قفل است")
                        return False
                else:
                    logging.warning(f"خطای دیتابیس در ارسال پیام: {str(e)}")
                    return False
                
        except Exception as e:
            logging.error(f"خطا در send_message_to_bot: {str(e)}")
            return False
        finally:
            # اطمینان حاصل کنیم که اتصال پایگاه داده بسته شود
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logging.error(f"خطا در بستن اتصال پایگاه داده: {str(e)}")
        
        # اگر به اینجا برسیم، یعنی خطای قفل پایگاه داده نبوده و باید از حلقه خارج شویم
        break
        
    return False  # اگر کد به اینجا برسد، یعنی ارسال پیام موفقیت‌آمیز نبوده است

def send_telegram_message(telegram_id, message_text):
    """
    ارسال پیام مستقیم به تلگرام
    
    Args:
        telegram_id: شناسه تلگرام کاربر
        message_text: متن پیام برای ارسال
        
    Returns:
        bool: نتیجه ارسال پیام (موفق یا ناموفق)
    """
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        data = {
            "chat_id": telegram_id,
            "text": message_text,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, data=data)
        
        if response.status_code == 200:
            logging.info(f"پیام با موفقیت به کاربر {telegram_id} ارسال شد")
            return True
        else:
            logging.error(f"خطا در ارسال پیام به کاربر {telegram_id}: {response.text}")
            return False
    except Exception as e:
        logging.error(f"خطا در ارسال پیام به تلگرام: {str(e)}")
        return False 