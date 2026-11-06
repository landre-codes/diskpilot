"""Shell principal: janela sem moldura, navegação e composição modular."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QCloseEvent,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_TAGLINE
from .config import AppConfig
from .features.base import BasePage, PageSpec
from .services.state import AppState
from .theme import ThemeManager, get_theme
from .widgets.common import Toast
from .widgets.dialogs import ProfileDialog
from .widgets.sidebar import Sidebar
from .widgets.title_bar import TitleBar


class FadeStack(QStackedWidget):
    """Troca de páginas com fade suave (sem recriar os widgets)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None

    def set_index_animated(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        if index == self.currentIndex():
            return
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
            for i in range(self.count()):
                self.widget(i).setGraphicsEffect(None)
        page = self.widget(index)
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        self.setCurrentIndex(index)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(190)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def clear() -> None:
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)
            if self._anim is anim:
                self._anim = None

        anim.finished.connect(clear)
        self._anim = anim
        anim.start()


class MainWindow(QWidget):
    def __init__(
        self,
        config: AppConfig,
        theme: ThemeManager,
        page_specs: list[PageSpec],
        state: AppState | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.theme = theme
        self.page_specs = page_specs
        self.state = state if state is not None else AppState(config)
        self._pages: dict[str, BasePage] = {}
        self._current_key = ""
        self._first_show = True
        self._manual_drag = False
        self._drag_offset = QPoint()
        self._pending_restore_pos: QPoint | None = None
        self._resize_manual = False
        self._resize_native = False
        self._resize_edges = Qt.Edges()
        self._resize_start_geo = QRect()
        self._resize_start_global = QPoint()
        self._shortcuts: list[QShortcut] = []
        self._shell_state: tuple[bool, bool] = (False, False)
        self._applying_state = False
        self._update_reasons: set[str] = set()

        self.setWindowTitle(APP_NAME)
        icon_path = Path(__file__).resolve().parent / "assets" / "app_icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setMinimumSize(1120, 700)
        self.setMouseTracking(True)
        self._build_ui()
        self._connect()
        self._setup_shortcuts()
        self._restore_geometry()
        self._apply_window_state()
        self._theme_changed(self.theme.key)
        if self.page_specs:
            self.navigate(self.page_specs[0].key, animate=False)
        self.title_bar.set_sidebar_collapsed(self.sidebar.collapsed)
        self._toast = Toast(self)
        self._toast.hide()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)
        self.shell = QFrame(self)
        self.shell.setObjectName("WindowShell")
        outer.addWidget(self.shell)

        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.title_bar = TitleBar(APP_NAME, APP_TAGLINE, self.shell)
        shell_layout.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        pages_for_sidebar = [(p.key, p.title, p.icon) for p in self.page_specs]
        self.sidebar = Sidebar(self.config, pages_for_sidebar, self.shell)
        body.addWidget(self.sidebar)
        self.content = QWidget(self.shell)
        self.content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(22, 18, 22, 18)
        content_layout.setSpacing(12)
        self.stack = FadeStack(self.content)
        for spec in self.page_specs:
            page = spec.factory(self.state)
            self._pages[spec.key] = page
            self.stack.addWidget(page)
            page.toastRequested.connect(self.show_toast)
            page.navigateRequested.connect(self.navigate)
            page.identityChanged.connect(self._refresh_identity)
        content_layout.addWidget(self.stack, 1)
        body.addWidget(self.content, 1)
        shell_layout.addLayout(body, 1)

    def _connect(self) -> None:
        self.title_bar.minimizeRequested.connect(self.showMinimized)
        self.title_bar.maximizeRequested.connect(self.toggle_maximize)
        self.title_bar.closeRequested.connect(self.close)
        self.title_bar.themeRequested.connect(self._toggle_theme)
        self.title_bar.menuRequested.connect(self.sidebar.toggle)
        self.title_bar.dragStarted.connect(self._start_drag)
        self.title_bar.dragMoved.connect(self._drag_move)
        self.title_bar.dragFinished.connect(self._end_drag)
        self.sidebar.pageSelected.connect(self.navigate)
        self.sidebar.collapsedChanged.connect(self._sidebar_collapsed)
        self.sidebar.logoRequested.connect(self._change_logo)
        self.sidebar.logoRemoveRequested.connect(self._remove_logo)
        self.sidebar.userRequested.connect(self._edit_profile)
        self.theme.aboutToChange.connect(self._begin_theme_change)
        self.theme.changed.connect(self._theme_changed)

    def _setup_shortcuts(self) -> None:
        def add(sequence: str, callback) -> None:
            sc = QShortcut(QKeySequence(sequence), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(callback)
            self._shortcuts.append(sc)

        add("Ctrl+O", self._shortcut_add)
        add("Ctrl+F", self._shortcut_search)
        add("Ctrl+R", self._shortcut_rescan)
        add("Ctrl+B", self.sidebar.toggle)
        add("F11", self.toggle_fullscreen)
        for i, spec in enumerate(self.page_specs[:9]):
            add(f"Ctrl+{i + 1}", lambda key=spec.key: self.navigate(key))

    # ------------------------------------------------------------- navegação
    def navigate(self, key: str, animate: bool = True) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        index = self.stack.indexOf(page)
        if index == self.stack.currentIndex():
            page.on_show()
            self.sidebar.set_active(key)
            self._current_key = key
            return
        current = self.stack.currentWidget()
        if isinstance(current, BasePage):
            current.on_hide()
        if animate:
            self.stack.set_index_animated(index)
        else:
            self.stack.setCurrentIndex(index)
        self._current_key = key
        self.sidebar.set_active(key)
        page.on_show()

    def _shortcut_add(self) -> None:
        self.navigate("analyzer")
        analyzer = self._pages.get("analyzer")
        if analyzer is not None and hasattr(analyzer, "add_folders"):
            QTimer.singleShot(30, analyzer.add_folders)

    def _shortcut_search(self) -> None:
        self.navigate("analyzer")
        analyzer = self._pages.get("analyzer")
        if analyzer is not None and hasattr(analyzer, "focus_search"):
            QTimer.singleShot(60, analyzer.focus_search)

    def _shortcut_rescan(self) -> None:
        if self.state.roots:
            self.navigate("analyzer")
            self.state.start_scan(force=True)
        else:
            self._shortcut_add()

    # --------------------------------------------------------------- janela
    def _repolish(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _theme_changed(self, key: str) -> None:
        self.title_bar.set_theme(key)
        self.sidebar.refresh_user()
        for widget in (self.shell, self.title_bar, self.sidebar):
            self._repolish(widget)
        # A troca é aplicada em um único quadro para evitar flashes.
        QTimer.singleShot(0, self._finish_theme_change)

    def _begin_theme_change(self, _key: str) -> None:
        self._suspend_updates("theme")
        # Segurança caso algo falhe antes do sinal changed.
        QTimer.singleShot(1500, lambda: self._resume_updates("theme"))

    def _finish_theme_change(self) -> None:
        self._resume_updates("theme")

    def _suspend_updates(self, reason: str) -> None:
        first = not self._update_reasons
        self._update_reasons.add(reason)
        if first:
            self.setUpdatesEnabled(False)

    def _resume_updates(self, reason: str) -> None:
        self._update_reasons.discard(reason)
        if self._update_reasons:
            return
        self.setUpdatesEnabled(True)
        self.update()
        self.repaint()

    def _toggle_theme(self) -> None:
        key = self.theme.toggle()
        self.show_toast(
            f"Tema {'escuro' if key == 'dark' else 'claro'} aplicado.", "info"
        )

    def _sidebar_collapsed(self, collapsed: bool) -> None:
        self.title_bar.set_sidebar_collapsed(collapsed)
        self.config.set("sidebar_collapsed", collapsed)

    def _apply_window_state(self) -> None:
        if self._applying_state:
            return
        self._applying_state = True
        try:
            maximized = self.isMaximized() or self.isFullScreen()
            self._shell_state = (self.isMaximized(), self.isFullScreen())
            margins = 0 if maximized else 6
            self.layout().setContentsMargins(margins, margins, margins, margins)
            self.shell.setProperty("windowMaximized", maximized)
            self.title_bar.setProperty("windowMaximized", maximized)
            self.sidebar.setProperty("windowMaximized", maximized)
            self.title_bar.set_maximized(maximized)
            for widget in (self.shell, self.title_bar, self.sidebar):
                self._repolish(widget)
        finally:
            self._applying_state = False
            self._resume_updates("state")

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if event.type() == QEvent.WindowStateChange and hasattr(self, "shell"):
            state = (self.isMaximized(), self.isFullScreen())
            if state != self._shell_state:
                self._shell_state = state
                self._suspend_updates("state")
                QTimer.singleShot(0, self._apply_window_state)
                QTimer.singleShot(1500, lambda: self._resume_updates("state"))
        super().changeEvent(event)

    def toggle_maximize(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            state = str(self.config.get("window_state", "normal"))
            if state == "maximized":
                QTimer.singleShot(0, self.showMaximized)
            elif state == "fullscreen":
                QTimer.singleShot(0, self.showFullScreen)

    # ---------------------------------------------------------------- drag
    def _start_drag(self, global_pos: QPoint) -> None:
        if self.isFullScreen():
            return
        if self.isMaximized():
            self._pending_restore_pos = global_pos
            return
        self._pending_restore_pos = None
        self._drag_offset = global_pos - self.frameGeometry().topLeft()
        self._manual_drag = True

    def _restore_for_drag(self, global_pos: QPoint) -> None:
        ratio = (global_pos.x() - self.geometry().x()) / max(1, self.width())
        width = max(self.minimumWidth(), self.normalGeometry().width())
        height = max(self.minimumHeight(), self.normalGeometry().height())
        x = int(global_pos.x() - width * ratio)
        y = int(global_pos.y() - 30)
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            x = max(avail.left(), min(x, avail.right() - width + 1))
            y = max(avail.top(), min(y, avail.bottom() - height + 1))
        self.showNormal()
        self.setGeometry(x, y, width, height)
        self._drag_offset = global_pos - self.frameGeometry().topLeft()

    def _drag_move(self, global_pos: QPoint) -> None:
        if self._pending_restore_pos is not None:
            self._restore_for_drag(global_pos)
            self._pending_restore_pos = None
            self._manual_drag = True
        if self._manual_drag:
            self.move(global_pos - self._drag_offset)

    def _end_drag(self) -> None:
        self._pending_restore_pos = None
        self._manual_drag = False

    # --------------------------------------------------------------- resize
    @staticmethod
    def _cursor_for_edges(edges: Qt.Edges):
        left = bool(edges & Qt.LeftEdge)
        right = bool(edges & Qt.RightEdge)
        top = bool(edges & Qt.TopEdge)
        bottom = bool(edges & Qt.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.SizeBDiagCursor
        if left or right:
            return Qt.SizeHorCursor
        if top or bottom:
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _edges_at(self, pos: QPoint) -> Qt.Edges:
        edges = Qt.Edges()
        if self.isMaximized() or self.isFullScreen():
            return edges
        margin = 10
        if pos.x() <= margin:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - margin:
            edges |= Qt.RightEdge
        if pos.y() <= margin:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - margin:
            edges |= Qt.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            edges = self._edges_at(event.position().toPoint())
            if edges:
                self._resize_edges = edges
                self._resize_start_geo = self.geometry()
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_manual = True
                self._resize_native = False
                handle = self.windowHandle()
                if handle is not None and handle.startSystemResize(edges):
                    self._resize_native = True
                    self._resize_manual = False
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resize_manual and (event.buttons() & Qt.LeftButton):
            self._resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        if not self._resize_native:
            edges = self._edges_at(event.position().toPoint())
            self.setCursor(self._cursor_for_edges(edges))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._resize_manual = False
            self._resize_native = False
            self._resize_edges = Qt.Edges()
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def _resize_to(self, global_pos: QPoint) -> None:
        geo = QRect(self._resize_start_geo)
        dx = global_pos.x() - self._resize_start_global.x()
        dy = global_pos.y() - self._resize_start_global.y()
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        if self._resize_edges & Qt.LeftEdge:
            geo.setLeft(min(geo.left() + dx, geo.right() - min_w))
        if self._resize_edges & Qt.RightEdge:
            geo.setRight(max(geo.right() + dx, geo.left() + min_w))
        if self._resize_edges & Qt.TopEdge:
            geo.setTop(min(geo.top() + dy, geo.bottom() - min_h))
        if self._resize_edges & Qt.BottomEdge:
            geo.setBottom(max(geo.bottom() + dy, geo.top() + min_h))
        self.setGeometry(geo)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_toast") and self._toast.isVisible():
            self._toast.move(
                max(20, self.width() - self._toast.width() - 24),
                max(20, self.height() - self._toast.height() - 24),
            )

    # ------------------------------------------------- hit test nativo (Win)
    def nativeEvent(self, eventType, message):  # noqa: N802
        """Resize nativo nas bordas, inclusive sobre a sombra translúcida.

        O Windows envia WM_NCHITTEST antes de entregar o mouse ao widget;
        assim o redimensionamento funciona mesmo quando o cursor está sobre
        a margem transparente ou sobre um filho próximo à borda.
        """
        if sys.platform.startswith("win"):
            try:
                if bytes(eventType) == b"windows_generic_MSG":
                    from ctypes import wintypes

                    msg = wintypes.MSG.from_address(int(message))
                    if (
                        msg.message == 0x0084  # WM_NCHITTEST
                        and not self.isMaximized()
                        and not self.isFullScreen()
                    ):
                        x = ctypes.c_short(msg.lParam & 0xFFFF).value
                        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                        local = self.mapFromGlobal(QPoint(x, y))
                        border = 10
                        left = local.x() < border
                        right = local.x() >= self.width() - border
                        top = local.y() < border
                        bottom = local.y() >= self.height() - border
                        code = None
                        if left and top:
                            code = 13  # HTTOPLEFT
                        elif right and top:
                            code = 14  # HTTOPRIGHT
                        elif left and bottom:
                            code = 16  # HTBOTTOMLEFT
                        elif right and bottom:
                            code = 17  # HTBOTTOMRIGHT
                        elif left:
                            code = 10  # HTLEFT
                        elif right:
                            code = 11  # HTRIGHT
                        elif top:
                            code = 12  # HTTOP
                        elif bottom:
                            code = 15  # HTBOTTOM
                        if code is not None:
                            return True, code
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    # ------------------------------------------------------------ geometria
    def _restore_geometry(self) -> None:
        avail = (
            QGuiApplication.primaryScreen().availableGeometry()
            if QGuiApplication.primaryScreen()
            else QRect(0, 0, 1366, 768)
        )
        default_w = min(1600, max(1120, int(avail.width() * 0.75)))
        default_h = min(980, max(700, int(avail.height() * 0.82)))
        rect = QRect(
            avail.center().x() - default_w // 2,
            avail.center().y() - default_h // 2,
            default_w,
            default_h,
        )
        saved = self.config.get("geometry", None)
        if isinstance(saved, (list, tuple)) and len(saved) == 4:
            try:
                candidate = QRect(
                    int(saved[0]), int(saved[1]), int(saved[2]), int(saved[3])
                )
                if candidate.width() >= 600 and candidate.height() >= 500:
                    rect = candidate
            except (TypeError, ValueError):
                pass
        rect.setWidth(max(1120, min(rect.width(), max(1120, avail.width()))))
        rect.setHeight(max(700, min(rect.height(), max(700, avail.height()))))
        screen = QGuiApplication.screenAt(rect.center())
        if screen is None:
            avail2 = QGuiApplication.primaryScreen().availableGeometry()
            rect.moveCenter(avail2.center())
        self.setGeometry(rect)

    def _save_geometry(self) -> None:
        geo = (
            self.normalGeometry()
            if self.isMaximized() or self.isFullScreen()
            else self.geometry()
        )
        self.config.set(
            "geometry", [geo.x(), geo.y(), geo.width(), geo.height()], save=False
        )
        if self.isFullScreen():
            state = "fullscreen"
        elif self.isMaximized():
            state = "maximized"
        else:
            state = "normal"
        self.config.set("window_state", state, save=False)
        self.config.set("sidebar_collapsed", self.sidebar.collapsed, save=False)
        self.config.save()

    # ------------------------------------------------------------- identidade
    def _refresh_identity(self) -> None:
        self.sidebar.refresh_logo()
        self.sidebar.refresh_user()
        settings = self._pages.get("settings")
        if settings is not None and hasattr(settings, "_refresh_identity"):
            settings._refresh_identity()

    def _change_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher logo da empresa",
            str(Path.home()),
            "Imagens (*.png *.jpg *.jpeg *.webp *.svg *.bmp);;Todos os arquivos (*)",
        )
        if not path:
            return
        try:
            stored = self.config.import_asset(path, "logo")
            self.config.set("logo", stored)
        except Exception as exc:
            self.show_toast(f"Não foi possível salvar o logo: {exc}", "danger")
            return
        self._refresh_identity()
        self.show_toast("Logo atualizado. O arquivo foi salvo com persistência.", "success")

    def _remove_logo(self) -> None:
        self.config.set("logo", "")
        self._refresh_identity()
        self.show_toast("Logo removido.", "info")

    def _edit_profile(self) -> None:
        dialog = ProfileDialog(self, self.config)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_identity()
            self.show_toast("Perfil atualizado.", "success")

    # ------------------------------------------------------------ drag & drop
    def _directories_from_mime(self, mime) -> list[str]:
        paths: list[str] = []
        if not mime.hasUrls():
            return paths
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if os.path.isdir(path):
                paths.append(path)
        return paths

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._directories_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._directories_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._directories_from_mime(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        added = self.state.add_roots(paths, autoscan=True)
        self.navigate("analyzer")
        if added:
            noun = "pasta adicionada" if len(added) == 1 else "pastas adicionadas"
            self.show_toast(f"{len(added)} {noun}. Iniciando análise…", "info")
        else:
            self.show_toast("As pastas arrastadas já estão na análise.", "info")
        event.acceptProposedAction()

    # --------------------------------------------------------------- toast
    def show_toast(self, message: str, kind: str = "info") -> None:
        if not hasattr(self, "_toast"):
            self._toast = Toast(self)
        self._toast.present(message, kind)

    def bring_to_front(self) -> None:
        """Ativa a instância já aberta quando uma segunda é iniciada."""
        from PySide6.QtWidgets import QApplication

        was_maximized = bool(self.windowState() & Qt.WindowMaximized)
        if self.isMinimized():
            if was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
        elif not self.isVisible():
            self.show()
        modal = QApplication.activeModalWidget()
        target = modal if modal is not None else self
        target.raise_()
        target.activateWindow()
        if target is self and self.windowHandle() is not None:
            self.windowHandle().requestActivate()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_geometry()
        if hasattr(self.state, "shutdown"):
            self.state.shutdown()
        event.accept()
