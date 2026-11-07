# DiskPilot 1.3.6 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 65.184 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 20.710 | `7ff81a7707ba48a7de65a3071001e5e5279b69f43d28922f4f7b67207027313c` |
| `parte2.txt` | 20.710 | `b8b1951ca62592052882ba51f302ff6c5c8f3bf1fa657f8fc5b7742a1bd9c10b` |
| `parte3.txt` | 20.710 | `6318f5ed0dcfd8bb680b970d6d512edbbb90ce83bd9248dc9db57373eae7f82c` |
| `parte4.txt` | 20.710 | `b771d19aded906adf30e52fa79a8f9df97a75eba11c3bd89d785ff37ea75f366` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
d75e2c81410587152cfb48eaf8b06d12a388ae1abf8f4d2bfefd85c5019a6a9c
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
   iniciando DiskPilot 1.3.6
   ```

## Tempo de troca de tema

Cada troca registra o tempo no log:

```text
diskpilot.theme: tema light aplicado em 0.15s (cache=sim)
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

Esperado: `20370` nas quatro partes.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Esta versão: troca de tema com cache de QSS, sem a geração de ícones do
  qt_material, com tempo medido no log; avatar/logo com escala suave; janela
  limitada ao tamanho da tela e `diagnostico.py` incluído.
- Este pacote é gerado a partir do commit `v1.3.6` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/main/entrega/restaurar_diskpilot.py
```
