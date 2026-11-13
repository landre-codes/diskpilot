# DiskPilot

Shell gerencial modular em **Python + PySide6** para análise de uso de disco, com uma GUI replicável em outros domínios.

O projeto nasceu como um "Everything gerencial e enxuto": em vez de apenas localizar arquivos, ele mostra **onde o espaço está sendo consumido**, permite **navegar pelos tamanhos aninhados**, aplica **filtros com debounce** e produz **recomendações de limpeza com diferentes níveis de segurança**.

> Princípio importante: o aplicativo **não apaga arquivos automaticamente**. As recomendações apenas indicam caminhos, explicam o risco e oferecem atalhos para inspeção no Explorer.

> **Aviso de responsabilidade:** o DiskPilot é uma ferramenta de leitura e estimativa. Tamanhos são lógicos e podem diferir do espaço físico; varreduras extensas podem ser parciais; duplicatas são comparadas por nome/tamanho, não por conteúdo. A decisão de remover, mover ou compartilhar dados é integralmente do usuário e da equipe.

---

## Recursos

### Shell / aparência
- Janela sem moldura e sem borda externa, com barra de título própria (slogan centralizado) e redimensionamento nativo nas bordas (Windows).
- Sem `QGraphicsDropShadowEffect`: a sombra gráfica foi removida para evitar artefatos de repintura em janelas translúcidas.
- Instância única por usuário: abrir o app novamente reativa a janela existente em vez de criar outra.
- `Ctrl + roda do mouse` é consumido globalmente para evitar zoom/rolagem acidental em widgets Qt.
- Interface e componentes nativos do Qt em **pt_BR** (`QLocale` + `QTranslator`).
- Botões de minimizar, maximizar/restaurar e fechar com proporções fixas e ícones MDI.
- Duplo clique na barra de título maximiza/restaura; arraste move a janela (inclusive restaurando ao arrastar uma janela maximizada).
- Temas **dark_cyan** e **light_cyan** via `qt-material`, com QSS próprio para cards, tabelas, menus, foco e estados de hover.
- Tipografia maior e adaptativa: o tamanho base acompanha a altura útil da tela e é recalculado ao aplicar o tema.
- Ícones Material Design (MDI) via `qtawesome` em botões, campos de busca, seletores, árvore, diálogos e recomendações.
- Abas verticais com ícones, indicador ativo, tooltip no modo compacto e transição de página com fade.
- Menu hambúrguer com animação de largura; o estado (expandido/recolhido) é persistido.
- Logo da empresa no topo da barra lateral, com clique para alterar, menu de contexto para remover e **persistência local**.
- Usuário atual no rodapé da barra lateral, com avatar gerado a partir das iniciais (ou foto importada). Fotos podem ser **arrastadas para reposicionar** e ajustadas com a **roda do mouse (zoom)**; o enquadramento é salvo localmente e aplicado na sidebar, nas configurações e na prévia do perfil.
- **Seletor de foto próprio**: “Escolher foto” abre um diálogo no mesmo padrão visual do seletor de pastas, com locais (Imagens, Início, Documentos, Downloads, unidades), navegação por caminho, grade de miniaturas, prévia com dimensões/tamanho/data, caminho completo copiável e seleção por duplo clique/Enter. A rotação EXIF é respeitada nas miniaturas e na prévia.

### Painel
- Mini-dashboard com espaço total, quantidade de arquivos/pastas, espaço liberável com segurança e valores em revisão.
- Gráfico de rosca da distribuição por raiz, com total central, percentuais nos arcos e legenda.
- Ranking dos maiores diretórios com barras proporcionais e participação percentual.
- Prévia das recomendações e resumo operacional da última análise.
- Dados persistidos para reaparecerem após reiniciar o app.

### Análise de diretórios
- Seleção de **uma ou várias pastas** pelo seletor próprio (Ctrl+clique), por arrastar e soltar ou por múltiplas adições.
- O seletor de pastas mostra o **caminho completo** da pasta atual ou da pasta selecionada, com botão de copiar; cada linha também exibe o caminho integral em tooltip, útil para caminhos longos e unidades de rede.
- Chips das raízes selecionadas, com remoção individual.
- Varredura em segundo plano com `QThreadPool`, progresso, cancelamento e tolerância a erros de permissão. Logs em `diskpilot.log`/`diskpilot-crash.log` na pasta do projeto e na pasta de configuração.
- Botão **Top 100**: ranking dos 100 maiores diretórios e dos 100 maiores arquivos da análise, com filtro por tamanho (todos, > 100 MB, > 1 GB), tamanho, percentual, caminho completo, cópia do caminho e abertura no Explorer.
- Coluna **Autor** na árvore: mostra o autor gravado nos metadados do arquivo (o campo “Authors” do Windows — funciona para Office, PDF e outros formatos que guardam essa informação). A consulta roda em segundo plano, com cache por caminho, para não travar a interface; o nome também aparece no tooltip e na linha copiada. Pastas e formatos sem metadados de autor aparecem como `—`.
- Colunas com mínimos maiores: **Nome** 280 px, **Tamanho** 124, **% do pai** 90, **Itens** 100, **Modificado** 150, **Autor** 200, **Tipo** 100 e **Caminho completo** 600. Quando a janela não comporta todos os mínimos, a tabela usa rolagem horizontal em vez de esmagar o conteúdo.
- Coluna opcional **Caminho completo** na árvore, ativada pelo checkbox na barra de ferramentas e persistida na configuração. A coluna cresce até o caminho mais longo exibido (sem reticências), mantém **Nome** com no mínimo 280 px e usa rolagem horizontal em janelas estreitas. O caminho do item selecionado também aparece inteiro em um rodapé selecionável.
- Os chips das raízes e a tabela do **Top 100** também exibem o caminho completo; no Top 100 a coluna de caminho cresce até o conteúdo e há um rodapé com o caminho da linha selecionada.
- **Exportação de dados** pelo botão **Exportar** no cabeçalho da análise (ou pelo Top 100): janela com seleção de formato e destino. CSV para Excel/LibreOffice, XLSX com abas Resumo, Top 100 e Sugestões, e XLSB binário (requer Microsoft Excel instalado). A coluna **Autor** também é incluída nos arquivos exportados.
- Os diálogos de abrir/salvar arquivo usam a implementação do Qt (não a nativa do Windows) e a automação do XLSB inicializa/finaliza o COM na mesma thread; isso evita o `RPC_E_WRONG_THREAD` que podia fechar o app ao cancelar uma exportação.
- Árvore aninhada carregada sob demanda, com:
  - tamanho de cada pasta (soma recursiva) e de cada arquivo;
  - percentual em relação ao pai;
  - quantidade de arquivos, data de modificação e tipo;
  - barras proporcionais na coluna de tamanho;
  - limite de itens por pasta para manter a interface responsiva.
- Busca com **debounce de 260 ms** e limpeza rápida. O campo fica alinhado à esquerda e o contador de resultados ocupa o espaço restante, sem elidir o texto quando há largura suficiente.
- Estados vazios com descrição responsiva: a largura acompanha o cartão (até 520 px) e a altura mínima é calculada pelo texto, com margens compactas em janelas baixas — a mensagem “Analisando pastas…” não é cortada.
- Filtros: tudo, pastas, arquivos, arquivos > 100 MB e > 1 GB.
- Conversor de unidade na tabela: automático, KB, MB, GB ou TB.
- Ordenação: tamanho (maior/menor), nome (A–Z/Z–A) e mais recentes.
- Expansão limitada para evitar materializar uma árvore enorme de uma vez.
- Ao pesquisar/filtrar, os ancestrais dos resultados são exibidos automaticamente.
- Menu de contexto: abrir no Explorer, copiar caminho e abrir pasta pai.
- Duplo clique expande pastas ou abre arquivos.

### Recomendações
- Caches regeneráveis (`node_modules`, `__pycache__`, `.next`, `.pytest_cache`, etc.), classificados como **seguros**.
- Artefatos de build e ambientes virtuais (`build`, `dist`, `target`, `.venv`, ...), classificados para **revisão**.
- Arquivos grandes sem alteração há mais de um ano.
- Possíveis duplicatas por nome + tamanho (com aviso de que o conteúdo não foi comparado).
- Arquivos compactados muito grandes e arquivos temporários/backups.
- Caminhos reais, botão para abrir o local e cópia de todos os caminhos para compartilhar com a equipe.
- Nenhuma exclusão automática: o texto de cada card explica o risco e o que verificar antes.

### Configurações
- Troca de tema em tempo real e persistência.
- Alteração do logo da empresa e do perfil (nome e foto), com cópia dos ativos para a pasta de configuração.
- Resumo do armazenamento, última análise e local da configuração.
- Limpeza explícita dos resultados armazenados, mantendo as pastas escolhidas.
- Lista de atalhos de teclado.

---

## Como executar

Pré-requisitos: Python 3.10+ (testado com Python 3.14) e Windows, Linux ou macOS com suporte a Qt.

```powershell
cd "C:\Users\usuario\Desktop\Projetos IA\diskpilot"
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```

Na IDE, basta configurar/executar `main.py`. O `run.py` continua disponível como entrada alternativa. Também é possível executar o pacote com `py -3.14 -m app`, ou usar o atalho:

```text
iniciar.cmd
```

> Se a IDE estiver usando um ambiente virtual próprio, instale as dependências no interpretador selecionado: `python -m pip install -r requirements.txt`.

### Diagnóstico de tela e janela

Se a janela abrir com tamanho estranho, algum botão não responder ou a interface
parecer cortada, rode:

```powershell
py diagnostico.py
```

Ele mostra Python, PySide6, versão do Qt, tela, `devicePixelRatio`, escala e a
geometria em cada etapa de maximizar/restaurar, e grava
`diagnostico-diskpilot.txt` ao lado do script.

---

## Exportar para um ambiente corporativo sem Git

Não é necessário clonar nem usar Git. O projeto é composto por arquivos Python comuns; você pode copiar a pasta ou um ZIP.

Para gerar pacotes de distribuição:

```powershell
cd "C:\Users\usuario\Desktop\Projetos IA\diskpilot"
py -3.14 exportar.py
```

Serão criados em `dist/`:

- `DiskPilot-<versao>-source.zip`: apenas o código-fonte e a documentação;
- `DiskPilot-<versao>-offline-win64.zip`: código + wheels + `instalar_offline.cmd`, para máquinas sem acesso ao PyPI;
- `SHA256SUMS.txt`: hashes para conferir a integridade após a cópia.

### No ambiente corporativo

Com internet/espelho interno do PyPI:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Sem internet, usando o pacote offline:

1. Copie o ZIP offline por pendrive, unidade de rede ou portal interno.
2. Extraia em uma pasta local.
3. Execute `instalar_offline.cmd`.
4. Depois, use `iniciar.cmd`.

O pacote offline atual foi gerado para **Windows x64 + Python 3.10 a 3.14**. Ele contém wheels específicas do MarkupSafe para essas versões; as demais dependências são abi3 ou Python puro.

### E o Git?

Git não é necessário. Se quiser manter histórico e o ambiente interno permitir arquivos `.bundle`, uma alternativa é gerar um único arquivo:

```powershell
git init
git add .
git commit -m "DiskPilot"
git bundle create DiskPilot.bundle --all
```

Copie `DiskPilot.bundle` e, no ambiente interno:

```powershell
git clone DiskPilot.bundle diskpilot
```

Se clones de repositórios forem bloqueados, use o ZIP mesmo — não há dependência de Git no funcionamento do app.

No Windows, o app usa o plugin nativo do Qt e o redimensionamento por `WM_NCHITTEST`; em outras plataformas há fallback de redimensionamento manual.

### Dependências
- `PySide6-Essentials` (módulos Qt usados pelo app, sem WebEngine)
- `qt-material`
- `qtawesome` (tema MDI)
- `openpyxl` (exportação XLSX)
- `pywin32` (exportação XLSB via Microsoft Excel, Windows)

---

## Persistência

As configurações ficam em um JSON no diretório de configuração do usuário (`QStandardPaths.AppConfigLocation`), por exemplo:

```text
C:\Users\<usuario>\AppData\Local\DiskPilot\DiskPilot\config.json
```

São persistidos:

- tema atual;
- geometria/estado da janela;
- estado do menu lateral;
- caminho do logo;
- nome e avatar do usuário;
- pastas selecionadas;
- resumo da última análise (tamanhos, contagens, sugestões e data).

Os arquivos de logo/avatar são copiados para `assets/` ao lado do `config.json`. Mover ou apagar a imagem original não quebra o perfil.

---

## Estrutura

```text
diskpilot/
├─ main.py                      # entrada recomendada para IDE/terminal
├─ run.py                       # entrada alternativa (mesma inicialização)
├─ iniciar.cmd                  # atalho Windows
├─ requirements.txt
├─ README.md
└─ app/
   ├─ __init__.py               # nome, tagline e versão
   ├─ __main__.py               # permite `python -m app`
   ├─ i18n.py                   # locale e traduções pt_BR do Qt
   ├─ input_guard.py            # filtro global de Ctrl+roda do mouse
   ├─ single_instance.py        # instância única + ativação da janela
   ├─ pages.py                  # registro das páginas padrão
   ├─ shell.py                  # janela sem moldura, navegação, atalhos, drag/drop
   ├─ config.py                 # persistência JSON e importação de ativos
   ├─ theme.py                  # paletas, QSS e integração qt-material
   ├─ icons.py                  # cache de ícones MDI e avatares
   ├─ utils.py                  # formatação, Explorer, clipboard
   ├─ widgets/
   │  ├─ buttons.py             # botões com hover, abas desenhadas, busca, selects
   │  ├─ charts.py              # donut e barras com QPainter
   │  ├─ common.py              # cards, headers, chips, empty state, toast
   │  ├─ dialogs.py             # seletor de pastas, perfil, confirmação
   │  ├─ sidebar.py             # logo, abas verticais, usuário
   │  └─ title_bar.py           # controles da janela
   ├─ services/
   │  ├─ model.py               # Node, ScanResult, Suggestion
   │  ├─ scanner.py             # varredura recursiva cancelável
   │  ├─ suggestions.py         # heurísticas de limpeza
   │  └─ state.py               # estado compartilhado + QThreadPool
   └─ features/
      ├─ base.py                # BasePage e PageSpec
      ├─ dashboard.py
      ├─ recommendations.py
      ├─ settings.py
      └─ analyzer/
         ├─ page.py
         └─ tree.py
```

---

## Como reutilizar o shell em outro domínio

O shell não conhece o domínio de disco. Ele apenas recebe uma lista de `PageSpec` e instancia as páginas:

```python
from app.config import AppConfig
from app.features.base import PageSpec
from app.shell import MainWindow
from app.theme import init_theme

# 1. Crie uma página herdando de BasePage
# 2. Registre-a com PageSpec
# 3. Passe a lista para MainWindow

specs = [
    PageSpec("dashboard", "Visão geral", "Resumo", "view-dashboard-outline", DashboardPage),
    PageSpec("clientes", "Clientes", "Cadastro e histórico", "account-group-outline", ClientesPage),
    PageSpec("config", "Configurações", "Preferências", "cog-outline", MinhaConfigPage),
]

theme = init_theme(app, config)
window = MainWindow(config, theme, specs)
window.show()
```

`BasePage` fornece:

- `self.state`: estado compartilhado;
- `toastRequested`, `navigateRequested`, `identityChanged`;
- `on_show()` / `on_hide()`;
- `toast(mensagem, tipo)`.

Para mudar o nome do produto, altere `APP_NAME`/`APP_TAGLINE` em `app/__init__.py`. Para mudar a identidade visual, trabalhe com os tokens de `app/theme.py`; evite cores hardcoded nos widgets.

### Criando um tema
As paletas ficam em `PALETTES` em `theme.py` (`dark` e `light`). O QSS usa `$tokens`, então novos componentes devem usar as mesmas variáveis para funcionar nos dois temas.

### Criando uma página de feature
```python
from app.features.base import BasePage
from app.widgets.common import PageHeader

class ClientesPage(BasePage):
    page_id = "clientes"
    page_title = "Clientes"
    page_icon = "account-group-outline"

    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        layout = QVBoxLayout(self)
        layout.addWidget(PageHeader("Clientes", "Cadastro e histórico", "CRM"))
        # ...
```

---

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+O` | Adicionar pastas |
| `Ctrl+F` | Pesquisar na análise |
| `Ctrl+R` | Reanalisar |
| `Ctrl+B` | Recolher/expandir menu lateral |
| `F11` | Alternar tela cheia |
| `Ctrl+1…4` | Ir direto para uma aba |
| `Esc` | Sair da tela cheia |

---

## Notas de implementação

- A varredura usa `os.scandir`, ignora links simbólicos para evitar ciclos e contabiliza erros de acesso sem interromper a análise.
- Os tamanhos são **lógicos** (`st_size`), que é o valor esperado em um gerenciador de arquivos. Arquivos esparsos, comprimidos ou com hard links podem ocupar menos espaço físico do que o valor exibido.
- A árvore é preguiçosa: os filhos de uma pasta só são criados quando ela é expandida, com limite de 1.200 itens por pasta e busca global limitada para manter a responsividade.
- As estimativas de limpeza não são destrutivas e podem se sobrepor; os cálculos já evitam contar arquivos de cache duas vezes e mostram "seguro" separado de "revisar".
- O logo e o avatar são copiados com `shutil`, não vinculados ao arquivo original.
- `circular_pixmap` pinta a imagem em coordenadas físicas e só aplica o `devicePixelRatio` no final; aceita `focus_x`, `focus_y` e `zoom`, permitindo o enquadramento ajustável do avatar. A imagem é carregada com `QImageReader.autoTransform`, então a rotação EXIF de fotos de celular é respeitada (antes a foto aparecia girada 90°). As prévias em `QLabel` usam `setScaledContents(True)` para não cortar o canto do pixmap em telas com DPI alto.
- O perfil salva `user.avatar_focus_x`, `user.avatar_focus_y` e `user.avatar_zoom`. No diálogo de perfil, arraste a foto para reposicionar e use a roda do mouse para ampliar; “Centralizar” volta ao ponto central.
- A exportação de dados usa `csv` (BOM UTF-8 e separador `;`), `openpyxl` (XLSX com abas de resumo, Top 100 e sugestões) e `pywin32` + Microsoft Excel (XLSB). O XLSB é gerado a partir do XLSX temporário com `FileFormat=50`; se o Excel ou o pywin32 não estiverem disponíveis, o app informa o requisito em vez de falhar silenciosamente.
- O `sidebar.py` detecta se `icons.py` aceita o parâmetro `dpr` (adicionado na 1.3.4) e chama `avatar_pixmap`/`circular_pixmap` com ou sem ele. Assim, uma atualização parcial de arquivos não quebra o avatar com `TypeError`.
- O seletor de pastas mostra unidades mapeadas pelo **caminho UNC** (`\\servidor\compartilhamento`) em vez da letra (`W:\`), e navega pelos nomes das pastas de rede quando o compartilhamento está acessível.
- O seletor de pastas usa `QFileSystemModel` e exibe o caminho completo do item atual/selecionado em um rótulo selecionável (com cópia), além de tooltip por linha. O caminho não é abreviado, o que ajuda em compartilhamentos de rede.
- O banner de progresso e a lista de caminhos das recomendações mostram o caminho integral: o banner usa quebra de linha e a lista usa rolagem horizontal. A função `short_path` foi removida do projeto.
- Unidades mapeadas são resolvidas via `QStorageInfo.device()`: quando o `\\servidor\compartilhamento` equivalente está acessível, o seletor, as raízes e o banner passam a usar o caminho UNC em vez de `W:\`/`Z:\`.
- O ranking **Top 100** percorre a árvore em memória com `heapq.nlargest` (duas passagens: diretórios e arquivos), sem ordenar todos os nós. Percentuais de diretórios são cumulativos e podem se sobrepor.
- **Memória**: diálogos transitórios são destruídos com `deleteLater`, menus e animações são liberados/reutilizados, e o resultado grande anterior é descartado antes de uma nova varredura (`RELEASE_RESULT_THRESHOLD`). A varredura tem limite de 1,5 milhão de entradas; o resumo persistido guarda apenas os 6 maiores diretórios, calculados com `heapq.nlargest`.
- **Expansão da árvore**: os filhos de uma pasta são carregados em lotes de 120 itens, com debounce de 60 ms. A árvore mostra “Carregando…” enquanto isso, mantém a contagem incremental e restaura as pastas expandidas após uma reordenação. Ícones de arquivo são cacheados por extensão, e a ordenação dos filhos usa `heapq.nlargest/nsmallest` com o limite de 1.200 itens exibidos.
- `qt-material` fornece a base do tema; o QSS em `theme.py` sobrescreve o que é necessário (especialmente `text-transform`, hovers e cores semânticas) para manter a identidade do app.
- A geometria inicial e a restaurada são limitadas à área útil da tela: em notebooks pequenos (ou com escala de 125%/150%) a janela não nasce maior que o monitor, então a barra de título e os botões de janela continuam clicáveis. O tamanho mínimo também se adapta ao monitor.
- O `WM_NCHITTEST` nativo converte a posição do cursor para o espaço lógico do Qt antes de detectar as bordas. Sem isso, em telas com escala o canto direito inteiro era confundido com borda de redimensionamento e os botões de maximizar/fechar não respondiam — o usuário precisava maximizar com duplo clique no meio da barra.
- O filtro global de `Ctrl+roda` é removido no `aboutToQuit` (`CtrlWheelGuard.stop`) e não chama `super().eventFilter` durante o teardown. Isso evita a recursão de `RuntimeError`/objetos C++ já destruídos no encerramento do Python/Qt.
- Auditoria estática (`ruff check --select F`) sem erros: imports não utilizados foram removidos e os módulos novos (`services/exporter.py`, filtros do Top 100 e coluna de caminho) passaram por compilação e testes de fumaça.
- Maximizar e restaurar são controlados pelo próprio app, e não por `showMaximized()`: em janelas sem moldura o `normalGeometry()` do Qt pode crescer a cada ciclo e devolver um retângulo maior que a tela. O estado salvo (geometria e maximizado) é aplicado antes do primeiro `show`, para a janela não piscar em tamanhos intermediários.
- A janela tem **tamanho máximo igual à área útil da tela** (e a posição é limitada para manter a barra de título alcançável), então nenhum salto de layout consegue empurrar os botões para fora do monitor. O log registra tela, escala e geometria em cada maximizar/restaurar para diagnóstico.
- A troca de tema usa **cache de QSS por tema** e uma única chamada a `setStyleSheet`. A geração de ícones do `qt_material` (que reescrevia centenas de SVG em `~/.qt_material` a cada troca) é desativada — o app usa apenas qtawesome —, e o QSS do outro tema é pré-montado em segundo plano após a abertura.
- A árvore desenha as **setas de expandir/recolher** e as guias de hierarquia em `drawBranches`, com a cor do tema, porque o QSS de `::branch` desliga o indicador nativo. O clique na seta alterna o nó.
- A árvore aceita `Ctrl+C` e menu de contexto para copiar **linha(s)** (Nome, Tamanho, %, Itens, Modificado, Autor, Tipo e Caminho, separados por tabulação), **tamanho** ou **caminho**. A seleção múltipla copia todas as linhas escolhidas.
- O autor é lido pelo Windows Property System (`System.Author`/`PKEY_Author`) em um pool de threads, com cache por caminho; há fallback para `docProps/core.xml` (OOXML) e `/Author` (PDF) quando o Property System não responde. Falhas de rede/permissão e arquivos sem metadados aparecem como `—`.
- Textos de `QLineEdit`, `QComboBox` e `QAbstractSpinBox` usam o token `input_text`: claro no tema escuro e **azul-escuro** (`#06232b`) no tema claro. A cor também é fixada nos estados `:hover` e `:focus`, e o placeholder usa o token `placeholder` (mais escuro no tema claro), garantindo contraste.
- Os estados de hover usam os tokens `hover`/`hover_border`, com contraste próprio em cada tema (no claro, `#d8ebef`), em vez de reutilizar `surface_2`/`surface_3`. Isso inclui os hovers desenhados à mão das abas verticais, do logo e do cartão do usuário — antes o `surface_2` ficava quase invisível sobre o `sidebar` no tema claro.
- A barra de título é **responsiva e sem moldura**: o título e o slogan usam rótulos que elidem (reticências) em vez de empurrar o layout. O slogan "Gestor de espaço" fica centralizado no meio exato da barra e não intercepta cliques — arraste e duplo clique funcionam em toda a barra.

---

## Limitações e próximos passos

- Não há exclusão em massa; isso é intencional por segurança.
- Duplicatas são detectadas por nome + tamanho; uma evolução natural é comparar hashes em segundo plano.
- O redimensionamento nativo por `WM_NCHITTEST` é específico do Windows; o fallback manual cobre outras plataformas.
- Para volumes muito grandes (milhões de itens), considere persistir a árvore em SQLite ou manter uma indexação incremental.
- O shell pode receber novas páginas sem alterações na janela principal.

---

## Licença

O código original do DiskPilot é distribuído sob a **licença MIT** — veja
[`LICENSE`](LICENSE).

As dependências mantêm suas próprias licenças e **não** são relicenciadas por
este projeto. As principais:

| Componente | Licença |
|---|---|
| PySide6 / Qt (via PySide6-Essentials, shiboken6) | LGPL-3.0-only (ou GPL / comercial) |
| qt-material | BSD-2-Clause |
| qtawesome | MIT |
| openpyxl / et-xmlfile | MIT |
| pywin32 | PSF-2.0 |
| Material Design Icons (fonte usada nos ícones) | Apache-2.0 |

O inventário completo, com as obrigações da LGPLv3 em caso de redistribuição
binária do aplicativo, está em [`THIRD-PARTY.md`](THIRD-PARTY.md).
