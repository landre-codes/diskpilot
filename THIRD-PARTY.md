# Licenças de terceiros

O código original do DiskPilot é distribuído sob a licença MIT (veja `LICENSE`).
Este documento lista as dependências e os recursos de terceiros que o
aplicativo usa, com a licença de cada um. Nenhuma delas é copiada para o
repositório: todas são instaladas pelo `pip` ou vêm embutidas nos pacotes.

## Dependências de execução

Versões verificadas no ambiente de desenvolvimento (Windows, Python 3.14).

| Componente | Versão | Licença | Papel no app |
|---|---|---|---|
| PySide6 / PySide6-Essentials | 6.12.0 | **LGPL-3.0-only** (alternativamente GPL-2.0, GPL-3.0 ou comercial) | Qt for Python: janela, widgets, `QThreadPool`, `QLocalServer`, traduções |
| PySide6-Addons | 6.12.0 | LGPL-3.0-only / GPL / comercial | módulos adicionais do Qt (não usado diretamente) |
| shiboken6 | 6.12.0 | LGPL-3.0-only / GPL / comercial | binding C++ do PySide6 |
| qt-material | 2.17 | **BSD-2-Clause** | base do tema (paleta e QSS de controles nativos) |
| qtawesome | 1.4.2 | **MIT** | ícones da interface |
| QtPy | 2.4.3 | **MIT** | camada de compatibilidade exigida pelo qtawesome |

`qt-material` também distribui as fontes **Roboto** (Apache-2.0). O app fixa
`font-family: "Segoe UI"` no QSS, então essas fontes normalmente não são
renderizadas.

## Fontes de ícones embutidas no qtawesome

O DiskPilot usa apenas ícones `mdi.*`. Os arquivos de fonte ficam dentro do
pacote `qtawesome`, não neste repositório.

| Conjunto | Licença | Usado pelo app |
|---|---|---|
| Material Design Icons 6 | Apache-2.0 (ícones e fontes); MIT (código) | **Sim** (`mdi.folder`, `mdi.help-circle-outline`, `mdi.*`) |
| Font Awesome 5/6 Free | SIL OFL-1.1 (fontes), CC BY 4.0 (ícones), MIT (código) | Não |
| Codicons | CC BY 4.0 (ícones), MIT (código) | Não |
| Phosphor | MIT | Não |
| Remix Icon | Apache-2.0 | Não |
| Elusive Icons | SIL OFL-1.1 / MIT | Não |

## O que isso significa na prática

- **MIT no código do DiskPilot** é compatível com todas as dependências acima:
  MIT é permissiva e pode ser combinada com BSD, Apache-2.0 e LGPL.
- **PySide6/Qt são LGPLv3, não MIT.** Usar o app internamente não gera
  obrigação nenhuma. Se você **redistribuir** o aplicativo (binário congelado
  com PyInstaller/Nuitka, instalador, imagem de máquina), a LGPLv3 exige:
  1. incluir o texto da licença e os avisos de copyright do Qt;
  2. permitir que o usuário substitua as bibliotecas Qt por outra versão
     compatível (o que já acontece enquanto as DLLs forem carregadas
     dinamicamente e não estaticamente ligadas);
  3. oferecer acesso ao código-fonte do Qt (ou link para ele).
- **Não é necessário abrir o código do DiskPilot** por causa da LGPL, desde que
  o vínculo com o Qt continue dinâmico.
- Ao publicar um executável, inclua também os avisos das fontes de ícones.

## Dependências de desenvolvimento

`exportar.py` (empacotamento) usa apenas a biblioteca padrão do Python e o
`pip` para baixar wheels. Não há dependência de build além das listadas acima.
