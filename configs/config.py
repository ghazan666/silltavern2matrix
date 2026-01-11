import os
import logging
from dataclasses import dataclass, field
from typing import Dict
from urllib.parse import urlparse
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rss_forwarder")


@dataclass
class EnvConfig:
    mx_homeserver: str
    mx_user_id: str
    mx_password: str
    mx_device_id: str
    mx_owner_id: str
    mx_store_path: str = "./matrix_store"
    mx_encryption_enabled: bool = False
    wss_port: int = 8080

    @staticmethod
    def load_logger() -> logging.Logger:
        return logger

    @staticmethod
    def load_config() -> "EnvConfig":
        load_dotenv()
        mx_homeserver = os.getenv("MATRIX_HOMESERVER")
        mx_user_id = os.getenv("MATRIX_USER_ID")
        mx_device_id = os.getenv("MATRIX_DEVICE_ID")
        mx_password = os.getenv("MATRIX_PASSWORD")
        mx_owner_id = os.getenv("MATRIX_OWNER_ID")
        mx_store_path = os.getenv("MATRIX_STORE_PATH", "./matrix_store")
        encryption_enabled = os.getenv("MATRIX_ENCRYPTION_ENABLED", "false").lower() == "true"
        wss_port = int(os.getenv("WSS_PORT", 8080))

        required = {
            "MATRIX_HOMESERVER": mx_homeserver,
            "MATRIX_USER_ID": mx_user_id,
            "MATRIX_DEVICE_ID": mx_device_id,
            "MATRIX_PASSWORD": mx_password,
            "MATRIX_OWNER_ID": mx_owner_id,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
        if mx_store_path and not os.path.isdir(mx_store_path):
            os.mkdir(mx_store_path)

        return EnvConfig(
            mx_homeserver=mx_homeserver,
            mx_user_id=mx_user_id,
            mx_device_id=mx_device_id,
            mx_password=mx_password,
            mx_owner_id=mx_owner_id,
            mx_store_path=mx_store_path,
            mx_encryption_enabled=encryption_enabled,
            wss_port=wss_port,
        )
