from __future__ import annotations

import time

from appshell.tasks import Task, TaskCancelled, TaskRunner


class _ValueTask(Task):
    def __init__(self, value: int) -> None:
        super().__init__()
        self.value = value

    def execute(self) -> int:
        return self.value


class _FailingTask(Task):
    def execute(self) -> int:
        raise RuntimeError("falha proposital")


class _CancellableTask(Task):
    def execute(self) -> int:
        while not self.cancel.is_set():
            time.sleep(0.01)
        raise TaskCancelled()


def test_task_runner_emits_result_and_releases_busy(qtbot) -> None:
    runner = TaskRunner()
    results = []
    runner.finished.connect(results.append)

    runner.submit(_ValueTask(42))
    qtbot.waitUntil(lambda: bool(results), timeout=3000)

    assert results == [42]
    assert not runner.busy


def test_task_runner_reports_failure(qtbot) -> None:
    runner = TaskRunner()
    errors = []
    runner.failed.connect(errors.append)

    runner.submit(_FailingTask())
    qtbot.waitUntil(lambda: bool(errors), timeout=3000)

    assert errors == ["falha proposital"]
    assert not runner.busy


def test_task_runner_cancels_task(qtbot) -> None:
    runner = TaskRunner()
    cancelled = []
    runner.cancelled.connect(lambda: cancelled.append(True))

    runner.submit(_CancellableTask())
    runner.cancel()
    qtbot.waitUntil(lambda: bool(cancelled), timeout=3000)

    assert cancelled == [True]
    assert not runner.busy
