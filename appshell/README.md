# appshell

Núcleo reutilizável de interface para aplicações PySide6. O pacote não importa
nada de `app`: ele conhece apenas contratos de página, contexto, tarefas e a
janela genérica.

## Peças principais

- `AppContext`: contrato entregue às páginas. O app pode expor propriedades e
  sinais adicionais; o shell só repassa o objeto.
- `BasePage` e `PageSpec`: página modular e registro usado pela navegação.
- `Task`, `TaskSignals` e `TaskRunner`: tarefas em segundo plano com progresso,
  cancelamento, falha e ciclo de vida controlado.
- `ShellWindow`: janela sem moldura, navegação, fade entre páginas, geometria,
  maximizar/restaurar, tela cheia, atalhos, resize nativo no Windows e toasts.
- `ShellOptions`: identidade da janela, página inicial, atalhos e opção de
  aceitar drag & drop.

## Exemplo mínimo

```python
from PySide6.QtWidgets import QLabel, QWidget
from appshell.pages import BasePage, PageSpec
from appshell.shell import ShellOptions, ShellWindow


class HomePage(BasePage):
    def __init__(self, context):
        super().__init__(context)
        QLabel("Olá", self)


class Context:
    def __init__(self, config):
        self.config = config

    def shutdown(self):
        pass


class Chrome:
    """O app fornece barra de título, sidebar e toast próprios."""

    def __init__(self):
        from app.widgets.title_bar import TitleBar
        from app.widgets.sidebar import Sidebar
        from app.widgets.common import Toast
        self.title_bar = TitleBar
        self.sidebar = Sidebar
        self.toast = Toast


def build_window(config, theme, context):
    pages = [PageSpec("home", "Início", "Página inicial", "home", HomePage)]
    chrome = Chrome()
    return ShellWindow(
        config,
        theme,
        pages,
        context,
        options=ShellOptions(title="Meu App", tagline="Descrição curta"),
        title_bar_factory=chrome.title_bar,
        sidebar_factory=lambda entries, parent: chrome.sidebar(config, entries, parent),
        toast_factory=chrome.toast,
    )
```

No template completo, a barra de título, a sidebar e o toast também são
genéricos; o exemplo acima mostra apenas como injetá-los enquanto o kit visual
ainda não foi movido para `appshell.widgets`.

## Regras de ouro

1. O shell não importa páginas, serviços ou modelos do domínio.
2. A página recebe `AppContext`, nunca um estado concreto do shell.
3. O worker recebe uma tarefa; ele não conhece a varredura, a exportação ou
   qualquer outro processo de negócio.
4. O app monta tudo no composition root (`main.py`): configuração, tema,
   contexto, páginas, chrome e callbacks.
