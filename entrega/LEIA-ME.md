# DiskPilot 1.3.9 — pacote de transporte em texto

Esta pasta existe para levar o projeto para um ambiente onde **só é possível
copiar texto** (sem clone, sem ZIP, sem download de release).

O conteúdo não é o código-fonte legível: é o projeto inteiro compactado
(`tar.xz`, 67.132 bytes) e codificado em **Base85**, dividido em 4 partes de
texto ASCII. O script `restaurar_diskpilot.py` remonta o arquivo, confere o
SHA-256 e extrai a pasta `DiskPilot/`.

## Arquivos

| Arquivo | Bytes | SHA-256 (sem espaços/quebras) |
|---|---|---|
| `parte1.txt` | 21.329 | `9aa90c0807a93ac2c005fb5f335756d92aa8470c02ff83285bd6840462d79c5e` |
| `parte2.txt` | 21.329 | `13ae381b0fdc83f14a90c8bbe85739623b12df3f21dd115dcf5b7aa167bcea68` |
| `parte3.txt` | 21.329 | `cd39cda417ffb7b70ba1de661c573bd9a6dd549b87e4c9e6017ded088016ebf0` |
| `parte4.txt` | 21.328 | `75e17ba39180e5a93ed117b8fc0b5d4de512815bad0cf0e124874a5294348c26` |

SHA-256 do `tar.xz` reconstruído (verificado pelo script):

```text
ee16fc6f3d90abd36adc08de67fe7947c8c98604d44d0a71f70f13750bb740a9
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
   iniciando DiskPilot 1.3.9
   ```

## Novidades desta versão

- **Hover visível no tema claro**: tokens `hover`/`hover_border` (`#d8ebef` /
  `#8fbac2`) aplicados a botões, itens de árvore, cartões, campos e combos.
  O tema escuro permanece igual.
- **Moldura nativa do Windows** (Configurações → Aparência): plano B para telas
  ou ambientes em que a barra de título personalizada não responde. Requer
  reiniciar o app; a escolha fica em `config.json` (`native_frame`).
- Correção: o "vigia de geometria" é interrompido ao maximizar, restaurar ou
  entrar em tela cheia, para não desfazer a ação do usuário.
- Mantém: setas da árvore, cópia com `Ctrl+C`, contraste dos campos e cache de
  tema.

## Se a barra de título continuar falhando

1. Rode `py diagnostico.py` e guarde `diagnostico-diskpilot.txt`.
2. Ative **Configurações → Aparência → Usar a moldura nativa do Windows** e
   reinicie. A barra passa a ser a do próprio Windows, que sempre responde.
3. Se a moldura nativa resolver, o problema está no caminho sem moldura
   (frameless) deste ambiente — e o relatório do diagnóstico mostra em qual
   etapa a geometria sai da tela.

## Diagnóstico de integridade do pacote

```powershell
py -c "from pathlib import Path; [print(p.name, len(''.join(p.read_text(encoding='ascii').split()))) for p in sorted(Path('.').glob('parte*.txt'))]"
```

Esperado: `20979`, `20979`, `20979`, `20978`.

## Observações

- Nenhum arquivo ou pasta é apagado pelo DiskPilot; ele é somente leitura.
- O pacote não inclui `.venv`, `dist`, caches ou logs.
- As dependências `qt-material` e `qtawesome` são instaladas por `pip`;
  `PySide6` já precisa existir no ambiente.
- O código é distribuído sob licença **MIT** (`LICENSE`); as dependências
  mantêm suas licenças — inventário em `THIRD-PARTY.md`.
- Este pacote é gerado a partir do commit `v1.3.9` deste repositório.

## URL dos arquivos crus

```text
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.9/entrega/parte1.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.9/entrega/parte2.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.9/entrega/parte3.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.9/entrega/parte4.txt
https://raw.githubusercontent.com/landre-codes/diskpilot/v1.3.9/entrega/restaurar_diskpilot.py
```
