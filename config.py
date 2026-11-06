import os
from dotenv import load_dotenv

load_dotenv()


class Config:

    SECRET_KEY = os.getenv(
        "GNANI_API_KEY",
        "temporary-development-secret-key"
    )

    SQLALCHEMY_DATABASE_URI = "sqlite:///dukaansathi.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False