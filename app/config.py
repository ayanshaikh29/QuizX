"""
Application Configuration
Handles environment-specific settings
Industry-safe version (no class-load crashes)
"""

import os


class Config:
    """Base configuration"""

    # ================= SECURITY =================
    SECRET_KEY = os.getenv("SECRET_KEY", "quizx_secret_key_change_later")

    # ================= DATABASE =================
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:12345678@localhost:5432/quizx"
    )

    # Fix Render / Heroku old postgres:// url
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 20)),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 1800)),
        "pool_pre_ping": True,
    }

    # ================= SESSION =================
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE", "False"
    ).lower() == "true"

    # ================= SOCKET.IO =================
    SOCKETIO_ASYNC_MODE = "threading"
    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"

    # ================= APP =================
    TIMEZONE = "Asia/Kolkata"


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # ❗ SECRET_KEY validation is done at runtime (not here)


# ================= CONFIG MAP =================
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Return config class based on FLASK_ENV"""
    env = os.getenv("FLASK_ENV", "development").lower()
    return config.get(env, config["default"])
