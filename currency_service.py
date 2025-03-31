import requests
import json
from datetime import datetime, timedelta
import logging
from config import CURRENCY_CONFIG

class CurrencyService:
    def __init__(self):
        self._cache = {}
        self._cache_time = None
        self._cache_duration = timedelta(minutes=5)  # بروزرسانی هر 5 دقیقه
    
    def get_ruble_rate(self):
        """دریافت نرخ روبل به تومان از Navasan.tech"""
        try:
            # بررسی اعتبار کش
            if self._cache_time and datetime.now() - self._cache_time < self._cache_duration:
                return self._cache.get('RUB_IRR')
            
            # دریافت نرخ از API نوسان
            response = requests.get(
                f"https://api.navasan.tech/latest/",
                params={
                    'api_key': CURRENCY_CONFIG['navasan_api_key'],
                    'item': 'rub'
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('rub'):
                ruble_rate = float(data['rub']['value'])
                
                # ذخیره در کش
                self._cache['RUB_IRR'] = ruble_rate
                self._cache_time = datetime.now()
                
                logging.info(f"نرخ جدید روبل به تومان از Navasan: {ruble_rate}")
                return ruble_rate
            
            logging.error("خطا در دریافت نرخ روبل از Navasan")
            return None
            
        except Exception as e:
            logging.error(f"خطا در دریافت نرخ ارز از Navasan: {e}")
            return None
    
    def _get_usd_to_irr_rate(self):
        """دریافت نرخ دلار به تومان"""
        try:
            # اینجا می‌توانید از API‌های مختلف استفاده کنید
            # مثال: bonbast.com یا tgju.org
            # فعلا یک مقدار ثابت برمی‌گردانیم
            return 52000  # نرخ فرضی دلار
        except Exception as e:
            logging.error(f"خطا در دریافت نرخ دلار: {e}")
            return 52000  # نرخ پیش‌فرض 