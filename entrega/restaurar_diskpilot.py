from pathlib import Path
import base64
import hashlib
import io
import tarfile

PARTES = [Path(f"parte{i}.txt") for i in range(1, 5)]
raw = "".join(p.read_text(encoding="ascii") for p in PARTES)
payload = base64.b85decode("".join(raw.split()))
esperado = "5dc772991591e1e3013ffdcf9a2b8a7d9ecdae1eaa36b2ea5d6b2c55320dab47"
if hashlib.sha256(payload).hexdigest() != esperado:
    raise SystemExit("Falha de integridade: recopie os blocos de texto.")
destino = Path("DiskPilot")
destino.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
    tar.extractall(destino)
print("DiskPilot restaurado em:", destino.resolve())
print("Agora: py -m pip install qt-material qtawesome openpyxl pywin32 && py main.py")
