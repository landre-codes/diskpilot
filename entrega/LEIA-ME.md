# DiskPilot 1.3.3 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 63.176 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 20.073 | `454a2db9b9ef3628d9bf7ff2d2fbf3f5ef820a75a14a78fd1e9b53f853152e0b` |
| `parte2.txt` | 20.073 | `e7150f253c674b3e60d711d997d5a16cb4058b1e47c1f18728b51241ec8430ce` |
| `parte3.txt` | 20.073 | `7a3080f4d4bd09fc3c4c4d735106c79eb72aeff884c65d4c0255ff096111b0f5` |
| `parte4.txt` | 20.071 | `e2e3de1c8fad0f496da0ae8d0f6bafc284a30549022f2945a95f153fead029e7` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
632ea26188033a15e63117759460feae19bb5996787021ea8c96032212de1e9a
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
   iniciando DiskPilot 1.3.3
   ```

## Diagnóstico

Se a integridade falhar, descubra qual parte está truncada:

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `19743`, `19743`, `19743`, `19741`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Esta versão limita a janela ao tamanho da tela (máximo), mantém a barra de
  título sempre alcançável e registra tela/escala/geometria no log.
- Este pacote é gerado a partir do commit `v1.3.3` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
