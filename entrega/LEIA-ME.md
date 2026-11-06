# DiskPilot 1.3.1 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 61.476 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 19.534 | `1e70f8739ac16fa7d419b7af731ced6e6f2e5c3b76c36639890d050b49fe743f` |
| `parte2.txt` | 19.534 | `9386cf63973ed5cd0651dbc61022bb4e236cc94fd86f5ff6524c6c18cc45be3a` |
| `parte3.txt` | 19.534 | `e41859ce071859e9d8ef0bbe6d650ce1726382f5cd8cace2230cbd09c2b14fe4` |
| `parte4.txt` | 19.531 | `ee8b36c946761ea6d33717ef3b4622b3b53f514b37c4292a2b5e5bd652edd6b4` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
5162ef63f3100dc8f29e67ed0bfa97b3e254b4823ad8d1d0c195a9dfa2ecad31
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
   iniciando DiskPilot 1.3.1
   ```

## Diagnóstico

Se a integridade falhar, descubra qual parte está truncada:

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `parte1.txt 19212`, `parte2.txt 19212`, `parte3.txt 19212`,
`parte4.txt 19209`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.3.1` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
