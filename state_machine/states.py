
from enum import Enum, auto


class ProtocolState(Enum):
    """
    MySQL 数据包接收状态。
    """

    LEN = auto()

    MORE_LENGTH = auto()

    DATA = auto()

    CLOSED = auto()


class SessionState(Enum):
    """
    MySQL 会话状态。
    """

    INIT = auto()

    AUTH = auto()

    READY = auto()

    CLOSED = auto()


class OperationState(Enum):
    """
    当前操作状态。
    """

    IDLE = auto()

    PROCESSING = auto()

    COMPLETED = auto()

    FAILED = auto()
