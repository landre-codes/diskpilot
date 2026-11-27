from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.features.recommendation_table import (
    RecommendationFilterProxy,
    RecommendationRow,
    RecommendationTable,
    RecommendationTableModel,
)
from app.features.recommendations import RecommendationsPage
from app.services.model import ScanResult, Suggestion
from app.services.state import AppState
from appshell.theme import init_theme


def _row(
    title: str,
    path: str,
    *,
    confidence: str = "safe",
    size: int = 1024,
    name: str = "cache",
) -> RecommendationRow:
    suggestion = Suggestion(
        key=title.casefold(),
        title=title,
        description=f"Descrição de {title}",
        savings=size,
        count=1,
        confidence=confidence,
        icon="delete-outline",
        note="",
        paths=[path],
    )
    return RecommendationRow(
        suggestion=suggestion,
        path=path,
        display_path=path,
        name=name,
        size=size,
        percent=10.0,
        items=1,
        mtime=0.0,
        kind="Pasta",
        confidence=confidence,
    )


def test_recommendation_table_filters_and_sorts(qapp, tmp_path: Path) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    model = RecommendationTableModel()
    model.set_rows(
        [
            _row("Caches", r"C:\dados\cache", size=500),
            _row(
                "Revisar",
                r"C:\dados\build",
                confidence="review",
                size=900,
                name="build",
            ),
        ]
    )
    proxy = RecommendationFilterProxy()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 2
    proxy.set_query("build")
    assert proxy.rowCount() == 1
    assert proxy.sourceModel().row_at(proxy.mapToSource(proxy.index(0, 0)).row()).path == r"C:\dados\build"
    proxy.set_query("cache")
    assert proxy.rowCount() == 1
    proxy.set_query("")
    proxy.set_confidence("review")
    assert proxy.rowCount() == 1
    proxy.set_confidence("all")
    proxy.sort(3, Qt.DescendingOrder)
    assert proxy.index(0, 3).data() == "900 B"


def test_recommendation_table_copies_full_paths(qapp, tmp_path: Path) -> None:
    init_theme(qapp, AppConfig(tmp_path / "config"))
    model = RecommendationTableModel()
    model.set_rows(
        [
            _row("Caches", r"C:\dados\cache", size=500),
            _row(
                "Revisar",
                r"C:\dados\build",
                confidence="review",
                size=900,
                name="build",
            ),
        ]
    )
    proxy = RecommendationFilterProxy()
    proxy.setSourceModel(model)
    table = RecommendationTable()
    table.setModel(proxy)
    table.selectRow(0)
    table.copy_selected()
    assert QApplication.clipboard().text() == r"C:\dados\cache"
    table.copy_all()
    assert QApplication.clipboard().text() == "C:\\dados\\cache\nC:\\dados\\build"
    table.close()


def test_recommendations_page_exposes_searchable_table(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = AppConfig(tmp_path / "config")
    init_theme(qapp, config)
    state = AppState(config)
    state.last_result = ScanResult(
        total_size=1000,
        total_files=2,
        total_dirs=0,
        suggestions=[
            Suggestion(
                key="caches",
                title="Caches",
                description="Caches regeneráveis",
                savings=500,
                count=1,
                confidence="safe",
                icon="delete-outline",
                paths=[r"C:\dados\cache"],
            ),
            Suggestion(
                key="build",
                title="Build",
                description="Artefatos de build",
                savings=900,
                count=1,
                confidence="review",
                icon="package-variant",
                paths=[r"C:\dados\build"],
            ),
        ],
    )
    page = RecommendationsPage(state)
    qtbot.addWidget(page)
    page.show()
    qtbot.wait(50)

    assert len(page._sections) == 2
    caches = next(section for section in page._sections if section.key == "caches")
    build = next(section for section in page._sections if section.key == "build")
    assert caches.model.rowCount() == 1
    assert build.model.rowCount() == 1

    page.search.set_text("build")
    qtbot.wait(400)
    assert not caches.isVisible()
    assert build.isVisible()
    assert build.table.model().index(0, 2).data() == r"C:\dados\build"
    assert "1 de 2" in page.count_label.text()

    build.set_expanded(False)
    assert not build.expanded
    build.set_expanded(True)
    assert build.expanded

    page.close()
    state.shutdown()


def test_short_path_keeps_last_parts() -> None:
    from app.features.recommendations import _short_path

    assert _short_path(
        r"C:\Users\usuario\AppData\Local\Temp\cache\deep",
        [r"C:\Users\usuario"],
    ).startswith("…\\")
    assert _short_path(r"C:\Users\usuario\cache", [r"C:\Users\usuario"]) == "cache"
