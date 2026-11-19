"""下载文件管理：安全路径解析、追加写入与大小统计。"""

from __future__ import annotations

import os

from exceptions import FileManagerError


class FileHandler:
    """把客户端传来的文件片段写入 Downloads 目录。"""

    def __init__(self, save_folder: str):
        self.save_folder = os.path.abspath(save_folder)
        try:
            os.makedirs(self.save_folder, exist_ok=True)
        except OSError as exc:
            raise FileManagerError(
                "unable to create save folder {}: {}".format(self.save_folder, exc)
            )

        self._sizes: dict[str, int] = {}

    def save_path(self, filename: str) -> str:
        """只保留文件名部分，防止客户端提供的路径造成目录穿越。"""
        normalized = str(filename).replace("\\", "/")
        basename = os.path.basename(normalized.rstrip("/")) or "unnamed"
        if basename in (".", ".."):
            basename = "unnamed"
        return os.path.join(self.save_folder, basename)

    def write_chunk(self, filename: str, data: bytes) -> int:
        """追加一个数据片段，返回写入字节数。"""
        if not data:
            return 0

        path = self.save_path(filename)
        try:
            with open(path, "ab") as handle:
                handle.write(data)
        except OSError as exc:
            raise FileManagerError("unable to write {}: {}".format(path, exc))

        self._sizes[path] = self._sizes.get(path, 0) + len(data)
        return len(data)

    def size(self, filename: str) -> int:
        """返回本次会话累计写入的字节数。"""
        path = self.save_path(filename)
        if path in self._sizes:
            return self._sizes[path]
        try:
            return os.path.getsize(path) if os.path.exists(path) else 0
        except OSError:
            return 0

