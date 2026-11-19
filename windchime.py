"""WindChime 程序入口与生命周期管理。"""

import asyncio
import signal
import sys
import traceback

from config import Config
from logger import setup_logger
from connection import MySQLListener
from file_manager import TaskManager, FileHandler
from exceptions import WindChimeError
from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet


class WindChimeApplication:
    """程序主控制器：负责初始化、服务调度和资源释放。"""

    def __init__(self, config):
        self.config = config

        self.logger = None
        self.listener = None
        self.task_manager = None
        self.file_handler = None

        self.shutdown_event = asyncio.Event()
        self._shutting_down = False

    def initialize(self):
        """初始化应用程序。"""
        self.config.initialize()

        self.logger = setup_logger(
            log_file=self.config.log_file,
            debug=self.config.debug,
            verbose=self.config.verbose,
        )

        self.task_manager = TaskManager(
            filenames=self.config.filelist,
            max_attempts=self.config.attempts,
        )

        self.file_handler = FileHandler(self.config.save_folder)

        self.listener = MySQLListener(
            config=self.config,
            logger=self.logger,
            task_manager=self.task_manager,
            file_handler=self.file_handler,
            on_finished=self.shutdown_event.set,
        )

        self.logger.info("WindChime initialized")

    def print_banner(self):
        """输出启动信息。"""
        print("WindChime - Rogue MySQL Server")
        print("[+] Target files:")
        for filename in self.config.filelist:
            print("\t" + filename)
        print(
            "[+] Starting listener on port {}... Ctrl+C to stop\n".format(
                self.config.port
            )
        )

    async def shutdown(self):
        """统一关闭应用程序（幂等）。"""
        if self._shutting_down:
            return

        self._shutting_down = True
        self.shutdown_event.set()

        if self.listener is not None:
            await self.listener.stop()

        if self.task_manager is not None:
            self.logger.info("task summary: %s", self.task_manager.get_summary())

        if self.logger:
            self.logger.info("WindChime stopped")

        print("[+] Exiting now...")

    async def run(self):
        """启动并运行服务，直到任务完成或收到退出信号。"""
        self.initialize()
        self.print_banner()

        await self.listener.start()

        try:
            # 任务完成时由会话处理器直接置位事件，无需轮询等待。
            await self.shutdown_event.wait()
            if self.task_manager.is_finished():
                self.logger.info(
                    "all tasks finished: %s", self.task_manager.get_summary()
                )

        finally:
            await self.shutdown()


def main():
    banner = Figlet(font="slant").renderText("WindChime")
    console = Console()
    console.print(f"[bold cyan]{banner}[/bold cyan]")  # 青色
    console.print(
        Panel.fit(
            "[bold cyan]作者[/bold cyan]：wolven\n"
            "[bold cyan]公众号[/bold cyan]：风铃Sec\n"
            "[bold green]GitHub[/bold green]：https://github.com/wolvene",
            title="[bold yellow]About[/bold yellow]",
            border_style="blue"
        )
    )

    """程序入口。"""
    try:
        config = Config.load()
        app = WindChimeApplication(config)

        async def runner():
            loop = asyncio.get_running_loop()

            try:
                loop.add_signal_handler(signal.SIGINT, app.shutdown_event.set)
                if hasattr(signal, "SIGTERM"):
                    loop.add_signal_handler(signal.SIGTERM, app.shutdown_event.set)
            except NotImplementedError:
                pass

            await app.run()

        asyncio.run(runner())

    except KeyboardInterrupt:
        print("\n[+] Exiting now...")

    except WindChimeError as exc:
        print("[-] Error: {}".format(exc))
        sys.exit(1)

    except OSError as exc:
        print("[-] System error: {}".format(exc))
        sys.exit(1)

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
