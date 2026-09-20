# -*- coding: utf-8 -*-
import logging
import os

try:  # اختياري: يقرأ الإعدادات من ملف .env
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}
QUIZ_SIZE = int(os.environ.get("QUIZ_SIZE", "20"))  # أقصى عدد أسئلة (0 = الكل)

# قناة الاشتراك الإجباري (فاضي = بدون شرط)
CHANNEL = os.environ.get("CHANNEL", "@Arbic2027").strip()
CHANNEL_URL = f"https://t.me/{CHANNEL.lstrip('@')}"

# التواصل وخدمة التقارير
OWNER_TG = os.environ.get("OWNER_TG", "AMMAR_KHALI_D").lstrip("@")
OWNER_WA = os.environ.get("OWNER_WA", "9647764907555")
OWNER_WA_LOCAL = os.environ.get("OWNER_WA_LOCAL", "07764907555")
REPORT_PRICE = os.environ.get(
    "REPORT_PRICE", "أسعار رمزية، نتفق عليها حسب عدد الصفحات وموعد التسليم"
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # عشان ما يطبع التوكن باللوق
logger = logging.getLogger("bot")
