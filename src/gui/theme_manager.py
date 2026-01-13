import os
import sys
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import QSettings, QTimer, Qt, QObject, Signal
from src.core.language_manager import tr
from src.core.logger import Logger

class ThemeManager(QObject):
    """
    Unified theme and stylesheet management for FluoQuant Pro.
    Supports Light, Dark, Macchiato, and Sakura themes.
    """
    _instance = None
    theme_changed = Signal(str)
    
    THEMES = {
        "light": tr("Light (PPT Style)"),
        "dark": tr("Dark (Modern)"),
        "macchiato": tr("Macchiato (High Contrast)"),
        "sakura": tr("Sakura (Cute Pink)"),
        "ocean": tr("Ocean (Deep Sea)"),
        "dopamine": tr("Dopamine (Vibrant)"),
        "macaron": tr("Macaron (Elegant)"),
        "eyecare": tr("Eye-Care (Healthy)")
    }

    def __init__(self):
        super().__init__()
        self.settings = QSettings("FluoQuantPro", "AppSettings")
        self._last_titlebar_style = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_current_theme(self):
        return self.settings.value("ui_theme", "light")

    def set_theme(self, theme_name):
        if theme_name in self.THEMES:
            self.settings.setValue("ui_theme", theme_name)
            self.apply_theme()
            self.theme_changed.emit(theme_name)
            return True
        return False

    def toggle_theme(self):
        """Toggles through all available themes."""
        current = self.get_current_theme()
        
        # Cycle: light -> dark -> macchiato -> sakura -> light
        themes = list(self.THEMES.keys())
        current_idx = themes.index(current) if current in themes else 0
        new_theme = themes[(current_idx + 1) % len(themes)]
            
        self.set_theme(new_theme)
        return new_theme

    def apply_theme(self, window=None):
        """Sets the application stylesheet and palette based on the current theme."""
        theme = self.get_current_theme()
        
        # Clear icon cache to force regeneration with new theme colors
        from src.gui.icon_manager import IconManager
        IconManager._cache.clear()

        if theme == "dark":
            bg_color = "#1e1e1e"
            text_color = "#e0e0e0"
            accent_color = "#3498db"
            header_bg = "#2d2d2d"
            header_text = "#ffffff"
            toolbar_bg = "#252526"
            border_color = "#3e3e42"
            item_hover = "#3e3e42"
            input_bg = "#2d2d2d"
            group_border = "#454545"
            tab_bg = "#2d2d2d"
            tab_selected = "#1e1e1e"
            button_bg = "#333333"
            button_hover = "#404040"
            button_pressed = "#505050"
            success_color = "#2ecc71"
            info_color = "#3498db"
            warning_color = "#f1c40f"
            danger_color = "#e74c3c"
        elif theme == "macchiato":
            bg_color = "#24273a"      # Base
            text_color = "#f4f4f4"    # Brightened Text
            accent_color = "#c6a0f6"  # Brighter Mauve
            header_bg = "#1e2030"     # Mantle
            header_text = "#ffffff"   # Pure White for Headers
            toolbar_bg = "#363a4f"    # Surface0
            border_color = "#494d64"  # Surface1
            item_hover = "#5b6078"    # Surface2
            input_bg = "#1e2030"      # Mantle
            group_border = "#494d64"  # Surface1
            tab_bg = "#1e2030"        # Mantle
            tab_selected = "#24273a"  # Base
            button_bg = "#363a4f"     # Surface0
            button_hover = "#494d64"  # Surface1
            button_pressed = "#5b6078" # Surface2
            success_color = "#a6da95" # Green
            info_color = "#8aadf4"    # Blue
            warning_color = "#eed49f" # Yellow
            danger_color = "#ed8796"  # Red
        elif theme == "sakura":
            bg_color = "#fff5f7"      # Very Light Pink
            text_color = "#5d2a37"    # Dark Rose for Contrast
            accent_color = "#ff85a2"  # Sakura Pink
            header_bg = "#ffebf0"     # Light Pink
            header_text = "#5d2a37"   # Dark Rose
            toolbar_bg = "#ffe0e9"    # Soft Pink
            border_color = "#ffccd9"  # Pink Border
            item_hover = "#ffebf0"    # Light Pink Hover
            input_bg = "#ffffff"      # White Input
            group_border = "#ffccd9"  # Pink Border
            tab_bg = "#ffe0e9"        # Soft Pink
            tab_selected = "#fff5f7"  # Base
            button_bg = "#ffffff"     # White Button
            button_hover = "#ffebf0"  # Light Pink Hover
            button_pressed = "#ffccd9" # Pink Pressed
            success_color = "#4caf50" # Green
            info_color = "#2196f3"    # Blue
            warning_color = "#ff9800" # Orange
            danger_color = "#f44336"  # Red
        elif theme == "ocean":
            bg_color = "#001B2E"      # Deep Sea Blue
            text_color = "#E0FBFC"    # Ice Blue Text
            accent_color = "#00B4D8"  # Vibrant Blue
            header_bg = "#1B263B"     # Navy
            header_text = "#E0FBFC"
            toolbar_bg = "#0D1B2A"    # Darker Navy
            border_color = "#415A77"  # Blue Grey
            item_hover = "#1B263B"
            input_bg = "#0D1B2A"
            group_border = "#415A77"
            tab_bg = "#0D1B2A"
            tab_selected = "#1B263B"
            button_bg = "#1B263B"
            button_hover = "#415A77"
            button_pressed = "#778DA9"
            success_color = "#52B788" # Seafoam Green
            info_color = "#48CAE4"    # Sky Blue
            warning_color = "#F4A261" # Sand Orange
            danger_color = "#FF6B6B"  # Soft Red
        elif theme == "dopamine":
            bg_color = "#FFF9E6"      # Cream Beige
            text_color = "#333333"    # Dark Grey
            accent_color = "#845EC2"  # Deep Purple
            header_bg = "#F0F8FF"     # Alice Blue
            header_text = "#845EC2"
            toolbar_bg = "#FFF9E6"
            border_color = "#E8E8E8"
            item_hover = "#F0F8FF"
            input_bg = "#ffffff"
            group_border = "#E8E8E8"
            tab_bg = "#F0F8FF"
            tab_selected = "#FFF9E6"
            button_bg = "#ffffff"
            button_hover = "#F0F8FF"
            button_pressed = "#E8E8E8"
            success_color = "#00F5FF" # Cyan
            info_color = "#4D96FF"    # Sky Blue
            warning_color = "#FFD93D" # Sunshine Yellow
            danger_color = "#FF6B6B"  # Coral Red
        elif theme == "macaron":
            bg_color = "#FFF9F5"      # Milk White
            text_color = "#7A7A7A"    # Medium Grey
            accent_color = "#6B5B95"  # Deep Purple Grey
            header_bg = "#FDF6F0"     # Light Beige
            header_text = "#6B5B95"
            toolbar_bg = "#FFF9F5"
            border_color = "#E8E8E8"
            item_hover = "#FDF6F0"
            input_bg = "#ffffff"
            group_border = "#E8E8E8"
            tab_bg = "#FDF6F0"
            tab_selected = "#FFF9F5"
            button_bg = "#ffffff"
            button_hover = "#FDF6F0"
            button_pressed = "#E8E8E8"
            success_color = "#FF9AA2" # Macaron Berry
            info_color = "#FFDAC1"    # Macaron Apricot
            warning_color = "#B5EAD7" # Macaron Green
            danger_color = "#FFB7B2"  # Macaron Red
        elif theme == "eyecare":
            bg_color = "#C7EDCC"      # Classic Bean Paste Green
            text_color = "#333333"    # Dark Grey
            accent_color = "#7AA87F"  # Moss Green
            header_bg = "#E3E8E6"     # Grey Green
            header_text = "#333333"
            toolbar_bg = "#F2F4F3"    # Very Light Grey Green
            border_color = "#BFA080"  # Warm Coffee
            item_hover = "#E3E8E6"
            input_bg = "#ffffff"
            group_border = "#BFA080"
            tab_bg = "#E3E8E6"
            tab_selected = "#C7EDCC"
            button_bg = "#ffffff"
            button_hover = "#E3E8E6"
            button_pressed = "#BFA080"
            success_color = "#7AA87F" # Moss Green
            info_color = "#8FA6C5"    # Foggy Blue
            warning_color = "#8FB596" # Bean Paste Green
            danger_color = "#C47474"  # Rust Red
        else: # light
            bg_color = "#ffffff"
            text_color = "#323130"
            accent_color = "#0078d4" # Office Blue
            header_bg = "#ffffff"
            header_text = "#323130"
            toolbar_bg = "#f3f2f1"
            border_color = "#edebe9"
            item_hover = "#f3f2f1"
            input_bg = "#ffffff"
            group_border = "#d2d0ce"
            tab_bg = "#f3f2f1"
            tab_selected = "#ffffff"
            button_bg = "#ffffff"
            button_hover = "#edebe9"
            button_pressed = "#e1dfdd"
            success_color = "#107c10" # Office Green
            info_color = "#0078d4"    # Office Blue
            warning_color = "#d83b01" # Office Orange
            danger_color = "#a80000"  # Office Red

        # Update application palette
        palette = QApplication.palette()
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Window, QColor(bg_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.WindowText, QColor(text_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Base, QColor(input_bg))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Text, QColor(text_color))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Button, QColor(header_bg))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.ButtonText, QColor(header_text))
        palette.setColor(palette.ColorGroup.All, palette.ColorRole.Highlight, QColor(accent_color))
        QApplication.setPalette(palette)

        # Load and process QSS
        try:
            # 1. 尝试相对于当前文件的路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            p_rel = os.path.normpath(os.path.join(current_dir, "..", "resources", "style.qss"))
            
            # 2. 尝试可执行文件所在目录
            if getattr(sys, 'frozen', False):
                base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            else:
                base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

            qss_locations = [
                p_rel,
                os.path.join(base_dir, "src", "resources", "style.qss"),
                os.path.join(base_dir, "resources", "style.qss"),
                os.path.join(base_dir, "_internal", "src", "resources", "style.qss")
            ]
            
            qss_path = None
            for loc in qss_locations:
                if os.path.exists(loc):
                    qss_path = loc
                    break
            
            if not qss_path:
                raise FileNotFoundError("Could not find style.qss in any of the expected locations.")

            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
            
            replacements = {
                "bg_color": bg_color,
                "text_color": text_color,
                "accent_color": accent_color,
                "header_bg": header_bg,
                "header_text": header_text,
                "toolbar_bg": toolbar_bg,
                "border_color": border_color,
                "item_hover": item_hover,
                "input_bg": input_bg,
                "group_border": group_border,
                "tab_bg": tab_bg,
                "tab_selected": tab_selected,
                "button_bg": button_bg,
                "button_hover": button_hover,
                "button_pressed": button_pressed,
                "success_color": success_color,
                "info_color": info_color,
                "warning_color": warning_color,
                "danger_color": danger_color
            }
            
            # Platform specific adjustments
            if sys.platform == "darwin":
                replacements.update({
                    "font_weight": "500",
                    "base_font_size": "12px",
                    "title_font_size": "28px",
                    "sidebar_padding": "4px",
                    "item_spacing": "4px"
                })
            else:
                replacements.update({
                    "font_weight": "600",
                    "base_font_size": "13px",
                    "title_font_size": "32px",
                    "sidebar_padding": "2px",
                    "item_spacing": "2px"
                })
            
            for key, value in replacements.items():
                qss = qss.replace(f"{{{key}}}", value)
            
            # Apply to application
            app = QApplication.instance()
            app.setStyleSheet(qss)
            
            self._last_titlebar_style = (header_bg, border_color, header_text)
            
            # Apply to all top-level windows
            for widget in app.topLevelWidgets():
                widget.setStyleSheet(qss)
                if hasattr(widget, 'menu_actions_widget'):
                    widget.menu_actions_widget.setStyleSheet(qss)
                
                # Apply titlebar style to top-level windows
                self.apply_windows_titlebar_style(widget, header_bg, border_color, header_text)
                
            Logger.info(f"[Theme] Stylesheet applied (Theme: {theme})")
        except Exception as e:
            Logger.error(f"[Theme] Failed to load stylesheet: {e}")
            if window:
                window.setStyleSheet(f"QMainWindow {{ background-color: {bg_color}; color: {text_color}; }}")

    def apply_windows_titlebar_style(self, window, caption_hex: str, border_hex: str, text_hex: str):
        """Win32 specific titlebar styling."""
        try:
            if sys.platform != "win32":
                return

            hwnd = int(window.winId())

            def to_colorref(hex_color: str) -> int:
                s = (hex_color or "").strip()
                if s.startswith("#"):
                    s = s[1:]
                if len(s) != 6:
                    return 0
                r = int(s[0:2], 16)
                g = int(s[2:4], 16)
                b = int(s[4:6], 16)
                return (b << 16) | (g << 8) | r

            dwmapi = ctypes.windll.dwmapi
            set_attr = dwmapi.DwmSetWindowAttribute

            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            caption = ctypes.c_uint(to_colorref(caption_hex))
            border = ctypes.c_uint(to_colorref(border_hex))
            text = ctypes.c_uint(to_colorref(text_hex))

            set_attr(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
            set_attr(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border))
            set_attr(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text))

            Logger.debug(f"[Theme] Windows titlebar styled: caption={caption_hex}")
        except Exception as e:
            Logger.debug(f"[Theme] Windows titlebar styling skipped: {e}")
