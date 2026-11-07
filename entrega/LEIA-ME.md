# DiskPilot 1.3.8 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 66.468 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.120 | `9f70274c8bc01d60bc6006d93c6a94289d4df8869f92c28b5728fa5c40834130` |
| `parte2.txt` | 21.120 | `207c0ffcc1ae123c357755b2433c0213779db348716213151de72f4efb85c89a` |
| `parte3.txt` | 21.120 | `6390b0247c4847cf87fb879946c3b6dd50f587214e3bba4b56571090700711d2` |
| `parte4.txt` | 21.117 | `0c4765125b0404e940876eb6e0b7113bfeb5512fa5e39b8de430dbe24140349b` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
50f0cf0d29c5e59e50388bd392e946d7a8857142ff48064854f95e30ec2f66d3
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
   iniciando DiskPilot 1.3.8
   ```

## Novidades desta versão

- Tema claro: texto de campos e combos em **azul-escuro** (`#06232b`), inclusive
  nos estados de foco e hover; placeholder mais escuro (`#1f4d57`).
- Tema escuro preservado como estava.
- Setas de expandir/recolher visíveis na árvore, nos dois temas, com guias de
  hierarquia; clique na seta alterna o nó.
- `Ctrl+C` na árvore copia as linhas selecionadas (Nome, Tamanho, %, Itens,
  Modificado, Tipo, Caminho — separados por tabulação). O menu de contexto tem
  **Copiar linha(s)**, **Copiar tamanho** e **Copiar caminho**.
- Troca de tema com QSS em cache; tempo registrado no log
  (`tema light aplicado em 0.15s (cache=sim)`).

## Diagnóstico de tela

```powershell
py diagnostico.py
```

Grava `diagnostico-diskpilot.txt` com Python, PySide6, versão do Qt, tela,
`devicePixelRatio`, escala e a geometria em cada etapa de maximizar/restaurar.

## Diagnóstico de integridade do pacote

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `20772`, `20772`, `20772`, `20769`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.3.8` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.8/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.8/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.8/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.8/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.8/entrega/restaurar_diskpilot.py
```
