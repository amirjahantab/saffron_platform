"""Encode generated editorial/demo sources for the web, without changing their composition."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent.parent
for stem in ["jahantab-editorial", "demo-jar", "demo-box"]:
    source = root / "assets" / "source-images" / f"{stem}.png"
    target = root / "static" / "images" / f"{stem}.webp"
    with Image.open(source) as opened:
        opened.convert("RGB").save(target, "WEBP", quality=85, method=6)
    print(f"{target.name}: {target.stat().st_size} bytes")
