# DiskPilot 1.8.2 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 81.344 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 25.679 | `9bb0a601a722dc51fad5d6e0a23055d7f487b96ec905c8a6b862619d3c49788c` |
| `parte2.txt` | 25.682 | `1a3e9031b70d067e6b62dbb30200b73a7fb0584b7e417237691cee4d2c198a72` |
| `parte3.txt` | 25.683 | `5a8f8c4380eede525986d23cba16a6f094f48203f4d4dbdee9d8c31836b5404f` |
| `parte4.txt` | 25.680 | `fb64c5d426da985718486ecb6c443b882066354c61b2a14e3f819e1f9c48bfe2` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
91361f1e2389f97119ce16372562726a881e2b7966787f0e59359826651aabf6
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
   iniciando DiskPilot 1.8.2
   ```

## Novidades desta versão

- **Colunas maiores**: a tabela da análise passou a respeitar mínimos por coluna
  (Nome 280 px, Tamanho 124, % do pai 90, Itens 100, Modificado 150, Autor 200,
  Tipo 100 e Caminho completo 600). Em janelas estreitas surge rolagem
  horizontal em vez de reduzir as colunas abaixo do legível.
- **Coluna Autor**: a tabela da análise agora mostra o autor gravado nos
  metadados de cada arquivo (campo “Authors” do Windows; funciona para Office,
  PDF e formatos que guardam essa informação). A consulta é feita em segundo
  plano, com cache por caminho, e o nome aparece no tooltip e nas linhas
  copiadas. Pastas e arquivos sem metadados mostram `—`; CSV/XLSX/XLSB incluem
  a coluna.
- **Cancelar exportação sem fechar o app**: os diálogos de abrir/salvar usam a
  implementação do Qt em vez da nativa do Windows, e a automação do XLSB
  inicializa/finaliza o COM na mesma thread. Isso elimina o
  `RPC_E_WRONG_THREAD` que fechava o DiskPilot ao cancelar a exportação.
- **Estado vazio sem corte**: a descrição “Analisando pastas…” usa toda a
  largura disponível (até 520 px) e tem altura mínima calculada pelo texto, em
  vez de ser espremida em uma coluna estreita. Em janelas baixas, o cartão
  reduz margens e espaçamentos para o texto continuar inteiro.
- **Busca à esquerda e contador mais largo**: o campo de pesquisa fica alinhado
  à esquerda e o contador (“0 resultados”, “1.234 resultados · … exibidos”)
  ocupa o espaço restante, com elipse apenas quando realmente não couber.
- **Orientação EXIF da foto**: fotos de celular gravadas “deitadas” com a
  rotação no metadado EXIF agora são exibidas na posição correta no perfil, na
  sidebar e nas configurações. O carregamento usa `QImageReader` com
  `autoTransform`, em vez de `QPixmap(path)`.
- **Enquadramento da foto do perfil**: no diálogo de perfil, arraste a foto
  dentro do círculo para reposicionar e use a roda do mouse para zoom. O botão
  “Centralizar” redefine o enquadramento. Os valores são salvos em
  `user.avatar_focus_x`, `user.avatar_focus_y` e `user.avatar_zoom` e aplicados
  na sidebar, nas configurações e na prévia do perfil.
- **Unidades mapeadas em UNC**: no seletor de pastas e nas raízes, unidades como
  `W:\` e `Z:\` são resolvidas para `\\servidor\compartilhamento` via
  `QStorageInfo` quando o caminho UNC está acessível. O seletor mostra o caminho
  completo e navega pelos nomes das pastas de rede; o banner e os chips também
  usam o UNC.
- **Banner de progresso com caminho completo**: “Lendo pasta: …” agora mostra o
  caminho integral, com quebra de linha, em vez de `short_path`. A lista de
  caminhos das recomendações também usa o caminho completo e rolagem
  horizontal. A função `short_path` foi removida do projeto.
- **Caminhos UNC completos**: a árvore, os chips das raízes, o Top 100 e os
  rodapés exibem o caminho integral, inclusive os dois backslashes iniciais de
  `\\servidor\compartilhamento`. A coluna de caminho do Top 100 cresce até o
  conteúdo, sem reticências; o caminho da linha selecionada aparece no rodapé.
- **Caminho completo de rede visível**: a coluna “Caminho completo” da árvore
  cresce até o maior caminho exibido, sem reticências, e o caminho do item
  selecionado aparece inteiro em um rodapé selecionável. A coluna Nome mantém
  no mínimo 280 px; quando necessário surge rolagem horizontal.
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

Esperado: `25420`, `25420`, `25420`, `25420`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material`, `qtawesome`, `openpyxl` e `pywin32` são
  instaladas por `pip`; `PySide6` já precisa existir no ambiente. O XLSB exige
  Microsoft Excel instalado. A coluna **Autor** usa o Property System do
  Windows via `pywin32`, com fallback para OOXML/PDF; quando o arquivo não tem
  autor gravado ou o caminho não permite a leitura, ela mostra `—` sem
  interromper a análise.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.8.2` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.8.2/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.8.2/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.8.2/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.8.2/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.8.2/entrega/restaurar_diskpilot.py
```
