"""
Plugin Base Class
所有功能模組都必須繼承此 class，實作對應方法即可自動被主程式載入。
"""
from PyQt6.QtWidgets import QWidget


class PluginBase(QWidget):
    """
    每個 plugin 繼承此 class。
    必填屬性：
        PLUGIN_NAME  (str)  : 顯示在側邊欄的名稱
        PLUGIN_ICON  (str)  : 顯示在側邊欄的 emoji / 符號
        PLUGIN_DESC  (str)  : 功能簡短說明
    """
    PLUGIN_NAME: str = "未命名功能"
    PLUGIN_ICON: str = "🔧"
    PLUGIN_DESC: str = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """在這裡建立 UI 元件，子類別必須實作。"""
        raise NotImplementedError(f"{self.__class__.__name__} 必須實作 setup_ui()")

    def on_activated(self):
        """每次切換到此 plugin 時觸發，可用來刷新資料。"""
        pass

    def on_deactivated(self):
        """切換離開此 plugin 時觸發，可用來儲存狀態。"""
        pass
