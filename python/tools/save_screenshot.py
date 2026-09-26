"""Save screenshot directly from Windows Clipboard into docs/images/ folder.

Usage:
    1. Press Alt + PrtScn (or PrtScn) on Power BI Desktop window.
    2. Run: python -m python.tools.save_screenshot 01_tong_quan
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageGrab
from python.common.config import ROOT


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m python.tools.save_screenshot 01_tong_quan")
        return

    filename = sys.argv[1].strip()
    if not filename.endswith(".png"):
        filename += ".png"

    img = ImageGrab.grabclipboard()
    if img is None:
        print("❌ Chưa thấy ảnh trong bộ nhớ tạm (Clipboard)!")
        print("👉 Vui lòng nhấn Alt + PrtScn (chụp cửa sổ) hoặc PrtScn (chụp màn hình) trước rồi chạy lại lệnh.")
        return

    out_dir = ROOT / "docs" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    img.save(out_path, "PNG")
    print(f"✅ ĐÃ LƯU ẢNH THÀNH CÔNG: docs/images/{filename}")


if __name__ == "__main__":
    main()
