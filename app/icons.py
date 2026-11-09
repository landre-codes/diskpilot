"""Ícones MDI, avatares e helpers de pintura."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".ico", ".heic"}
_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
_AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
_ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".tgz"}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".json",
    ".xml", ".yml", ".yaml", ".toml", ".ini", ".ps1", ".bat", ".cmd", ".sh",
    ".java", ".kt", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".sql",
}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv"}


def clear_icon_cache() -> None:
    _icon_cached.cache_clear()


@lru_cache(maxsize=1024)
def _icon_cached(prefixed_name: str, color: str) -> object:
    return qta.icon(prefixed_name, color=color)


def icon(name: str, color: str, size: int = 20):
    """Retorna um QIcon MDI cacheado. ``name`` sem o prefixo ``mdi.``."""
    for prefix in ("mdi", "mdi6"):
        try:
            return _icon_cached(f"{prefix}.{name}", color)
        except Exception:
            continue
    return _icon_cached("mdi.help-circle-outline", color)


@lru_cache(maxsize=256)
def _file_icon_cached(ext: str, is_dir: bool, color: str, accent: str):
    if is_dir:
        return icon("folder", accent)
    if ext in _IMAGE_EXT:
        md = "file-image-outline"
    elif ext in _VIDEO_EXT:
        md = "file-video-outline"
    elif ext in _AUDIO_EXT:
        md = "file-music-outline"
    elif ext in _ARCHIVE_EXT:
        md = "zip-box-outline"
    elif ext == ".pdf":
        md = "file-pdf-box"
    elif ext in _CODE_EXT:
        md = "file-code-outline"
    elif ext in _DOC_EXT:
        md = "file-document-outline"
    else:
        md = "file-outline"
    return icon(md, color)


def file_icon(name: str, is_dir: bool, color: str, accent: str):
    """Ícone por extensão (não por nome), para reutilizar em pastas grandes."""
    ext = "" if is_dir else Path(name).suffix.lower()
    return _file_icon_cached(ext, is_dir, color, accent)


def initials(name: str) -> str:
    parts = [p for p in str(name).strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def avatar_pixmap(
    name: str,
    size: int,
    color_a: str = "#19c8d8",
    color_b: str = "#4f9cf9",
    text_color: str = "#042126",
    dpr: float = 2.0,
) -> QPixmap:
    """Avatar geométrico com as iniciais do usuário."""
    dpr = max(1.0, dpr)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, size, size).adjusted(0.5, 0.5, -0.5, -0.5)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0, QColor(color_a))
    grad.setColorAt(1, QColor(color_b))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(rect)
    f = QFont("Segoe UI", max(7, int(size * 0.34)))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(QColor(text_color))
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, initials(name))
    p.end()
    return pm


def circular_pixmap(path: str, size: int, dpr: float = 2.0) -> QPixmap:
    """Carrega uma imagem, recorta em círculo e aplica máscara.

    Retratos são recortados com prioridade para o topo, preservando o rosto,
    em vez de cortar o centro da imagem.
    """
    pm = QPixmap(path)
    if pm.isNull():
        return QPixmap()
    dpr = max(1.0, dpr)
    side = int(size * dpr)
    pm = pm.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    result = QPixmap(side, side)
    result.fill(Qt.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    mask = QPainterPath()
    mask.addEllipse(QRectF(0, 0, side, side))
    p.setClipPath(mask)
    if pm.height() > side:
        # Retrato: começa perto do topo (8% de folga) para não cortar a cabeça.
        y = -int((pm.height() - side) * 0.08)
        x = 0
    else:
        x = (side - pm.width()) // 2
        y = 0
    p.drawPixmap(x, y, pm)
    p.end()
    # O DPR é aplicado só depois da pintura: o QPainter usa coordenadas
    # físicas e desenhar em `side` com DPR 2 cortava o canto da imagem.
    result.setDevicePixelRatio(dpr)
    return result


def rounded_pixmap(path: str, size: int, radius: int = 10) -> QPixmap:
    """Carrega imagem preservando proporção, com cantos arredondados."""
    pm = QPixmap(path)
    if pm.isNull():
        return QPixmap()
    dpr = 2.0
    target = QPixmap(int(size * dpr), int(size * dpr))
    target.fill(Qt.transparent)
    scaled = pm.scaled(
        int(size * dpr), int(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    p = QPainter(target)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path_ = QPainterPath()
    path_.addRoundedRect(
        QRectF(0, 0, int(size * dpr), int(size * dpr)), radius * dpr, radius * dpr
    )
    p.setClipPath(path_)
    x = (int(size * dpr) - scaled.width()) // 2
    y = (int(size * dpr) - scaled.height()) // 2
    p.drawPixmap(x, y, scaled)
    p.end()
    target.setDevicePixelRatio(dpr)
    return target


def draw_rating_dots(painter: QPainter, rect: QRect, count: int, color: QColor) -> None:
    """Pequeno ornamento usado em cards de recomendação."""
    painter.save()
    painter.setPen(Qt.NoPen)
    for i in range(3):
        c = QColor(color)
        c.setAlpha(220 if i < count else 55)
        painter.setBrush(c)
        painter.drawEllipse(QPoint(rect.left() + 6 + i * 13, rect.center().y()), 3, 3)
    painter.restore()
