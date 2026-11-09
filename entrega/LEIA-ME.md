# DiskPilot 1.5.0 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 70.708 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 22.327 | `adbcbe36395294ef513d1059757aa71a21b815969d3f1cd7fcfa3afa1dc37e81` |
| `parte2.txt` | 22.323 | `4c5df3bdb4c0d91cbc3a5e77e17bdf7159ed270131a0e65521a0d719873f1ca0` |
| `parte3.txt` | 22.331 | `839fbf5e6dd539b95df7b310655ff46d51215e8a3d48e76f8e1bd09ba4b2fa7a` |
| `parte4.txt` | 22.316 | `bd54238d56003418a9caea23b62a2ea66583065e0f4f9f792dbedc87cce4363c` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
9f5b708cb025a99a5d160c1872bba1b16334d0e0668af51e3927f4bd06822b6c
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
   py -m pip install qt-material qtawesome
   py main.py
   ```

5. Confirme no `diskpilot.log`:

   ```text
   iniciando DiskPilot 1.5.0
   ```

## Novidades desta versão

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

Esperado: `22097`, `22097`, `22097`, `22094`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.5.0` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.5.0/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.5.0/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.5.0/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.5.0/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.5.0/entrega/restaurar_diskpilot.py
```
