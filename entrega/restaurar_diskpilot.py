from pathlib import Path
import base64
import hashlib
import io
import tarfile

PARTES = [Path(f"parte{i}.txt") for i in range(1, 5)]
raw = "".join(p.read_text(encoding="ascii") for p in PARTES)
payload = base64.b85decode("".join(raw.split()))
esperado = "3f01b8415d1c04f02eebc930d274d439a5f94b0906e48bac687b9fe4d1c16866"
if hashlib.sha256(payload).hexdigest() != esperado:
    raise SystemExit("Falha de integridade: recopie os blocos de texto.")
destino = Path("DiskPilot")
destino.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
    tar.extractall(destino)
print("DiskPilot restaurado em:", destino.resolve())
print("Agora: py -m pip install qt-material qtawesome openpyxl pywin32 && py main.py")
