import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, 
                             QStackedWidget, QFrame, QScrollArea, QLabel, QSizePolicy)
from PySide6.QtCore import Qt, QSize, Signal, Property, QRect, QPoint
from PySide6.QtGui import QIcon, QPainter, QColor, QPen, QBrush, QPixmap, QFont
from PySide6.QtSvg import QSvgRenderer

from src.gui.theme_manager import ThemeManager
from src.core.language_manager import tr

# SVG Path Data - Professional & Scientific Style
SVG_ICONS = {
    "toolbox": "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z",
    "adjustments": "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6",
    "enhance": "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z M19 3v4 M21 5h-4",
    "colocalization": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 16a6 6 0 1 1 0-12 6 6 0 0 1 0 12Zm0-8a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
    "annotation": "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
    "results": "M3 3v18h18 M18 17V9 M13 17V5 M8 17v-3",
    "collapse": "M15 18l-6-6 6-6",
    "expand": "M9 18l6-6-6-6"
}

class SidebarButton(QToolButton):
    def __init__(self, key, text, parent=None):
        super().__init__(parent)
        self.key = key
        self.setText(text)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        
        import sys
        if sys.platform == "darwin":
            self.setFont(QFont("PingFang SC", 12))
        else:
            self.setFont(QFont("Segoe UI", 9))
        
        self._is_collapsed = False
        self._theme = "light"
        self._accent_color = "#3498db"
        
    def set_collapsed(self, collapsed):
        self._is_collapsed = collapsed
        if collapsed:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setFixedSize(36, 36)
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setFixedHeight(36)
            self.setMinimumWidth(0) # Allow squishing
            self.setMaximumWidth(220)

    def update_icon(self, theme, color):
        self._theme = theme
        self._accent_color = color
        mode = 'fill' if theme == 'sakura' else 'stroke'
        path_data = SVG_ICONS.get(self.key, "")
        
        svg_xml = f"""
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="{path_data}" 
                  {mode}="{color}" 
                  {'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"' if mode == 'stroke' else ''} />
        </svg>
        """
        
        renderer = QSvgRenderer(svg_xml.encode())
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(18, 18))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            # Draw Selection Indicator on the LEFT
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Indicator bar
            indicator_w = 3
            indicator_h = 20
            x = 1
            y = (self.height() - indicator_h) // 2
            
            painter.setBrush(QBrush(QColor(self._accent_color)))
            painter.setPen(Qt.NoPen)
            
            # Rounded rect for indicator
            painter.drawRoundedRect(x, y, indicator_w, indicator_h, 2, 2)
            painter.end()

class RightSidebarControlPanel(QWidget):
    currentChanged = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RightSidebarControlPanel")
        self.setMinimumWidth(0) # Allow shrinking to zero
        
        self.is_collapsed = False
        self.buttons = []
        
        self.setup_ui()
        self.apply_theme_styles()
        
        # Connect to theme changes
        ThemeManager.instance().theme_changed.connect(self.apply_theme_styles)

    def setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Sidebar Column (placed on the RIGHT within this widget)
        # Layout: [ Content Area (Expanded) ] [ Sidebar Bar ]
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("SidebarFrame")
        self.sidebar_vbox = QVBoxLayout(self.sidebar_frame)
        import sys
        if sys.platform == "darwin":
            self.sidebar_vbox.setContentsMargins(2, 6, 2, 6)
            self.sidebar_vbox.setSpacing(6)
        else:
            self.sidebar_vbox.setContentsMargins(0, 10, 0, 10)
            self.sidebar_vbox.setSpacing(4)
        self.sidebar_vbox.setAlignment(Qt.AlignTop)
        
        # 2. Content Stack
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("SidebarContentStack")
        # Ensure content stack expands to fill height and can be squished
        self.content_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.content_stack.setMinimumWidth(0)
        
        self.main_layout.addWidget(self.content_stack, 1)
        self.main_layout.addWidget(self.sidebar_frame)

        # Collapse Button at bottom
        self.sidebar_vbox.addStretch()
        self.btn_collapse = QToolButton()
        self.btn_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_collapse.setFixedSize(36, 32)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        self.sidebar_vbox.addWidget(self.btn_collapse, 0, Qt.AlignCenter)

    def add_tab(self, key, widget, label):
        btn = SidebarButton(key, label, self)
        btn.clicked.connect(lambda: self.on_button_clicked(btn))
        self.sidebar_vbox.insertWidget(len(self.buttons), btn)
        self.buttons.append(btn)
        
        self.content_stack.addWidget(widget)
        
        if len(self.buttons) == 1:
            btn.setChecked(True)
            self.content_stack.setCurrentIndex(0)
            
        self.apply_theme_styles()

    def on_button_clicked(self, clicked_btn):
        for i, btn in enumerate(self.buttons):
            if btn == clicked_btn:
                btn.setChecked(True)
                self.content_stack.setCurrentIndex(i)
                self.currentChanged.emit(i)
            else:
                btn.setChecked(False)
        self.apply_theme_styles() # Update icon colors

    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        for btn in self.buttons:
            btn.set_collapsed(self.is_collapsed)
        
        if self.is_collapsed:
            self.sidebar_frame.setFixedWidth(40)
        else:
            self.sidebar_frame.setMinimumWidth(40)
            self.sidebar_frame.setMaximumWidth(220)
            # Reset fixed width to allow layout system to compress it
            self.sidebar_frame.setFixedWidth(16777215) 
        
        self.apply_theme_styles()

    def resizeEvent(self, event):
        """Auto-collapse sidebar if the panel becomes too narrow."""
        super().resizeEvent(event)
        w = self.width()
        # If the total width is very small, we must collapse the sidebar to save space
        if w < 180 and not self.is_collapsed:
            self.toggle_collapse()
        elif w > 300 and self.is_collapsed:
            # Optionally auto-expand if there's plenty of room
            # self.toggle_collapse() 
            pass

    def apply_theme_styles(self):
        theme = ThemeManager.instance().get_current_theme()
        colors = self._get_theme_colors(theme)
        
        # Rounded corners for Sakura, sharp for others
        radius = "24px" if theme == "sakura" else "4px"
        margin = "4px" if theme == "sakura" else "2px"
        
        qss = f"""
        #SidebarFrame {{
            background-color: {colors['toolbar_bg']};
            border-left: 1px solid {colors['border_color']};
        }}
        
        SidebarButton {{
            background-color: transparent;
            color: {colors['text_color']};
            border: none;
            border-radius: {radius};
            margin: 2px {margin};
            padding: 4px 8px;
            text-align: left;
        }}
        
        SidebarButton:hover {{
            background-color: {colors['item_hover']};
        }}
        
        SidebarButton:checked {{
            background-color: {colors['tab_selected']};
            color: {colors['accent_color']};
            font-weight: bold;
        }}
        
        QToolButton#CollapseBtn {{
            border: none;
            background: transparent;
        }}
        """
        self.sidebar_frame.setStyleSheet(qss)
        
        # Update Icons
        for btn in self.buttons:
            color = colors['accent_color'] if btn.isChecked() else colors['text_color']
            btn.update_icon(theme, color)
            
        # Update Collapse Button
        col_icon_key = 'expand' if self.is_collapsed else 'collapse'
        col_icon_path = SVG_ICONS[col_icon_key]
        self.btn_collapse.setIcon(self._create_simple_icon(col_icon_path, colors['text_color']))
        self.btn_collapse.setStyleSheet(f"border: none; color: {colors['text_color']};")

    def _get_theme_colors(self, theme):
        # Professional color mapping aligned with ThemeManager
        if theme == "dark":
            return {"toolbar_bg": "#252526", "text_color": "#e0e0e0", "accent_color": "#3498db", "border_color": "#3e3e42", "item_hover": "#3e3e42", "tab_selected": "#1e1e1e"}
        elif theme == "macchiato":
            return {"toolbar_bg": "#363a4f", "text_color": "#f4f4f4", "accent_color": "#c6a0f6", "border_color": "#494d64", "item_hover": "#5b6078", "tab_selected": "#24273a"}
        elif theme == "sakura":
            return {"toolbar_bg": "#ffe0e9", "text_color": "#5d2a37", "accent_color": "#ff85a2", "border_color": "#ffccd9", "item_hover": "#ffebf0", "tab_selected": "#fff5f7"}
        elif theme == "ocean":
            return {"toolbar_bg": "#0D1B2A", "text_color": "#E0FBFC", "accent_color": "#00B4D8", "border_color": "#415A77", "item_hover": "#1B263B", "tab_selected": "#1B263B"}
        elif theme == "dopamine":
            return {"toolbar_bg": "#FFF9E6", "text_color": "#333333", "accent_color": "#845EC2", "border_color": "#E8E8E8", "item_hover": "#F0F8FF", "tab_selected": "#FFF9E6"}
        elif theme == "macaron":
            return {"toolbar_bg": "#FFF9F5", "text_color": "#7A7A7A", "accent_color": "#6B5B95", "border_color": "#E8E8E8", "item_hover": "#FDF6F0", "tab_selected": "#FFF9F5"}
        elif theme == "eyecare":
            return {"toolbar_bg": "#F2F4F3", "text_color": "#333333", "accent_color": "#7AA87F", "border_color": "#BFA080", "item_hover": "#E3E8E6", "tab_selected": "#C7EDCC"}
        else: # light
            return {"toolbar_bg": "#f3f3f3", "text_color": "#333333", "accent_color": "#2980b9", "border_color": "#dcdcdc", "item_hover": "#e1e1e1", "tab_selected": "#ffffff"}

    def _create_simple_icon(self, path_data, color):
        svg_xml = f"""
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="{path_data}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        """
        renderer = QSvgRenderer(svg_xml.encode())
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def count(self): return self.content_stack.count()
    def widget(self, index): return self.content_stack.widget(index)
    def setCurrentIndex(self, index):
        if 0 <= index < len(self.buttons): self.on_button_clicked(self.buttons[index])
    def currentIndex(self): return self.content_stack.currentIndex()
    def setCurrentWidget(self, widget):
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == widget:
                self.setCurrentIndex(i)
                break
    def setTabText(self, index, text):
        if 0 <= index < len(self.buttons): self.buttons[index].setText(text)
    def tabText(self, index):
        if 0 <= index < len(self.buttons): return self.buttons[index].text()
        return ""
    def clear(self):
        for btn in self.buttons:
            self.sidebar_vbox.removeWidget(btn)
            btn.deleteLater()
        self.buttons = []
        while self.content_stack.count() > 0:
            self.content_stack.removeWidget(self.content_stack.widget(0))
