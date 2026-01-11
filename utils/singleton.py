from threading import Lock
from logging import Logger

from configs.config import EnvConfig


class SingletonMixin:
    _instances = {}
    _lock = Lock()

    def __init__(self, cfg: EnvConfig, logger: Logger):
        self.cfg = cfg
        self.logger = logger

    def __new__(cls, *args, **kwargs):
        # Double-checked locking to avoid races
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]
