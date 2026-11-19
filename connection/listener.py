"""TCP 监听器：接受客户端连接并交给 MySQL 会话处理器。"""

from __future__ import annotations

import asyncio

from connection.mysql_handler import MySQLConnectionHandler


class MySQLListener:
    """监听 MySQL 端口，管理所有活动连接。"""

    def __init__(self, config, logger, task_manager, file_handler, on_finished=None):
        self.config = config
        self.logger = logger
        self.task_manager = task_manager
        self.file_handler = file_handler
        self.on_finished = on_finished

        self.server = None
        self.connections: set = set()
        self.handlers: set = set()
        self._connection_counter = 0

    async def start(self) -> None:
        """启动 TCP 监听。start_server 默认已开始接受连接。"""
        self.server = await asyncio.start_server(
            self.handle_client,
            host="0.0.0.0",
            port=self.config.port,
            backlog=5,
        )

        for sock in self.server.sockets:
            self.logger.info("MySQL listener started: %s", sock.getsockname())

    async def handle_client(self, reader, writer) -> None:
        """接受并调度客户端连接。"""
        self._connection_counter += 1

        handler = MySQLConnectionHandler(
            reader,
            writer,
            self.logger,
            self.task_manager,
            self.file_handler,
            connection_id=self._connection_counter,
            on_finished=self._on_finished,
        )

        task = asyncio.current_task()
        self.connections.add(task)
        self.handlers.add(handler)

        try:
            await handler.handle()
        finally:
            self.connections.discard(task)
            self.handlers.discard(handler)

    def _on_finished(self) -> None:
        """会话完成全部任务：通知主程序结束。"""
        if self.on_finished is not None:
            self.on_finished()

    async def stop(self) -> None:
        """停止监听并以 RST 强制断开所有活动连接。"""
        if self.server is not None:
            self.logger.info("stopping MySQL listener...")
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        # 对标原版进程退出：直接重置所有连接，不给客户端继续交互的机会。
        for handler in list(self.handlers):
            handler.abort()

        current = asyncio.current_task()
        tasks = [task for task in self.connections if task is not current]

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.logger.info("MySQL listener stopped")
