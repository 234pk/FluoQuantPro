import json
import os
from PySide6.QtCore import QObject, Signal, QSettings
from typing import Dict

class LanguageManager(QObject):
    """
    Manages application-wide translation and language settings.
    Loads translations from an external JSON file.
    """
    language_changed = Signal(str)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LanguageManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self.settings = QSettings("FluoQuantPro", "Settings")
        self.current_lang = self.settings.value("language", "en")
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()
        self._initialized = True

    def _load_translations(self):
        """Loads translations from the JSON file."""
        try:
            # 兼容开发环境和打包环境
            # 开发环境：src/core/language_manager.py -> src/resources/translations.json
            # 打包环境：_internal/src/resources/translations.json 或 _internal/resources/translations.json
            
            # 优先尝试使用 get_resource_path (如果 main.py 注入了或者我们自己实现)
            # 由于这是 core 模块，我们自己简单实现一个 resource finder
            
            import sys
            
            json_path = None
            
            # 1. 尝试相对于 exe 的路径 (打包后)
            if getattr(sys, 'frozen', False):
                # PyInstaller mode
                base_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
                # 我们的 spec 把 src/resources 映射到了 src/resources 吗？
                # 检查 spec: datas=[('resources', 'resources')] -> 这映射的是根目录的 resources
                # 如果我们把 src/resources/translations.json 加进去，应该放在哪？
                
                # 尝试路径 1: _internal/src/resources/translations.json
                p1 = os.path.join(base_dir, "_internal", "src", "resources", "translations.json")
                if os.path.exists(p1): json_path = p1
                
                # 尝试路径 2: _internal/resources/translations.json (如果映射到了根目录)
                p2 = os.path.join(base_dir, "_internal", "resources", "translations.json")
                if os.path.exists(p2): json_path = p2
                
                # 尝试路径 3: 就在 _internal 下
                p3 = os.path.join(base_dir, "_internal", "translations.json")
                if os.path.exists(p3): json_path = p3
                
                # Mac .app 路径
                if not json_path and sys.platform == 'darwin':
                    # .app/Contents/Resources/translations.json
                    p4 = os.path.join(base_dir, "Resources", "translations.json")
                    if os.path.exists(p4): json_path = p4
                    
            # 2. 尝试相对于当前文件的路径 (开发环境)
            if not json_path:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # src/core -> src/resources
                p_dev = os.path.join(current_dir, "..", "resources", "translations.json")
                if os.path.exists(p_dev): json_path = p_dev

            if json_path and os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
                print(f"Loaded translations from: {json_path}")
            else:
                print(f"Warning: Translation file not found. Checked multiple locations.")
        except Exception as e:
            print(f"Error loading translations: {e}")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = LanguageManager()
        return cls._instance

    def set_language(self, lang: str):
        if lang != self.current_lang:
            self.current_lang = lang
            self.settings.setValue("language", lang)
            self.language_changed.emit(lang)

    def tr(self, text: str) -> str:
        """Translates the given text to the current language."""
        if self.current_lang == "en":
            return text
        
        translation = self.translations.get(text)
        if translation:
            return translation.get(self.current_lang, text)
        return text

# Global shortcut
def tr(text: str) -> str:
    return LanguageManager.instance().tr(text)
