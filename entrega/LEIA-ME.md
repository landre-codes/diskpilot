# DiskPilot 1.4.0 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 67.496 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.445 | `9e8dee7ff4203b02104013743e1e9287ca6dbb63bb48b94b6949b9a8f1ed169f` |
| `parte2.txt` | 21.445 | `c8b527badc5c64ce91a1e5370855c49e685ffb09cb56b9e64ffc5560e37441c8` |
| `parte3.txt` | 21.445 | `41ea77d1261b31e824d909f279ba55b1e967ec1056ddfecc70b962282375cac5` |
| `parte4.txt` | 21.443 | `ac442bebc7f6223350bc2d16cce8628643d22eb503193614fedfd2174ab0f26e` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
2da021cc789c50dffb68a2d055f9b320c39bf01ec109d32b9c024f6fd975639c
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
   iniciando DiskPilot 1.4.0
   ```

## Novidades desta versão

- **Barra de título responsiva**: o título e o slogan agora elidem (reticências)
  e encolhem; os botões de janela mantêm tamanho e posição e nunca ficam fora
  da área clicável em telas pequenas. Em larguras menores o slogan é ocultado.
- Corrigido o "vigia de geometria" que podia desfazer um maximizar/restaurar
  feito logo após a abertura.
- Hover com tokens próprios, visível no tema claro (`#d8ebef` / `#8fbac2`).
- Removida a opção experimental de moldura nativa: a janela volta a ser sempre
  sem moldura, com a barra de título do app.
- Mantém: setas da árvore, cópia com `Ctrl+C`, contraste dos campos em
  azul-escuro no tema claro e cache de QSS na troca de tema.

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

Esperado: `21093`, `21093`, `21093`, `21091`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.4.0` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.0/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.0/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.0/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.0/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.0/entrega/restaurar_diskpilot.py
```
