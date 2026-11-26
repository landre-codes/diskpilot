from __future__ import annotations

import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QBoxLayout

from app.config import AppConfig
from appshell.tasks import Task, TaskCancelled, TaskRunner
from appshell.theme import init_theme
from appshell.widgets.buttons import ActionButton, IconButton, NavButton
from appshell.widgets.common import PageHeader


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


def test_icon_button_exposes_accessible_name(qapp, tmp_path) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    button = IconButton("close", "Fechar painel", None, 16)

    assert button.accessibleName() == "Fechar painel"


def test_nav_button_active_pill_fades_in_and_out(qapp, qtbot, tmp_path) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    button = NavButton("dados", "Dados", "database")
    qtbot.addWidget(button)
    button.show()

    button.set_active(True)
    qtbot.wait(40)
    assert 0.0 < button._active_progress < 1.0
    qtbot.waitUntil(lambda: button._active_progress >= 0.99, timeout=1000)

    button.set_active(False)
    qtbot.waitUntil(lambda: button._active_progress <= 0.01, timeout=1000)
    button.close()


def test_action_buttons_accept_keyboard_focus(qapp, tmp_path) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    primary = ActionButton("Executar", "play", "primary")
    ghost = ActionButton("Cancelar", "close", "ghost")

    assert primary.focusPolicy() & Qt.StrongFocus
    assert ghost.focusPolicy() & Qt.StrongFocus


def test_mouse_click_does_not_leave_action_button_focused(
    qapp, qtbot, tmp_path
) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    button = ActionButton("Executar", "play", "primary")
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    QTest.mouseClick(button, Qt.LeftButton)

    assert button.hasFocus() is False
    assert button.isDown() is False


def test_mouse_click_does_not_leave_icon_button_focused(
    qapp, qtbot, tmp_path
) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    button = IconButton("cog", "Configurações")
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    QTest.mouseClick(button, Qt.LeftButton)

    assert button.hasFocus() is False
    assert button.isDown() is False


def test_page_header_wraps_actions_when_narrow(qapp) -> None:
    header = PageHeader("Análise de diretórios", "subtítulo")
    for number in range(4):
        header.add_action(IconButton("close", f"Ação {number}", None, 16))

    header.resize(500, 220)
    header.show()
    qapp.processEvents()
    assert header.row.direction() == QBoxLayout.Direction.TopToBottom

    header.resize(1600, 220)
    qapp.processEvents()
    assert header.row.direction() == QBoxLayout.Direction.LeftToRight
    header.close()


def test_task_runner_shutdown_reports_timeout_and_keeps_task(qtbot) -> None:
    runner = TaskRunner()
    started = threading.Event()
    release = threading.Event()

    class _BlockingTask(Task):
        def execute(self) -> int:
            started.set()
            release.wait(5)
            return 1

    runner.submit(_BlockingTask())
    assert started.wait(2)
    try:
        assert runner.shutdown(wait_ms=10) is False
        assert runner.busy is True
    finally:
        release.set()

    qtbot.waitUntil(lambda: not runner.busy, timeout=5000)
    assert runner.shutdown(wait_ms=1000) is True
