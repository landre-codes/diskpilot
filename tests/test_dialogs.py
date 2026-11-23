from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from PySide6.QtGui import QColor, QImage

from app.config import AppConfig
from app.services.model import ScanResult, ScanWarning
from appshell.theme import init_theme
from app.widgets.dialogs import (
    ExportDialog,
    FolderPickerDialog,
    ImagePickerDialog,
    TopItemsDialog,
    WarningsDialog,
)
from appshell.widgets.dialogs import SheetDialog


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(tmp_path / "config")


def test_folder_picker_loads_and_selects_folder(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    (tmp_path / "Alfa").mkdir()
    (tmp_path / "Beta").mkdir()

    dialog = FolderPickerDialog(None, str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitUntil(
        lambda: dialog._folder_model.rowCount() >= 2,
        timeout=4000,
    )
    index = dialog._folder_model.index(0, 0)
    dialog.folder_list.setCurrentIndex(index)

    assert dialog._folder_model.path_at(0) in {
        str(tmp_path / "Alfa"),
        str(tmp_path / "Beta"),
    }
    assert len(dialog.selected_paths()) == 1
    dialog.close()


def test_export_dialog_validates_and_writes_csv(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    result = ScanResult(total_size=0, total_files=0, total_dirs=0)

    dialog = ExportDialog(None, result)
    qtbot.addWidget(dialog)
    dialog.folder_edit.setText(str(tmp_path))
    dialog.name_edit.setText("saida.csv")
    dialog._update_target()

    assert dialog._validated_path() == tmp_path / "saida.csv"
    dialog._export()
    qtbot.waitUntil(
        lambda: bool(dialog.exported_path),
        timeout=5000,
    )

    assert Path(dialog.exported_path).is_file()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


def test_image_picker_loads_folder_in_background(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    folder = tmp_path / "fotos"
    folder.mkdir()
    for index in range(2):
        image = QImage(48, 48, QImage.Format_RGB32)
        image.fill(QColor("#336699"))
        image.save(str(folder / f"foto_{index}.png"))

    dialog = ImagePickerDialog(None, str(folder))
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: dialog.grid.count() >= 2, timeout=5000)

    assert not dialog._loading
    dialog.grid.setCurrentRow(0)
    assert dialog.selected_path.endswith(".png")
    dialog.close()


def test_top_items_loads_in_background(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    result = ScanResult(total_size=100, total_files=1, total_dirs=1)

    dialog = TopItemsDialog(None, result)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: not dialog._loading, timeout=5000)

    assert dialog.summary.text() != ""
    dialog.close()


def test_warnings_dialog_lists_categories(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    result = ScanResult(
        total_size=100,
        total_files=1,
        total_dirs=1,
        errors=3,
        warnings=[
            ScanWarning("list_dir", "permission_denied", 2),
            ScanWarning("read_entry", "io_error", 1),
        ],
    )
    dialog = WarningsDialog(None, result)
    qtbot.addWidget(dialog)

    assert dialog.tree.topLevelItemCount() == 2
    assert dialog.tree.topLevelItem(0).text(0) == "Permissão negada"
    assert dialog.tree.topLevelItem(1).text(2) == "1"
    assert "Permissão negada" in dialog.summary_text()
    assert "Caminhos completos não são armazenados" in dialog.summary_text()
    dialog.close()


def test_sheet_dialog_focuses_body_not_close_button(
    qapp, qtbot, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    dialog = SheetDialog(None, "Teste", "Foco inicial")
    edit = QLineEdit("conteúdo")
    dialog.body.addWidget(edit)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitUntil(lambda: QApplication.focusWidget() is edit, timeout=2000)
    assert dialog.header.close_btn.hasFocus() is False
    dialog.close()


def test_sheet_dialog_is_resizable_and_scrollable(qapp, qtbot, tmp_path: Path) -> None:
    config = _config(tmp_path)
    init_theme(qapp, config)
    dialog = ExportDialog(None, ScanResult())
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    assert dialog.body_scroll.widgetResizable()
    assert dialog._resize_grip.isVisible()
    dialog.resize(dialog.minimumWidth(), dialog.minimumHeight())
    qtbot.wait(10)

    assert dialog.width() == dialog.minimumWidth()
    assert dialog.height() == dialog.minimumHeight()
    grip_pos = dialog._resize_grip.mapTo(dialog, QPoint(0, 0))
    assert grip_pos.x() + dialog._resize_grip.width() <= dialog.width()
    assert grip_pos.y() + dialog._resize_grip.height() <= dialog.height()
    dialog.close()
