import os
import sys
from pathlib import Path

# A suíte roda sem abrir janelas reais e a partir da raiz do projeto.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
