# DiskPilot 1.3.4 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 64.448 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 20.476 | `dedd99208da147a8d686e3dcdefdebcd57f4aeac0acaf9327ca110a4dc6d33a3` |
| `parte2.txt` | 20.476 | `0c28f61df78e0820bb8b927ff9778bcf23ba6f3d4d9041303c1e451e37dc502a` |
| `parte3.txt` | 20.476 | `7bc91f111359777ffbaa406654aed3fa36925d57c392e109adde193442d50d21` |
| `parte4.txt` | 20.476 | `7e86f2a06f69907498e9c675cbe8ebd089e83ac1d8c931e49922dec8fdb49f27` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
dedbaf378ce91644ddda19ff2d9be36989dcb56b25d1dc53b6e3e49607c4c095
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
   iniciando DiskPilot 1.3.4
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

Esperado: `20140` nas quatro partes.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Esta versão: janela limitada ao tamanho da tela, correção contínua de saltos
  de layout, barra de título sempre alcançável, avatar/logo com escala suave e
  `diagnostico.py` incluído.
- Este pacote é gerado a partir do commit `v1.3.4` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
