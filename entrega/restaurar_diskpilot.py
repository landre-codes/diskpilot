from pathlib import Path
import base64
import hashlib
import io
import tarfile

PARTES = [Path(f"parte{i}.txt") for i in range(1, 5)]
raw = "".join(p.read_text(encoding="ascii") for p in PARTES)
payload = base64.b85decode("".join(raw.split()))
esperado = "2da021cc789c50dffb68a2d055f9b320c39bf01ec109d32b9c024f6fd975639c"
if hashlib.sha256(payload).hexdigest() != esperado:
    raise SystemExit("Falha de integridade: recopie os blocos de texto.")
destino = Path("DiskPilot")
destino.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
    tar.extractall(destino)
print("DiskPilot restaurado em:", destino.resolve())
print("Agora: py -m pip install qt-material qtawesome && py main.py")
