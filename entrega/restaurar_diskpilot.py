from pathlib import Path
import base64
import hashlib
import io
import tarfile

PARTES = [Path(f"parte{i}.txt") for i in range(1, 5)]
raw = "".join(p.read_text(encoding="ascii") for p in PARTES)
payload = base64.b85decode("".join(raw.split()))
esperado = "e5904e993f5fbc62df15d1cefe0805278214269e01b19ea1d539438dde92643e"
if hashlib.sha256(payload).hexdigest() != esperado:
    raise SystemExit("Falha de integridade: recopie os blocos de texto.")
destino = Path("DiskPilot")
destino.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
    tar.extractall(destino)
print("DiskPilot restaurado em:", destino.resolve())
print("Agora: py -m pip install qt-material qtawesome && py main.py")
