import telebot
import requests
import json
import sqlite3
from telebot import types
from flask import Flask, request, render_template, render_template_string, jsonify, send_from_directory, redirect, url_for, session, send_file, Blueprint
import logging
from admin_config import AdminConfig
import locale
from config import BOT_CONFIG, FIVESIM_CONFIG, DB_CONFIG, PAYMENT_CONFIG  # حذف API_KEY, API_URL
from currency_service import CurrencyService
from datetime import datetime, timedelta
from database import setup_databases, add_balance, save_transaction, get_user_balance, setup_users_database
from wallet import Wallet
from payment import ZarinPal
from operator_config import OperatorConfig
import os
from persiantools.jdatetime import JalaliDateTime
import time
from card_payment import CardPayment
from backup_manager import BackupManager
import logging.handlers
from routes.order_details import order_details_bp  # برای مسیرهای جزئیات سفارش

locale.setlocale(locale.LC_ALL, '')

# تنظیمات اولیه
# BOT_TOKEN = '7234581002:AAHoft87ArR-mEjnSIAY8rHTcfJNteycfhg'
# FIVESIM_API_KEY = 'eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzQ0ODMyMjIsImlhdCI6MTc0Mjk0NzIyMiwicmF5IjoiMmRjMzBmY2M4YzVhMjA3MjVjNmVlNWU4NzI3MzMyOGYiLCJzdWIiOjI1NDcwNDl9.Sz_ce12BFv--6xYEo881udrXAmoyEjvafaKWN4mZqsyOlPARvCoGeSMiDReYNxj-zbx0hmuzurD55yX4V0UER38Vm5xNt4nCdcqX4QdiZD1GLW_MliFqAPY2leLosGohPvQrVBbuW9MWDrHuZPsd_gxF5Y-YuYTAHzOggQ82RufibXOgeRwpOZR4aoWeqMCDlnlfqYMQL6TWY5ttWFKDkq33_05g1ULKY3GPNcL6m2T4uJh7ebDYOcj2sGc9V28d3QdiWda7ow7jff1gEECdM87S5AZ6T6vklZQZlGEwoP2sc5gkhUgq-9ldTy74K-CFyxa0ZfJ05Va5yEd6Uf-Hhg'
# FIVESIM_API_URL = 'https://5sim.net/v1'
# WEBHOOK_URL = 'https://082a-209-38-109-245.ngrok-free.app'

bot = telebot.TeleBot(BOT_CONFIG['token'])
app = Flask(__name__, static_folder='static')
app.register_blueprint(order_details_bp)  # ثبت Blueprint مسیرهای جزئیات سفارش

# تنظیمات logging
logging.basicConfig(
    filename='bot.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# اضافه کردن handler برای نمایش لاگ‌ها در کنسول
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# تنظیم ادمین
admin_config = AdminConfig()

# ایجاد دیتابیس
def setup_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()

        # ایجاد جدول users اگر وجود ندارد
        cursor.execute('''CREATE TABLE IF NOT EXISTS users
            (user_id INTEGER PRIMARY KEY,
             balance INTEGER DEFAULT 0)''')

        # ایجاد جدول orders اگر وجود ندارد
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             phone_number TEXT,
             service TEXT,
             country TEXT,
             price INTEGER,
             order_id TEXT UNIQUE,
             status TEXT DEFAULT 'active',
             order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users(user_id))''')

        conn.commit()
        conn.close()
        logging.info("✅ دیتابیس با موفقیت راه‌اندازی شد")
        return True
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی دیتابیس: {e}")
        return False

def setup_admin_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()
        
        # ایجاد جدول اطلاعات کارت
        cursor.execute('''CREATE TABLE IF NOT EXISTS card_info
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             card_number TEXT,
             card_holder TEXT)''')
             
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error in setup_admin_database: {e}")

# توابع مدیریت موجودی کاربر
def get_user_balance(user_id):
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        
        # بررسی وجود کاربر
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result is None:
            # اگر کاربر وجود نداشت، یک رکورد جدید با موجودی 0 ایجاد می‌کنیم
            cursor.execute('INSERT INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
            conn.commit()
            balance = 0
        else:
            balance = result[0]
        
        conn.close()
        logging.info(f"User {user_id} balance checked: {balance}")
        return balance
        
    except Exception as e:
        logging.error(f"Error in get_user_balance for user {user_id}: {e}")
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

# تابع جدید برای دریافت سرویس‌های موجود از 5sim
def get_available_services():
    try:
        # اینجا باید از API شما برای دریافت سرویس‌ها استفاده شود
        # برای تست، یک لیست نمونه برمی‌گردانیم
        services = [
            "Telegram",
            "WhatsApp",
            "Instagram",
            "Facebook",
            "Twitter",
            "Viber",
            "WeChat",
            "Snapchat",
            "TikTok",
            "LinkedIn"
        ]
        logging.info(f"Retrieved {len(services)} services")
        return services
    except Exception as e:
        logging.error(f"Error in get_available_services: {e}")
        return []

# تابع جدید برای دریافت کشورهای موجود برای یک سرویس خاص
def get_countries_for_service(service):
    conn = sqlite3.connect('sms_bot.db')
    cursor = conn.cursor()
    
    # تنظیم کشورهای اختصاصی برای هر سرویس
    service_countries = {
        'telegram': [
            {'code': 'cyprus', 'name': 'قبرس'},
            {'code': 'paraguay', 'name': 'پاراگوئه'},
            {'code': 'maldives', 'name': 'مالدیو'},
            {'code': 'suriname', 'name': 'سورینام'},
            {'code': 'slovenia', 'name': 'اسلوونی'},
            {'code': 'canada', 'name': 'کانادا'}
        ],
        'whatsapp': [
            {'code': 'georgia', 'name': 'گرجستان'},
            {'code': 'cameroon', 'name': 'کامرون'},
            {'code': 'laos', 'name': 'لائوس'},
            {'code': 'benin', 'name': 'بنین'},
            {'code': 'dominican_republic', 'name': 'جمهوری دومینیکن'}
        ],
        'instagram': [
            {'code': 'poland', 'name': 'لهستان'},
            {'code': 'philippines', 'name': 'فیلیپین'},
            {'code': 'netherlands', 'name': 'هلند'},
            {'code': 'estonia', 'name': 'استونی'},
            {'code': 'vietnam', 'name': 'ویتنام'}
        ],
        'google': [
            {'code': 'cambodia', 'name': 'کامبوج'},
            {'code': 'philippines', 'name': 'فیلیپین'},
            {'code': 'indonesia', 'name': 'اندونزی'},
            {'code': 'ethiopia', 'name': 'اتیوپی'},
            {'code': 'russia', 'name': 'روسیه'}
        ]
    }
    
    # اگر سرویس در لیست ما باشد، کشورهای اختصاصی آن را برگردان
    if service in service_countries:
        return service_countries[service]
    
    # در غیر این صورت، کشورهای پیش‌فرض یا همه کشورها را از دیتابیس برگردان
    try:
        cursor.execute("SELECT DISTINCT country_code, country_name FROM products WHERE service = ?", (service,))
        countries = [{'code': row[0], 'name': row[1]} for row in cursor.fetchall()]
        conn.close()
        return countries
    except Exception as e:
        logging.error(f"خطا در دریافت کشورها: {e}")
        conn.close()
        return []

# تابع بروزرسانی شده برای دریافت قیمت‌ها
def get_prices(product):
    headers = {
        'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
        'Accept': 'application/json',
    }
    try:
        # دریافت قیمت‌های عمومی
        response = requests.get(
            f'{FIVESIM_CONFIG["api_url"]}/guest/products/{product}',
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"خطا در دریافت قیمت‌ها: {e}")
        return None

# تابع جدید برای دریافت محصولات موجود
def get_products(country='any', operator='any'):
    headers = {
        'Accept': 'application/json',
    }
    try:
        response = requests.get(
            f'{FIVESIM_CONFIG["api_url"]}/guest/products/{country}/{operator}',
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"پاسخ API برای محصولات {country}/{operator}: {data}")
        return data
    except Exception as e:
        logger.error(f"خطا در دریافت محصولات: {e}")
        return None

# تنظیم وب‌هوک
@app.route('/', methods=['GET', 'POST'])
def webhook():
    logging.info(f"Received webhook request: {request.method}")
    if request.method == 'POST':
        logging.info(f"Webhook data: {request.get_data()}")
        try:
            json_str = request.get_data().decode('UTF-8')
            update = telebot.types.Update.de_json(json_str)
            bot.process_new_updates([update])
            return ''
        except Exception as e:
            print(f"خطا در پردازش webhook: {e}")
            return 'error', 500
    return 'OK'

# حذف تابع main_keyboard و جایگزینی با inline_main_keyboard
def inline_main_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # دکمه‌های اصلی
    keyboard.add(
        types.InlineKeyboardButton('📱 خرید شماره مجازی', callback_data='buy_number'),
        types.InlineKeyboardButton('💰 موجودی', callback_data='check_balance'),
        types.InlineKeyboardButton('🛒 سفارش‌های من', callback_data='my_orders'),
        types.InlineKeyboardButton('❓ راهنما', callback_data='help')
    )
    
    # اضافه کردن دکمه پنل مدیریت فقط برای ادمین
    if user_id in BOT_CONFIG['admin_ids']:
        keyboard.add(types.InlineKeyboardButton('👨‍💻 پنل مدیریت', callback_data='admin_panel'))
    
    return keyboard

# نمایش سرویس‌های موجود
def services_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # سرویس‌های اصلی که دو به دو نمایش داده می‌شوند
    main_services = [
        ('telegram', 'تلگرام 📱'),
        ('whatsapp', 'واتس‌اپ 💬'),
        ('instagram', 'اینستاگرام 📸'),
        ('google', 'گوگل 🔍')
    ]
    
    # اضافه کردن دکمه‌ها دو به دو
    for i in range(0, len(main_services), 2):
        buttons = []
        for j in range(2):
            if i + j < len(main_services):
                service_id, name = main_services[i + j]
                buttons.append(types.InlineKeyboardButton(name, callback_data=f'service_{service_id}'))
        keyboard.row(*buttons)
    
    # اضافه کردن دکمه برگشت به منوی اصلی
    keyboard.add(types.InlineKeyboardButton("🔙 برگشت به منوی اصلی", callback_data="back_to_main"))
    
    return keyboard

# تغییر start handler
@bot.message_handler(commands=['start'])
def start_handler(message):
    try:
        keyboard = inline_main_keyboard(message.from_user.id)
        
        welcome_text = """
        🔥 خوش اومدی به فروشگاه شماره مجازی! 


همین حالا شماره خودتو بگیر و آنلاین فعالش کن! 🚀
        """

        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in start_handler: {e}")
        bot.reply_to(message, "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.")

# اضافه کردن handler برای بررسی مجدد عضویت
@bot.callback_query_handler(func=lambda call: call.data == "check_membership")
def check_membership(call):
    try:
        channels = admin_config.get_required_channels()
        if not channels:
            bot.edit_message_text(
                "👋 خوش آمدید!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=inline_main_keyboard(call.from_user.id)
            )
            return
            
        not_subscribed = []
        for channel in channels:
            try:
                member = bot.get_chat_member(f"@{channel[0]}", call.from_user.id)
                if member.status in ['left', 'kicked', 'restricted']:
                    channel_info = bot.get_chat(f"@{channel[0]}")
                    not_subscribed.append((
                        channel_info.title or channel[1],
                        channel[2]
                    ))
            except Exception as e:
                logger.error(f"خطا در بررسی عضویت کانال {channel[0]}: {e}")
                continue
        
        if not_subscribed:
            text = "⚠️ شما هنوز در همه کانال‌ها عضو نشده‌اید:\n\n"
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            for channel_name, channel_link in not_subscribed:
                text += f"• {channel_name}\n"
                keyboard.add(types.InlineKeyboardButton(f"عضویت در {channel_name}", url=channel_link))
            
            keyboard.add(types.InlineKeyboardButton("🔄 بررسی مجدد", callback_data="check_membership"))
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
        else:
            bot.edit_message_text(
                "✅ عضویت شما تایید شد!\n👋 خوش آمدید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=inline_main_keyboard(call.from_user.id)
            )
            
    except Exception as e:
        logger.error(f"خطا در بررسی عضویت: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

# ایجاد نمونه از کلاس Wallet
wallet = Wallet()

# آپدیت تابع handle_main_menu برای بخش موجودی
@bot.callback_query_handler(func=lambda call: call.data in ['buy_number', 'check_balance', 'help', 'help_buy_number', 'help_charge', 'help_get_code', 'help_payment', 'help_delivery', 'help_cancel'])
def handle_main_menu(call):
    try:
        if call.data == 'check_balance':
            user_id = call.from_user.id
            balance = get_user_balance(user_id)
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="add_funds"),
                types.InlineKeyboardButton("🔙 برگشت به منوی اصلی", callback_data="back_to_main")
            )
            
            message_text = f"""
💰 *کیف پول شما*

موجودی: `{balance:,} تومان`

💡 حداقل شارژ: 20,000 تومان
"""
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return

        elif call.data == 'buy_number':
            bot.edit_message_text(
                '📱 لطفاً سرویس مورد نظر خود را انتخاب کنید:',
                call.message.chat.id,
                call.message.message_id,
                reply_markup=services_keyboard()
            )
            
        elif call.data == 'help':
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("❓ نحوه خرید شماره مجازی", callback_data="help_buy_number"),
                types.InlineKeyboardButton("💰 نحوه شارژ حساب", callback_data="help_charge"),
                types.InlineKeyboardButton("📱 نحوه دریافت کد", callback_data="help_get_code"),
                types.InlineKeyboardButton("💳 روش‌های پرداخت", callback_data="help_payment"),
                types.InlineKeyboardButton("⏱ مدت زمان دریافت شماره", callback_data="help_delivery"),
                types.InlineKeyboardButton("❌ نحوه لغو سفارش", callback_data="help_cancel"),
                types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")
            )
            bot.edit_message_text(
                "❓ سوالات متداول\n\nلطفاً سوال مورد نظر خود را انتخاب کنید:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
        elif call.data == "help_buy_number":
            answer = """
📱 نحوه خرید شماره مجازی:

1️⃣ روی دکمه "خرید شماره مجازی" کلیک کنید
2️⃣ سرویس مورد نظر را انتخاب کنید
3️⃣ کشور مورد نظر را انتخاب کنید
4️⃣ اپراتور مورد نظر را انتخاب کنید
5️⃣ شماره مورد نظر را خریداری کنید

💡 نکته: قبل از خرید، موجودی حساب خود را بررسی کنید.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            
        elif call.data == "help_charge":
            answer = """
💰 نحوه شارژ حساب:

1️⃣ از طریق درگاه پرداخت:
- روی دکمه "شارژ حساب" کلیک کنید
- مبلغ مورد نظر را وارد کنید
- از درگاه پرداخت استفاده کنید

2️⃣ از طریق کارت به کارت:
- روی دکمه "پرداخت کارت به کارت" کلیک کنید
- مبلغ را به کارت اعلام شده واریز کنید
- تصویر رسید را ارسال کنید

💡 نکته: حداقل مبلغ شارژ 50,000 تومان می‌باشد.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            
        elif call.data == "help_get_code":
            answer = """
📱 نحوه دریافت کد:

1️⃣ پس از خرید شماره، دکمه "دریافت کد" را بزنید
2️⃣ کد را از پیامک یا اپلیکیشن دریافت کنید
3️⃣ کد را در ربات وارد کنید

💡 نکته: زمان دریافت کد معمولاً بین 1 تا 5 دقیقه می‌باشد.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            
        elif call.data == "help_payment":
            answer = """
💳 روش‌های پرداخت:

1️⃣ پرداخت آنلاین:
- درگاه پرداخت مستقیم
- پرداخت با کارت بانکی

2️⃣ پرداخت کارت به کارت:
- واریز مستقیم به کارت
- ارسال تصویر رسید

💡 نکته: در صورت نیاز به راهنمایی بیشتر، با پشتیبانی در ارتباط باشید.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            
        elif call.data == "help_delivery":
            answer = """
⏱ مدت زمان دریافت شماره:

1️⃣ زمان معمول:
- دریافت شماره: 1 تا 5 دقیقه
- دریافت کد: 1 تا 5 دقیقه

2️⃣ در صورت تاخیر:
- حداکثر 15 دقیقه صبر کنید
- در صورت عدم دریافت، با پشتیبانی تماس بگیرید

💡 نکته: زمان دریافت به نوع سرویس و کشور مورد نظر بستگی دارد.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            
        elif call.data == "help_cancel":
            answer = """
❌ نحوه لغو سفارش:

1️⃣ در صورت عدم دریافت شماره:
- روی دکمه "لغو سفارش" کلیک کنید
- مبلغ به حساب شما برگردانده می‌شود

2️⃣ شرایط لغو:
- قبل از دریافت کد
- در صورت تاخیر بیش از 15 دقیقه

💡 نکته: پس از دریافت کد، امکان لغو سفارش وجود ندارد.
"""
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سوالات", callback_data="help"))
            bot.edit_message_text(answer, call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    except Exception as e:
        logging.error(f"Error in handle_main_menu: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_menu(call):
    bot.edit_message_text(
        "👋 به منوی اصلی بازگشتید.\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=inline_main_keyboard(call.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('service_'))
def handle_service_selection(call):
    try:
        service = call.data.split('_')[1]
        products = get_products()
        
        if not products:
            bot.answer_callback_query(call.id, "❌ خطا در دریافت اطلاعات محصولات")
            return
            
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        # جایگزینی دیکشنری قدیمی با دیکشنری جدید متناسب با سرویس
        service_countries = {
            'telegram': [
                ('cyprus', 'قبرس 🇨🇾'),
                ('paraguay', 'پاراگوئه 🇵🇾'),
                ('maldives', 'مالدیو 🇲🇻'),
                ('suriname', 'سورینام 🇸🇷'),
                ('slovenia', 'اسلوونی 🇸🇮'),
                ('canada', 'کانادا 🇨🇦')
            ],
            'whatsapp': [
                ('georgia', 'گرجستان 🇬🇪'),
                ('cameroon', 'کامرون 🇨🇲'),
                ('laos', 'لائوس 🇱🇦'),
                ('benin', 'بنین 🇧🇯'),
                ('dominican_republic', 'جمهوری دومینیکن 🇩🇴')
            ],
            'instagram': [
                ('poland', 'لهستان 🇵🇱'),
                ('philippines', 'فیلیپین 🇵🇭'),
                ('netherlands', 'هلند 🇳🇱'),
                ('estonia', 'استونی 🇪🇪'),
                ('vietnam', 'ویتنام 🇻🇳')
            ],
            'google': [
                ('cambodia', 'کامبوج 🇰🇭'),
                ('philippines', 'فیلیپین 🇵🇭'),
                ('indonesia', 'اندونزی 🇮🇩'),
                ('ethiopia', 'اتیوپی 🇪🇹'),
                ('russia', 'روسیه 🇷🇺')
            ]
        }
        
        # انتخاب کشورهای مرتبط با سرویس انتخاب شده
        countries = service_countries.get(service, [])
        
        # نمایش کشورها دو به دو
        for i in range(0, len(countries), 2):
            buttons = []
            for j in range(2):
                if i + j < len(countries):
                    country_code, country_name = countries[i + j]
                    buttons.append(types.InlineKeyboardButton(country_name, callback_data=f'country_{service}_{country_code}'))
            keyboard.row(*buttons)
        
        # اضافه کردن دکمه برگشت به لیست سرویس‌ها
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سرویس‌ها", callback_data="back_to_services"))
        
        bot.edit_message_text(
            f"🌍 لطفاً کشور مورد نظر خود را برای سرویس {service} انتخاب کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"خطا در پردازش انتخاب سرویس: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

currency_service = CurrencyService()

def create_required_tables():
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # ایجاد جدول settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # تنظیمات پیش‌فرض
        default_settings = [
            ('ruble_rate', '600'),  # نرخ پیش‌فرض روبل به تومان
            ('profit_percentage', '30'),  # درصد سود پیش‌فرض
        ]
        
        # اضافه کردن تنظیمات پیش‌فرض
        cursor.executemany('''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES (?, ?)
        ''', default_settings)
        
        # ایجاد جدول سفارش‌ها
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                phone_number TEXT,
                service TEXT,
                country TEXT,
                operator TEXT,
                price INTEGER,
                status TEXT,
                date DATETIME,
                user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # ایجاد جدول کدهای فعال‌سازی
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activation_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                code TEXT,
                status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logging.info("Required tables created successfully")
        
    except Exception as e:
        logging.error(f"Error creating required tables: {e}")
        raise

def get_price_for_operator(country, product, operator):
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # اول مطمئن شویم که جدول settings وجود دارد
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # بررسی وجود تنظیمات پیش‌فرض
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (key, value) VALUES 
                ("ruble_rate", "0.35"),
                ("profit_percentage", "20")
            ''')
            conn.commit()
        
        # دریافت نرخ روبل و درصد سود
        cursor.execute('SELECT value FROM settings WHERE key = "ruble_rate"')
        ruble_rate = float(cursor.fetchone()[0]) if ruble_rate_result else 0
        
        cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
        profit_percentage = float(cursor.fetchone()[0]) if profit_result else 0
        
        # دریافت قیمت پایه
        base_price = get_prices(product)
        if not base_price:
            logging.error(f"No base price found for product {product}")
            return None
            
        # محاسبه قیمت نهایی
        final_price = base_price * ruble_rate * (1 + profit_percentage/100)
        
        logging.info(f"Price calculation successful: base={base_price}, rate={ruble_rate}, profit={profit_percentage}%")
        return round(final_price, 2)
        
    except sqlite3.Error as e:
        logging.error(f"Database error in price calculation: {e}")
        return None
    except Exception as e:
        logging.error(f"General error in price calculation: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_current_ruble_rate():
    try:
        # همیشه از مقدار ذخیره شده در دیتابیس استفاده می‌کنیم
        conn = sqlite3.connect('admin.db')  # استفاده از admin.db به جای bot.db
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key='ruble_rate'")
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return float(result[0])
        else:
            logging.error("نرخ روبل در دیتابیس یافت نشد")
            return 0  # برگرداندن صفر در صورت عدم وجود مقدار
    except Exception as e:
        logging.error(f"خطا در دریافت نرخ روبل از دیتابیس: {e}")
        return 0  # برگرداندن صفر در صورت بروز خطا

def ensure_settings_table_exists():
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # بررسی وجود جدول
        cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='settings' ''')
        
        # اگر جدول وجود نداشت، آن را بساز
        if cursor.fetchone()[0] == 0:
            create_required_tables()
            logging.info("Settings table created")
        
        conn.close()
        return True
        
    except Exception as e:
        logging.error(f"Error checking settings table: {e}")
        return False

# در ابتدای فایل، این import را اضافه کنید
from operator_config import OperatorConfig

# یک نمونه از کلاس OperatorConfig ایجاد کنید
operator_config = OperatorConfig()

@bot.callback_query_handler(func=lambda call: call.data.startswith('country_'))
def handle_country_selection(call):
    try:
        user_id = call.from_user.id
        
        # اطمینان از وجود جدول settings
        ensure_settings_table_exists()
        
        parts = call.data.split('_')
        service = parts[1]
        country = parts[2]
        
        # دریافت اطلاعات اپراتور از تنظیمات
        operator, country_name = operator_config.get_operator_info(service, country)
        
        # اگر کشور در تنظیمات یافت نشد، از نام کشور پیش‌فرض استفاده کنیم
        if not country_name:
            country_name = {
                'russia': 'روسیه 🇷🇺',
                'canada': 'کانادا 🇨🇦',
                'england': 'انگلستان 🇬🇧',
                'cyprus': 'قبرس 🇨🇾',
                'paraguay': 'پاراگوئه 🇵🇾',
                'maldives': 'مالدیو 🇲🇻',
                'suriname': 'سورینام 🇸🇷',
                'slovenia': 'اسلوونی 🇸🇮',
                # سایر کشورها را اضافه کنید...
            }.get(country, country)
        
        # اگر اپراتور تعریف نشده باشد، از مقدار پیش‌فرض استفاده کنیم
        if not operator:
            operator = "virtual4"  # اپراتور پیش‌فرض
            logging.warning(f"هیچ اپراتوری برای {service} در {country} تعریف نشده. از اپراتور پیش‌فرض استفاده می‌شود.")
        
        # دریافت قیمت سرویس برای این کشور
        headers = {
            'Accept': 'application/json',
        }
        
        params = (
            ('country', country),
            ('product', service),
        )
        
        response = requests.get(
            'https://5sim.net/v1/guest/prices',
            headers=headers,
            params=params
        )
        
        price_info = {
            'price_ruble': 0,
            'price_toman': 0,
            'available_count': 0,
            'operator': operator
        }
        
        price_text = ""
        
        if response.status_code == 200:
            data = response.json()
            
            if country in data and service in data[country]:
                operators_data = data[country][service]
                
                # بررسی آیا اپراتور تعریف شده موجود است
                if operator in operators_data and operators_data[operator]['count'] > 0:
                    operator_data = operators_data[operator]
                    price = operator_data['cost']
                    available_count = operator_data['count']
                else:
                    # اگر اپراتور تعریف شده موجود نیست، کمترین قیمت را پیدا کنیم
                    min_price = float('inf')
                    price = 0
                    available_count = 0
                    
                    for op_name, op_data in operators_data.items():
                        if op_data['count'] > 0 and op_data['cost'] < min_price:
                            min_price = op_data['cost']
                            price = min_price
                            available_count = op_data['count']
                            price_info['operator'] = op_name
                            
                    if min_price == float('inf'):
                        logging.warning(f"هیچ اپراتوری با موجودی برای {service} در {country} یافت نشد.")
                        price = 0
                        available_count = 0
                
                if price > 0:
                    # دریافت نرخ روبل و درصد سود از دیتابیس
                    conn = sqlite3.connect('admin.db')
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT value FROM settings WHERE key = "ruble_rate"')
                    ruble_rate_result = cursor.fetchone()
                    ruble_rate = float(ruble_rate_result[0]) if ruble_rate_result else 0
                    
                    cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
                    profit_result = cursor.fetchone()
                    profit_percentage = float(profit_result[0]) if profit_result else 0
                    
                    conn.close()
                    
                    # محاسبه قیمت نهایی
                    price_info['price_ruble'] = price
                    price_info['price_toman'] = round(price * ruble_rate * (1 + profit_percentage/100))
                    price_info['available_count'] = available_count
                    
                    operator_text = f"اپراتور: {price_info['operator']}"
                    price_text = f"""💵 قیمت: {price_info['price_toman']:,} تومان
📊 موجودی: {price_info['available_count']:,} عدد
🔌 {operator_text}"""
                    
                    logging.info(f"""
                    محاسبه قیمت برای {country}:
                    اپراتور: {price_info['operator']}
                    قیمت پایه (روبل): {price}
                    نرخ روبل: {ruble_rate}
                    درصد سود: {profit_percentage}%
                    قیمت نهایی (تومان): {price_info['price_toman']}
                    تعداد موجود: {available_count}
                    """)
        
        # ایجاد کیبورد
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        if price_info['available_count'] > 0:
            # دکمه خرید با اپراتور مشخص شده
            keyboard.add(types.InlineKeyboardButton(
                f"📱 خرید شماره ({price_info['operator']})", 
                callback_data=f"buy_number_{service}_{country}_{price_info['operator']}"
            ))
        else:
            # اگر موجودی نداریم، پیغام خطا نمایش دهیم
            keyboard.add(types.InlineKeyboardButton(
                "⚠️ فعلاً موجود نیست", 
                callback_data="no_operator"
            ))
        
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت به سرویس‌ها", callback_data="back_to_services"))
        
        # متن پیام
        message_text = f"""🌍 شما {country_name} را برای سرویس {service} انتخاب کرده‌اید.

{price_text}

برای خرید شماره، روی دکمه زیر کلیک کنید:"""
        
        bot.edit_message_text(
            message_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in handle_country_selection: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")
        bot.send_message(call.message.chat.id, "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_services")
def back_to_services(call):
    bot.edit_message_text(
        'لطفاً سرویس مورد نظر خود را انتخاب کنید:',
        call.message.chat.id,
        call.message.message_id,
        reply_markup=services_keyboard()
    )

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    try:
        # پردازش پیام
        pass
    except Exception as e:
        bot.reply_to(message, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        print(f"خطای کلی: {e}")

# تغییر در تابع admin_panel
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"),
        types.InlineKeyboardButton("💰 تنظیم درصد سود", callback_data="set_profit"),
        types.InlineKeyboardButton("💱 تنظیم نرخ روبل", callback_data="set_ruble_rate"),
        types.InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="manage_channels"),
        types.InlineKeyboardButton("🧾 تراکنش‌ها", callback_data="transactions"),
        # اضافه کردن دکمه مدیریت کاربران
        types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="manage_users"),
        types.InlineKeyboardButton("📱 تنظیمات اپراتور", callback_data="operator_settings"),
        types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")
    )
    
    bot.send_message(
        message.chat.id,
        "👨‍💻 پنل مدیریت\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def handle_admin_stats(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
        return

    try:
        # اتصال به دیتابیس کاربران
        users_conn = sqlite3.connect(DB_CONFIG['users_db'])
        users_cursor = users_conn.cursor()
        
        # تعداد کل کاربران
        users_cursor.execute('SELECT COUNT(DISTINCT user_id) FROM users')
        total_users = users_cursor.fetchone()[0]
        users_conn.close()
        
        # اتصال به دیتابیس ربات
        bot_conn = sqlite3.connect('bot.db')
        bot_cursor = bot_conn.cursor()
        
        # دریافت نرخ فعلی روبل
        current_rate = get_current_ruble_rate()
        
        # دریافت درصد سود از جدول settings
        admin_conn = sqlite3.connect('admin.db')
        admin_cursor = admin_conn.cursor()
        admin_cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
        profit_percentage = float(admin_cursor.fetchone()[0] or 30)
        admin_conn.close()
        
        # محاسبه درآمدها از جدول orders
        # درآمد امروز
        bot_cursor.execute('''
            SELECT COALESCE(SUM(price), 0) FROM orders 
            WHERE date(created_at) = date('now')
        ''')
        today_total = bot_cursor.fetchone()[0] or 0
        today_income = int(today_total - (today_total / (1 + profit_percentage/100)))
        
        # درآمد هفته
        bot_cursor.execute('''
            SELECT COALESCE(SUM(price), 0) FROM orders 
            WHERE date(created_at) >= date('now', '-7 days')
        ''')
        week_total = bot_cursor.fetchone()[0] or 0
        week_income = int(week_total - (week_total / (1 + profit_percentage/100)))
        
        # درآمد ماه
        bot_cursor.execute('''
            SELECT COALESCE(SUM(price), 0) FROM orders 
            WHERE date(created_at) >= date('now', '-30 days')
        ''')
        month_total = bot_cursor.fetchone()[0] or 0
        month_income = int(month_total - (month_total / (1 + profit_percentage/100)))
        
        bot_conn.close()
        
        # ایجاد کیبورد
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        # ردیف اول: تعداد کاربران
        keyboard.add(
            types.InlineKeyboardButton(f"{total_users:,}", callback_data="show_users"),
            types.InlineKeyboardButton("👥 کاربران", callback_data="show_users")
        )
        
        # ردیف دوم: نرخ روبل
        keyboard.add(
            types.InlineKeyboardButton(f"{current_rate:,}", callback_data="show_rate"),
            types.InlineKeyboardButton("💱 روبل", callback_data="show_rate")
        )
        
        # ردیف سوم: درآمد امروز
        keyboard.add(
            types.InlineKeyboardButton(f"{today_income:,}", callback_data="today_income"),
            types.InlineKeyboardButton("📅 امروز", callback_data="today_income")
        )
        
        # ردیف چهارم: درآمد هفتگی
        keyboard.add(
            types.InlineKeyboardButton(f"{week_income:,}", callback_data="week_income"),
            types.InlineKeyboardButton("📆 هفته", callback_data="week_income")
        )
        
        # ردیف پنجم: درآمد ماهانه
        keyboard.add(
            types.InlineKeyboardButton(f"{month_income:,}", callback_data="month_income"),
            types.InlineKeyboardButton("📊 ماه", callback_data="month_income")
        )
        
        # ردیف ششم: بروزرسانی نرخ روبل
        keyboard.add(types.InlineKeyboardButton("🔄 بروزرسانی نرخ روبل", callback_data="update_rate"))
        
        # ردیف هفتم: بازگشت
        keyboard.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        
        # ارسال پیام با آمار
        bot.edit_message_text(
            f"""📊 پنل مدیریت ربات
                        

♦️ در این بخش می‌توانید آمار کلی ربات خود را مشاهده کنید. این آمار شامل تعداد کاربران، درآمد روزانه، هفتگی و ماهانه می‌باشد. همچنین می‌توانید نرخ روبل را به‌روزرسانی کنید.

برای مشاهده جزئیات بیشتر، لطفاً از دکمه‌های زیر استفاده کنید.""",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in handle_admin_stats: {e}")
        bot.answer_callback_query(call.id, "❌ خطا در دریافت آمار")

@bot.callback_query_handler(func=lambda call: call.data == "update_rate")
def update_currency_rate(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    current_rate = currency_service.get_ruble_rate()
    if current_rate:
        admin_config.set_ruble_rate(current_rate)
        bot.answer_callback_query(call.id, "✅ نرخ ارز با موفقیت بروز شد")
        handle_admin_stats(call)  # نمایش مجدد آمار
    else:
        bot.answer_callback_query(call.id, "❌ خطا در دریافت نرخ ارز")

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def handle_admin_panel_button(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data="manage_users"),
        types.InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="broadcast_message"),
        types.InlineKeyboardButton("💰 تنظیم درصد سود", callback_data="set_profit"),
        types.InlineKeyboardButton("💳 تنظیم کارت بانکی", callback_data="set_card"),  # اضافه کردن دکمه جدید
        types.InlineKeyboardButton("💱 تنظیم نرخ روبل", callback_data="set_ruble_rate"),
        types.InlineKeyboardButton("📋 تراکنش‌ها", callback_data="transactions"),
        types.InlineKeyboardButton("🔐 قفل ربات", callback_data="toggle_lock"),
        types.InlineKeyboardButton("📱 تنظیمات اپراتور", callback_data="operator_settings"),
        types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        "👨‍💻 پنل مدیریت\n\nلطفاً یک گزینه را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "set_card")
def handle_set_card(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
        return
        
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💳 ثبت کارت جدید", callback_data="new_card"),
        types.InlineKeyboardButton("🔍 مشاهده اطلاعات", callback_data="check_card_info"),
        types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel")
    )
    
    bot.edit_message_text(
        "💳 مدیریت کارت بانکی\n\n"
        "لطفاً یک گزینه را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "manage_users")
def handle_manage_users(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی به این بخش را ندارید")
            return
            
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("👥 لیست کاربران", callback_data="users_list"),
            types.InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="search_user"),
            types.InlineKeyboardButton("✉️ پیام همگانی", callback_data="broadcast_message"),
            types.InlineKeyboardButton("🎁 تخفیف گروهی", callback_data="group_discount")
        )
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        
        bot.edit_message_text(
            """👥 بخش مدیریت کاربران

لطفاً یکی از گزینه‌های زیر را انتخاب کنید:""",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in handle_manage_users: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        print(f"Error in handle_manage_users: {e}")  # اضافه کردن لاگ اضافی برای دیباگ

@bot.callback_query_handler(func=lambda call: call.data == "users_list")
def handle_users_list(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی به این بخش را ندارید")
            return
            
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, balance 
            FROM users 
            ORDER BY user_id DESC 
            LIMIT 10
        ''')
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            text = "❌ هیچ کاربری یافت نشد!"
        else:
            text = "👥 لیست 10 کاربر آخر:\n\n"
            for user in users:
                text += f"🆔 آیدی: {user[0]}\n"
                text += f"💰 موجودی: {user[1]:,} تومان\n"
                text += "➖➖➖➖➖➖➖➖\n"
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("⬅️ صفحه قبل", callback_data="users_prev_page"),
            types.InlineKeyboardButton("➡️ صفحه بعد", callback_data="users_next_page")
        )
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in users_list: {e}")
        bot.answer_callback_query(call.id, "❌ خطا در دریافت لیست کاربران")
        print(f"Error in users_list: {e}")  # اضافه کردن لاگ اضافی برای دیباگ

@bot.callback_query_handler(func=lambda call: call.data == "search_user")
def handle_search_user(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    msg = bot.edit_message_text(
        """🔍 جستجوی کاربر
        
لطفاً آیدی عددی کاربر مورد نظر را وارد کنید:""",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, process_user_search)

def process_user_search(message):
    if message.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    try:
        search_term = message.text.strip()
        if not search_term.isdigit():
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔄 جستجوی مجدد", callback_data="search_user"))
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
            bot.reply_to(message, "❌ لطفاً یک شناسه کاربری معتبر (عدد) وارد کنید.", reply_markup=keyboard)
            return
            
        user_id = int(search_term)
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # جستجو بر اساس آیدی
        cursor.execute('SELECT user_id, balance FROM users WHERE user_id = ?', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("💰 تغییر موجودی", callback_data=f"modify_balance_{user[0]}"),
                types.InlineKeyboardButton("✉️ ارسال پیام", callback_data=f"send_message_{user[0]}")
            )
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
            
            text = f"""👤 اطلاعات کاربر:

🆔 آیدی: {user[0]}
💰 موجودی: {user[1]:,} تومان"""
            
            bot.reply_to(message, text, reply_markup=keyboard)
        else:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔄 جستجوی مجدد", callback_data="search_user"))
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
            bot.reply_to(message, "❌ کاربر مورد نظر یافت نشد.", reply_markup=keyboard)
            
    except Exception as e:
        logging.error(f"Error in process_user_search: {e}")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
        bot.reply_to(message, "❌ خطا در جستجوی کاربر", reply_markup=keyboard)
        print(f"Error in process_user_search: {e}")  # اضافه کردن لاگ اضافی برای دیباگ

@bot.callback_query_handler(func=lambda call: call.data.startswith('modify_balance_'))
def handle_modify_balance(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    user_id = call.data.split('_')[2]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("➕ افزایش", callback_data=f"add_balance_{user_id}"),
        types.InlineKeyboardButton("➖ کاهش", callback_data=f"reduce_balance_{user_id}")
    )
    keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data=f"search_user"))
    
    bot.edit_message_text(
        "💰 لطفاً نوع تغییر موجودی را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith(('add_balance_', 'reduce_balance_')))
def handle_balance_amount(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    parts = call.data.split('_')
    action = parts[0]  # 'add' یا 'reduce'
    user_id = parts[2]  # شناسه کاربر
    
    msg = bot.edit_message_text(
        f"💰 لطفاً مبلغ مورد نظر را به تومان وارد کنید:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, process_balance_change, action, user_id)

def process_balance_change(message, action, user_id):
    try:
        if message.from_user.id not in BOT_CONFIG['admin_ids']:
            return
            
        amount = int(message.text.strip().replace(',', ''))
        if amount <= 0:
            raise ValueError("مبلغ باید بزرگتر از صفر باشد")
            
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # بررسی موجودی فعلی
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        current_balance = cursor.fetchone()
        
        if current_balance is None:
            bot.reply_to(message, "❌ کاربر در دیتابیس یافت نشد!")
            return
            
        current_balance = current_balance[0]
        
        if action == "add":
            new_balance = current_balance + amount
        else:  # action == "reduce"
            if current_balance < amount:
                bot.reply_to(message, "❌ موجودی کاربر کافی نیست!")
                return
            new_balance = current_balance - amount
        
        # بروزرسانی موجودی
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
        conn.close()
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت به جستجو", callback_data="search_user"))
        
        # ارسال پیام به کاربر
        try:
            bot.send_message(
                user_id,
                f"""💰 تغییر در موجودی حساب

{'➕' if action == 'add' else '➖'} مبلغ: {amount:,} تومان
💰 موجودی فعلی: {new_balance:,} تومان"""
            )
        except Exception as e:
            print(f"Error sending message to user: {e}")
            
        bot.reply_to(
            message,
            f"✅ موجودی کاربر با موفقیت {'افزایش' if action == 'add' else 'کاهش'} یافت.\n💰 موجودی فعلی: {new_balance:,} تومان",
            reply_markup=keyboard
        )
        
    except ValueError as e:
        bot.reply_to(message, str(e))
    except Exception as e:
        logging.error(f"Error in process_balance_change: {e}")
        print(f"Error in process_balance_change: {e}")  # اضافه کردن لاگ اضافی برای دیباگ
        bot.reply_to(message, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_message")
def handle_broadcast(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    msg = bot.edit_message_text(
        """✉️ پیام همگانی

لطفاً پیامی که می‌خواهید به تمام کاربران ارسال شود را وارد کنید:""",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    if message.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        
        success = 0
        failed = 0
        
        for user in users:
            try:
                bot.send_message(user[0], f"""📨 پیام از طرف مدیریت:

{message.text}""")
                success += 1
            except Exception as e:
                print(f"Error sending message to user {user[0]}: {e}")
                failed += 1
                
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
        
        bot.reply_to(
            message,
            f"""✅ پیام همگانی با موفقیت ارسال شد!

✓ ارسال موفق: {success}
❌ ارسال ناموفق: {failed}
📊 مجموع: {success + failed}""",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in process_broadcast: {e}")
        print(f"Error in process_broadcast: {e}")  # اضافه کردن لاگ اضافی برای دیباگ
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_users"))
        
        bot.reply_to(
            message,
            "❌ خطا در ارسال پیام همگانی!",
            reply_markup=keyboard
        )

# هندلر تنظیم درصد سود
@bot.callback_query_handler(func=lambda call: call.data == "set_profit")
def handle_set_profit(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        # دریافت درصد سود فعلی
        conn = sqlite3.connect('admin.db')
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
        current_profit = cursor.fetchone()
        conn.close()
        
        current_profit = float(current_profit[0]) if current_profit else 0
            
        msg = bot.edit_message_text(
            f"""💰 تنظیم درصد سود

درصد سود فعلی: {current_profit}%
لطفاً درصد سود جدید را وارد کنید (فقط عدد):""",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(msg, process_profit_percentage)
    except Exception as e:
        logging.error(f"Error in set_profit: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

def process_profit_percentage(message):
    try:
        # بررسی اینکه عدد وارد شده معتبر است
        try:
            profit = float(message.text.strip().replace(',', ''))
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد معتبر وارد کنید")
            return
            
        if profit < 0:
            bot.reply_to(message, "❌ درصد سود نمی‌تواند منفی باشد")
            return
            
        conn = sqlite3.connect('admin.db')
        cursor = conn.cursor()
        
        # بررسی وجود رکورد
        cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
        if cursor.fetchone() is None:
            # اگر رکورد وجود نداشت، ایجاد می‌کنیم
            cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('profit_percentage', str(profit)))
        else:
            # اگر رکورد وجود داشت، آپدیت می‌کنیم
            cursor.execute('UPDATE settings SET value = ? WHERE key = "profit_percentage"', (str(profit),))
        
        conn.commit()
        conn.close()
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("🔄 تنظیم مجدد", callback_data="set_profit"),
            types.InlineKeyboardButton("🔙 برگشت به پنل", callback_data="admin_panel")
        )
        
        bot.reply_to(
            message, 
            f"""✅ درصد سود با موفقیت تنظیم شد

💰 درصد سود جدید: {profit}%""",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in process_profit_percentage: {e}")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت به پنل", callback_data="admin_panel"))
        bot.reply_to(message, "❌ خطایی رخ داد", reply_markup=keyboard)

# هندلر تنظیم نرخ روبل
@bot.callback_query_handler(func=lambda call: call.data == "set_ruble_rate")
def handle_set_ruble_rate(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        msg = bot.edit_message_text(
            """💱 تنظیم نرخ روبل
            
لطفاً نرخ روبل را به تومان وارد کنید (فقط عدد):""",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(msg, process_ruble_rate)
    except Exception as e:
        logging.error(f"Error in set_ruble_rate: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

def process_ruble_rate(message):
    try:
        if not message.text.replace('.', '').isdigit():
            bot.reply_to(message, "❌ لطفاً فقط عدد وارد کنید")
            return
            
        rate = float(message.text)
        conn = sqlite3.connect('admin.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE settings SET value = ? WHERE key = "ruble_rate"', (rate,))
        conn.commit()
        conn.close()
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت به پنل مدیریت", callback_data="admin_panel"))
        
        bot.reply_to(
            message, 
            f"✅ نرخ روبل با موفقیت به {rate:,} تومان تغییر یافت",
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in process_ruble_rate: {e}")
        bot.reply_to(message, "❌ خطایی رخ داد")

# هندلر نمایش تراکنش‌ها
@bot.callback_query_handler(func=lambda call: call.data == "transactions")
def handle_transactions(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cp.payment_id, cp.user_id, cp.amount, cp.status, cp.created_at 
            FROM card_payments cp
            ORDER BY cp.created_at DESC 
            LIMIT 5
        ''')
        transactions = cursor.fetchall()
        conn.close()
        
        if not transactions:
            text = "❌ هیچ تراکنشی یافت نشد!"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        else:
            text = "🧾 تراکنش‌های اخیر (صفحه 1):\n\n"
            for t in transactions:
                status_emoji = "⏳" if t[3] == "pending" else "✅" if t[3] == "approved" else "❌"
                text += f"🆔 شناسه پرداخت: {t[0]}\n"
                text += f"👤 کاربر: {t[1]}\n"
                text += f"💰 مبلغ: {t[2]:,} تومان\n"
                text += f"📝 وضعیت: {status_emoji} {t[3]}\n"
                text += f"🕒 تاریخ: {t[4]}\n"
                text += "➖➖➖➖➖➖➖➖\n"
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("⬅️ صفحه قبل", callback_data="transactions_prev"),
                types.InlineKeyboardButton("➡️ صفحه بعد", callback_data="transactions_next")
            )
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in transactions: {e}")
        print(f"Error in transactions: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

# هندلر تغییر صفحه تراکنش‌ها
@bot.callback_query_handler(func=lambda call: call.data.startswith('transactions_'))
def handle_transactions_pagination(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        action = call.data.split('_')[1]  # 'prev' یا 'next'
        current_page = int(call.message.text.split('صفحه ')[1].split(':')[0])
        
        if action == 'prev' and current_page > 1:
            page = current_page - 1
        elif action == 'next':
            page = current_page + 1
        else:
            bot.answer_callback_query(call.id, "❌ این صفحه وجود ندارد!")
            return
            
        offset = (page - 1) * 5
        
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cp.payment_id, cp.user_id, cp.amount, cp.status, cp.created_at 
            FROM card_payments cp
            ORDER BY cp.created_at DESC 
            LIMIT 5 OFFSET ?
        ''', (offset,))
        transactions = cursor.fetchall()
        conn.close()
        
        if not transactions:
            text = "❌ هیچ تراکنشی در این صفحه یافت نشد!"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        else:
            text = f"🧾 تراکنش‌های اخیر (صفحه {page}):\n\n"
            for t in transactions:
                status_emoji = "⏳" if t[3] == "pending" else "✅" if t[3] == "approved" else "❌"
                text += f"🆔 شناسه پرداخت: {t[0]}\n"
                text += f"👤 کاربر: {t[1]}\n"
                text += f"💰 مبلغ: {t[2]:,} تومان\n"
                text += f"📝 وضعیت: {status_emoji} {t[3]}\n"
                text += f"🕒 تاریخ: {t[4]}\n"
                text += "➖➖➖➖➖➖➖➖\n"
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("⬅️ صفحه قبل", callback_data="transactions_prev"),
                types.InlineKeyboardButton("➡️ صفحه بعد", callback_data="transactions_next")
            )
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in transactions pagination: {e}")
        print(f"Error in transactions pagination: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

def save_user(user):
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # بررسی وجود کاربر
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user.id,))
        existing_user = cursor.fetchone()
        
        if existing_user is None:
            # اگر کاربر وجود نداشت، اضافه کن با موجودی صفر
            cursor.execute('''
                INSERT INTO users (user_id, balance)
                VALUES (?, 0)
            ''', (user.id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logging.error(f"Error saving user: {e}")
        print(f"Error saving user: {e}")  # اضافه کردن لاگ اضافی برای دیباگ
        return False

@bot.callback_query_handler(func=lambda call: call.data == "manage_channels")
def handle_manage_channels(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی به این بخش را ندارید")
            return
            
        channels = admin_config.get_required_channels()
        logging.info(f"Retrieved channels for display: {channels}")  # اضافه کردن لاگ
        
        text = "📢 مدیریت کانال‌های اجباری\n\n"
        
        if channels and len(channels) > 0:
            text += "📋 لیست کانال‌های فعلی:\n\n"
            for i, channel in enumerate(channels, 1):
                try:
                    chat_info = bot.get_chat(f"@{channel[0]}")
                    text += f"{i}. {chat_info.title}\n"
                    text += f"🆔 @{channel[0]}\n"
                    text += f"🔗 {channel[2]}\n"
                    text += "➖➖➖➖➖➖➖➖\n"
                except Exception as e:
                    logging.error(f"Error getting chat info for @{channel[0]}: {e}")
                    text += f"{i}. @{channel[0]} (غیرقابل دسترس)\n"
                    text += "➖➖➖➖➖➖➖➖\n"
        else:
            text += "❌ هیچ کانالی ثبت نشده است.\n"
            
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("➕ افزودن کانال", callback_data="add_channel"),
            types.InlineKeyboardButton("❌ حذف کانال", callback_data="remove_channel")
        )
        keyboard.add(
            types.InlineKeyboardButton("🔄 بررسی وضعیت", callback_data="check_channels_status"),
            types.InlineKeyboardButton("⚡️ وضعیت قفل", callback_data="toggle_lock")
        )
        keyboard.add(
            types.InlineKeyboardButton("🤖 افزودن ربات به کانال", url="https://t.me/HajNumber_Bot")
        )
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logging.error(f"Error in manage_channels: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def handle_add_channel(call):
    try:
        text = """➕ افزودن کانال جدید

⚠️ قبل از افزودن کانال:
1. ابتدا ربات @HajNumber_Bot را به کانال اضافه کنید
2. ربات را ادمین کانال کنید (با دسترسی ارسال پیام)
3. سپس آیدی کانال را با @ وارد کنید

لطفاً آیدی کانال را وارد کنید (با @ شروع شود):"""

        msg = bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🤖 افزودن ربات به کانال", url="https://t.me/HajNumber_Bot")
            )
        )
        bot.register_next_step_handler(msg, process_channel_username)
    except Exception as e:
        logging.error(f"Error in add_channel: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

def process_channel_username(message):
    try:
        if message.from_user.id not in BOT_CONFIG['admin_ids']:
            return
            
        username = message.text.strip()
        if not username.startswith('@'):
            raise ValueError("❌ آیدی کانال باید با @ شروع شود!")
            
        username = username[1:]  # حذف @ از ابتدای نام کاربری
        
        # بررسی وجود کانال و دسترسی ربات
        try:
            chat_info = bot.get_chat(f"@{username}")
            bot_member = bot.get_chat_member(f"@{username}", bot.get_me().id)
            
            if bot_member.status not in ['administrator', 'creator']:
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton("🤖 افزودن ربات به کانال", url="https://t.me/HajNumber_Bot"),
                    types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data="add_channel"),
                    types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels")
                )
                bot.reply_to(
                    message, 
                    "❌ ربات باید ادمین کانال باشد!\n\n1️⃣ ابتدا ربات را به کانال اضافه کنید\n2️⃣ سپس ربات را ادمین کنید\n3️⃣ دوباره تلاش کنید",
                    reply_markup=keyboard
                )
                return
                
            # دریافت لینک دعوت
            try:
                invite_link = bot.export_chat_invite_link(f"@{username}")
            except:
                invite_link = f"https://t.me/{username}"
            
            # ذخیره کانال
            admin_config.add_required_channel(
                username=username,
                display_name=chat_info.title,
                invite_link=invite_link
            )
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به مدیریت کانال‌ها", callback_data="manage_channels"))
            
            bot.reply_to(
                message,
                f"""✅ کانال با موفقیت اضافه شد!

📢 نام: {chat_info.title}
🆔 @{username}
🔗 {invite_link}""",
                reply_markup=keyboard
            )
            
        except telebot.apihelper.ApiException as e:
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            if "chat not found" in str(e).lower():
                keyboard.add(
                    types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data="add_channel"),
                    types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels")
                )
                bot.reply_to(message, "❌ کانال یافت نشد!", reply_markup=keyboard)
            elif "bot is not a member" in str(e).lower():
                keyboard.add(
                    types.InlineKeyboardButton("🤖 افزودن ربات به کانال", url="https://t.me/HajNumber_Bot"),
                    types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data="add_channel"),
                    types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels")
                )
                bot.reply_to(message, "❌ ربات عضو کانال نیست!\n\nلطفاً ابتدا ربات را به کانال اضافه کنید.", reply_markup=keyboard)
            else:
                keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels"))
                bot.reply_to(message, "❌ خطا در دسترسی به کانال!", reply_markup=keyboard)
                
    except ValueError as e:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data="add_channel"))
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels"))
        bot.reply_to(message, str(e), reply_markup=keyboard)
        
    except Exception as e:
        logging.error(f"Error in process_channel_username: {e}")
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels"))
        bot.reply_to(message, "❌ خطایی رخ داد", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "remove_channel")
def handle_remove_channel(call):
    try:
        channels = admin_config.get_required_channels()
        if not channels:
            bot.answer_callback_query(call.id, "❌ هیچ کانالی برای حذف وجود ندارد")
            return
            
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for channel in channels:
            keyboard.add(types.InlineKeyboardButton(
                f"❌ {channel[1]} (@{channel[0]})",
                callback_data=f"del_channel_{channel[0]}"
            ))
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels"))
        
        bot.edit_message_text(
            "❌ کانال مورد نظر برای حذف را انتخاب کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in remove_channel: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_channel_'))
def handle_delete_channel(call):
    try:
        username = call.data.split('_')[2]
        admin_config.remove_required_channel(username)
        
        bot.answer_callback_query(call.id, "✅ کانال با موفقیت حذف شد")
        handle_manage_channels(call)  # بازگشت به صفحه مدیریت کانال‌ها
        
    except Exception as e:
        logging.error(f"Error in delete_channel: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data == "check_channels_status")
def handle_check_channels_status(call):
    try:
        channels = admin_config.get_required_channels()
        if not channels:
            bot.answer_callback_query(call.id, "❌ هیچ کانالی ثبت نشده است")
            return
            
        text = "📊 وضعیت کانال‌ها:\n\n"
        all_ok = True
        
        for channel in channels:
            try:
                # بررسی وضعیت ربات در کانال
                bot_member = bot.get_chat_member(f"@{channel[0]}", bot.get_me().id)
                chat_info = bot.get_chat(f"@{channel[0]}")
                
                if bot_member.status in ['administrator', 'creator']:
                    text += f"✅ {chat_info.title}\n"
                    text += f"🆔 @{channel[0]}\n"
                    text += "💠 وضعیت: ربات ادمین است\n"
                else:
                    text += f"⚠️ {chat_info.title}\n"
                    text += f"🆔 @{channel[0]}\n"
                    text += "💠 وضعیت: ربات ادمین نیست!\n"
                    all_ok = False
                    
            except Exception as e:
                text += f"❌ @{channel[0]}\n"
                text += "💠 وضعیت: خطا در دسترسی!\n"
                all_ok = False
                
            text += "➖➖➖➖➖➖➖➖\n"
            
        text += f"\n{'✅ همه کانال‌ها فعال هستند' if all_ok else '⚠️ برخی کانال‌ها مشکل دارند'}"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="manage_channels"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logging.error(f"Error in check_channels_status: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data == "toggle_lock")
def handle_toggle_lock(call):
    try:
        current_status = admin_config.get_lock_status()
        new_status = not current_status
        admin_config.set_lock_status(new_status)
        
        status_text = "فعال ✅" if new_status else "غیرفعال ❌"
        bot.answer_callback_query(call.id, f"✅ وضعیت قفل کانال‌ها: {status_text}")
        handle_manage_channels(call)  # بازگشت به صفحه مدیریت کانال‌ها
        
    except Exception as e:
        logging.error(f"Error in toggle_lock: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

# ایجاد دایرکتوری logs اگر وجود ندارد
if not os.path.exists('logs'):
    os.makedirs('logs')

# تنظیم لاگر مخصوص فرآیند خرید
purchase_logger = logging.getLogger('purchase_logger')
purchase_logger.setLevel(logging.INFO)

# تنظیم فایل لاگ با چرخش روزانه
purchase_handler = logging.handlers.TimedRotatingFileHandler(
    'logs/purchase.log',
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8'
)

# تنظیم فرمت لاگ
purchase_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
purchase_handler.setFormatter(purchase_formatter)
purchase_logger.addHandler(purchase_handler)

# اضافه کردن لاگ‌ها در بخش خرید
def handle_buy_number(call):
    try:
        purchase_logger = logging.getLogger('purchase_logger')
        purchase_logger.info(f"Starting purchase process for user {call.from_user.id}")

        # دریافت اطلاعات از callback_data
        _, service, country = call.data.split('_')
        purchase_logger.info(f"Service: {service}, Country: {country}")

        # بررسی موجودی کاربر
        user_balance = get_user_balance(call.from_user.id)
        purchase_logger.info(f"User balance: {user_balance}")

        # دریافت قیمت
        price = get_prices(product)
        purchase_logger.info(f"Product price: {price}")

        if user_balance < price:
            purchase_logger.warning(f"Insufficient balance for user {call.from_user.id}")
            bot.answer_callback_query(call.id, "❌ موجودی شما کافی نیست")
            return

        # خرید شماره از API
        headers = {
            'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
            'Accept': 'application/json',
        }
        
        purchase_logger.info(f"Sending request to 5sim API...")
        response = requests.get(
            f'https://5sim.net/v1/user/buy/activation/{country}/any/{service}',
            headers=headers
        )
        
        purchase_logger.info(f"5sim API Response Status: {response.status_code}")
        purchase_logger.info(f"5sim API Response: {response.text}")

        if response.status_code == 200:
            order = response.json()
            
            # کم کردن موجودی
            new_balance = add_balance(call.from_user.id, -price)
            logging.info(f"New balance after purchase: {new_balance}")

            try:
                # بررسی وجود جدول
                conn = sqlite3.connect(DB_CONFIG['users_db'])
                cursor = conn.cursor()
                
                # ایجاد جدول اگر وجود ندارد
                cursor.execute('''CREATE TABLE IF NOT EXISTS orders
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     phone_number TEXT,
                     service TEXT,
                     country TEXT,
                     price INTEGER,
                     order_id TEXT UNIQUE,
                     status TEXT DEFAULT 'active',
                     order_date DATETIME DEFAULT CURRENT_TIMESTAMP)''')
                
                # ذخیره اطلاعات سفارش
                cursor.execute('''
                    INSERT INTO orders 
                    (user_id, phone_number, service, country, price, order_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    call.from_user.id,
                    order['phone'],
                    service,
                    country,
                    price,
                    order['id'],
                    'active'
                ))
                conn.commit()
                logging.info(f"Order saved successfully. Order ID: {order['id']}")

                # ارسال پیام موفقیت به کاربر
                keyboard = types.InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    types.InlineKeyboardButton("📱 مشاهده جزئیات", url=f"{BOT_CONFIG['webhook_base_url']}/number/{order['id']}"),
                    types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")
                )

                bot.edit_message_text(
                    f"✅ خرید با موفقیت انجام شد!\n\n"
                    f"📱 شماره: {order['phone']}\n"
                    f"🌍 کشور: {country}\n"
                    f"🔰 سرویس: {service}\n"
                    f"💰 مبلغ پرداخت شده: {price:,} تومان\n"
                    f"💎 موجودی فعلی: {new_balance:,} تومان",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
                logging.info("Success message sent to user")

            except sqlite3.Error as db_error:
                logging.error(f"Database error: {db_error}")
                # برگرداندن پول در صورت خطا
                add_balance(call.from_user.id, price)
                bot.answer_callback_query(call.id, "❌ خطا در ثبت سفارش")
            finally:
                conn.close()

        else:
            purchase_logger.error(f"5sim API error: {response.text}")
            bot.answer_callback_query(call.id, "❌ خطا در خرید شماره")

    except Exception as e:
        logging.error(f"Error in handle_buy_number: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ خطای غیرمنتظره")

def buy_activation_number(country, operator, product, forwarding=False, forwarding_number=None, reuse=None, voice=None, ref=None, max_price=None):
    """
    خرید شماره از سرویس 5sim
    """
    try:
        # ساخت URL با پارامترهای اختیاری
        base_url = f"https://5sim.net/v1/user/buy/activation/{country}/{operator}/{product}"
        params = {}
        
        if forwarding:
            params['forwarding'] = '1'
            if forwarding_number:
                params['number'] = forwarding_number
        if reuse:
            params['reuse'] = '1'
        if voice:
            params['voice'] = '1'
        if ref:
            params['ref'] = ref
        if max_price:
            params['maxPrice'] = str(max_price)

        # تنظیم هدرها طبق مستندات
        headers = {
            'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
            'Accept': 'application/json'
        }
        
        logging.info(f"Sending request to 5sim API: URL={base_url}, Params={params}")
        
        response = requests.get(
            base_url,
            headers=headers,
            params=params,
            timeout=30
        )
        
        logging.info(f"5sim API response status: {response.status_code}")
        logging.info(f"5sim API response body: {response.text}")
        
        # بررسی پاسخ متنی "no free phones"
        if response.text.strip() == "no free phones":
            return {
                'success': False,
                'error': 'در حال حاضر شماره‌ای برای این سرویس موجود نیست. لطفاً اپراتور دیگری را امتحان کنید.'
            }
            
        # بررسی کد وضعیت
        response.raise_for_status()
        
        # پردازش پاسخ JSON
        result = response.json()
        
        if not result:
            return {
                'success': False,
                'error': 'پاسخ API خالی است'
            }
            
        return {
            'success': True,
            'data': {
                'order_id': result['id'],
                'phone': result['phone'],
                'operator': result['operator'],
                'product': result['product'],
                'price': result['price'],
                'status': result['status'],
                'expires': result['expires'],
                'created_at': result['created_at'],
                'country': result['country']
            }
        }
        
    except requests.exceptions.RequestException as e:
        error_msg = f"خطا در ارتباط با سرور: {str(e)}"
        logging.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"خطای غیرمنتظره: {str(e)}"
        logging.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_number_'))
def handle_buy_number(call):
    try:
        user_id = call.from_user.id
        
        # بررسی موجودی کاربر
        balance = get_user_balance(user_id)
        logging.info(f"User {user_id} balance checked: {balance}")
        
        parts = call.data.split('_')
        # فرمت جدید: buy_number_service_country_operator
        service = parts[2]
        country = parts[3]
        operator = parts[4]  # حالا اپراتور را از callback_data می‌گیریم
        
        # دریافت نام کشور از تنظیمات
        config_operator, country_name = operator_config.get_operator_info(service, country)
        
        # اگر نام کشور در تنظیمات نباشد، از دیکشنری استفاده می‌کنیم
        if not country_name:
            country_name = {
                'russia': 'روسیه 🇷🇺',
                'canada': 'کانادا 🇨🇦',
                'england': 'انگلستان 🇬🇧',
                'cyprus': 'قبرس 🇨🇾',
                'paraguay': 'پاراگوئه 🇵🇾',
                'maldives': 'مالدیو 🇲🇻',
                'suriname': 'سورینام 🇸🇷',
                'slovenia': 'اسلوونی 🇸🇮',
                'poland': 'لهستان 🇵🇱',
                # سایر کشورها را اضافه کنید...
            }.get(country, country)
            
        # دریافت قیمت
        headers = {
            'Accept': 'application/json',
        }
        
        params = (
            ('country', country),
            ('product', service),
        )
        
        response = requests.get(
            'https://5sim.net/v1/guest/prices',
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if country in data and service in data[country]:
                operators_data = data[country][service]
                
                if operator in operators_data and operators_data[operator]['count'] > 0:
                    price_ruble = operators_data[operator]['cost']
                    
                    # دریافت نرخ روبل و درصد سود از دیتابیس
                    conn = sqlite3.connect('admin.db')
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT value FROM settings WHERE key = "ruble_rate"')
                    ruble_rate_result = cursor.fetchone()
                    ruble_rate = float(ruble_rate_result[0]) if ruble_rate_result else 0
                    
                    cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
                    profit_result = cursor.fetchone()
                    profit_percentage = float(profit_result[0]) if profit_result else 0
                    
                    conn.close()
                    
                    price_toman = round(price_ruble * ruble_rate * (1 + profit_percentage/100))
                    
                    if balance < price_toman:
                        # موجودی ناکافی
                        bot.answer_callback_query(call.id, "⚠️ موجودی شما کافی نیست")
                        keyboard = types.InlineKeyboardMarkup(row_width=1)
                        keyboard.add(
                            types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="add_funds"),
                            types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_services")
                        )
                        bot.edit_message_text(
                            f"""❌ موجودی شما کافی نیست!

💵 موجودی فعلی: {balance:,} تومان
💰 قیمت شماره: {price_toman:,} تومان
⚠️ کمبود موجودی: {price_toman - balance:,} تومان

لطفاً ابتدا حساب خود را شارژ کنید.""",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=keyboard
                        )
                        return
                    
                    # خرید شماره
                    bot.edit_message_text(
                        f"⏳ در حال خرید شماره {service} از {country_name}... لطفاً صبر کنید.",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    
                    # خرید شماره با استفاده از API
                    result = buy_activation_number(country, operator, service)
                    logging.info(f"Buy number result: {result}")
                    
                    # بررسی نتیجه خرید
                    if result and isinstance(result, dict) and result.get('success') and 'data' in result:
                        # دریافت اطلاعات از ساختار جدید
                        order_data = result['data']
                        activation_id = order_data['order_id']
                        phone_number = order_data['phone']
                        status = order_data['status']
                        
                        # کم کردن موجودی کاربر
                        add_balance(user_id, -price_toman)
                        
                        # ثبت تراکنش در دیتابیس
                        order_info = {
                            'user_id': user_id,
                            'activation_id': activation_id,
                            'service': service,
                            'country': country,
                            'operator': operator,
                            'phone': phone_number,
                            'price': price_toman,
                            'status': status.lower()
                        }
                        
                        # ذخیره در دیتابیس و دریافت شناسه سفارش
                        order_id = save_order(order_info)
                        
                        if order_id:
                            # استفاده از یک URL کامل با هاست
                            details_url = f"https://clever-bluejay-charmed.ngrok-free.app/number_details/{order_id}"
                            
                            keyboard = types.InlineKeyboardMarkup(row_width=1)
                            keyboard.add(
                                types.InlineKeyboardButton("🔄 دریافت کد", callback_data=f"get_code_{activation_id}"),
                                types.InlineKeyboardButton("❌ لغو سفارش", callback_data=f"cancel_order_{activation_id}"),
                                types.InlineKeyboardButton("🌐 مشاهده جزئیات در وب", url=details_url),
                                types.InlineKeyboardButton("🔙 برگشت به سرویس‌ها", callback_data="back_to_services")
                            )
                            
                            bot.edit_message_text(
                                f"""✅ شماره با موفقیت خریداری شد!

🌍 سرویس: {service}
🌎 کشور: {country_name}
📱 شماره: {phone_number}
🔌 اپراتور: {operator}
💵 قیمت: {price_toman:,} تومان
⏱ وضعیت: در انتظار دریافت کد

💻 برای مشاهده جزئیات بیشتر و دریافت کد، می‌توانید روی دکمه "مشاهده جزئیات در وب" کلیک کنید.""",
                                call.message.chat.id,
                                call.message.message_id,
                                reply_markup=keyboard
                            )
                        else:
                            # خطا در ذخیره اطلاعات
                            logging.error("Error saving order to database")
                            bot.edit_message_text(
                                "❌ خطا در ثبت سفارش. لطفاً با پشتیبانی تماس بگیرید.",
                                call.message.chat.id,
                                call.message.message_id,
                                reply_markup=services_keyboard()
                            )
                    else:
                        # خطا در خرید شماره
                        error_msg = "خطا در خرید شماره"
                        if isinstance(result, dict):
                            if 'message' in result:
                                error_msg = result['message']
                            elif not result.get('success'):
                                error_msg = "خرید ناموفق بود"
                        
                        logging.error(f"Error buying number: {error_msg}")
                        bot.edit_message_text(
                            f"""❌ خطا در خرید شماره!

⚠️ {error_msg}

لطفاً مجدداً تلاش کنید یا کشور/سرویس دیگری انتخاب کنید.""",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=services_keyboard()
                        )
                else:
                    # اپراتور موجود نیست
                    bot.answer_callback_query(call.id, f"⚠️ اپراتور {operator} برای این کشور موجود نیست")
                    bot.edit_message_text(
                        f"""⚠️ اپراتور {operator} برای کشور {country_name} و سرویس {service} موجود نیست.

لطفاً کشور یا سرویس دیگری انتخاب کنید.""",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=services_keyboard()
                    )
            else:
                # کشور یا سرویس موجود نیست
                bot.answer_callback_query(call.id, "⚠️ این سرویس برای کشور انتخابی موجود نیست")
                bot.edit_message_text(
                    "⚠️ این سرویس برای کشور انتخابی موجود نیست. لطفاً کشور یا سرویس دیگری انتخاب کنید.",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=services_keyboard()
                )
        else:
            # خطا در دریافت قیمت‌ها
            bot.answer_callback_query(call.id, "❌ خطا در دریافت اطلاعات قیمت")
            bot.edit_message_text(
                "❌ خطا در دریافت اطلاعات قیمت. لطفاً مجدداً تلاش کنید.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=services_keyboard()
            )
            
    except Exception as e:
        logging.error(f"Error in handle_buy_number: {e}")
        # افزودن اطلاعات بیشتر برای عیب‌یابی
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")
        bot.send_message(call.message.chat.id, "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('get_code_'))
def handle_get_code(call):
    try:
        order_id = call.data.split('_')[2]
        
        # دریافت کد از 5sim با API جدید
        headers = {
            'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
            'Accept': 'application/json',
        }
        
        check_url = f'https://5sim.net/v1/user/check/{order_id}'
        logging.info(f"Checking order status: {check_url}")
        
        response = requests.get(
            check_url,
            headers=headers,
            timeout=30
        )
        
        logging.info(f"Check status response: {response.status_code}")
        logging.info(f"Check status data: {response.text}")
        
        if response.status_code == 200:
            order_status = response.json()
            
            if order_status.get('sms', []):
                # کد دریافت شده است
                sms = order_status['sms'][0]
                code_text = sms['text']
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("مشاهده جزئیات سفارش", url=f"https://clever-bluejay-charmed.ngrok-free.app/number_details/{order_id}"))
                keyboard.add(types.InlineKeyboardButton("🔙 برگشت به منوی اصلی", callback_data="back_to_main"))
                
                text = f"""✅ کد تایید دریافت شد

📱 شماره: {order_status['phone']}
📨 پیام: {code_text}
⏰ زمان دریافت: {sms['created_at']}

برای مشاهده تمام کدهای دریافتی این سفارش، روی دکمه زیر کلیک کنید."""
                
                # آپدیت وضعیت سفارش در دیتابیس
                conn = sqlite3.connect('bot.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE orders SET status = ? WHERE id = ?', ('RECEIVED', order_id))
                
                # ذخیره کد در جدول activation_codes
                cursor.execute("""
                    INSERT INTO activation_codes (order_id, code, created_at)
                    VALUES (?, ?, ?)
                """, (order_id, code_text, sms['created_at']))
                
                conn.commit()
                conn.close()
                
                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
            else:
                bot.answer_callback_query(call.id, "⏳ کد هنوز دریافت نشده است. لطفاً کمی صبر کنید.")
        else:
            bot.answer_callback_query(call.id, "❌ خطا در بررسی وضعیت سفارش")
            
    except Exception as e:
        logging.error(f"خطا در دریافت کد: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

def refund_order_amount(order_id):
    """
    برگرداندن مبلغ سفارش به کاربر در هنگام لغو سفارش
    """
    try:
        # دریافت اطلاعات سفارش
        conn_orders = sqlite3.connect('bot.db')
        cursor_orders = conn_orders.cursor()
        
        # جستجوی سفارش بر اساس activation_id
        cursor_orders.execute('''
            SELECT user_id, price, status FROM orders 
            WHERE activation_id = ?
        ''', (order_id,))
        
        order = cursor_orders.fetchone()
        
        if not order:
            logging.error(f"سفارش با شناسه {order_id} یافت نشد")
            conn_orders.close()
            return False, "سفارش یافت نشد"
            
        user_id, price, status = order
        
        # اگر سفارش قبلاً لغو شده باشد، وجه را برنگردان
        if status.upper() == "CANCELED":
            logging.warning(f"سفارش {order_id} قبلاً لغو شده است")
            conn_orders.close()
            return False, "سفارش قبلاً لغو شده است"
            
        # بروزرسانی وضعیت سفارش
        cursor_orders.execute('''
            UPDATE orders SET status = "CANCELED" 
            WHERE activation_id = ?
        ''', (order_id,))
        
        conn_orders.commit()
        conn_orders.close()
        
        # دریافت موجودی قبل از افزایش
        current_balance = get_user_balance(user_id)
        
        if current_balance is None:
            logging.error(f"کاربر با شناسه {user_id} یافت نشد")
            return False, "کاربر یافت نشد"
            
        # افزایش موجودی کاربر با استفاده از تابع موجود
        add_balance(user_id, price)
        
        # دریافت موجودی جدید (برای لاگ)
        new_balance = get_user_balance(user_id)
        
        logging.info(f"مبلغ {price} تومان به حساب کاربر {user_id} برگشت داده شد. موجودی جدید: {new_balance}")
        
        # برگرداندن هر دو مقدار: مبلغ برگشتی و موجودی جدید
        return True, {'refund_amount': price, 'new_balance': new_balance}
        
    except Exception as e:
        logging.error(f"خطا در برگرداندن وجه: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        if 'conn_orders' in locals():
            conn_orders.close()
            
        return False, str(e)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_order_'))
def handle_cancel_order(call):
    try:
        # دریافت شناسه سفارش
        order_id = int(call.data.split('_')[2])
        
        # اطلاع به کاربر
        bot.edit_message_text(
            "⏳ در حال لغو سفارش... لطفاً صبر کنید.",
            call.message.chat.id,
            call.message.message_id
        )
        
        # دریافت کلید API از تنظیمات
        headers = {
            'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
            'Accept': 'application/json',
        }
        
        # درخواست لغو سفارش به API
        response = requests.get(
            f'https://5sim.net/v1/user/cancel/{order_id}',
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            # برگرداندن وجه به کاربر با استفاده از تابع جدید
            success, result = refund_order_amount(order_id)
            
            if success:
                # نمایش پیام موفقیت
                if isinstance(result, dict):  # اگر نتیجه دیکشنری باشد (فرمت جدید)
                    refund_amount = result['refund_amount']
                    new_balance = result['new_balance']
                    
                    success_message = f"""✅ سفارش با موفقیت لغو شد
                    
  💰 موجودی فعلی شما: {new_balance:,} تومان

💰 مبلغ برگشتی به حساب شما: {refund_amount:,} تومان"""
                else:  # برای سازگاری با نسخه‌های قبلی
                    success_message = f"""✅ سفارش با موفقیت لغو شد

💰 مبلغ برگشتی به حساب شما: {result:,} تومان"""
            else:
                # لغو سفارش انجام شده اما مشکلی در برگرداندن وجه بوده
                success_message = f"""✅ سفارش با موفقیت لغو شد

⚠️ هشدار: {result}
لطفاً با پشتیبانی تماس بگیرید."""
                
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="buy_number"))
            
            bot.edit_message_text(
                success_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
        # ... ادامه کد بدون تغییر ...
    except Exception as e:
        logging.error(f"خطا در لغو سفارش: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        bot.edit_message_text(
            "❌ خطا در لغو سفارش. لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🔙 برگشت", callback_data="my_orders")
            )
        )

# ایجاد نمونه از کلاس OperatorConfig
operator_config = OperatorConfig()

# و در تابع initialize یا main
def initialize_bot():
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # ایجاد جدول settings در شروع برنامه
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # بررسی و اضافه کردن تنظیمات پیش‌فرض
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (key, value) VALUES 
                ("ruble_rate", "0.35"),
                ("profit_percentage", "20")
            ''')
        
        conn.commit()
        logging.info("Bot initialized successfully with required tables")
        
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

@bot.callback_query_handler(func=lambda call: call.data == "operator_settings")
def handle_operator_settings(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        settings = operator_config.get_all_settings()
        
        text = "📱 تنظیمات اپراتور\n\n"
        services = {'telegram': 'تلگرام', 'whatsapp': 'واتساپ', 'instagram': 'اینستاگرام', 'google': 'گوگل'}
        
        # کشورهای هر سرویس به زبان فارسی
        service_countries = {
            'telegram': {'cyprus': 'قبرس', 'paraguay': 'پاراگوئه', 'maldives': 'مالدیو', 'suriname': 'سورینام', 'slovenia': 'اسلوونی', 'canada': 'کانادا'},
            'whatsapp': {'georgia': 'گرجستان', 'cameroon': 'کامرون', 'laos': 'لائوس', 'benin': 'بنین', 'dominican_republic': 'جمهوری دومینیکن'},
            'instagram': {'poland': 'لهستان', 'philippines': 'فیلیپین', 'netherlands': 'هلند', 'estonia': 'استونی', 'vietnam': 'ویتنام'},
            'google': {'cambodia': 'کامبوج', 'philippines': 'فیلیپین', 'indonesia': 'اندونزی', 'ethiopia': 'اتیوپی', 'russia': 'روسیه'}
        }
        
        for service in services:
            text += f"🔹 {services[service]}:\n"
            for country_code, country_name in service_countries[service].items():
                operator = next((s[2] for s in settings if s[0] == service and s[1] == country_code), 'تنظیم نشده')
                text += f"  • {country_name}: {operator}\n"
            text += "\n"
            
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✏️ تغییر تنظیمات", callback_data="change_operator"),
            types.InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel")
        )
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"Error in operator_settings: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

@bot.callback_query_handler(func=lambda call: call.data == "change_operator")
def handle_change_operator(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        text = "📱 لطفاً سرویس را انتخاب کنید:"
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("تلگرام", callback_data="select_service_telegram"),
            types.InlineKeyboardButton("واتساپ", callback_data="select_service_whatsapp"),
            types.InlineKeyboardButton("اینستاگرام", callback_data="select_service_instagram"),
            types.InlineKeyboardButton("گوگل", callback_data="select_service_google"),
            types.InlineKeyboardButton("🔙 برگشت", callback_data="operator_settings")
        )
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"خطا در تغییر اپراتور: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_service_'))
def handle_select_service(call):
    try:
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            bot.answer_callback_query(call.id, "⛔️ شما دسترسی ندارید")
            return
            
        service = call.data.split('_')[2]
        
        # کشورهای هر سرویس به زبان فارسی
        service_countries = {
            'telegram': {'cyprus': 'قبرس', 'paraguay': 'پاراگوئه', 'maldives': 'مالدیو', 'suriname': 'سورینام', 'slovenia': 'اسلوونی', 'canada': 'کانادا'},
            'whatsapp': {'georgia': 'گرجستان', 'cameroon': 'کامرون', 'laos': 'لائوس', 'benin': 'بنین', 'dominican_republic': 'جمهوری دومینیکن'},
            'instagram': {'poland': 'لهستان', 'philippines': 'فیلیپین', 'netherlands': 'هلند', 'estonia': 'استونی', 'vietnam': 'ویتنام'},
            'google': {'cambodia': 'کامبوج', 'philippines': 'فیلیپین', 'indonesia': 'اندونزی', 'ethiopia': 'اتیوپی', 'russia': 'روسیه'}
        }
        
        if service not in service_countries:
            bot.answer_callback_query(call.id, "❌ سرویس نامعتبر است!")
            return
        
        text = f"📱 لطفاً کشور را برای سرویس {service} انتخاب کنید:"
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        for country_code, country_name in service_countries[service].items():
            keyboard.add(types.InlineKeyboardButton(country_name, callback_data=f"select_country_{service}_{country_code}"))
        
        keyboard.add(types.InlineKeyboardButton("🔙 برگشت", callback_data="change_operator"))
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logging.error(f"خطا در انتخاب سرویس: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_country_'))
def handle_select_country(call):
    try:
        _, service, country = call.data.split('_')[1:]
        msg = bot.edit_message_text(
            f"🔧 لطفاً نام اپراتور جدید را وارد کنید:\n\nمثال: virtual40",
            call.message.chat.id,
            call.message.message_id
        )
        bot.register_next_step_handler(msg, process_operator_change, service, country)
        
    except Exception as e:
        logging.error(f"Error in select_country: {e}")
        bot.answer_callback_query(call.id, "❌ خطایی رخ داد")

def process_operator_change(message, service, country):
    try:
        operator = message.text.strip().lower()
        
        if operator_config.set_operator(service, country, operator):
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به تنظیمات", callback_data="operator_settings"))
            
            bot.reply_to(
                message,
                f"✅ اپراتور با موفقیت تغییر کرد!\n\nسرویس: {service}\nکشور: {country}\nاپراتور جدید: {operator}",
                reply_markup=keyboard
            )
        else:
            bot.reply_to(message, "❌ خطا در تغییر اپراتور")
            
    except Exception as e:
        logging.error(f"Error in process_operator_change: {e}")
        bot.reply_to(message, "❌ خطایی رخ داد")


@bot.callback_query_handler(func=lambda call: call.data == 'my_orders')
def handle_my_orders(call):
    user_id = call.from_user.id
    
    try:
        orders_url = f"{BOT_CONFIG['webhook_url'].rstrip('/')}/orders/{user_id}"
        
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("🌐 مشاهده سفارش‌ها در وب", url=orders_url)
        )
        keyboard.add(
            types.InlineKeyboardButton("🔙 برگشت به منو", callback_data="back_to_main")
        )
        
        bot.edit_message_text(
            "📦 سفارش‌های من\n\nبرای مشاهده جزئیات سفارش‌های خود، می‌توانید روی دکمه زیر کلیک کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in handle_my_orders: {e}")
        bot.answer_callback_query(call.id, "❌ خطا در دریافت سفارش‌ها")

@app.route('/orders/<int:user_id>')
def user_orders(user_id):
    try:
        # اضافه کردن لاگ برای شروع
        logger.info(f"Fetching orders for user_id: {user_id}")
        
        # دریافت سفارش‌های کاربر از دیتابیس
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # بررسی وجود جدول
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='orders'
        """)
        if not cursor.fetchone():
            logger.error("Table 'orders' does not exist")
            return "جدول سفارش‌ها وجود ندارد", 500
            
        # دریافت سفارش‌ها
        cursor.execute('''
            SELECT activation_id, phone, service, country, price, status, created_at
            FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        orders_data = cursor.fetchall()
        logger.info(f"Found {len(orders_data)} orders for user {user_id}")
        
        conn.close()
        
        orders = []
        base_url = BOT_CONFIG['webhook_url'].rstrip('/')
        
        for order in orders_data:
            orders.append({
                'id': order[0],  # activation_id
                'phone_number': order[1],
                'service': order[2],
                'country': order[3],
                'price': order[4],  # حذف فرمت کردن اعداد از اینجا
                'status': order[5],
                'date': order[6],
                'details_url': f"https://clever-bluejay-charmed.ngrok-free.app/number_details/{order[0]}"
            })
        
        # اضافه کردن لاگ برای رندر
        logger.info(f"Rendering template with {len(orders)} orders")
        
        # بررسی وجود تمپلیت
        try:
            return render_template('user_orders.html', orders=orders)
        except Exception as template_error:
            logger.error(f"Template error: {template_error}")
            return "خطا در بارگذاری قالب صفحه", 500
        
    except Exception as e:
        logger.error(f"Error in user_orders: {str(e)}")
        return f"خطای سیستمی: {str(e)}", 500

@bot.callback_query_handler(func=lambda call: call.data == "add_funds")
def handle_add_funds(call):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("💳 پرداخت آنلاین (درگاه زرین‌پال)", callback_data="zarinpal_payment"),
        types.InlineKeyboardButton("💳 پرداخت کارت به کارت", callback_data="card_payment"),
        types.InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        "💰 لطفاً روش پرداخت را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "zarinpal_payment")
def handle_zarinpal_payment(call):
    msg = bot.edit_message_text(
        "💳 لطفاً مبلغ مورد نظر را به تومان وارد کنید:\n"
        "مثال: 50000",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, process_zarinpal_amount)

def process_zarinpal_amount(message):
    try:
        amount = int(message.text)
        if amount < 5000:
            bot.reply_to(message, "❌ حداقل مبلغ شارژ 5,000 تومان می‌باشد.")
            return
            
        # درخواست به API زرین‌پال
        data = {
            "merchant_id": PAYMENT_CONFIG['zarinpal_merchant'],
            "amount": amount * 10,  # تبدیل به ریال
            "description": f"شارژ حساب کاربر {message.from_user.id}",
            "callback_url": f"{PAYMENT_CONFIG['callback_url']}/{message.from_user.id}/{amount}",  # این مسیر درست است چون از config می‌خواند
            "metadata": {
                "mobile": message.from_user.username or str(message.from_user.id),
                "email": "",
                "order_id": f"charge_{message.from_user.id}_{int(time.time())}"
            }
        }
        
        # تعیین آدرس API بر اساس حالت sandbox
        if PAYMENT_CONFIG['sandbox_mode']:
            request_url = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
        else:
            request_url = "https://payment.zarinpal.com/pg/v4/payment/request.json"
            
        response = requests.post(
            request_url,
            json=data,
            headers={'accept': 'application/json', 'content-type': 'application/json'}
        )
        
        result = response.json()
        
        if result['data']['code'] == 100:
            # ساخت لینک پرداخت بر اساس حالت sandbox
            if PAYMENT_CONFIG['sandbox_mode']:
                payment_url = f"https://sandbox.zarinpal.com/pg/StartPay/{result['data']['authority']}"
            else:
                payment_url = f"https://payment.zarinpal.com/pg/StartPay/{result['data']['authority']}"
                
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton("💳 پرداخت آنلاین", url=payment_url),
                types.InlineKeyboardButton("🔙 برگشت", callback_data="add_funds")
            )
            bot.reply_to(
                message,
                f"✅ لینک پرداخت {amount:,} تومان ایجاد شد.\n"
                "برای پرداخت روی دکمه زیر کلیک کنید:",
                reply_markup=keyboard
            )
        else:
            bot.reply_to(message, "❌ خطا در ایجاد لینک پرداخت. لطفاً مجدداً تلاش کنید.")
            
    except ValueError:
        bot.reply_to(message, "❌ لطفاً یک عدد معتبر وارد کنید.")

@app.route('/verify/<user_id>/<amount>')
def verify_payment(user_id, amount):
    try:
        logging.info(f"Payment verification started for user {user_id}, amount {amount}")
        authority = request.args.get('Authority')
        status = request.args.get('Status')
        
        if status != 'OK':
            return render_template('payment_result.html', success=False, message="پرداخت توسط کاربر لغو شد")
        
        # تایید پرداخت با زرین‌پال
        data = {
            "merchant_id": PAYMENT_CONFIG['zarinpal_merchant'],
            "amount": int(amount) * 10,  # تبدیل به ریال
            "authority": authority
        }
        
        verify_url = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json" if PAYMENT_CONFIG['sandbox_mode'] else "https://payment.zarinpal.com/pg/v4/payment/verify.json"
        
        response = requests.post(
            verify_url,
            json=data,
            headers={'accept': 'application/json', 'content-type': 'application/json'}
        )
        
        result = response.json()
        logging.info(f"Zarinpal verification response: {result}")
        
        if result['data']['code'] in [100, 101]:
            # افزایش موجودی کاربر
            new_balance = add_balance(int(user_id), int(amount))
            
            if new_balance is not None:
                # ثبت تراکنش
                conn = sqlite3.connect(DB_CONFIG['users_db'])
                cursor = conn.cursor()
                
                cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     amount INTEGER,
                     type TEXT,
                     description TEXT,
                     ref_id TEXT,
                     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
                
                cursor.execute('''
                    INSERT INTO transactions (user_id, amount, type, description, ref_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    int(user_id),
                    int(amount),
                    'deposit',
                    'شارژ حساب از طریق درگاه زرین‌پال',
                    result['data']['ref_id']
                ))
                
                conn.commit()
                conn.close()
                
                # ارسال پیام به کاربر
                success_message = f"""✅ پرداخت شما با موفقیت انجام شد

💰 مبلغ: {int(amount):,} تومان
🔢 کد پیگیری: {result['data']['ref_id']}
💎 موجودی فعلی: {new_balance:,} تومان"""

                try:
                    bot.send_message(int(user_id), success_message)
                except Exception as e:
                    logging.error(f"Error sending message to user: {e}")
                
                return render_template(
                    'payment_result.html',
                    success=True,
                    amount=f"{int(amount):,}",
                    ref_id=result['data']['ref_id'],
                    balance=f"{new_balance:,}"
                )
            else:
                logging.error("Failed to update balance")
                return render_template(
                    'payment_result.html',
                    success=False,
                    message="خطا در بروزرسانی موجودی"
                )
        else:
            return render_template(
                'payment_result.html',
                success=False,
                message=f"خطا در تایید پرداخت: {result['data'].get('message', 'خطای نامشخص')}"
            )
            
    except Exception as e:
        logging.error(f"Payment verification error: {e}", exc_info=True)
        return render_template(
            'payment_result.html',
            success=False,
            message="خطا در پردازش پرداخت"
        )

card_payment = CardPayment(bot)

@bot.callback_query_handler(func=lambda call: call.data == "card_payment")
def handle_card_payment(call):
    msg = bot.edit_message_text(
        "💳 لطفاً مبلغ مورد نظر را به تومان وارد کنید:\n"
        "مثال: 50000",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, card_payment.handle_new_payment)

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def handle_copy(call):
    text = call.data.split("_", 1)[1]
    bot.answer_callback_query(call.id, f"✅ کپی شد:\n{text}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("send_receipt_"))
def handle_send_receipt(call):
    payment_id = call.data.split("_")[2]
    msg = bot.edit_message_text(
        "🧾 لطفاً تصویر رسید پرداخت را ارسال کنید:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, card_payment.handle_receipt, payment_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_payment_", "reject_payment_")))
def handle_payment_verification(call):
    action, payment_id = call.data.split("_")[0], call.data.split("_")[2]
    card_payment.verify_payment(call, payment_id, action)

@bot.callback_query_handler(func=lambda call: call.data == "check_card_info")
def check_card_info(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
        return
        
    try:
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()
        cursor.execute('SELECT card_number, card_holder FROM card_info LIMIT 1')
        card_info = cursor.fetchone()
        conn.close()
        
        if card_info:
            bot.answer_callback_query(
                call.id,
                f"اطلاعات کارت:\n"
                f"شماره: {card_info[0]}\n"
                f"به نام: {card_info[1]}",
                show_alert=True
            )
        else:
            bot.answer_callback_query(call.id, "❌ اطلاعات کارتی ثبت نشده است", show_alert=True)
            
    except Exception as e:
        logging.error(f"Error checking card info: {e}")
        bot.answer_callback_query(call.id, "❌ خطا در بررسی اطلاعات کارت", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "new_card")
def handle_new_card(call):
    if call.from_user.id not in BOT_CONFIG['admin_ids']:
        bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
        return
        
    msg = bot.edit_message_text(
        "💳 لطفاً شماره کارت را وارد کنید:\n"
        "مثال: 6037-9974-1234-5678",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(msg, process_card_number)

def process_card_number(message):
    if message.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    # حذف خط تیره و فاصله از شماره کارت
    card_number = message.text.strip().replace('-', '').replace(' ', '')
    
    # بررسی صحت شماره کارت
    if not card_number.isdigit() or len(card_number) != 16:
        msg = bot.reply_to(
            message, 
            "❌ شماره کارت نامعتبر است. لطفاً یک شماره کارت 16 رقمی وارد کنید:\n"
            "مثال: 6037997412345678"
        )
        bot.register_next_step_handler(msg, process_card_number)
        return
        
    try:
        # ذخیره شماره کارت در دیتابیس
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()
        
        # پاک کردن اطلاعات قبلی
        cursor.execute('DELETE FROM card_info')
        
        # افزودن شماره کارت جدید
        cursor.execute('INSERT INTO card_info (card_number) VALUES (?)', (card_number,))
        conn.commit()
        conn.close()
        
        # درخواست نام صاحب کارت
        msg = bot.reply_to(
            message, 
            "✅ شماره کارت ذخیره شد.\n\n"
            "👤 لطفاً نام و نام خانوادگی صاحب کارت را وارد کنید:"
        )
        bot.register_next_step_handler(msg, process_card_holder)
        
    except Exception as e:
        logging.error(f"Error saving card number: {e}")
        bot.reply_to(message, "❌ خطا در ذخیره شماره کارت. لطفاً مجدداً تلاش کنید.")

def process_card_holder(message):
    if message.from_user.id not in BOT_CONFIG['admin_ids']:
        return
        
    card_holder = message.text.strip()
    
    if len(card_holder) < 3:
        msg = bot.reply_to(message, "❌ نام صاحب کارت نامعتبر است. لطفاً مجدداً وارد کنید:")
        bot.register_next_step_handler(msg, process_card_holder)
        return
        
    try:
        conn = sqlite3.connect(DB_CONFIG['admin_db'])
        cursor = conn.cursor()
        cursor.execute('UPDATE card_info SET card_holder = ? WHERE card_holder IS NULL', (card_holder,))
        conn.commit()
        
        # بررسی اطلاعات نهایی
        cursor.execute('SELECT card_number, card_holder FROM card_info LIMIT 1')
        card_info = cursor.fetchone()
        conn.close()
        
        if card_info:
            card_number, card_holder = card_info
            
            # نمایش اطلاعات ذخیره شده
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به پنل مدیریت", callback_data="admin_panel"))
            
            bot.reply_to(
                message,
                f"✅ اطلاعات کارت با موفقیت ذخیره شد:\n\n"
                f"💳 شماره کارت: <code>{card_number}</code>\n"
                f"👤 صاحب کارت: <code>{card_holder}</code>",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            bot.reply_to(message, "❌ خطا در ذخیره اطلاعات کارت. لطفاً مجدداً تلاش کنید.")
            
    except Exception as e:
        logging.error(f"Error saving card holder: {e}")
        bot.reply_to(message, "❌ خطا در ذخیره نام صاحب کارت. لطفاً مجدداً تلاش کنید.")

@app.route('/test_db_connection')
def test_db_connection():
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        return jsonify({'success': True, 'message': '✅ اتصال به دیتابیس موفق'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'❌ خطا در اتصال به دیتابیس: {str(e)}'})

@app.route('/test_create_user', methods=['POST'])
def test_create_user():
    try:
        data = request.get_json()
        user_id = int(data['user_id'])
        
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)', (user_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'✅ کاربر {user_id} با موفقیت ایجاد شد'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'❌ خطا در ایجاد کاربر: {str(e)}'})

@app.route('/test_add_balance', methods=['POST'])
def test_add_balance():
    try:
        data = request.get_json()
        user_id = int(data['user_id'])
        amount = int(data['amount'])
        
        new_balance = add_balance(user_id, amount)
        if new_balance is not None:
            return jsonify({
                'success': True,
                'message': f'✅ موجودی با موفقیت افزایش یافت\n💰 موجودی جدید: {new_balance:,} تومان'
            })
        else:
            return jsonify({'success': False, 'message': '❌ خطا در افزایش موجودی'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'❌ خطا: {str(e)}'})

@app.route('/test_transaction', methods=['POST'])
def test_transaction():
    try:
        data = request.get_json()
        user_id = int(data['user_id'])
        amount = int(data['amount'])
        
        # اول موجودی را افزایش می‌دهیم
        new_balance = add_balance(user_id, amount)
        if new_balance is None:
            return jsonify({
                'success': False,
                'message': '❌ خطا در افزایش موجودی'
            })

        # سپس تراکنش را ثبت می‌کنیم
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS transactions
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             amount INTEGER,
             type TEXT,
             description TEXT,
             ref_id TEXT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users(user_id))''')
        
        ref_id = f'TEST{int(time.time())}'
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description, ref_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, 'deposit', 'تراکنش تست', ref_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'✅ تراکنش با موفقیت ثبت شد\n'
                      f'💰 مبلغ: {amount:,} تومان\n'
                      f'💎 موجودی جدید: {new_balance:,} تومان'
        })
        
    except sqlite3.Error as e:
        logging.error(f"Database error in test_transaction: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ خطای دیتابیس: {str(e)}'
        })
    except Exception as e:
        logging.error(f"Error in test_transaction: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ خطا: {str(e)}'
        })

@app.route('/test_check_balance', methods=['POST'])
def test_check_balance():
    try:
        data = request.get_json()
        user_id = int(data['user_id'])
        balance = get_user_balance(user_id)
        
        return jsonify({
            'success': True,
            'message': f'💰 موجودی فعلی: {balance:,} تومان'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'❌ خطا: {str(e)}'})

@app.route('/test_payment')
def test_payment_page():
    return render_template('test_payment.html')

@app.route('/recreate_transactions_table')
def recreate_transactions_table():
    try:
        if setup_users_database():
            return jsonify({
                'success': True,
                'message': '✅ جدول تراکنش‌ها با موفقیت بازسازی شد'
            })
        else:
            return jsonify({
                'success': False,
                'message': '❌ خطا در بازسازی جدول تراکنش‌ها'
            })
    except Exception as e:
        logging.error(f"Error in recreate_transactions_table: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ خطا: {str(e)}'
        })

# ایجاد نمونه از BackupManager
backup_manager = BackupManager(backup_interval=5)

@app.route('/test_backup')
def test_backup_page():
    return render_template('test_backup.html')

@app.route('/create_backup')
def create_backup():
    try:
        if backup_manager.create_backup():
            return jsonify({
                'success': True,
                'message': '✅ پشتیبان با موفقیت ایجاد شد'
            })
        return jsonify({
            'success': False,
            'message': '❌ خطا در ایجاد پشتیبان'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ خطا: {str(e)}'
        })

@app.route('/restore_backup')
def restore_backup():
    try:
        if backup_manager.restore_backup():
            return jsonify({
                'success': True,
                'message': '✅ بازیابی پشتیبان با موفقیت انجام شد'
            })
        return jsonify({
            'success': False,
            'message': '❌ خطا در بازیابی پشتیبان'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ خطا: {str(e)}'
        })

@app.route('/backup_content')
def backup_content():
    try:
        with open('data/users_backup.json', 'r', encoding='utf-8') as f:
            content = json.load(f)
        return jsonify({
            'success': True,
            'content': content
        })
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': '❌ فایل پشتیبان یافت نشد'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'❌ خطا: {str(e)}'
        })

@app.route('/backup_status')
def backup_status():
    return jsonify({
        'success': True,
        'message': f'✅ سرویس پشتیبان‌گیری فعال است\n'
                  f'⏱ فاصله زمانی: {backup_manager.backup_interval} ثانیه'
    })

def initialize_bot():
    """تابع راه‌اندازی اولیه ربات"""
    try:
        # بازیابی موجودی کاربران از فایل پشتیبان
        if backup_manager.restore_backup():
            logging.info("✅ موجودی کاربران با موفقیت بازیابی شد")
        else:
            logging.warning("⚠️ فایل پشتیبان یافت نشد یا مشکلی در بازیابی وجود دارد")
        
        # شروع سرویس پشتیبان‌گیری خودکار
        backup_manager.start()
        logging.info("✅ سرویس پشتیبان‌گیری خودکار فعال شد")
        
        return True
    except Exception as e:
        logging.error(f"❌ خطا در راه‌اندازی اولیه ربات: {e}")
        return False

@app.route('/check_database')
def check_database():
    try:
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        
        # بررسی تعداد کاربران و مجموع موجودی
        cursor.execute('SELECT COUNT(*), SUM(balance) FROM users')
        users_count, total_balance = cursor.fetchone()
        
        # بررسی 5 کاربر اخیر - بدون استفاده از join_date
        cursor.execute('SELECT user_id, balance FROM users ORDER BY user_id DESC LIMIT 5')
        recent_users = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': users_count or 0,
                'total_balance': total_balance or 0,
                'recent_users': [
                    {'user_id': uid, 'balance': bal}
                    for uid, bal in recent_users
                ]
            }
        })
    except Exception as e:
        logging.error(f"Error in check_database: {e}")
        return jsonify({
            'success': False,
            'message': f'❌ خطا در بررسی دیتابیس: {str(e)}'
        })

@app.route('/test_purchase')
def test_purchase_page():
    return render_template('test_purchase.html')

@app.route('/test_get_services')
def test_get_services():
    try:
        # استفاده از تابع واقعی ربات
        services = get_available_services()
        
        if not services:
            return jsonify({
                'success': False,
                'message': 'هیچ سرویسی یافت نشد'
            })

        logging.info(f"Available services: {services}")
        
        return jsonify({
            'success': True,
            'services': services
        })
    except Exception as e:
        logging.error(f"Error in test_get_services: {e}")
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت سرویس‌ها: {str(e)}'
        })

@app.route('/test_get_countries/<service>')
def test_get_countries(service):
    try:
        # استفاده از تابع واقعی ربات
        countries = get_countries_for_service(service)
        
        if not countries:
            return jsonify({
                'success': False,
                'message': 'هیچ کشوری برای این سرویس یافت نشد'
            })

        logging.info(f"Available countries for {service}: {countries}")
        
        return jsonify({
            'success': True,
            'countries': countries
        })
    except Exception as e:
        logging.error(f"Error in test_get_countries: {e}")
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت لیست کشورها: {str(e)}'
        })

@app.route('/test_get_number', methods=['POST'])
def test_get_number():
    try:
        data = request.get_json()
        service = data['service']
        country = data['country']
        
        # استفاده از توابع واقعی ربات
        products = get_products(country)
        if not products:
            return jsonify({
                'success': False,
                'message': 'شماره‌ای برای این سرویس و کشور یافت نشد'
            })

        # دریافت قیمت
        price = get_prices(products[0])
        if not price:
            return jsonify({
                'success': False,
                'message': 'خطا در دریافت قیمت'
            })

        return jsonify({
            'success': True,
            'number': products[0],  # شماره موجود
            'price': price,
            'service': service,
            'country': country
        })
    except Exception as e:
        logging.error(f"Error in test_get_number: {e}")
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت شماره: {str(e)}'
        })

@app.route('/test_purchase_number', methods=['POST'])
def test_purchase_number():
    try:
        data = request.get_json()
        service = data['service']
        country = data['country']
        number = data['number']
        
        # بررسی موجودی کاربر (برای تست از یک کاربر ثابت استفاده می‌کنیم)
        test_user_id = 1457637832  # می‌توانید این را تغییر دهید
        user_balance = get_user_balance(test_user_id)
        price = get_prices(number)

        if user_balance < price:
            return jsonify({
                'success': False,
                'message': 'موجودی کافی نیست'
            })

        # انجام خرید با استفاده از API واقعی
        order_id = f'TEST{int(time.time())}'
        
        # کم کردن موجودی کاربر
        new_balance = add_balance(test_user_id, -price)
        if new_balance is None:
            return jsonify({
                'success': False,
                'message': 'خطا در بروزرسانی موجودی'
            })

        # ذخیره اطلاعات سفارش در دیتابیس
        conn = sqlite3.connect(DB_CONFIG['users_db'])
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO orders 
            (user_id, service, country, phone_number, price, status, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (test_user_id, service, country, number, price, 'active', order_id))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'order_id': order_id,
            'number': number,
            'price': price,
            'balance': new_balance
        })
        
    except Exception as e:
        logging.error(f"Error in test_purchase_number: {e}")
        return jsonify({
            'success': False,
            'message': f'خطا در خرید شماره: {str(e)}'
        })

# در ابتدای فایل bot.py
def create_required_tables():
    try:
        conn = sqlite3.connect('orders.db')
        cursor = conn.cursor()
        
        # بررسی ستون‌های موجود
        cursor.execute("PRAGMA table_info(orders)")
        columns = cursor.fetchall()
        existing_columns = [column[1] for column in columns]
        
        # اگر جدول وجود نداشت، آن را بساز
        if not existing_columns:
            cursor.execute('''
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    service TEXT NOT NULL,
                    country TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    price REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL
                )
            ''')
        else:
            # اضافه کردن ستون‌های جدید اگر وجود نداشتند
            if 'phone' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN phone TEXT')
            if 'status' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN status TEXT DEFAULT "PENDING"')
            if 'service' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN service TEXT')
            if 'country' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN country TEXT')
            if 'operator' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN operator TEXT')
            if 'created_at' not in existing_columns:
                cursor.execute('ALTER TABLE orders ADD COLUMN created_at TEXT')
        
        conn.commit()
        conn.close()
        logging.info("جداول با موفقیت بروزرسانی شدند")
        return True
        
    except Exception as e:
        logging.error(f"خطا در ایجاد جداول مورد نیاز: {str(e)}")
        return False

def save_order(order_data):
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # اطمینان از وجود جدول orders
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activation_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                country TEXT NOT NULL,
                operator TEXT NOT NULL,
                phone TEXT NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # اطمینان از وجود جدول activation_codes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activation_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        ''')
        
        # درج سفارش جدید
        cursor.execute('''
            INSERT INTO orders (
                user_id, activation_id, service, country, 
                operator, phone, price, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_data['user_id'],
            order_data['activation_id'],
            order_data['service'],
            order_data['country'],
            order_data['operator'],
            order_data['phone'],
            order_data['price'],
            order_data['status']
        ))
        
        # دریافت شناسه سفارش ذخیره شده
        order_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        logging.info(f"Order saved successfully: {order_data} with id {order_id}")
        return order_id
        
    except Exception as e:
        logging.error(f"خطا در ذخیره سفارش: {e}")
        if 'conn' in locals():
            conn.close()
        return None

@app.route('/price_calculator')
def price_calculator():
    try:
        # دریافت نرخ روبل و درصد سود از دیتابیس
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key='ruble_rate'")
        ruble_rate = cursor.fetchone()[0]
        
        cursor.execute("SELECT value FROM settings WHERE key='profit_percentage'")
        profit_percentage = cursor.fetchone()[0]
        
        conn.close()
        
        return render_template('price_calculator.html', 
                             ruble_rate=ruble_rate,
                             profit_percentage=profit_percentage)
    except Exception as e:
        logging.error(f"Error in price_calculator: {e}")
        return "خطا در بارگذاری صفحه"

@app.route('/update_ruble_rate')
def update_ruble_rate():
    try:
        api_key = 'free26Ln3Pt7qXlEydjJYJEKDcjEYKuS'  # API key ناواسان
        response = requests.get(f'https://api.navasan.tech/latest/?api_key={api_key}&item=rub')
        data = response.json()
        
        if data.get('rub'):
            new_rate = float(data['rub']['value'])
            
            # ذخیره نرخ جدید در دیتابیس
            conn = sqlite3.connect('bot.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE settings SET value = ? WHERE key = 'ruble_rate'", (str(new_rate),))
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'rate': new_rate,
                'date': data['rub']['date'],
                'change': data['rub']['change']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'نرخ روبل یافت نشد'
            })
            
    except Exception as e:
        logging.error(f"Error in update_ruble_rate: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/get_ruble_rate')
def get_ruble_rate():
    try:
        import requests
        
        api_key = 'free26Ln3Pt7qXlEydjJYJEKDcjEYKuS'
        response = requests.get(f'https://api.navasan.tech/latest/?api_key={api_key}&item=rub')
        data = response.json()
        
        if data.get('rub'):
            return jsonify({
                'success': True,
                'rate': float(data['rub']['value']),
                'date': data['rub']['date'],
                'change': data['rub']['change']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'نرخ روبل یافت نشد'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/get_settings')
def get_settings():
    try:
        conn = sqlite3.connect('admin.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM settings WHERE key = "current_rate"')
        rate_result = cursor.fetchone()
        current_rate = float(rate_result[0]) if rate_result else 1000
        
        cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
        profit_result = cursor.fetchone()
        profit_percentage = float(profit_result[0]) if profit_result else 20
        
        conn.close()
        
        return jsonify({
            'success': True,
            'current_rate': current_rate,
            'profit_percentage': profit_percentage
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/telegram_prices')
def telegram_prices():
    return render_template('telegram_prices.html')

@app.route('/api/get_telegram_price/<country>')
def get_telegram_price(country):
    try:
        headers = {
            'Accept': 'application/json',
        }
        
        params = (
            ('country', country),
            ('product', 'telegram'),
        )
        
        response = requests.get(
            'https://5sim.net/v1/guest/prices',
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if country in data and 'telegram' in data[country]:
                operators = data[country]['telegram']
                
                min_price = float('inf')
                available_count = 0
                
                for operator_data in operators.values():
                    if operator_data['count'] > 0 and operator_data['cost'] < min_price:
                        min_price = operator_data['cost']
                        available_count = operator_data['count']
                
                if min_price != float('inf'):
                    # دریافت نرخ روبل از دیتابیس admin.db
                    conn = sqlite3.connect('admin.db')
                    cursor = conn.cursor()
                    
                    # دریافت نرخ روبل
                    cursor.execute('SELECT value FROM settings WHERE key = "ruble_rate"')
                    ruble_rate_result = cursor.fetchone()
                    ruble_rate = float(ruble_rate_result[0]) if ruble_rate_result else 0
                    
                    # دریافت درصد سود
                    cursor.execute('SELECT value FROM settings WHERE key = "profit_percentage"')
                    profit_result = cursor.fetchone()
                    profit_percentage = float(profit_result[0]) if profit_result else 0
                    
                    conn.close()
                    
                    if ruble_rate == 0:
                        logging.error("نرخ روبل صفر است. لطفاً ابتدا نرخ روبل را تنظیم کنید.")
                        return jsonify({
                            'status': 'خطا',
                            'price_ruble': min_price,
                            'price_toman': 0,
                            'available_count': available_count,
                            'error': 'نرخ روبل تنظیم نشده است'
                        })
                    
                    # محاسبه قیمت نهایی
                    final_price_ruble = min_price
                    final_price_toman = round(min_price * ruble_rate * (1 + profit_percentage/100))
                    
                    logging.info(f"""
                    محاسبه قیمت برای {country}:
                    قیمت پایه (روبل): {min_price}
                    نرخ روبل: {ruble_rate}
                    درصد سود: {profit_percentage}%
                    قیمت نهایی (تومان): {final_price_toman}
                    تعداد موجود: {available_count}
                    """)
                    
                    return jsonify({
                        'status': 'موجود',
                        'price_ruble': final_price_ruble,
                        'price_toman': final_price_toman,
                        'available_count': available_count
                    })
                    
                # ... rest of the code remains the same ...
    except Exception as e:
        logging.error(f"Error in get_telegram_price: {e}")
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت قیمت برای {country}: {str(e)}'
        })

@app.route('/test_api_key')
def test_api_key():
    try:
        headers = {
            'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
            'Accept': 'application/json',
        }
        
        response = requests.get(f'{FIVESIM_CONFIG["api_url"]}/v1/guest/countries', headers=headers)
        
        if response.status_code == 200:
            return jsonify({
                'status': 'success',
                'message': 'کلید API معتبر است'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'خطا در اعتبارسنجی کلید API: {response.status_code}'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'خطا در تست کلید API: {str(e)}'
        })

# در بخش if __name__ == '__main__':
if __name__ == '__main__':
    try:
        # ایجاد جداول مورد نیاز
        if not create_required_tables():
            logging.error("❌ خطا در ایجاد جداول مورد نیاز")
            exit(1)
            
        # راه‌اندازی دیتابیس و بازیابی موجودی‌ها
        if not setup_database():
            logging.error("❌ خطا در راه‌اندازی دیتابیس")
            exit(1)
            
        # بازیابی اطلاعات از فایل پشتیبان
        backup_file = 'data/users_backup.json'
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
                
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            
            for user_id, balance in users_data.items():
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, balance)
                    VALUES (?, ?)
                ''', (int(user_id), balance))
            
            conn.commit()
            conn.close()
            logging.info(f"✅ موجودی {len(users_data)} کاربر از فایل پشتیبان بازیابی شد")
        
        # شروع سرویس پشتیبان‌گیری
        backup_manager = BackupManager(backup_interval=5)
        backup_manager.start()
        
        # راه‌اندازی ربات
        bot.remove_webhook()
        bot.set_webhook(url=BOT_CONFIG['webhook_url'])
        
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False
        )
        
    except Exception as e:
        logging.error(f"Error in main: {e}")
        exit(1)

@bot.callback_query_handler(func=lambda call: call.data == "no_operator")
def handle_no_operator(call):
    bot.answer_callback_query(call.id, "⚠️ این سرویس فعلاً موجود نیست")

# تابع کمکی برای فرمت کردن اعداد
@app.template_filter('format_number')
def format_number(value):
    return "{:,}".format(value)
