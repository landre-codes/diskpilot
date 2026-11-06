"""Permite executar o pacote com ``python -m app``.

Útil quando a IDE abre a pasta ``app`` como raiz do projeto.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
