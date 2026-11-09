# DiskPilot 1.4.3 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 68.528 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.632 | `a990bf86f9de27e0850910b1b7a07e24f2fe0f1402e7695c0d3276bec0969652` |
| `parte2.txt` | 21.640 | `bb962bd241e19ee8f4ac61edc8e01bbbb10226ef9ebb8a7f3625a07acedacc8f` |
| `parte3.txt` | 21.631 | `c9f39f751469db432ccf2592a10d9feae04ee179c5c9f8d4ef5de2fdeb60ae89` |
| `parte4.txt` | 21.634 | `899f78ca4e805d53a8048bf4d814ca1096590b0c2e129e82f74e46af2ca70be0` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
1432daabc90db9f8a8e8cceee2fa03b5bfb994e73edd9bf3d6fbbed3d9eb01de
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
   iniciando DiskPilot 1.4.3
   ```

## Novidades desta versão

- **Compatibilidade do avatar**: o `sidebar.py` detecta se o `icons.py`
  instalado aceita `dpr` e chama `avatar_pixmap`/`circular_pixmap`
  adequadamente. Corrige o `TypeError` que aparecia ao misturar um `sidebar.py`
  novo com um `icons.py` antigo (de antes da 1.3.4).
- **Hover das abas verticais no tema claro**: o fundo das abas, do logo e do
  cartão do usuário agora usa o token `hover` (`#d8ebef`), em vez de
  `surface_2` — que era quase idêntico ao fundo da barra lateral e deixava o
  hover praticamente invisível.
- **Botões de janela clicáveis em telas com escala**: o `WM_NCHITTEST` agora
  converte a posição física do Windows para o espaço lógico do Qt. Antes, em
  telas com 125%/150%, a região direita da barra era tratada como borda de
  redimensionamento e os botões de maximizar/restaurar e fechar não respondiam.
- **Sem moldura externa**: removidos o contorno arredondado e a margem
  transparente de 6 px. A janela usa toda a área disponível e a barra de título
  encosta nas bordas, como em um aplicativo comum.
- **"Gestor de espaço" centralizado** de verdade na barra de título, em uma
  camada que não bloqueia arraste, duplo clique nem os botões.
- Removida a opção experimental de moldura nativa (e resíduos em configurações
  antigas): a janela é sempre sem moldura, com a barra de título do app.
- Mantém: barra de título responsiva, setas da árvore, cópia com `Ctrl+C`,
  contraste dos campos em azul-escuro no tema claro e cache de QSS.

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

Esperado: `21415`, `21415`, `21415`, `21415`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.4.3` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.3/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.3/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.3/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.3/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.3/entrega/restaurar_diskpilot.py
```
