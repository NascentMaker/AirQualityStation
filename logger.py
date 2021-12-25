import adafruit_logging as logging

loggers = {}


def get_logger(name: str) -> logging.Logger:
    """
    Return an instance of the named logger.

    Args:
        name: unique name for this logger
    """
    if name not in loggers.keys():
        loggers[name] = logging.getLogger(name)
    return loggers[name]
