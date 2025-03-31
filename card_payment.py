from telebot import types
import sqlite3
import logging
import time
from config import BOT_CONFIG, DB_CONFIG
from database import add_balance, save_transaction

class CardPayment:
    def __init__(self, bot):
        self.bot = bot
        self.setup_database()

    def setup_database(self):
        try:
            # ایجاد جدول پرداخت‌های کارت به کارت
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS card_payments
                (payment_id TEXT PRIMARY KEY,
                 user_id INTEGER,
                 amount INTEGER,
                 status TEXT DEFAULT 'pending',
                 receipt TEXT,
                 admin_response TEXT,
                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in setup_database: {e}")

    def get_card_info(self):
        try:
            conn = sqlite3.connect(DB_CONFIG['admin_db'])
            cursor = conn.cursor()
            cursor.execute('SELECT card_number, card_holder FROM card_info LIMIT 1')
            card_info = cursor.fetchone()
            conn.close()
            return card_info
        except Exception as e:
            logging.error(f"Error getting card info: {e}")
            return None

    def save_payment_request(self, user_id, amount):
        try:
            payment_id = f"CP{int(time.time())}{user_id}"
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO card_payments (payment_id, user_id, amount) VALUES (?, ?, ?)',
                (payment_id, user_id, amount)
            )
            conn.commit()
            conn.close()
            return payment_id
        except Exception as e:
            logging.error(f"Error saving payment request: {e}")
            return None

    def handle_new_payment(self, message):
        try:
            amount = int(message.text.strip())
            if amount < 5000:
                self.bot.reply_to(message, "❌ حداقل مبلغ شارژ 5,000 تومان می‌باشد.")
                return

            card_info = self.get_card_info()
            if not card_info:
                self.bot.reply_to(message, "❌ اطلاعات کارت بانکی تنظیم نشده است.")
                return

            card_number, card_holder = card_info
            payment_id = self.save_payment_request(message.from_user.id, amount)

            if not payment_id:
                self.bot.reply_to(message, "❌ خطا در ثبت درخواست پرداخت.")
                return

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(f"💳 شماره کارت: {card_number}", callback_data=f"copy_{card_number}"),
                types.InlineKeyboardButton(f"👤 به نام: {card_holder}", callback_data=f"copy_{card_holder}"),
                types.InlineKeyboardButton("✅ ارسال رسید پرداخت", callback_data=f"send_receipt_{payment_id}"),
                types.InlineKeyboardButton("🔙 برگشت", callback_data="add_funds")
            )

            self.bot.reply_to(
                message,
                f"💳 اطلاعات واریز:\n\n"
                f"💰 مبلغ: {amount:,} تومان\n"
                f"🔢 شماره کارت: <code>{card_number}</code>\n"
                f"👤 به نام: <code>{card_holder}</code>\n\n"
                f"⚠️ لطفاً پس از واریز، رسید پرداخت را با دکمه زیر ارسال کنید.",
                reply_markup=keyboard,
                parse_mode='HTML'
            )

        except ValueError:
            self.bot.reply_to(message, "❌ لطفاً یک عدد معتبر وارد کنید.")
        except Exception as e:
            logging.error(f"Error in handle_new_payment: {e}")
            self.bot.reply_to(message, "❌ خطایی رخ داد. لطفاً مجدداً تلاش کنید.")

    def handle_receipt(self, message, payment_id):
        if not message.photo:
            msg = self.bot.reply_to(message, "❌ لطفاً تصویر رسید را ارسال کنید:")
            self.bot.register_next_step_handler(msg, self.handle_receipt, payment_id)
            return

        try:
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            cursor.execute('UPDATE card_payments SET receipt = ? WHERE payment_id = ?',
                         (message.photo[-1].file_id, payment_id))
            cursor.execute('SELECT amount FROM card_payments WHERE payment_id = ?', (payment_id,))
            amount = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            # ارسال به ادمین‌ها
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_payment_{payment_id}"),
                types.InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")
            )

            for admin_id in BOT_CONFIG['admin_ids']:
                self.bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    f"💳 درخواست شارژ جدید\n\n"
                    f"🔢 شناسه پرداخت: {payment_id}\n"
                    f"👤 کاربر: {message.from_user.id}\n"
                    f"💰 مبلغ: {amount:,} تومان",
                    reply_markup=keyboard
                )

            # حذف پیام‌های قبلی
            try:
                for i in range(10):  # حذف 10 پیام آخر
                    self.bot.delete_message(message.chat.id, message.message_id - i)
            except:
                pass

            # ارسال پیام جدید با دکمه برگشت
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به منوی اصلی", callback_data="back_to_main"))
            
            self.bot.send_message(
                message.chat.id,
                "✅ رسید شما با موفقیت ارسال شد.\nلطفاً منتظر تایید مدیریت باشید.",
                reply_markup=keyboard
            )

        except Exception as e:
            logging.error(f"Error handling receipt: {e}")
            self.bot.reply_to(message, "❌ خطا در ارسال رسید. لطفاً مجدداً تلاش کنید.")

    def verify_payment(self, call, payment_id, action):
        if call.from_user.id not in BOT_CONFIG['admin_ids']:
            self.bot.answer_callback_query(call.id, "⛔️ شما دسترسی ادمین ندارید")
            return

        try:
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, amount, status FROM card_payments WHERE payment_id = ?', (payment_id,))
            payment = cursor.fetchone()

            if not payment:
                self.bot.answer_callback_query(call.id, "❌ پرداخت مورد نظر یافت نشد")
                return

            user_id, amount, status = payment

            if status != 'pending':
                self.bot.answer_callback_query(call.id, "❌ این پرداخت قبلاً بررسی شده است")
                return

            if action == "reject":
                msg = self.bot.edit_message_caption(
                    "❌ لطفاً دلیل رد پرداخت را وارد کنید:",
                    call.message.chat.id,
                    call.message.message_id
                )
                self.bot.register_next_step_handler(msg, self.process_rejection, payment_id)
                return

            # افزایش موجودی کاربر
            new_balance = add_balance(user_id, amount)
            if new_balance is not None:
                # ثبت تراکنش
                save_transaction(
                    user_id=user_id,
                    amount=amount,
                    type_trans='deposit',
                    description='شارژ حساب از طریق کارت به کارت',
                    ref_id=payment_id
                )
                cursor.execute('''
                    UPDATE card_payments 
                    SET status = 'approved', 
                        admin_response = ? 
                    WHERE payment_id = ?
                ''', (f"تایید شده توسط {call.from_user.id}", payment_id))
                conn.commit()

                # ارسال پیام به کاربر
                keyboard = types.InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    types.InlineKeyboardButton("🛍 شروع خرید", callback_data="buy_number"),
                    types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
                )
                
                self.bot.send_message(
                    user_id,
                    f"""✅ پرداخت شما تایید شد

💰 مبلغ: {amount:,} تومان
🔢 شناسه پرداخت: {payment_id}
💎 موجودی فعلی: {new_balance:,} تومان""",
                    reply_markup=keyboard
                )

                # آپدیت پیام ادمین
                self.bot.edit_message_caption(
                    f"✅ پرداخت تایید شد\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"👤 کاربر: {user_id}\n"
                    f"💎 موجودی جدید: {new_balance:,} تومان",
                    call.message.chat.id,
                    call.message.message_id
                )

                self.bot.answer_callback_query(call.id, "✅ پرداخت با موفقیت تایید شد")
            else:
                raise Exception("Failed to update balance")

        except Exception as e:
            logging.error(f"Error in verify_payment: {e}")
            self.bot.answer_callback_query(call.id, "❌ خطا در تایید پرداخت")
        finally:
            if 'conn' in locals():
                conn.close()

    def process_rejection(self, message, payment_id):
        if message.from_user.id not in BOT_CONFIG['admin_ids']:
            return

        try:
            reason = message.text.strip()
            conn = sqlite3.connect(DB_CONFIG['users_db'])
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE card_payments 
                SET status = 'rejected', 
                    admin_response = ? 
                WHERE payment_id = ?
            ''', (reason, payment_id))
            
            cursor.execute('SELECT user_id, amount FROM card_payments WHERE payment_id = ?', (payment_id,))
            payment = cursor.fetchone()
            conn.commit()
            conn.close()

            if payment:
                user_id, amount = payment
                self.bot.send_message(
                    user_id,
                    f"❌ پرداخت شما رد شد\n\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"🔢 شناسه پرداخت: {payment_id}\n"
                    f"📝 دلیل: {reason}"
                )

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 برگشت به منوی اصلی", callback_data="back_to_main"))
            
            self.bot.reply_to(
                message,
                "✅ پاسخ شما ارسال شد.",
                reply_markup=keyboard
            )

        except Exception as e:
            logging.error(f"Error in process_rejection: {e}")
            self.bot.reply_to(message, "❌ خطا در ثبت پاسخ") 