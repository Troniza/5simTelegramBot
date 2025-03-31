from flask import Blueprint, render_template, request, jsonify
import sqlite3
import logging
import sys
import os
import requests
import datetime

# اضافه کردن مسیر ریشه پروژه به sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_utils import send_message_to_bot
from config import FIVESIM_CONFIG

# حذف import مستقیم از bot.py
# from bot import refund_order_amount

order_details_bp = Blueprint('order_details_bp', __name__)

# تعریف فیلتر برای فرمت کردن اعداد
@order_details_bp.app_template_filter('format_number')
def format_number(value):
    return "{:,}".format(value)

@order_details_bp.route('/number_details/<order_id>')
def number_details(order_id):
    """
    نمایش جزئیات یک سفارش شماره تلفن بر اساس شناسه سفارش
    """
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # دریافت اطلاعات سفارش
        cursor.execute("""
            SELECT id, phone, service, country, operator,
                   price, status, created_at, user_id, activation_id
            FROM orders
            WHERE id = ?
        """, (order_id,))
        
        order = cursor.fetchone()
        
        if not order:
            logging.error(f"سفارش با شناسه {order_id} یافت نشد")
            return render_template('order_status.html', 
                                   status_type="error",
                                   title="سفارش یافت نشد",
                                   message="سفارش مورد نظر در سیستم یافت نشد.",
                                   user_id=None)
            
        # تبدیل به دیکشنری برای نمایش
        order_data = {
            'id': order[0],
            'phone_number': order[1],
            'service': order[2],
            'country': order[3],
            'operator': order[4],
            'price': order[5],
            'status': order[6],
            'date': order[7],
            'user_id': order[8],
            'activation_id': order[9],
            'codes': []
        }
        
        # بررسی کدهای فعال‌سازی دریافت شده
        has_codes = False
        
        # دریافت کدهای فعال‌سازی
        try:
            cursor.execute("""
                SELECT code, created_at
                FROM activation_codes
                WHERE order_id = ?
                ORDER BY created_at DESC
            """, (order_id,))
            
            codes = cursor.fetchall()
            if codes:
                has_codes = True
                order_data['codes'] = [{'code': code[0], 'time': code[1]} for code in codes]
            
        except sqlite3.OperationalError as e:
            # اگر جدول activation_codes وجود نداشت یا مشکلی داشت، ادامه می‌دهیم
            if "no such table" in str(e):
                logging.warning(f"جدول activation_codes یافت نشد: {e}")
            else:
                logging.error(f"خطا در دریافت کدهای فعال‌سازی: {e}")
        
        # بررسی وضعیت سفارش برای تصمیم‌گیری در مورد نحوه نمایش
        status = order_data['status'].lower()
        
        # بررسی زمان گذشته از ایجاد سفارش
        created_time = datetime.datetime.strptime(order_data['date'], '%Y-%m-%d %H:%M:%S')
        current_time = datetime.datetime.now()
        time_diff = current_time - created_time
        
        # آیا بیشتر از 20 دقیقه از زمان ایجاد سفارش گذشته است؟
        time_expired = time_diff > datetime.timedelta(minutes=20)
        
        conn.close()
        
        # تصمیم‌گیری در مورد نحوه نمایش
        if status == 'canceled' or status.upper() == 'CANCELED':
            # سفارش لغو شده است
            return render_template('order_status.html', 
                                   status_type="canceled",
                                   title="سفارش لغو شده",
                                   message="این سفارش قبلاً لغو شده است و دیگر قابل استفاده نیست.",
                                   user_id=order_data['user_id'])
                                   
        elif has_codes:
            # کد فعال‌سازی دریافت شده است
            code_value = order_data['codes'][0]['code']
            return render_template('order_status.html', 
                                   status_type="success",
                                   title="کد فعال‌سازی دریافت شد",
                                   message=f"کد فعال‌سازی برای این شماره دریافت شده است: <div class='code-value'>{code_value}</div>",
                                   user_id=order_data['user_id'])
                                   
        elif time_expired and status.lower() == 'pending':
            # زمان منقضی شده و هنوز در حالت انتظار است
            return render_template('order_status.html', 
                                   status_type="expired",
                                   title="زمان سفارش منقضی شده",
                                   message="زمان این سفارش به پایان رسیده است و دیگر فعال نیست.",
                                   user_id=order_data['user_id'])
        
        # در غیر این صورت، صفحه عادی جزئیات شماره را نمایش می‌دهیم
        return render_template('number_details.html', order=order_data)
        
    except Exception as e:
        logging.error(f"خطا در number_details: {str(e)}")
        return render_template('order_status.html', 
                               status_type="error",
                               title="خطا در سیستم",
                               message=f"خطا در دریافت اطلاعات سفارش: {str(e)}",
                               user_id=None)
        
@order_details_bp.route('/orders/<user_id>')
def user_orders(user_id):
    """
    نمایش لیست سفارش‌های یک کاربر بر اساس شناسه کاربر
    """
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # دریافت اطلاعات سفارش‌های کاربر
        cursor.execute("""
            SELECT id, phone, service, country, operator,
                   price, status, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        
        orders = cursor.fetchall()
        
        # تبدیل به لیست دیکشنری برای نمایش
        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order[0],
                'phone_number': order[1],
                'service': order[2],
                'country': order[3],
                'operator': order[4],
                'price': order[5],
                'status': order[6],
                'date': order[7]
            })
        
        conn.close()
        return render_template('user_orders.html', orders=orders_data, user_id=user_id)
        
    except Exception as e:
        logging.error(f"خطا در user_orders: {str(e)}")
        return f"خطا در دریافت اطلاعات سفارش‌های کاربر: {str(e)}", 500

@order_details_bp.route('/check_code/<order_id>', methods=['GET'])
def check_code(order_id):
    """
    بررسی آیا کد فعال‌سازی برای سفارش دریافت شده است
    """
    try:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        
        # دریافت کدهای فعال‌سازی برای سفارش
        cursor.execute("""
            SELECT code, created_at
            FROM activation_codes
            WHERE order_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (order_id,))
        
        code = cursor.fetchone()
        conn.close()
        
        if code:
            return jsonify({
                'code_received': True,
                'code': code[0],
                'time': code[1]
            })
        else:
            return jsonify({
                'code_received': False
            })
            
    except Exception as e:
        logging.error(f"خطا در check_code: {str(e)}")
        return jsonify({
            'code_received': False,
            'error': str(e)
        }), 500

@order_details_bp.route('/cancel_order/<order_id>')
def cancel_order(order_id):
    conn = None
    try:
        # import تابع refund_order_amount اینجا در داخل تابع انجام می‌شود (lazy import)
        from bot import refund_order_amount
        
        # دریافت اطلاعات سفارش
        conn = sqlite3.connect('bot.db', timeout=20)  # افزایش تایم‌اوت برای قفل پایگاه داده
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, price, status, activation_id FROM orders WHERE id = ?
        ''', (order_id,))
        
        order_info = cursor.fetchone()
        
        if not order_info:
            if conn:
                conn.close()
            return jsonify({'success': False, 'message': 'سفارش یافت نشد'})
            
        user_id, price, status, activation_id = order_info
        
        # اگر سفارش قبلاً لغو شده باشد
        if status == 'canceled' or status.upper() == 'CANCELED':
            if conn:
                conn.close()
            return jsonify({'success': False, 'message': 'این سفارش قبلاً لغو شده است'})
        
        # ارسال درخواست لغو به 5sim API
        try:
            # دریافت کلید API از تنظیمات
            headers = {
                'Authorization': f'Bearer {FIVESIM_CONFIG["api_key"]}',
                'Accept': 'application/json',
            }
            
            # درخواست لغو سفارش به API
            api_response = requests.get(
                f'https://5sim.net/v1/user/cancel/{activation_id}',
                headers=headers,
                timeout=30
            )
            
            if api_response.status_code != 200:
                logging.error(f"خطا در لغو سفارش در 5sim API: {api_response.text}")
                return jsonify({
                    'success': False, 
                    'message': f'خطا در لغو سفارش در 5sim: {api_response.text}'
                })
                
        except Exception as e:
            logging.error(f"خطا در ارتباط با 5sim API: {str(e)}")
            return jsonify({
                'success': False, 
                'message': f'خطا در ارتباط با 5sim: {str(e)}'
            })
        
        # استفاده از refund_order_amount برای برگشت مبلغ به کاربر
        success, result = refund_order_amount(activation_id)
        
        if not success:
            return jsonify({
                'success': False,
                'message': f'خطا در برگشت مبلغ: {result}'
            })
            
        # ارسال پیام به کاربر از طریق ربات تلگرام
        try:
            # تعیین متن پیام با توجه به نتیجه
            if isinstance(result, dict):
                # فرمت جدید - دیکشنری با refund_amount و new_balance
                refund_amount = result['refund_amount']
                new_balance = result['new_balance']
                
                message = f"""✅ سفارش #{order_id} با موفقیت لغو شد
                
💰 موجودی فعلی شما: {new_balance:,} تومان

💰 مبلغ برگشتی به کیف پول شما: {refund_amount:,} تومان"""
            else:
                # فرمت قدیمی - فقط مبلغ برگشتی
                message = f"""✅ سفارش #{order_id} با موفقیت لغو شد

💰 مبلغ {result:,} تومان به کیف پول شما بازگشت داده شد."""
            
            send_message_to_bot(user_id, message)
        except Exception as e:
            logging.warning(f"خطا در ارسال پیام لغو سفارش به کاربر: {str(e)}")
            # این خطا نباید مانع از انجام عملیات لغو شود
        
        if conn:
            conn.close()
        return jsonify({'success': True})
        
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            logging.error(f"پایگاه داده قفل شده است: {str(e)}")
            # اینجا می‌توانیم یک مکانیزم retry اضافه کنیم
            return jsonify({'success': False, 'message': 'سیستم در حال پردازش اطلاعات است. لطفاً کمی بعد دوباره تلاش کنید.'})
        else:
            logging.error(f"خطای پایگاه داده در لغو سفارش: {str(e)}")
            return jsonify({'success': False, 'message': f'خطا در لغو سفارش: {str(e)}'})
    except Exception as e:
        logging.error(f"خطا در لغو سفارش: {str(e)}")
        return jsonify({'success': False, 'message': f'خطا در لغو سفارش: {str(e)}'})
    finally:
        # اطمینان حاصل کنیم که اتصال پایگاه داده بسته شود
        if conn:
            try:
                conn.close()
            except Exception as e:
                logging.error(f"خطا در بستن اتصال پایگاه داده: {str(e)}") 