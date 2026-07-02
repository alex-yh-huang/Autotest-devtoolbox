# 🛠️ DevToolbox

基於 PyQt6 的模組化開發者工具箱，Plugin 架構設計，方便擴充各種開發工作流程。

## 📦 安裝

```bash
pip install -r requirements.txt
```

## ▶️ 執行

```bash
python main.py
```

## 📁 目錄結構

```
toolbox/
├── main.py              ← 程式入口
├── main_window.py       ← 主視窗（側邊欄 + 內容區 + 系統匣）
├── requirements.txt
├── DevToolbox.spec      ← PyInstaller 打包設定
├── core/
│   ├── plugin_base.py   ← 所有 Plugin 的基底類別
│   └── plugin_loader.py ← 自動掃描載入 Plugin
└── plugins/
    └── p01_ssh_forwarder.py  ← SSH 通道管理
```

## 📦 打包成 .exe（Windows）

```bash
pyinstaller --clean DevToolbox.spec
```

打包後的 `DevToolbox.exe` 在 `dist/` 目錄。

## 🔧 打包除錯說明

### 問題：打包後 UI 空白、側邊欄沒有功能按鈕

原因：PyInstaller 預設不會帶入 `plugins/` 目錄，必須使用 `.spec` 檔打包。

若新增新的 Plugin（例如 `plugins/p02_my_tool.py`），請在 `DevToolbox.spec` 的 `hiddenimports` 加上對應模組路徑，再重新執行打包：

```python
hiddenimports=[
    'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'configparser', 'yaml', 'importlib.util', 'importlib.machinery',
    'plugins.p01_ssh_forwarder',  # ← 每個 Plugin 都要在這裡加上
    'plugins.p02_my_tool',
],
```

### 除錯技巧

打包時先把 `DevToolbox.spec` 裡的 `console=False` 改成 `console=True`，
執行 exe 時會跳出終端機視窗，可以看到 Plugin Loader 的載入 log。

```bash
pyinstaller DevToolbox.spec
```

---

## ➕ 新增功能（Plugin 擴充方式）

在 `plugins/` 目錄新建一個 `.py` 檔，繼承 `PluginBase`：

```python
# plugins/p02_my_feature.py
from PyQt6.QtWidgets import QVBoxLayout, QLabel
from core.plugin_base import PluginBase

class MyFeaturePlugin(PluginBase):
    PLUGIN_NAME = "我的功能"
    PLUGIN_ICON = "🚀"
    PLUGIN_DESC = "功能簡短說明"
    PLUGIN_ORDER = 2   # 側邊欄排序（數字越小越前面）

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hello, Plugin!"))

    def on_activated(self):
        """每次切換到此功能時觸發（可選）"""
        pass

    def on_deactivated(self):
        """離開此功能時觸發（可選）"""
        pass
```

重新啟動程式，新功能會自動出現在側邊欄。**不需修改任何主程式檔案。**

記得同步更新 `DevToolbox.spec` 的 `hiddenimports`，打包才會包含新 Plugin。

---

## 🖥️ 系統匣（縮到桌面）

| 操作 | 效果 |
|------|------|
| 按視窗 ✕ | 縮到系統匣，程式繼續背景執行 |
| 單擊托盤圖示 | 顯示 / 隱藏視窗 |
| 雙擊托盤圖示 | 呼出視窗 |
| 右鍵托盤圖示 | 顯示、縮到匣、結束程式 |
