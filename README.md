# DiskPilot

Shell gerencial modular em **Python + PySide6** para análise de uso de disco, com uma GUI replicável em outros domínios.

O projeto nasceu como um "Everything gerencial e enxuto": em vez de apenas localizar arquivos, ele mostra **onde o espaço está sendo consumido**, permite **navegar pelos tamanhos aninhados**, aplica **filtros com debounce** e produz **recomendações de limpeza com diferentes níveis de segurança**.

> Princípio importante: o aplicativo **não apaga arquivos automaticamente**. As recomendações apenas indicam caminhos, explicam o risco e oferecem atalhos para inspeção no Explorer.

> **Aviso de responsabilidade:** o DiskPilot é uma ferramenta de leitura e estimativa. Tamanhos são lógicos e podem diferir do espaço físico; varreduras extensas podem ser parciais; duplicatas são comparadas apenas por nome/tamanho, sem leitura do conteúdo. A decisão de remover, mover ou compartilhar dados é integralmente do usuário e da equipe.

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
- Marca **fixa** do DiskPilot no topo da barra lateral, parte da identidade visual do produto. Não é configurável.
- Usuário atual no rodapé da barra lateral, com avatar gerado a partir das iniciais (ou foto importada). Fotos podem ser **arrastadas para reposicionar** e ajustadas com a **roda do mouse (zoom)**; o enquadramento é salvo localmente e aplicado na sidebar, nas configurações e na prévia do perfil.
- **Seletor de foto próprio**: “Escolher foto” abre um diálogo no mesmo padrão visual do seletor de pastas, com locais (Imagens, Início, Documentos, Downloads, unidades), navegação por caminho, grade de miniaturas, prévia com dimensões/tamanho/data, caminho completo copiável e seleção por duplo clique/Enter. A rotação EXIF é respeitada nas miniaturas e na prévia. A pasta é enumerada em segundo plano e a grade é preenchida em lotes, então o diálogo abre mesmo com dezenas de milhares de imagens.
- **Diálogos redimensionáveis e roláveis**: as janelas sem moldura (perfil, exportação, Top 100, seletores e confirmação) usam uma área de rolagem no corpo, tamanho mínimo confortável e uma alça própria no canto inferior direito. O conteúdo deixa de ser cortado em telas com DPI alto e o aviso `Unable to set geometry` deixa de aparecer.

### Painel
- Mini-dashboard com espaço total, quantidade de arquivos/pastas, espaço liberável com segurança e valores em revisão.
- Gráfico de rosca da distribuição por raiz, com total central, percentuais nos arcos e legenda.
- Ranking dos maiores diretórios com barras proporcionais e participação percentual.
- Prévia das recomendações e resumo operacional da última análise.
- Dados persistidos para reaparecerem após reiniciar o app.

### Análise de diretórios
- Seleção de **uma ou várias pastas** pelo seletor próprio (Ctrl+clique), por arrastar e soltar ou por múltiplas adições.
- O seletor de pastas mostra o **caminho completo** da pasta atual ou da pasta selecionada, com botão de copiar; cada linha também exibe o caminho integral em tooltip, útil para caminhos longos e unidades de rede.
- Chips das raízes selecionadas, com o **nome da pasta** visível e o caminho completo no tooltip; remoção individual. Ao adicionar pastas com um resultado já existente, apenas as novas raízes são varridas e o resultado anterior é preservado; raízes aninhadas ou resultados truncados disparam uma reanálise completa.
- Falhas de permissão não interrompem a análise: a pasta ou entrada inacessível é registrada como aviso categorizado (permissão negada, item removido, caminho longo ou erro de I/O), o restante da árvore continua e o total aparece no cabeçalho, com detalhes sob demanda. Caminhos completos não são persistidos nesse resumo.
- Varredura em segundo plano com `QThreadPool`, progresso agregado, cancelamento e tolerância a erros de permissão. Várias raízes são varridas em paralelo (até 4 workers) quando o motor é memória. O motor indexado grava os nós diretamente no SQLite durante a varredura e mantém somente a raiz e os diretórios abertos em RAM; a árvore é carregada sob demanda. O limite é compartilhado e calculado pela memória disponível (piso de 250 mil, teto de 5 milhões de entradas; `scan.max_entries` pode reduzir o valor). O progresso combina arquivos, pastas e bytes das raízes ativas. Logs em `~/DiskPilot/logs/diskpilot.log` e `diskpilot-crash.log` por padrão, com pasta configurável pela página **Logs**.
- Botão **Top 100**: ranking dos 100 maiores diretórios e dos 100 maiores arquivos da análise, com filtro por tamanho (todos, > 100 MB, > 1 GB), tamanho, percentual, caminho completo, cópia do caminho e abertura no Explorer. O ranking é calculado em uma thread de trabalho; o diálogo abre imediatamente e mostra “Carregando ranking…”.
- Coluna **Autor** na árvore: mostra o autor gravado nos metadados do arquivo (o campo “Authors” do Windows — funciona para Office, PDF e outros formatos que guardam essa informação). A consulta roda em segundo plano, com cache por caminho, para não travar a interface; o nome também aparece no tooltip e na linha copiada. Pastas e formatos sem metadados de autor aparecem como `—`.
- Colunas com mínimos maiores: **Nome** 280 px, **Tamanho** 124, **% do pai** 90, **Itens** 100, **Modificado** 150, **Autor** 200, **Tipo** 100 e **Caminho completo** 600. Quando a janela não comporta todos os mínimos, a tabela usa rolagem horizontal em vez de esmagar o conteúdo.
- Coluna opcional **Caminho completo** na árvore, ativada pelo checkbox na barra de ferramentas e persistida na configuração. A coluna cresce até o caminho mais longo exibido (sem reticências), mantém **Nome** com no mínimo 280 px e usa rolagem horizontal em janelas estreitas. O caminho do item selecionado também aparece inteiro em um rodapé selecionável.
- Os chips das raízes mostram o nome da pasta, com o caminho completo no tooltip; a tabela do **Top 100** também exibe o caminho completo; no Top 100 a coluna de caminho cresce até o conteúdo e há um rodapé com o caminho da linha selecionada.
- **Exportação de dados** pelo botão **Exportar** no cabeçalho da análise (ou pelo Top 100): janela com seleção de formato, **pasta de destino editável**, nome do arquivo e prévia do caminho. A pasta é escolhida pelo seletor próprio (mesmo padrão dos Locais do seletor de fotos), sem `QFileDialog`. CSV para Excel/LibreOffice, XLSX com abas Resumo, Top 100 e Sugestões, e XLSB binário (requer Microsoft Excel instalado). A coluna **Autor** também é incluída nos arquivos exportados.
- A gravação da exportação roda em uma **thread separada** (QThreadPool): a janela permanece responsiva e o XLSB inicializa/finaliza o COM na mesma thread, evitando o `RPC_E_WRONG_THREAD` que podia fechar o app ao cancelar uma exportação. O cálculo do Top 100 usado na exportação também foi movido para essa thread: a janela de exportação abre imediatamente, mesmo com milhões de nós na árvore.
- Árvore aninhada carregada sob demanda, com:
  - tamanho de cada pasta (soma recursiva) e de cada arquivo;
  - percentual em relação ao pai;
  - quantidade de arquivos, data de modificação e tipo;
  - barras proporcionais na coluna de tamanho;
  - limite de itens por pasta para manter a interface responsiva.
- Busca com **debounce de 260 ms** e limpeza rápida. No motor indexado, a busca usa FTS5/trigram diretamente no SQLite e monta apenas os ramos correspondentes; no modo memória, a varredura percorre a árvore em segundo plano. A renderização é limitada para manter a interface fluida. O campo fica alinhado à esquerda e o contador de resultados ocupa o espaço restante, sem elidir o texto quando há largura suficiente.
- Toda análise concluída mantém um **índice SQLite com FTS5** usado para busca, top 100, resumo e persistência. No motor indexado, o próprio scanner grava os nós no SQLite e a árvore é lazy; no modo memória, o índice é construído depois da varredura. A busca cai para memória se o índice não estiver disponível. O índice usa identidade exata do caminho (preservando maiúsculas/minúsculas) e uma chave normalizada separada; caminhos literalmente repetidos são reportados como `duplicate_path`.
- Diagnóstico local opt-in do índice: defina `DISKPILOT_INDEX_DIAGNOSTICS=1` (ou uma pasta) para gravar um JSON com caminhos completos quando houver colisão. Fica desativado por padrão por privacidade; os logs normais só registram categorias, contagens e hashes.
- Índices persistentes criados por versões anteriores, sem `path_exact`, continuam aceitos: as sugestões indexadas usam `path` como fallback e o merge de raízes lê o esquema legado. Falhas de SQL no cálculo de sugestões agora são registradas no log em vez de sumirem silenciosamente.
- As sugestões indexadas consultam apenas os candidatos acima dos limiares (antigos, duplicatas, compactados e temporários) e filtram os milhares de caches/builds em Python; não varrem 1,4 milhão de nós nem estouram o limite de variáveis/expressão do SQLite. As consultas usam cursores com lotes limitados (`fetchmany`) e mantêm em memória apenas os exemplos exibidos e os maiores grupos de duplicatas, sem `fetchall()` sobre todos os candidatos. No índice real de 1,37 milhão de entradas, o cálculo caiu de ~71 s para ~1,4 s.
- **Reanalisar** (botão ou `Ctrl+R`) com uma análise em andamento pede confirmação antes de cancelar a atual.
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
- Possíveis duplicatas por **nome + tamanho**, sem ler o conteúdo dos arquivos. Os mais pesados aparecem primeiro, o que já permite liberar espaço com uma revisão manual.
- A página de recomendações reutiliza os cards já montados ao navegar; não refaz a análise nem consulta o disco para decidir ícones. Isso evita travamentos em caminhos de rede.
- “Adicionar pastas” abre o diálogo imediatamente e lista as subpastas em segundo plano, sem `QFileSystemModel`: a enumeração usa `os.scandir` em um worker e um `QListView` com modelo leve. A rolagem não faz I/O e não cria widgets por linha, então pastas com milhares de subpastas continuam fluidas mesmo em shares de rede. Unidades mapeadas são resolvidas sem `os.path.isdir` no UNC.
- Arquivos compactados muito grandes e arquivos temporários/backups.
- Caminhos reais, botão para abrir o local e cópia de todos os caminhos para compartilhar com a equipe.
- Nenhuma exclusão automática: o texto de cada card explica o risco e o que verificar antes.

### Logs e diagnóstico
- Página **Logs** com terminal monoespaçado em **verde**, ícones Material coerentes por nível (`information-outline` INFO, `alert-outline` WARNING, `alert-octagon-outline` ERROR, `bug-outline` DEBUG), datas no formato **dd/mm/aaaa HH:MM:SS** e texto selecionável.
- Reajustes internos de geometria/maximizar/restaurar são registrados em **DEBUG** e não aparecem no log normal (INFO), mantendo o terminal focado em eventos da aplicação.
- Alternância entre o log do aplicativo e o **crash log**, filtro por nível, busca por texto (inclusive pela data brasileira) e acompanhamento em tempo real.
- Botões **Copiar terminal** e **Copiar diagnóstico** (versão, SO, Python, Qt, raízes, última análise e últimas linhas).
- Pasta padrão `~/DiskPilot/logs`; **Alterar pasta…** migra o log e o crash log atuais sem reiniciar, e **Padrão** volta ao diretório do usuário.
- Arquivos rotativos de 2 MB com 3 backups e **retenção máxima de 3 dias** no conteúdo e nos backups; logs antigos da pasta de configuração são importados no primeiro uso do novo padrão.

### Configurações
- Troca de tema em tempo real e persistência.
- Alteração do perfil (nome e foto), com cópia da imagem para a pasta de configuração.
- Crédito **© 2026 Landre Codes** no rodapé da barra lateral, no cartão **Sobre** e no diagnóstico copiável; o rodapé tem tooltip “Desenvolvido por Landre Codes”.
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

> Não execute arquivos internos como `app/features/settings.py` diretamente.
> Imports como `from .. import APP_NAME` exigem que o módulo seja importado como
> parte do pacote; rodar o arquivo como script gera
> `attempted relative import with no known parent package`.
> Mantenha o *working directory* da IDE na raiz do projeto.

> Se a IDE estiver usando um ambiente virtual próprio, instale as dependências no interpretador selecionado: `python -m pip install -r requirements.txt`.

### Testes automatizados

A suíte usa **pytest + QtBot** e roda com o plugin offscreen, sem abrir janelas reais:

```powershell
py -3.14 -m pip install -r requirements-dev.txt
py -3.14 -m pytest -q
```

O `pyproject.toml` limita a coleta a `tests/`; o template em `templates/basic` deve ser validado como projeto gerado independente.

Ela cobre a ordenação do Top 100, a varredura paralela com orçamento compartilhado, o seletor de pastas, a exportação CSV, o seletor de imagens em segundo plano e o carregamento assíncrono do Top 100.

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
- nome e avatar do usuário;
- pastas selecionadas;
- resumo agregado da última análise (tamanhos, contagens, data, economia e avisos), **sem** os caminhos das sugestões nem o Top 6 de diretórios;
- histórico dos últimos **50 snapshots** (`scan.history`), com totais, economia identificada e totais por raiz — sem listas de arquivos;
- o índice SQLite da última análise (`scan.index_path`), o snapshot anterior para rollback (`scan.index_previous_path`) e as raízes efetivamente persistidas (`scan.indexed_roots`);
- o motor de análise (`scan.engine`: `auto`/`stream`/`memory`), o limite manual opcional (`scan.max_entries`), a retenção do índice anterior (`scan.index_previous_days`) e a quota (`scan.index_max_gb`). O fallback para memória em falha do SQLite é controlado por `scan.allow_memory_fallback` e fica **desativado por padrão**; quando ativado, o orçamento é reduzido para o piso de 250 mil entradas.

Ao abrir o app, o índice ativo é carregado em segundo plano. No motor indexado, o `ScanResult` é montado apenas com as raízes e os totais; os filhos são consultados no SQLite quando a pasta é expandida, então a árvore, o Top 100, a exportação e a busca voltam sem reexecutar a varredura e sem reconstruir milhões de nós em RAM. As sugestões detalhadas e o Top 6 ficam na tabela `meta` do próprio índice (`summary_json`), e são reutilizados no restore somente quando data, raízes, caminho do índice, contagem de nós e totais coincidem, evitando recalcular todos os arquivos e o risco de exibir sugestões de outro snapshot; resumos antigos gravados no `config.json` ainda são aceitos e migrados na primeira restauração, e se não houver resumo compatível o cálculo é refeito. O modo memória reconstrói o `ScanResult` completo. Se o índice ativo estiver ausente ou inválido, o app tenta o snapshot anterior; se a configuração perdeu a referência, ele ainda tenta os índices `search-*.sqlite` gerenciados mais recentes antes de limpar a referência. O banco inválido não é apagado imediatamente: ele permanece disponível para inspeção e pode ser removido pelo GC depois da carência.

A publicação do índice é uma operação com rollback: o banco novo só passa a ser o ativo depois que o resumo é gravado na `meta` e `config.json` é gravado com sucesso. Se a gravação do resumo ou da configuração falhar, o snapshot anterior continua referenciado e o banco novo não publicado é descartado. Como o resumo detalhado vive no índice, não há duas fontes de verdade para divergir. O índice anterior é mantido como rollback; a limpeza de órfãos só ocorre depois da publicação, com proteção explícita do ativo, do anterior e de bancos em construção. A remoção automática só aceita arquivos `search-<uuid>.sqlite` dentro da pasta gerenciada pelo DiskPilot.

O índice grava `schema_version`, `complete`, `node_count`, as raízes e o resumo detalhado (`summary_json`) em uma tabela `meta`. Na restauração, o app rejeita snapshots incompletos, versões incompatíveis, hierarquias com `parent_id` inexistente ou não anterior ao filho (ciclos, inclusive `parent_id = id`), `root_id` inconsistente e contagens divergentes. No modo indexado, a validação é feita por consultas de contagem e integridade, sem materializar a árvore; no modo memória, a leitura usa lotes. O cancelamento é cooperativo, inclusive durante consultas SQLite. O `config.json` mantém apenas os agregados para o dashboard e as configurações.

Se uma pasta foi adicionada mas o novo índice ainda não foi publicado, a reabertura mantém o snapshot anterior e sinaliza a raiz como pendente no cabeçalho da análise; os totais exibidos são os do snapshot, não uma mistura com a pasta ainda não indexada. Inclusões solicitadas durante a restauração ficam enfileiradas e só são varridas depois que o snapshot é carregado, evitando uma varredura completa concorrente.

A imagem do avatar é copiada para `assets/` ao lado do `config.json`. Mover ou apagar a imagem original não quebra o perfil; a marca do app é fixa.

### Índices em disco

O índice fica em `<pasta de configurações>/index`, por exemplo
`C:\Users\<usuario>\AppData\Local\DiskPilot\DiskPilot\index`, com arquivos
`search-<uuid>.sqlite` (e auxiliares `-wal`/`-shm` durante a escrita).

- O índice **ativo** é mantido no fechamento normal e restaurado na próxima
  abertura.
- O índice **anterior** é mantido como rollback (`scan.index_previous_path`)
  por até **7 dias** (`scan.index_previous_days`) ou até a quota de espaço
  (`scan.index_max_gb`, padrão **8 GB**) ser pressionada, desde que o ativo já
  tenha sido restaurado com sucesso e o anterior tenha pelo menos 24 horas.
- Índices órfãos, não referenciados por ativo/anterior e com mais de 24 horas,
  são removidos após uma publicação/restauração bem-sucedida e também por um
  timer diário de retenção.
- Ao limpar os resultados, os índices ativo e anterior são removidos e as
  referências são zeradas.
- O botão **Limpar índice anterior** nas Configurações remove apenas o
  snapshot de rollback, preservando o ativo.
- Um índice inválido/ausente tem a referência limpa, mas o arquivo não é
  apagado imediatamente: ele fica disponível para inspeção e só pode ser
  removido pelo GC depois da carência.
- O índice temporário usado na consolidação de raízes é removido assim que o
  merge termina ou falha.

O tamanho do banco é proporcional ao **número de nós e ao texto dos
caminhos/FTS5**, não ao volume de bytes analisado. Em análises com milhões de
entradas, alguns GB são esperados; o planejamento de disco deve considerar
ativo + anterior (e, transitoriamente, o índice em construção/merge). Antes de
criar ou consolidar o índice, o app verifica o espaço livre e falha cedo,
preservando o snapshot anterior, quando não há margem para o banco, o merge e o
WAL.

Configurações corrompidas são copiadas para `config.corrompido-<data>.json`; o app mantém apenas os cinco backups mais recentes. A última configuração gravada com sucesso também fica em `config.good.json` e é usada para recuperar tema, pastas e preferências quando o JSON principal está corrompido; esse backup remove `suggestions` e `top_dirs` do resumo para não propagar caminhos detalhados. Staging de exportação (`diskpilot-xlsb-*`, `diskpilot-export-*`) é removido na saída normal e, após 24 horas, na inicialização seguinte. A limpeza só atua em diretórios com esses prefixos no diretório temporário do sistema e que tenham o marcador `.diskpilot-owner`, evitando apagar pastas de terceiros com nome parecido.

---

## Estrutura

```text
diskpilot/
├─ main.py                      # entrada recomendada para IDE/terminal
├─ run.py                       # entrada alternativa (mesma inicialização)
├─ iniciar.cmd                  # atalho Windows
├─ requirements.txt
├─ requirements-dev.txt          # pytest, pytest-qt e ruff (somente desenvolvimento)
├─ README.md
├─ tests/                        # suíte pytest + QtBot
│  ├─ conftest.py
│  ├─ test_appshell.py
│  ├─ test_model.py
│  ├─ test_scanner.py
│  ├─ test_shell.py
│  ├─ test_state.py
│  ├─ test_tree.py
│  ├─ test_index_store.py
│  ├─ test_utils.py
│  └─ test_dialogs.py
├─ templates/
│  └─ basic/                    # scaffold Copier: appshell + NotesPage
├─ appshell/                     # núcleo genérico, sem dependência de app/
│  ├─ config.py                 # JsonSettings + preferências genéricas
│  ├─ context.py                # AppContext e SettingsStore
│  ├─ pages.py                  # BasePage e PageSpec
│  ├─ tasks.py                  # Task, TaskSignals e TaskRunner
│  ├─ theme.py                  # paletas, QSS e integração qt-material
│  ├─ icons.py                  # cache de ícones MDI e avatares
│  ├─ utils.py                  # formatação, Explorer, clipboard
│  ├─ shell.py                  # ShellWindow, ShellOptions e FadeStack
│  ├─ widgets/
│  │  ├─ buttons.py             # botões com hover, abas desenhadas, busca, selects
│  │  ├─ charts.py              # donut e barras com QPainter
│  │  ├─ common.py              # cards, headers, chips, empty state, toast
│  │  ├─ dialogs.py             # SheetDialog, confirmação e resize grip
│  │  ├─ sidebar.py             # marca configurável, abas verticais, usuário
│  │  └─ title_bar.py           # controles da janela
│  └─ README.md                 # como reutilizar o núcleo
└─ app/
   ├─ __init__.py               # nome, tagline e versão
   ├─ __main__.py               # permite `python -m app`
   ├─ i18n.py                   # locale e traduções pt_BR do Qt
   ├─ input_guard.py            # filtro global de Ctrl+roda do mouse
   ├─ single_instance.py        # instância única + ativação da janela
   ├─ pages.py                  # registro das páginas padrão
   ├─ shell.py                  # composição do DiskPilot sobre appshell
   ├─ config.py                 # defaults de disco e propriedade roots
   ├─ logging_setup.py          # logs rotativos, crash log e migração
   ├─ widgets/
   │  └─ dialogs.py             # seletores, perfil, exportação e Top 100
   ├─ services/
   │  ├─ model.py               # Node, ScanResult, Suggestion
   │  ├─ scanner.py             # varredura recursiva cancelável
   │  ├─ index_store.py         # índice SQLite/FTS5 e persistência
   │  ├─ suggestions.py         # heurísticas de limpeza
   │  └─ state.py               # estado compartilhado + TaskRunner
   └─ features/
      ├─ base.py                # reexporta BasePage e PageSpec de appshell
      ├─ dashboard.py
      ├─ logs.py                # terminal de logs e diagnóstico
      ├─ recommendations.py
      ├─ settings.py
      └─ analyzer/
         ├─ page.py
         └─ tree.py
```

---

## Como reutilizar o shell em outro domínio

A camada genérica vive em `appshell/` e não importa nada de `app/`. O app monta
tudo no composition root: configuração, tema, contexto, páginas e chrome.

```python
from appshell.pages import BasePage, PageSpec
from appshell.shell import ShellOptions, ShellWindow

specs = [
    PageSpec("dashboard", "Visão geral", "Resumo", "view-dashboard-outline", DashboardPage),
    PageSpec("clientes", "Clientes", "Cadastro e histórico", "account-group-outline", ClientesPage),
    PageSpec("config", "Configurações", "Preferências", "cog-outline", MinhaConfigPage),
]

window = ShellWindow(
    config,
    theme,
    specs,
    context,
    options=ShellOptions(title="Meu App", tagline="Gestor de clientes"),
    title_bar_factory=lambda title, tagline, parent: TitleBar(title, tagline, parent),
    sidebar_factory=lambda pages, parent: Sidebar(config, pages, parent),
    toast_factory=lambda parent: Toast(parent),
    close_requested=context.shutdown,
)
window.show()
```

`BasePage` fornece:

- `self.state`: contexto compartilhado (o `AppContext` do app);
- `toastRequested`, `navigateRequested`, `identityChanged`;
- `on_show()` / `on_hide()`;
- `toast(mensagem, tipo)`.

Para mudar o nome do produto, altere `APP_NAME`/`APP_TAGLINE` em `app/__init__.py`.
Para mudar a identidade visual, trabalhe com os tokens de `appshell/theme.py`; evite cores hardcoded nos widgets. O `appshell/README.md` traz um exemplo mínimo de composição e as regras de desacoplamento.

### Gerando um app novo com Copier

O template fica em `templates/basic/` e gera um projeto autocontido: a feature
de exemplo (`NotesPage`) e uma cópia do `appshell/` são incluídas no destino.

```powershell
py -3.14 -m pip install copier
py -3.14 -m copier copy templates/basic "C:\Projetos\meu_app" --trust
```

O `--trust` é necessário porque o template executa uma tarefa que copia o
`appshell/` para o projeto gerado. Depois:

```powershell
cd "C:\Projetos\meu_app"
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```

### Criando um tema
As paletas ficam em `PALETTES` em `appshell/theme.py` (`dark` e `light`). O QSS usa `$tokens`, então novos componentes devem usar as mesmas variáveis para funcionar nos dois temas.

### Criando uma página de feature
```python
from appshell.pages import BasePage
from appshell.widgets.common import PageHeader

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

- A varredura usa `os.scandir`, ignora links simbólicos para evitar ciclos e contabiliza erros de acesso sem interromper a análise. Quando há várias raízes, elas são distribuídas em um `ThreadPoolExecutor` com até 4 workers; um `_ScanBudget` compartilhado garante que o limite efetivo valha para o conjunto, e um agregador combina o progresso sem regredir os contadores. O limite é automático (250 mil a 5 milhões, conforme a memória disponível) e pode ser reduzido por `scan.max_entries`.
- Os tamanhos são **lógicos** (`st_size`), que é o valor esperado em um gerenciador de arquivos. Arquivos esparsos, comprimidos ou com hard links podem ocupar menos espaço físico do que o valor exibido.
- A árvore é preguiçosa: os filhos de uma pasta só são criados quando ela é expandida, com limite de 1.200 itens por pasta e busca global limitada para manter a responsividade.
- As estimativas de limpeza não são destrutivas e podem se sobrepor; os cálculos já evitam contar arquivos de cache duas vezes e mostram "seguro" separado de "revisar".
- O avatar é copiado com `shutil`, não vinculado ao arquivo original.
- `circular_pixmap` pinta a imagem em coordenadas físicas e só aplica o `devicePixelRatio` no final; aceita `focus_x`, `focus_y` e `zoom`, permitindo o enquadramento ajustável do avatar. A imagem é carregada com `QImageReader.autoTransform`, então a rotação EXIF de fotos de celular é respeitada (antes a foto aparecia girada 90°). As prévias em `QLabel` usam `setScaledContents(True)` para não cortar o canto do pixmap em telas com DPI alto.
- O perfil salva `user.avatar_focus_x`, `user.avatar_focus_y` e `user.avatar_zoom`. No diálogo de perfil, arraste a foto para reposicionar e use a roda do mouse para ampliar; “Centralizar” volta ao ponto central.
- A exportação de dados usa `csv` (BOM UTF-8 e separador `;`), `openpyxl` (XLSX com abas de Resumo, **Ganho verificado**, Top 100 e Sugestões) e `pywin32` + Microsoft Excel (XLSB). A aba **Ganho verificado** compara os dois snapshots mais recentes, mostra a redução líquida observada e o aumento, separa a economia identificada (segura/revisão) e lista o histórico; snapshots truncados ou com raízes diferentes são marcados como não comparáveis, pois movimentos, permissões e mudanças de raiz também alteram os totais. O XLSB é gerado a partir do XLSX temporário com `FileFormat=50`; se o Excel ou o pywin32 não estiverem disponíveis, o app informa o requisito em vez de falhar silenciosamente. A gravação ocorre em `QThreadPool` e o destino é escolhido por um diálogo próprio, com pasta e nome editáveis.
- **Polars não foi adicionado**: o escopo atual exporta o Top 100 (200 linhas) e sugestões; uma dependência Rust/pesada não traria ganho. Para exportar a árvore inteira, Polars/Parquet seriam uma opção futura.
- O `sidebar.py` detecta se `icons.py` aceita o parâmetro `dpr` (adicionado na 1.3.4) e chama `avatar_pixmap`/`circular_pixmap` com ou sem ele. Assim, uma atualização parcial de arquivos não quebra o avatar com `TypeError`.
- O seletor de pastas mostra unidades mapeadas pelo **caminho UNC** (`\\servidor\compartilhamento`) em vez da letra (`W:\`), e navega pelos nomes das pastas de rede quando o compartilhamento está acessível.
- O seletor de pastas usa um `QListView` com modelo leve e enumeração em segundo plano, e exibe o caminho completo do item atual/selecionado em um rótulo selecionável (com cópia), além de tooltip por linha. O caminho não é abreviado, o que ajuda em compartilhamentos de rede.
- O banner de progresso e a lista de caminhos das recomendações mostram o caminho integral: o banner usa quebra de linha e a lista usa rolagem horizontal. A função `short_path` foi removida do projeto.
- Unidades mapeadas são resolvidas via `QStorageInfo.device()`: quando o `\\servidor\compartilhamento` equivalente está acessível, o seletor, as raízes e o banner passam a usar o caminho UNC em vez de `W:\`/`Z:\`.
- O ranking **Top 100** percorre a árvore em memória uma única vez, mantendo dois heaps (`heapq.nlargest`) para diretórios e arquivos, sem ordenar todos os nós. No diálogo, o cálculo roda em um worker próprio e a tabela mostra “Carregando ranking…” até o resultado chegar. Percentuais de diretórios são cumulativos e podem se sobrepor.
- **Memória**: diálogos transitórios são destruídos com `deleteLater`, menus e animações são liberados/reutilizados, e o resultado grande anterior é descartado antes de uma nova varredura (`RELEASE_RESULT_THRESHOLD`). A varredura usa limite automático de 250 mil a 5 milhões de entradas, calculado pela memória física disponível; o resumo persistido guarda apenas os 6 maiores diretórios, calculados com `heapq.nlargest`.
- **Expansão da árvore**: os filhos de uma pasta são carregados em lotes de 120 itens, com debounce de 60 ms. A árvore mostra “Carregando…” enquanto isso, mantém a contagem incremental e restaura as pastas expandidas após uma reordenação. Ícones de arquivo são cacheados por extensão, e a ordenação dos filhos usa `heapq.nlargest/nsmallest` com o limite de 1.200 itens exibidos.
- `qt-material` fornece a base do tema; o QSS em `appshell/theme.py` sobrescreve o que é necessário (especialmente `text-transform`, hovers e cores semânticas) para manter a identidade do app.
- A geometria inicial e a restaurada são limitadas à área útil da tela: em notebooks pequenos (ou com escala de 125%/150%) a janela não nasce maior que o monitor, então a barra de título e os botões de janela continuam clicáveis. O tamanho mínimo também se adapta ao monitor.
- O `WM_NCHITTEST` nativo converte a posição do cursor para o espaço lógico do Qt antes de detectar as bordas. Sem isso, em telas com escala o canto direito inteiro era confundido com borda de redimensionamento e os botões de maximizar/fechar não respondiam — o usuário precisava maximizar com duplo clique no meio da barra.
- O filtro global de `Ctrl+roda` é removido no `aboutToQuit` (`CtrlWheelGuard.stop`) e não chama `super().eventFilter` durante o teardown. Isso evita a recursão de `RuntimeError`/objetos C++ já destruídos no encerramento do Python/Qt.
- Auditoria estática (`ruff check --select F`) sem erros e suíte **pytest + QtBot** cobrindo modelo, varredura paralela, seletor de pastas, exportação CSV, seletor de imagens e Top 100 assíncrono. Imports não utilizados foram removidos e os módulos novos (`services/exporter.py`, filtros do Top 100 e coluna de caminho) passaram por compilação e testes de fumaça.
- `SheetDialog` envolve o corpo em um `QScrollArea` e usa mínimo por diálogo (por exemplo, 840×520 no seletor de pastas e 600×420 na exportação). A alça de redimensionamento é desenhada pelo próprio app, em vez de `setSizeGripEnabled(True)`, porque o estilo do Qt procurava `icon:/primary/sizegrip.svg` e emitia um aviso no console.
- O seletor de imagens usa `_ImageScanTask` + sinais para listar a pasta fora da GUI e adiciona os itens da grade em lotes de 120. O Top 100 usa `_TopItemsTask`; nenhum dos dois calcula a pasta/ranking no construtor do diálogo.
- A suíte de testes fica em `tests/` e é opcional em produção: `requirements-dev.txt` adiciona pytest, pytest-qt e ruff, e `tests/conftest.py` força `QT_QPA_PLATFORM=offscreen` e a raiz do projeto no `sys.path`.
- Maximizar e restaurar são controlados pelo próprio app, e não por `showMaximized()`: em janelas sem moldura o `normalGeometry()` do Qt pode crescer a cada ciclo e devolver um retângulo maior que a tela. O estado salvo (geometria e maximizado) é aplicado antes do primeiro `show`, para a janela não piscar em tamanhos intermediários.
- A janela tem **tamanho máximo igual à área útil da tela** (e a posição é limitada para manter a barra de título alcançável), então nenhum salto de layout consegue empurrar os botões para fora do monitor. O log de depuração registra tela, escala e geometria em cada maximizar/restaurar; no nível INFO esses reajustes não poluem o terminal.
- A troca de tema usa **cache de QSS por tema** e uma única chamada a `setStyleSheet`. A geração de ícones do `qt_material` (que reescrevia centenas de SVG em `~/.qt_material` a cada troca) é desativada — o app usa apenas qtawesome —, e o QSS do outro tema é pré-montado em segundo plano após a abertura.
- A árvore desenha as **setas de expandir/recolher** e as guias de hierarquia em `drawBranches`, com a cor do tema, porque o QSS de `::branch` desliga o indicador nativo. O clique na seta alterna o nó.
- A árvore aceita `Ctrl+C` e menu de contexto para copiar **linha(s)** (Nome, Tamanho, %, Itens, Modificado, Autor, Tipo e Caminho, separados por tabulação), **tamanho** ou **caminho**. A seleção múltipla copia todas as linhas escolhidas.
- O autor é lido pelo Windows Property System (`System.Author`/`PKEY_Author`) em um pool de threads, com cache por caminho; há fallback para `docProps/core.xml` (OOXML) e `/Author` (PDF) quando o Property System não responde. Falhas de rede/permissão e arquivos sem metadados aparecem como `—`.
- O logging é centralizado em `app/logging_setup.py`: `RotatingFileHandler` de 2 MB com 3 backups em `~/DiskPilot/logs`, retenção de 3 dias (linhas antigas do log ativo e arquivos rotacionados), crash log via `faulthandler`, importação dos logs antigos da pasta de configuração e migração em tempo de execução sem reiniciar. Se a pasta escolhida ficar indisponível, o app usa o diretório padrão e continua registrando.
- `KeyboardInterrupt` (Ctrl+C no console/IDE) é registrado como interrupção manual em `INFO`, e não como `CRITICAL` com stack trace. O hook de exceções só trata erros reais como críticos.
- Textos de `QLineEdit`, `QComboBox` e `QAbstractSpinBox` usam o token `input_text`: claro no tema escuro e **azul-escuro** (`#06232b`) no tema claro. A cor também é fixada nos estados `:hover` e `:focus`, e o placeholder usa o token `placeholder` (mais escuro no tema claro), garantindo contraste.
- Os estados de hover usam os tokens `hover`/`hover_border`, com contraste próprio em cada tema (no claro, `#d8ebef`), em vez de reutilizar `surface_2`/`surface_3`. Isso inclui os hovers desenhados à mão das abas verticais e do cartão do usuário — antes o `surface_2` ficava quase invisível sobre o `sidebar` no tema claro.
- O título de `PageHeader` usa `ElidedLabel`: em janelas estreitas ele elide em vez de empurrar/cortar os botões de ação do cabeçalho.
- A página de recomendações não refaz a análise ao ser aberta: os cards são atualizados pelos sinais de varredura e a criação não faz `os.path.isdir` por caminho. Antes, cada navegação recriava os cards e consultava até 60 caminhos por sugestão, o que congelava a UI em shares de rede.
- O seletor de pastas não usa `QFileSystemModel`: as subpastas são enumeradas em um `QThreadPool` com `os.scandir` e exibidas em um `QListView` com `QAbstractListModel`. A GUI não cria um widget por pasta nem faz `stat` ao rolar; a lista de unidades é montada após o `show` e a resolução de UNC para os locais não verifica `isdir`, então unidades de rede desconectadas não bloqueiam a abertura. `activated`/Enter e duplo clique navegam sem disparar a navegação duas vezes.
- A adição de pastas pelo seletor usa `add_roots(..., trusted=True)`: o caminho já foi validado/enumerado pelo diálogo, então não há `os.path.isdir` extra em cada pasta de rede ao confirmar.
- `top_items` faz uma única travessia com dois heaps no modo memória; no modo indexado, consulta diretamente `nodes` por `size DESC LIMIT`. O cálculo do Top 100 da exportação roda na thread de escrita.
- A duração da análise é exibida ao usuário como `hh:mm:ss` por `appshell.utils.format_duration`; a exportação mantém a coluna numérica em segundos para planilhas.
- O índice SQLite é persistente e, no motor indexado, é construído **durante** a varredura: `IndexWriter` reserva o id do diretório, grava arquivos em lotes e atualiza os agregados ao fechar cada pasta. `SearchIndex` abre conexões curtas por consulta; a árvore usa `children_for_node()` sob demanda. `AppState` publica `scan.index_path`, `scan.index_previous_path` e `scan.indexed_roots` só depois de gravar a configuração. No fechamento, o índice ativo é mantido; ao reabrir, `RestoreTask` monta apenas as raízes e os filhos são carregados ao expandir. A adição de raiz no motor indexado varre só a nova raiz e consolida os dois bancos por SQL (`merge_indexes`), sem reindexar os arquivos antigos. A remoção de raiz apaga somente os nós daquela raiz no índice, atualiza `scans`/`meta` e recalcula o resumo, sem reexecutar a varredura; no modo memória, a árvore já carregada é filtrada e um novo índice é construído em segundo plano. Índices órfãos são removidos apenas depois da carência e com proteção do ativo/anterior.
- O núcleo `appshell/` não importa `app`: `AppContext`, `BasePage`/`PageSpec`, `TaskRunner` e `ShellWindow` formam o contrato reutilizável. O `MainWindow` do DiskPilot é uma composição fina que injeta `TitleBar`, `Sidebar`, `Toast`, atalhos e o estado de disco.
- `AppState` usa o `TaskRunner` genérico para a varredura: a tarefa só implementa `execute()`, e o runner cuida do pool, dos sinais, do cancelamento e da liberação da tarefa. O mesmo contrato pode ser usado por exportação, carregamento de pastas e Top 100.
- `app/features/base.py` reexporta `BasePage` e `PageSpec` de `appshell.pages` para manter compatibilidade com as páginas existentes.
- `_AuthorSignals`, `_FolderScanSignals` e `_ExportSignals` não são filhos dos widgets: o `QRunnable` mantém a referência e pode terminar depois do fechamento da janela sem emitir em um QObject já destruído.
- Acessibilidade: listas de pastas/fotos, campo de caminho, terminal de logs e campos de pasta/nome da exportação têm `accessibleName`; a lista de pastas aceita Enter.
- O seletor de foto usa miniaturas e prévias decodificadas no tamanho de exibição (com cache), em vez de carregar a imagem inteira; a atualização automática do terminal pausa enquanto há texto selecionado para não atrapalhar a cópia.
- `log_tail` lê o arquivo de trás para frente em blocos, então um crash log grande não precisa ser carregado inteiro na memória.
- A barra de título é **responsiva e sem moldura**: o título e o slogan usam rótulos que elidem (reticências) em vez de empurrar o layout. O slogan "Gestor de espaço" fica centralizado no meio exato da barra e não intercepta cliques — arraste e duplo clique funcionam em toda a barra.

---

## Limitações e próximos passos

- Não há exclusão em massa; isso é intencional por segurança.
- Duplicatas são comparadas por nome + tamanho, sem abrir/ler o conteúdo dos arquivos. A lista é ordenada pelo espaço potencialmente recuperável, e os caminhos são exibidos para revisão manual antes de qualquer remoção.
- O redimensionamento nativo por `WM_NCHITTEST` é específico do Windows; o fallback manual cobre outras plataformas.
- A varredura paralela distribui raízes independentes, não subpastas de uma mesma raiz. Um disco lento ainda limita o ganho, e o limite automático é compartilhado por todas as raízes.
- No motor indexado, a busca/filtro usa FTS5 no SQLite e materializa apenas os ramos correspondentes (até 5.000 correspondências). No modo memória, percorre a árvore inteira em segundo plano. A renderização é limitada para manter a interface fluida; em buscas muito amplas, o contador indica que há mais resultados e pede para refinar o termo.
- Para volumes muito grandes, o motor indexado (`scan.engine=auto`, padrão) grava direto no SQLite, carrega a árvore sob demanda e consolida raízes por SQL. O modo `scan.engine=memory` mantém o caminho antigo, útil para diagnóstico ou para funcionalidades que dependem da árvore completa. O limite automático continua protegendo contra OOM; mesmo no motor indexado, o SQLite e o disco crescem com o número de nós, e a validação real de 2–5 milhões no `F:\` ainda precisa ser executada.
- O índice é um arquivo SQLite separado. Medições do caminho em memória (Windows, Python 3.14, `synchronous=FULL` e checkpoint) indexaram ~110.111 nós em ~1,27 s e 46 MB, ~500.501 em ~9,84 s e 198 MB, e ~1.500.501 em ~38,5 s e 589 MB. A restauração em processo limpo levou ~0,26 s / ~2,47 s / ~7,54 s, com working set de ~81 MB / ~217 MB / ~564 MB. No motor indexado, 100.000 arquivos reais em 100 pastas foram varridos e gravados em ~3,0 s, com pico de ~52 MB; a restauração lazy levou ~0,07 s. Um índice sintético de 1.500.000 nós foi restaurado em modo lazy em ~0,71 s, acrescentando ~1,2 MB ao working set. O tempo e o tamanho variam com o disco, o cache e a versão do SQLite.
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
