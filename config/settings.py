import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# API Configuration
# Keep API key exactly as configured (already URL-encoded)
MOLIT_API_KEY = os.getenv("MOLIT_API_KEY", "")

# Target Regions (Seoul 7 Districts)
# LAWD_CD is the first 5 digits of the legal district code
TARGET_REGIONS = {
    "강남구": "11680",
    "서초구": "11650",
    "송파구": "11710",
    "용산구": "11170",
    "성동구": "11200",
    "동작구": "11590",
    "강동구": "11740",
}

# Filtering Criteria
FILTER_MIN_HOUSEHOLDS = 200
FILTER_MAX_AGE_YEARS = 20  # Built in last 20 years

# Email Settings
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # App password for Gmail
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "bbokigun@gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Paths
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "apartment_cache.db"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "report.log"
