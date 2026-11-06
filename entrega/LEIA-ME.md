# DiskPilot 1.3.0 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 58.964 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 18.735 | `e86f83f0420ca736b12c3a0ed026963d03b220c852b574cfb516e60ba9cef8da` |
| `parte2.txt` | 18.735 | `fe8960f27d108bd9980fedc9a2d8dddafed206a9ae310ae25c46896d1f1672d1` |
| `parte3.txt` | 18.735 | `1f5db1a323cfa75f7b53e87b54fc740e0af470088e2c12b9b96b284fc08d6364` |
| `parte4.txt` | 18.732 | `c7d4abd5789d54808ee305c827f106ea809859192b59c6adfca838034a9357ea` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
bc3ceae55e2be5fe44a442269e3a535dfa6c823221c586ca01227f9939549968
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
   iniciando DiskPilot 1.3.0
   ```

## Diagnóstico

Se a integridade falhar, descubra qual parte está truncada:

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `parte1.txt 18427`, `parte2.txt 18427`, `parte3.txt 18427`,
`parte4.txt 18424`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- Este pacote é gerado a partir do commit `v1.3.0` deste repositório.

## URL dos arquivos crus

Com o repositório publicado, o padrão é:

```text
https://raw.githubusercontent.com/<usuario>/<repo>/main/entrega/parte1.txt
https://raw.githubusercontent.com/<usuario>/<repo>/main/entrega/parte2.txt
https://raw.githubusercontent.com/<usuario>/<repo>/main/entrega/parte3.txt
https://raw.githubusercontent.com/<usuario>/<repo>/main/entrega/parte4.txt
https://raw.githubusercontent.com/<usuario>/<repo>/main/entrega/restaurar_diskpilot.py
```
