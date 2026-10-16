"""Export a square master PNG into the icon set an Electron app expects.

Usage: python export_icons.py <master.png> <assets_dir>

Writes <assets_dir>/icon.png (512), <assets_dir>/icon.ico (multi-size) and
<assets_dir>/icons/{N}x{N}.png for N in 16,32,48,64,128,256,512 (the layout
electron-builder reads for Linux). Always downscales from the master with
Lanczos so small sizes stay as crisp as the art allows.
"""
import sys
from pathlib import Path

from PIL import Image

PNG_SIZES = [16, 32, 48, 64, 128, 256, 512]
ICO_SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]


def main(master_path: str, assets_dir: str) -> None:
    master = Image.open(master_path).convert("RGBA")
    if master.width != master.height:
        sys.exit(f"master must be square, got {master.size}")
    if master.width < 512:
        sys.exit(f"master should be at least 512px (ideally 1024), got {master.width}")

    out = Path(assets_dir)
    (out / "icons").mkdir(parents=True, exist_ok=True)

    for s in PNG_SIZES:
        master.resize((s, s), Image.LANCZOS).save(out / "icons" / f"{s}x{s}.png")
    master.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
    # Pillow resamples the source for each requested size when saving ICO.
    master.resize((256, 256), Image.LANCZOS).save(out / "icon.ico", sizes=ICO_SIZES)

    print(f"wrote icon.png, icon.ico and {len(PNG_SIZES)} sizes under {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
