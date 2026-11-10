from pathlib import Path
import base64
import hashlib
import io
import tarfile

PARTES = [Path(f"parte{i}.txt") for i in range(1, 5)]
raw = "".join(p.read_text(encoding="ascii") for p in PARTES)
payload = base64.b85decode("".join(raw.split()))
esperado = "769c84c3ff14a5088d095bb4651df9c6bdb8c6710e79ae1b8b39644b5b0e9ba5"
if hashlib.sha256(payload).hexdigest() != esperado:
    raise SystemExit("Falha de integridade: recopie os blocos de texto.")
destino = Path("DiskPilot")
destino.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
    tar.extractall(destino)
print("DiskPilot restaurado em:", destino.resolve())
print("Agora: py -m pip install qt-material qtawesome openpyxl pywin32 && py main.py")
