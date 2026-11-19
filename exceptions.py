class WindChimeError(Exception):
    """WindChimeSQL 基础异常类。"""
    pass


class ProtocolError(WindChimeError):
    """MySQL 协议解析异常。"""
    pass


class InvalidPacketError(ProtocolError):
    """无效数据包异常。"""
    pass


class PacketOrderError(ProtocolError):
    """数据包顺序异常。"""
    pass


class ConfigurationError(WindChimeError):
    """配置错误。"""
    pass


class FileManagerError(WindChimeError):
    """文件任务管理异常。"""
    pass


class TaskError(FileManagerError):
    """文件任务执行异常。"""
    pass
