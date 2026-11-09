# DiskPilot 1.6.6 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 76.276 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 24.082 | `345625722c67d97725cd91fc0a59830c0b97b20b4bf0f937ad76153ff9dd9d9c` |
| `parte2.txt` | 24.086 | `dc0548614c8fb69433ad7fee568cfeaec473acfc4edab560366006164200997a` |
| `parte3.txt` | 24.081 | `23249c00d5d1ebc0fbbd8293f8d0543faa18818544a1ddd70b2fbcb8ee8f5129` |
| `parte4.txt` | 24.082 | `70694b999def19bc26a867c456fbb55602cd2497e788eb4779578fc1abd06b22` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
4ab20c2e21856747d81f5f8d446d5b5f148119fec8f8d603ceded50a79ac2a9c
```

## Como usar

1. Copie os 5 arquivos para uma pasta vazia, mantendo os nomes.
2. Execute:

   ```powershell
   py restaurar_diskpilot.py
   ```

3. Se o SHA-256 não bater, o script aborta com
   `Falha de integridade: recopie os blocos de texto.` Nada é extraído.
4. Instale as duas dependências que não vêm com o PySide6 e execute:

   ```powershell
   cd DiskPilot
   py -m pip install qt-material qtawesome openpyxl pywin32
   py main.py
   ```

5. Confirme no `diskpilot.log`:

   ```text
   iniciando DiskPilot 1.6.6
   ```

## Novidades desta versão

- **Caminho completo de rede visível**: a coluna “Caminho completo” agora cresce
  até o maior caminho exibido, sem reticências, e o caminho do item selecionado
  aparece inteiro em um rodapé selecionável. A coluna Nome mantém no mínimo
  280 px; quando necessário surge rolagem horizontal.
- **Auditoria estática**: `ruff check --select F` sem erros; imports não
  utilizados foram removidos dos módulos da interface e dos serviços.
- **Coluna de caminho sem esmagar o Nome**: ao ativar “Caminho completo”, o
  layout reserva pelo menos 280 px para o Nome; em janelas estreitas surge
  rolagem horizontal em vez de reduzir a coluna Nome.
- **Filtro por tamanho no Top 100**: a tabela dos maiores itens agora tem um
  seletor “Tamanho” com as opções Todos, > 100 MB e > 1 GB, aplicado tanto a
  diretórios quanto a arquivos.
- **Janela de exportação na análise**: botão **Exportar** no cabeçalho abre uma
  janela para escolher CSV, XLSX ou XLSB e o destino. O XLSX traz abas Resumo,
  Top 100 e Sugestões; o XLSB requer Microsoft Excel e pywin32.
- **Coluna de caminho corrigida**: a coluna “Caminho completo” deixou de ter
  largura fixa; agora é redimensionável, começa com 600 px e usa reticências no
  meio para caminhos longos. O checkbox continua persistindo a preferência.
- **Caminho completo na árvore**: checkbox “Caminho completo” na barra de
  ferramentas exibe a coluna com o caminho integral de cada item; a preferência
  é salva. O caminho também continua no tooltip da linha.
- **Encerramento sem traceback**: o filtro global de `Ctrl+roda` é removido no
  `aboutToQuit` e não chama `super().eventFilter` com objetos C++ já
  destruídos, corrigindo o erro `QHBoxLayout already deleted` no shutdown.
- **Foto de perfil corrigida**: o pixmap circular agora é pintado em
  coordenadas físicas e recebe o DPR só no final, evitando o recorte em quatro
  cantos que aparecia nas prévias. Retratos priorizam o topo (rosto), e as
  prévias usam escala correta em telas com DPI alto.
- **Exportação de dados**: CSV (Excel/LibreOffice, UTF-8 com BOM e separador
  `;`), XLSX (abas Resumo, Top 100 e Sugestões) e XLSB (binário do Excel;
  requer Microsoft Excel e pywin32 instalados).
- **Expansão da árvore em lotes**: pastas grandes não travam mais a interface.
  Os filhos são carregados em lotes de 120 itens, com debounce de 60 ms e aviso
  “Carregando…”; a ordenação usa `heapq` com limite de 1.200 itens e os ícones
  de arquivo são cacheados por extensão. As pastas expandidas são restauradas
  após reordenar ou filtrar.
- **Caminho completo no seletor de pastas**: além da navegação, o diálogo mostra
  o caminho inteiro da pasta atual ou da pasta selecionada, com botão de copiar
  e tooltip com o caminho integral em cada linha. Útil para caminhos longos e
  compartilhamentos de rede.
- **Top 100**: novo botão na análise abre o ranking dos 100 maiores diretórios
  e dos 100 maiores arquivos, com tamanho, percentual, caminho completo,
  cópia do caminho e abertura no Explorer.
- **Gerenciamento de memória**: diálogos transitórios, menus e animações são
  destruídos ou reutilizados; o resultado grande anterior é liberado antes de
  uma nova varredura; o Top 100 e o resumo usam `heapq.nlargest`, mantendo
  apenas os itens necessários em memória.
- **Compatibilidade do avatar**: o `sidebar.py` detecta se o `icons.py`
  instalado aceita `dpr` e chama `avatar_pixmap`/`circular_pixmap`
  adequadamente. Corrige o `TypeError` que aparecia ao misturar um `sidebar.py`
  novo com um `icons.py` antigo (de antes da 1.3.4).
- **Hover das abas verticais no tema claro**: o fundo das abas, do logo e do
  cartão do usuário agora usa o token `hover` (`#d8ebef`), em vez de
  `surface_2` — que era quase idêntico ao fundo da barra lateral e deixava o
  hover praticamente invisível.
- **Botões de janela clicáveis em telas com escala**: o `WM_NCHITTEST` agora
  converte a posição física do Windows para o espaço lógico do Qt. Antes, em
  telas com 125%/150%, a região direita da barra era tratada como borda de
  redimensionamento e os botões de maximizar/restaurar e fechar não respondiam.
- **Sem moldura externa**: removidos o contorno arredondado e a margem
  transparente de 6 px. A janela usa toda a área disponível e a barra de título
  encosta nas bordas, como em um aplicativo comum.
- **"Gestor de espaço" centralizado** de verdade na barra de título, em uma
  camada que não bloqueia arraste, duplo clique nem os botões.
- Removida a opção experimental de moldura nativa (e resíduos em configurações
  antigas): a janela é sempre sem moldura, com a barra de título do app.
- Mantém: barra de título responsiva, setas da árvore, cópia com `Ctrl+C`,
  contraste dos campos em azul-escuro no tema claro e cache de QSS.

## Diagnóstico

```powershell
py diagnostico.py
```

Grava `diagnostico-diskpilot.txt` com Python, PySide6, versão do Qt, tela,
`devicePixelRatio`, escala e a geometria em cada etapa de maximizar/restaurar.

## Diagnóstico de integridade do pacote

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `23837`, `23837`, `23837`, `23834`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material`, `qtawesome`, `openpyxl` e `pywin32` são
  instaladas por `pip`; `PySide6` já precisa existir no ambiente. O XLSB exige
  Microsoft Excel instalado.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.6.6` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.6.6/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.6.6/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.6.6/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.6.6/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.6.6/entrega/restaurar_diskpilot.py
```
