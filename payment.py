import requests
import logging
from config import PAYMENT_CONFIG

class ZarinPal:
    def __init__(self):
        self.merchant_id = PAYMENT_CONFIG['zarinpal_merchant']
        self.sandbox = PAYMENT_CONFIG['sandbox_mode']
        self.callback_url = PAYMENT_CONFIG['callback_url']
        
        if self.sandbox:
            self.request_url = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
            self.payment_url = "https://sandbox.zarinpal.com/pg/StartPay/"
            self.verify_url = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
        else:
            self.request_url = "https://payment.zarinpal.com/pg/v4/payment/request.json"
            self.payment_url = "https://payment.zarinpal.com/pg/StartPay/"
            self.verify_url = "https://payment.zarinpal.com/pg/v4/payment/verify.json"

    def create_payment(self, amount, user_id, description="افزایش موجودی کیف پول"):
        try:
            # ساختار درخواست طبق مستندات جدید
            data = {
                "merchant_id": self.merchant_id,
                "amount": amount * 10,  # تبدیل تومان به ریال
                "description": description,
                "callback_url": f"{self.callback_url}?user_id={user_id}&amount={amount}",
                "metadata": {
                    "mobile": "0",  # تغییر به یک رشته خالی یا "0"
                    "email": "none@mail.com",  # تغییر به یک ایمیل پیش‌فرض
                    "order_id": str(user_id)  # تبدیل به رشته
                }
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/json"
            }
            
            logging.info(f"Sending payment request to ZarinPal: {data}")
            logging.info(f"Request URL: {self.request_url}")
            
            response = requests.post(self.request_url, json=data, headers=headers)
            logging.info(f"ZarinPal Response Status: {response.status_code}")
            logging.info(f"ZarinPal Response Headers: {response.headers}")
            
            try:
                result = response.json()
                logging.info(f"ZarinPal payment request response: {result}")
            except ValueError as e:
                logging.error(f"Invalid JSON response: {response.text}")
                return False, None, None
            
            if result.get('data', {}).get('code') == 100:
                authority = result['data']['authority']
                payment_url = f"{self.payment_url}{authority}"
                logging.info(f"Payment URL created successfully: {payment_url}")
                return True, payment_url, authority
            
            error = result.get('errors')
            if error:
                error_msg = error.get('message', 'Unknown error')
                logging.error(f"Payment creation failed with error: {error_msg}")
            else:
                error_msg = result.get('data', {}).get('message', 'Unknown error')
                logging.error(f"Payment creation failed with message: {error_msg}")
            
            return False, None, None
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error in create_payment: {e}")
            return False, None, None
        except Exception as e:
            logging.error(f"Unexpected error in create_payment: {e}", exc_info=True)
            return False, None, None

    def verify_payment(self, authority, amount):
        try:
            data = {
                "merchant_id": self.merchant_id,
                "amount": amount * 10,  # تبدیل تومان به ریال
                "authority": authority
            }
            
            headers = {
                "accept": "application/json",
                "content-type": "application/json"
            }
            
            response = requests.post(self.verify_url, json=data, headers=headers)
            result = response.json()
            logging.info(f"ZarinPal verify response: {result}")
            
            if result.get('data', {}).get('code') in [100, 101]:  # 101 برای تراکنش‌های تکراری
                ref_id = result['data']['ref_id']
                card_pan = result['data'].get('card_pan', '')
                return True, ref_id, card_pan
            
            error = result.get('errors', {})
            if error:
                error_msg = error[0].get('message', 'Unknown error') if isinstance(error, list) else 'Unknown error'
            else:
                error_msg = result.get('data', {}).get('message', 'Payment verification failed')
            logging.error(f"Payment verification failed: {error_msg}")
            return False, None, None
                
        except Exception as e:
            logging.error(f"Error in verify_payment: {e}")
            return False, None, None 