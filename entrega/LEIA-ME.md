# DiskPilot 1.4.1 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 68.268 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.551 | `754e2a5d87f3e6307855f1461445854e25a8652b66b5ede25469d7061ff6c3e5` |
| `parte2.txt` | 21.557 | `3a87480ae6c762313f91ce29cd54cfa0de0ba2a20aca6b73629fff9ca1faffe1` |
| `parte3.txt` | 21.552 | `69130ec273fa686c3e063c57f1a23011eb7be19d93230188722922ad4f6da97a` |
| `parte4.txt` | 21.545 | `07cbbbdb19effcf898a6eacd55ebb8934f6ee9dd5168d8339c00190e7ebf103f` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
306d4877bd151ae3b99778428a73494df73d417a78267d599c95f0a416d3ece7
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
   iniciando DiskPilot 1.4.1
   ```

## Novidades desta versão

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

Esperado: `21334`, `21334`, `21334`, `21333`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.4.1` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.1/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.1/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.1/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.1/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.4.1/entrega/restaurar_diskpilot.py
```
