"""Compatibilidade: o contrato de páginas agora vive em ``appshell.pages``."""

from __future__ import annotations

from appshell.pages import BasePage, PageSpec

__all__ = ["BasePage", "PageSpec"]
