import logging
import os

# Safe default before init() — WindowSettings / mixins import this early.
logger = logging.getLogger("exhibit")


class CustomFormatter(logging.Formatter):
    log_end = ": %(message)s"
    log_start = "%(asctime)s (%(filename)s:%(lineno)d) "
    level_name = "\x1b[31;20m%(levelname)s\x1b[0m"
    time_format = "%H:%M:%S"

    FORMATS = {
        logging.DEBUG: log_start + "\x1b[34;1m%(levelname)s\x1b[0m" + log_end,
        logging.INFO: log_start + "\x1b[32;1m%(levelname)s\x1b[0m" + log_end,
        logging.WARNING: log_start + "\x1b[33;1m%(levelname)s\x1b[0m" + log_end,
        logging.ERROR: log_start + "\x1b[31;1m%(levelname)s\x1b[0m" + log_end,
        logging.CRITICAL: log_start + "\x1b[31;1m%(levelname)s\x1b[0m" + log_end,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, self.time_format)
        return formatter.format(record)


def init():
    global logger
    # When XDG_DATA_HOME is set (Flatpak: ~/.var/app/<id>/data) it already is
    # the app data root. Otherwise use ~/.local/share/exhibit.
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share", "exhibit"
    )
    os.makedirs(data_home, exist_ok=True)
    log_path = os.path.join(data_home, "log.txt")

    if os.path.exists(log_path):
        os.remove(log_path)

    logging.basicConfig(
        filename=log_path,
        filemode="a",
        format=f"%(asctime)s (%(filename)s:%(lineno)d) %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    ch = logging.StreamHandler()
    # Console: INFO by default; EXHIBIT_DEBUG=1 keeps DEBUG spam for agents.
    console_level = (
        logging.DEBUG if os.environ.get("EXHIBIT_DEBUG") else logging.INFO
    )
    ch.setLevel(console_level)

    ch.setFormatter(CustomFormatter())

    logger = logging.getLogger("exhibit")
    logger.setLevel(logging.DEBUG)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(ch)
