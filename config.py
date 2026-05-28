import os
from dotenv import load_dotenv

# Cargar variables del archivo .env automáticamente
load_dotenv()

class Config:
    SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-key")
    DATABASE_URL = os.environ.get("DATABASE_URL")

    MAIL_SERVER         = "smtp.gmail.com"
    MAIL_PORT           = 465
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME", "ww.sco.lol@gmail.com")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD", "hgzm kujp blfu sczr")
    MAIL_DEFAULT_SENDER = MAIL_USERNAME