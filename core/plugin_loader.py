"""
Plugin Loader - 支援一般執行 & PyInstaller 打包
"""
import importlib.util
import inspect
import sys
import traceback
from pathlib import Path
from typing import List, Type

from core.plugin_base import PluginBase


def discover_plugins(plugins_path: Path) -> List[Type[PluginBase]]:
    """
    從指定路徑掃描 plugin，同時相容：
    1. python main.py  （從 .py 原始檔載入）
    2. PyInstaller exe （從 _MEIPASS/plugins/*.py 載入）
    """
    print(f"[Loader] 掃描：{plugins_path}  存在：{plugins_path.exists()}")

    if not plugins_path.exists():
        print(f"[Loader] ❌ 找不到 plugins 目錄！")
        return []

    plugin_classes = []

    for py_file in sorted(plugins_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"plugins.{py_file.stem}"
        try:
            if module_name not in sys.modules:
                spec = importlib.util.spec_from_file_location(module_name, str(py_file))
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
            else:
                mod = sys.modules[module_name]

            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if (issubclass(obj, PluginBase)
                        and obj is not PluginBase
                        and obj.__module__ == module_name):
                    plugin_classes.append(obj)
                    print(f"[Loader] ✅ {obj.PLUGIN_ICON} {obj.PLUGIN_NAME}")

        except Exception as e:
            print(f"[Loader] ❌ {py_file.name}: {e}")
            traceback.print_exc()

    plugin_classes.sort(key=lambda c: getattr(c, "PLUGIN_ORDER", 99))
    print(f"[Loader] 共 {len(plugin_classes)} 個 plugin")
    return plugin_classes
