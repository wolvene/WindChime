"""日志配置：文件日志 + 可选控制台输出。"""

import logging
import os
from logging.handlers import WatchedFileHandler


def setup_logger(log_file, debug=False, verbose=False):
    """创建（或重建）WindChime 日志器。"""
    logger = logging.getLogger("WindChime")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    # 重复调用时先清理旧 handler，避免日志重复输出。
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    log_dir = os.path.dirname(os.path.abspath(log_file))
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")

    file_handler = WatchedFileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
