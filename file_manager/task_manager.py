"""文件任务管理器：跟踪每个目标文件的请求状态与重试次数。"""

from dataclasses import dataclass
from enum import Enum, auto

from exceptions import TaskError


class TaskStatus(Enum):
    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class FileTask:
    filename: str
    attempts: int = 0
    status: TaskStatus = TaskStatus.PENDING


class TaskManager:
    """管理所有待检索文件的生命周期。"""

    def __init__(self, filenames, max_attempts=3):
        if max_attempts < 1:
            raise ValueError("max_attempts must be greater than 0")

        self.max_attempts = max_attempts

        # 去重并保持顺序
        seen = set()
        names = []
        for name in filenames:
            if name and name not in seen:
                seen.add(name)
                names.append(name)

        if not names:
            raise TaskError("no files to retrieve")

        self.tasks = [FileTask(filename=name) for name in names]

    @property
    def pending_count(self):
        return sum(t.status == TaskStatus.PENDING for t in self.tasks)

    @property
    def processing_count(self):
        return sum(t.status == TaskStatus.PROCESSING for t in self.tasks)

    @property
    def completed_count(self):
        return sum(t.status == TaskStatus.COMPLETED for t in self.tasks)

    @property
    def failed_count(self):
        return sum(t.status == TaskStatus.FAILED for t in self.tasks)

    def start_task(self, filename):
        task = self._get_task(filename)
        if task.status != TaskStatus.PENDING:
            raise TaskError("task cannot be started: {}".format(filename))

        task.status = TaskStatus.PROCESSING
        return task

    def retry_task(self, filename):
        """记录一次失败；返回 True 表示允许重试，False 表示彻底放弃。"""
        task = self._get_task(filename)
        if task.status != TaskStatus.PROCESSING:
            raise TaskError("task is not processing: {}".format(filename))

        task.attempts += 1

        if task.attempts >= self.max_attempts:
            task.status = TaskStatus.FAILED
            return False

        task.status = TaskStatus.PENDING
        return True

    def complete_task(self, filename):
        task = self._get_task(filename)
        if task.status != TaskStatus.PROCESSING:
            raise TaskError("task is not processing: {}".format(filename))
        task.status = TaskStatus.COMPLETED

    def get_next_task(self):
        """获取下一个待处理任务；没有时返回 None。"""
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def get_task(self, filename):
        return self._get_task(filename)

    def _get_task(self, filename):
        for task in self.tasks:
            if task.filename == filename:
                return task
        raise TaskError("task not found: {}".format(filename))

    def is_finished(self):
        return all(
            task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for task in self.tasks
        )

    def get_summary(self):
        return {
            "total": len(self.tasks),
            "pending": self.pending_count,
            "processing": self.processing_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
        }
