# تنظیمات اصلی ربات
BOT_CONFIG = {
    'token': '7728660088:AAHW7p6ebM1m9Xpi9vTgPQDBaSOgOFPhaPM',
    'admin_ids': [1457637832],  # آیدی عددی ادمین‌ها - عدد را جایگزین کردم
    'webhook_url': 'https://clever-bluejay-charmed.ngrok-free.app',  # آدرس ngrok را اینجا قرار دهید
    'website_url': 'https://clever-bluejay-charmed.ngrok-free.app'  # آدرس سایت شما
}

# تنظیمات 5sim
FIVESIM_CONFIG = {
    'api_key': 'eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NzQ0ODMyMjIsImlhdCI6MTc0Mjk0NzIyMiwicmF5IjoiMmRjMzBmY2M4YzVhMjA3MjVjNmVlNWU4NzI3MzMyOGYiLCJzdWIiOjI1NDcwNDl9.Sz_ce12BFv--6xYEo881udrXAmoyEjvafaKWN4mZqsyOlPARvCoGeSMiDReYNxj-zbx0hmuzurD55yX4V0UER38Vm5xNt4nCdcqX4QdiZD1GLW_MliFqAPY2leLosGohPvQrVBbuW9MWDrHuZPsd_gxF5Y-YuYTAHzOggQ82RufibXOgeRwpOZR4aoWeqMCDlnlfqYMQL6TWY5ttWFKDkq33_05g1ULKY3GPNcL6m2T4uJh7ebDYOcj2sGc9V28d3QdiWda7ow7jff1gEECdM87S5AZ6T6vklZQZlGEwoP2sc5gkhUgq-9ldTy74K-CFyxa0ZfJ05Va5yEd6Uf-Hhg',
    'api_url': 'https://5sim.net/v1'
}

# تنظیمات API نرخ ارز
CURRENCY_CONFIG = {
    'navasan_api_key': 'free26Ln3Pt7qXlEydjJYJEKDcjEYKuS'
}

# تنظیمات دیتابیس
DB_CONFIG = {
    'users_db': 'users.db',
    'admin_db': 'admin.db'
}

# اضافه کردن تنظیمات درگاه پرداخت
PAYMENT_CONFIG = {
    'zarinpal_merchant': '1344b5d4-0048-11e8-94db-005056a205be',  # مرچنت کد تست زرین‌پال
    'sandbox_mode': True,  # True برای تست، False برای حالت اصلی
    'callback_url': BOT_CONFIG['webhook_url'] + '/verify'  # آدرس برگشت از درگاه
} 