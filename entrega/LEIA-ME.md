# DiskPilot 1.3.5 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 65.100 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 20.684 | `7559e4bbfef93c1e1fa63ca2bf13ae25ec0595f853bbdf7314a1ec9b16ea755b` |
| `parte2.txt` | 20.684 | `6eda20772f05213b06e35979d8864fbaabe253d07f7d6fd12291ee5fccb080f0` |
| `parte3.txt` | 20.684 | `e7a953bdec4ea76ee9dc04b877b0296f3a15c985fa9a45fac092b2406470703f` |
| `parte4.txt` | 20.683 | `3fcdebf02d86ce65a09b5a6eb96a24a128f3296d3cf59754af6704346371281a` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
04f566f095c0a1cd2cc130afaa333e0c7c795ff3fb3496d83eb7e1f8db28d1c9
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
   iniciando DiskPilot 1.3.5
   ```

## Diagnóstico de tela

Se a janela abrir com tamanho estranho, algum botão não responder ou a
interface parecer cortada:

```powershell
py diagnostico.py
```

Ele grava `diagnostico-diskpilot.txt` com Python, PySide6, versão do Qt, tela,
`devicePixelRatio`, escala e a geometria em cada etapa de maximizar/restaurar.

## Diagnóstico de integridade do pacote

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `20344`, `20344`, `20344`, `20343`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Esta versão: troca de tema com cache de QSS (uma única aplicação por troca),
  sem a geração de ícones do qt_material; avatar/logo com escala suave; janela
  limitada ao tamanho da tela e `diagnostico.py` incluído.
- Este pacote é gerado a partir do commit `v1.3.5` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
