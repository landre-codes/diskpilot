"""Registro de páginas padrão do shell.

Para reutilizar a GUI em outro domínio, crie novas implementações de
``BasePage`` e devolva outra lista de ``PageSpec`` para ``MainWindow``.
"""

from __future__ import annotations

from .features.analyzer.page import AnalyzerPage
from .features.base import PageSpec
from .features.dashboard import DashboardPage
from .features.logs import LogsPage
from .features.recommendations import RecommendationsPage
from .features.settings import SettingsPage


def default_pages() -> list[PageSpec]:
    return [
        PageSpec(
            "dashboard",
            "Visão geral",
            "Resumo da última análise",
            "view-dashboard-outline",
            DashboardPage,
        ),
        PageSpec(
            "analyzer",
            "Análise de diretórios",
            "Árvore, tamanhos e filtros",
            "folder-search-outline",
            AnalyzerPage,
        ),
        PageSpec(
            "recommendations",
            "Recomendações",
            "Como liberar espaço com segurança",
            "lightbulb-on-outline",
            RecommendationsPage,
        ),
        PageSpec(
            "logs",
            "Logs",
            "Eventos e diagnóstico",
            "console",
            LogsPage,
        ),
        PageSpec(
            "settings",
            "Configurações",
            "Tema, identidade e dados",
            "cog-outline",
            SettingsPage,
        ),
    ]
