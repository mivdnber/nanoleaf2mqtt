from nanoleaf2mqtt.config import LOG_LEVEL
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "nanoleaf2mqtt",
            "stream": "ext://sys.stderr",
            "level": LOG_LEVEL,
        }
    },
    "formatters": {
        "nanoleaf2mqtt": {
            "format": "[%(asctime)s] %(levelname)s %(name)s - %(message)s",
            # "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "loggers": {
        "httpx": {
            "handlers": ["default"],
            "level": "CRITICAL",
        },
        "httpcore": {
            "handlers": ["default"],
            "level": "CRITICAL",
        },
    },
    "root": {
        "handlers": ["default"],
        "level": LOG_LEVEL,
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
