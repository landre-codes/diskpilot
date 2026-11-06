# DiskPilot 1.3.2 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 62.480 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 19.851 | `0cc8c16b010a058420425f5a0dded8779772352f8400e43eb8fc7adba3acfa9b` |
| `parte2.txt` | 19.851 | `cf13716d0863179a4feac72c00344d717a51e9f629b966b32282341a1c69f248` |
| `parte3.txt` | 19.851 | `42c918c33d6093b0ae92c6740264d2ce248c3572e18f69ef827a5d14776416cf` |
| `parte4.txt` | 19.851 | `c2648f57d3b3438c167a9ee2ac1595dae6730a68e2fb91b0c824551a4fdcc6df` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
e5904e993f5fbc62df15d1cefe0805278214269e01b19ea1d539438dde92643e
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
   iniciando DiskPilot 1.3.2
   ```

## Diagnóstico

Se a integridade falhar, descubra qual parte está truncada:

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `19525` nas quatro partes.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Esta versão corrige a geometria em telas pequenas e o ciclo
  maximizar/restaurar (a janela não volta maior que a tela).
- Este pacote é gerado a partir do commit `v1.3.2` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
