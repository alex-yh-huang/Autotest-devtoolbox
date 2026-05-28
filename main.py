"""
DevToolbox - 主程式入口
執行: python main.py
打包: pyinstaller DevToolbox.spec
"""
import sys
import os
from pathlib import Path

# ── DPI 縮放修正（必須在 QApplication 建立前設定）──────────
# 讓 Windows 知道這支程式自己處理 DPI，不要系統幫忙放大（避免模糊或跑版）
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# 打包後額外確保 Windows 高 DPI 正常
if hasattr(sys, "frozen"):
    try:
        import ctypes
        # 告訴 Windows：本程式支援 Per-Monitor V2 DPI（多螢幕各自 DPI）
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ── BASE_DIR：frozen(打包) vs 一般執行 ──────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from core.plugin_loader import discover_plugins
from main_window import MainWindow


def main():
    # Per-Monitor DPI：視窗移到哪個螢幕就用那個螢幕的 DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DevToolbox")
    app.setStyle("Fusion")
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    plugins = discover_plugins(BASE_DIR / "plugins")

    window = MainWindow(plugins)

    # ── 視窗定位到主螢幕中央，尺寸依螢幕大小自動調整 ──────────
    screen = app.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        dpr = screen.devicePixelRatio()
        # 目標：螢幕寬的 75%、高的 80%（最小 960x640）
        w = max(960, int(geo.width() * 0.75))
        h = max(640, int(geo.height() * 0.80))
        window.resize(w, h)
        # 置中
        window.move(
            geo.x() + (geo.width() - w) // 2,
            geo.y() + (geo.height() - h) // 2,
        )

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
