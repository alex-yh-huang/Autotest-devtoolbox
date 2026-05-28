"""
主視窗 - 側邊欄導航 + 動態載入 Plugin
新增：系統匣（System Tray）縮起來 / 桌搭功能
"""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QFrame, QSizePolicy,
    QApplication, QPushButton, QScrollArea,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import QTimer

from core.plugin_loader import discover_plugins


def _make_tray_icon() -> QIcon:
    """動態產生一個簡單的工具箱圖示（不需要外部圖片檔）"""
    px = QPixmap(64, 64)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 背景圓形
    painter.setBrush(QColor("#4a9eff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 60, 60)

    # 工具圖示「🛠」用文字畫
    painter.setPen(QColor("white"))
    font = QFont()
    font.setPointSize(28)
    painter.setFont(font)
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "🛠")

    painter.end()
    return QIcon(px)


class SidebarButton(QWidget):
    """
    側邊欄功能按鈕 — 用 QWidget 包裝避免 QPushButton+layout 在 Windows 顯示異常
    """
    def __init__(self, icon: str, name: str, desc: str, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._selected = False
        self._on_click_cb = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(2)

        # 上排：icon + name
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet("font-size: 17px; background: transparent;")
        self._icon_lbl.setFixedWidth(24)

        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            "color: #e0e0e0; font-size: 13px; font-weight: bold; background: transparent;"
        )

        top.addWidget(self._icon_lbl)
        top.addWidget(self._name_lbl, 1)
        layout.addLayout(top)

        # 下排：desc
        self._desc_lbl = QLabel(desc)
        self._desc_lbl.setStyleSheet("color: #666; font-size: 11px; background: transparent;")
        self._desc_lbl.setWordWrap(True)
        layout.addWidget(self._desc_lbl)

        self._update_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def set_click_callback(self, cb):
        self._on_click_cb = cb

    def _update_style(self):
        if self._selected:
            self.setStyleSheet("""
                SidebarButton {
                    background: #1e2d42;
                    border-left: 3px solid #4a9eff;
                    border-radius: 6px;
                }
            """)
        else:
            self.setStyleSheet("""
                SidebarButton {
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                }
                SidebarButton:hover {
                    background: #252525;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._on_click_cb:
                self._on_click_cb(self._index)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet("""
                SidebarButton { background: #252525; border-radius: 6px; border: none; }
            """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_style()
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, plugins):
        super().__init__()
        self.plugins = plugins
        self.plugin_instances = []
        self.sidebar_buttons = []
        self._tray_quitting = False   # 標記是真的要退出，還是只是縮到托盤

        self.setWindowTitle("🛠️  DevToolbox")
        self.setMinimumSize(960, 640)
        # 初始大小由 main.py 依螢幕動態設定，這裡不 hardcode

        self._setup_palette()
        self._build_ui()
        self._setup_tray()      # ← 新增：建立系統匣
        self._load_plugins()

        if self.sidebar_buttons:
            self._switch_plugin(0)

    def _setup_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,      QColor("#1a1a1a"))
        palette.setColor(QPalette.ColorRole.WindowText,  QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Base,        QColor("#1e1e1e"))
        palette.setColor(QPalette.ColorRole.Text,        QColor("#d4d4d4"))
        palette.setColor(QPalette.ColorRole.Button,      QColor("#2a2a2a"))
        palette.setColor(QPalette.ColorRole.ButtonText,  QColor("#e0e0e0"))
        self.setPalette(palette)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 側邊欄 ─────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background: #141414;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(2)

        # 標題
        title = QLabel("DevToolbox")
        title.setStyleSheet(
            "color: #4a9eff; font-size: 15px; font-weight: bold;"
            "padding: 4px 6px 14px 6px; letter-spacing: 1px; background: transparent;"
        )
        sidebar_layout.addWidget(title)

        # 分隔線
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background: #2a2a2a; margin-bottom: 6px;")
        sidebar_layout.addWidget(line)

        # Plugin 按鈕放這裡
        self.btn_container = QVBoxLayout()
        self.btn_container.setSpacing(2)
        self.btn_container.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addLayout(self.btn_container)
        sidebar_layout.addStretch()

        # 版本
        version = QLabel("v1.0.0")
        version.setStyleSheet("color: #444; font-size: 11px; padding: 4px 6px; background: transparent;")
        sidebar_layout.addWidget(version)

        # 右側分隔線
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #2a2a2a;")

        # ── 內容區 ─────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #1a1a1a;")

        main_layout.addWidget(sidebar)
        main_layout.addWidget(sep)
        main_layout.addWidget(self.stack, 1)

    # ──────────────────────────────────────────────────────
    #  系統匣（Tray）相關
    # ──────────────────────────────────────────────────────
    def _setup_tray(self):
        """建立系統匣圖示與右鍵選單"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return  # 系統不支援就跳過，不影響原功能

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(_make_tray_icon())
        self.tray_icon.setToolTip("DevToolbox")

        # 右鍵選單
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #2a3f5f;
            }
            QMenu::separator {
                height: 1px;
                background: #333;
                margin: 4px 8px;
            }
        """)

        action_show = tray_menu.addAction("🛠️  顯示 DevToolbox")
        action_show.triggered.connect(self._show_window)

        action_hide = tray_menu.addAction("➖  縮到系統匣")
        action_hide.triggered.connect(self._hide_to_tray)

        tray_menu.addSeparator()

        action_quit = tray_menu.addAction("✖  結束程式")
        action_quit.triggered.connect(self._quit_app)

        self.tray_icon.setContextMenu(tray_menu)

        # 雙擊圖示 → 顯示/隱藏視窗
        self.tray_icon.activated.connect(self._on_tray_activated)

        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        """雙擊或單擊托盤圖示"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 單擊：若隱藏則顯示，若顯示則縮到托盤
            if self.isVisible():
                self._hide_to_tray()
            else:
                self._show_window()

    def _show_window(self):
        """從托盤呼出視窗，定位到滑鼠所在螢幕的中央"""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # 重新定位到當前游標所在螢幕的中央（解決多螢幕跑版）
        try:
            from PyQt6.QtGui import QCursor
            cursor_pos = QCursor.pos()
            screen = QApplication.screenAt(cursor_pos)
            if screen is None:
                screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                w = self.width()
                h = self.height()
                w = min(w, geo.width())
                h = min(h, geo.height())
                self.resize(w, h)
                self.move(
                    geo.x() + (geo.width() - w) // 2,
                    geo.y() + (geo.height() - h) // 2,
                )
        except Exception:
            pass

    def _hide_to_tray(self):
        """隱藏到系統匣，顯示氣泡提示（第一次才提示）"""
        self.hide()
        if hasattr(self, 'tray_icon') and not getattr(self, '_tray_hinted', False):
            self.tray_icon.showMessage(
                "DevToolbox",
                "已縮到系統匣，點擊圖示可重新開啟",
                QSystemTrayIcon.MessageIcon.Information,
                2500
            )
            self._tray_hinted = True

    def _quit_app(self):
        """真正退出程式"""
        self._tray_quitting = True
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        QApplication.quit()

    # ──────────────────────────────────────────────────────
    #  關閉事件：攔截 X 按鈕 → 改成縮到托盤
    # ──────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self._tray_quitting:
            event.accept()   # 真的要關
        elif hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            event.ignore()   # 攔截，改縮到托盤
            self._hide_to_tray()
        else:
            event.accept()

    # ──────────────────────────────────────────────────────
    #  原有 Plugin 邏輯（未修改）
    # ──────────────────────────────────────────────────────
    def _load_plugins(self):
        for i, plugin_cls in enumerate(self.plugins):
            try:
                instance = plugin_cls()
                self.plugin_instances.append(instance)
                self.stack.addWidget(instance)

                btn = SidebarButton(
                    plugin_cls.PLUGIN_ICON,
                    plugin_cls.PLUGIN_NAME,
                    plugin_cls.PLUGIN_DESC,
                    index=i,
                )
                btn.set_click_callback(self._switch_plugin)
                self.sidebar_buttons.append(btn)
                self.btn_container.addWidget(btn)

            except Exception as e:
                import traceback
                print(f"[MainWindow] 載入 plugin {plugin_cls.PLUGIN_NAME} 失敗: {e}")
                traceback.print_exc()

    def _switch_plugin(self, index: int):
        # 更新按鈕狀態
        for i, btn in enumerate(self.sidebar_buttons):
            btn.set_selected(i == index)

        # 通知舊 plugin
        current = self.stack.currentWidget()
        if hasattr(current, "on_deactivated"):
            current.on_deactivated()

        # 切換
        self.stack.setCurrentIndex(index)
        new_plugin = self.plugin_instances[index]
        if hasattr(new_plugin, "on_activated"):
            new_plugin.on_activated()

        self.setWindowTitle(f"🛠️  DevToolbox — {self.plugins[index].PLUGIN_NAME}")
