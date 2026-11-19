"""MySQL 协议数据包的封装与解析。

MySQL 报文格式（Protocol::Packet）：
    [3 bytes] payload 长度（小端）
    [1 byte ] 报文序号
    [n bytes] payload

单个报文的 payload 最大为 0xFFFFFF（16MB-1），超过时客户端会拆分为
多个报文，而不是扩展头部长度。
"""

from __future__ import annotations

import asyncio

from exceptions import InvalidPacketError

HEADER_LEN = 4
MAX_PAYLOAD_LENGTH = 0xFFFFFF


class MySQLPacket:
    """一个 MySQL 协议报文。"""

    __slots__ = ("packet_num", "payload")

    def __init__(self, packet_num: int | "MySQLPacket", payload):
        # 传入上一个报文时，自动递增序号（与原始 RogueSQL 行为一致）
        if isinstance(packet_num, MySQLPacket):
            packet_num = packet_num.packet_num + 1

        self.packet_num = int(packet_num) & 0xFF

        if payload is None:
            self.payload = b""
        elif isinstance(payload, str):
            # 协议报文是字节流；surrogateescape 保证任意字节都能往返
            self.payload = payload.encode("utf-8", "surrogateescape")
        else:
            self.payload = bytes(payload)

    def to_bytes(self) -> bytes:
        """序列化为可直接写入 socket 的字节串。"""
        length = len(self.payload)
        if length > MAX_PAYLOAD_LENGTH:
            raise InvalidPacketError(
                "payload too large for a single MySQL packet: {} bytes".format(length)
            )
        return length.to_bytes(3, "little") + bytes([self.packet_num]) + self.payload

    def __bytes__(self) -> bytes:
        return self.to_bytes()

    def __repr__(self) -> str:
        return "MySQLPacket(num={}, len={})".format(
            self.packet_num, len(self.payload)
        )

    @classmethod
    def parse(cls, raw: bytes) -> "MySQLPacket":
        """从完整报文（含 4 字节头）解析出一个数据包。"""
        if len(raw) < HEADER_LEN:
            raise InvalidPacketError("incomplete MySQL packet header")

        length = int.from_bytes(raw[:3], "little")
        packet_num = raw[3]

        if len(raw) < HEADER_LEN + length:
            raise InvalidPacketError(
                "incomplete MySQL packet body: expected {}, got {}".format(
                    length, len(raw) - HEADER_LEN
                )
            )

        return cls(packet_num, raw[HEADER_LEN:HEADER_LEN + length])

    @classmethod
    async def read_from(cls, reader: asyncio.StreamReader) -> "MySQLPacket":
        """从数据流中异步读取一个完整报文。"""
        header = await reader.readexactly(HEADER_LEN)
        length = int.from_bytes(header[:3], "little")
        packet_num = header[3]
        payload = await reader.readexactly(length) if length else b""
        return cls(packet_num, payload)
