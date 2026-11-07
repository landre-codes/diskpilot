# DiskPilot 1.3.7 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 66.340 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.078 | `40f9e82768f76dcc90a2c619f158ca7dfa8af4b3bb3950496d8261e7c72c4e1a` |
| `parte2.txt` | 21.078 | `63886686213be6b9bc0f4f8a606d76ee082e374abdea2315347e93ea2445b8e9` |
| `parte3.txt` | 21.078 | `627964af4999c96941f76c869800c945ac6ace1bbbe3d6a872926a52692d50e3` |
| `parte4.txt` | 21.075 | `e5a111bf62a79c354ab37078777c44a0ca5da20e59c8a8f25c89e95745e412a1` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
4c3ff3f58192ec3c3fd471fe1b072d37a5b9cd6c6104fa88bc67061d65e9ed2b
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
   iniciando DiskPilot 1.3.7
   ```

## Novidades desta versão

- Setas de expandir/recolher visíveis na árvore, nos dois temas, com guias de
  hierarquia; clique na seta alterna o nó.
- `Ctrl+C` na árvore copia as linhas selecionadas (Nome, Tamanho, %, Itens,
  Modificado, Tipo, Caminho — separados por tabulação). O menu de contexto tem
  **Copiar linha(s)**, **Copiar tamanho** e **Copiar caminho**, e a seleção
  múltipla é aceita.
- Texto de campos e combos com contraste garantido: claro no tema escuro,
  azul-escuro no tema claro (token `input_text`).
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

Esperado: `20732`, `20732`, `20732`, `20729`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.3.7` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.7/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.7/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.7/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.7/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.7/entrega/restaurar_diskpilot.py
```
