# {{ project_name }}

Aplicação de exemplo gerada a partir do shell do DiskPilot. O núcleo genérico
está em `appshell/` e a feature de exemplo em `app/features/notes.py`.

## Executar

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```

## Testes

```powershell
py -3.14 -m pip install -r requirements-dev.txt
py -3.14 -m pytest tests -q
```

## Estrutura

```text
{{ project_slug }}/
├─ main.py                 # composition root
├─ app/
│  ├─ context.py           # AppContext do domínio
│  ├─ pages.py             # PageSpec registrado no shell
│  └─ features/notes.py    # feature de exemplo
├─ appshell/               # cópia do núcleo, gerada pelo template
├─ tests/
└─ requirements*.txt
```

## Próximos passos

- Troque `NotesPage` pelo primeiro domínio real.
- Adicione novas páginas em `app/pages.py`.
- Use `TaskRunner` para qualquer operação lenta.
- Mantenha o shell sem imports de `app/`.
