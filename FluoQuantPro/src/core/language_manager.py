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
        
        # 默认跟随系统语言
        import locale
        sys_lang = locale.getdefaultlocale()[0] # e.g. 'zh_CN' or 'en_US'
        default_lang = "zh" if sys_lang and sys_lang.startswith("zh") else "en"
        
        self.current_lang = self.settings.value("language", default_lang)
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()
        self._initialized = True

    def _load_translations(self):
        """Loads translations from the JSON file."""
        try:
            import sys
            json_path = None
            
            # 开发环境路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            p_dev = os.path.join(current_dir, "..", "resources", "translations.json")
            
            if os.path.exists(p_dev):
                json_path = p_dev
            else:
                # 打包环境路径
                if getattr(sys, 'frozen', False):
                    base_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
                    for sub in ["_internal/src/resources", "_internal/resources", "resources"]:
                        p = os.path.join(base_dir, sub, "translations.json")
                        if os.path.exists(p):
                            json_path = p
                            break

            if json_path and os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
                print(f"Loaded translations from: {json_path}")
            else:
                print(f"Warning: Translation file not found.")
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
        if not text:
            return ""
            
        if self.current_lang == "en":
            return text
        
        # 查找翻译
        translation = self.translations.get(text)
        if isinstance(translation, dict):
            return translation.get(self.current_lang, text)
        
        return text

    def format_number(self, value: float, decimals: int = 2) -> str:
        """Localize number formatting (e.g. 1,234.56 vs 1.234,56)."""
        # 目前中文和英文的小数点习惯一致，但预留此接口
        return f"{value:,.{decimals}f}"

    def format_date(self, date_obj) -> str:
        """Localize date formatting."""
        if self.current_lang == "zh":
            return date_obj.strftime("%Y-%m-%d %H:%M:%S")
        return date_obj.strftime("%b %d, %Y %I:%M %p")

# Global shortcut
def tr(text: str) -> str:
    return LanguageManager.instance().tr(text)
