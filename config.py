import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'indievault-chave-secreta')
    DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'indievault_db')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
    URL_IMPORTACAO_PADRAO = os.getenv(
        'DEFAULT_IMPORT_URL',
        'https://www.freetogame.com/api/games?platform=pc'
    )
