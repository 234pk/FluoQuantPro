import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QPalette
from PySide6.QtCore import QSize, Qt, QRectF, QPointF, QByteArray
from PySide6.QtWidgets import QApplication
try:
    from PySide6.QtSvg import QSvgRenderer
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

class IconManager:
    """
    Unified icon management for FluoQuant Pro.
    Handles high DPI scaling, theme-based icons with local fallbacks, 
    custom generated icons, and caching.
    Supports SVG-based icons with dynamic theme color injection.
    """
    _cache = {}
    _resource_dir = None

    # Icon category mapping
    ICON_CATEGORIES = {
        # 历史导航 (nav)
        "refresh": "nav", "undo": "nav", "redo": "nav",
        # 交互工具 (tool)
        "select": "tool", "batch_select": "tool", "hand": "tool", "crop": "tool", "wand": "tool",
        "align_left": "tool", "align_center": "tool", "align_right": "tool",
        # 绘图标注 (draw)
        "line": "draw", "rect": "draw", "circle": "draw", "ellipse": "draw", "polygon": "draw", "text": "draw", "arrow": "draw",
        # 数据分析 (data)
        "chart": "data", "table": "data", "count": "data", "sort": "data", "coloc": "data", "expand": "data", "measure": "data", "stats": "data",
        # 文件管理 (file)
        "folder": "file", "save": "file", "import": "file", "export": "file", "export_img": "file",
        # 危险操作 (danger)
        "delete": "danger", "clear": "danger",
        # 新增操作 (success)
        "add": "success",
        # 系统设置 (meta)
        "settings": "meta", "help": "meta", "info": "meta", "shortcuts": "meta", "scale": "meta", "theme": "meta",
        # 其它
        "fit-width": "nav", "log": "data", "auto": "tool"
    }

    # Theme-based color palette for each category
    THEME_ICON_COLORS = {
        "dark": {
            "nav": "#B0BEC5", "tool": "#4DD0E1", "draw": "#FFB74D", "data": "#9575CD",
            "file": "#78909C", "danger": "#EF5350", "success": "#66BB6A", "meta": "#26C6DA"
        },
        "light": {
            "nav": "#546E7A", "tool": "#29B6F6", "draw": "#FFA726", "data": "#7E57C2",
            "file": "#607D8B", "danger": "#E53935", "success": "#43A047", "meta": "#00897B"
        },
        "macchiato": {
            "nav": "#8D6E63", "tool": "#FF7043", "draw": "#D4E157", "data": "#5C6BC0",
            "file": "#4E342E", "danger": "#D32F2F", "success": "#689F38", "meta": "#00796B"
        },
        "sakura": {
            "nav": "#F48FB1", "tool": "#BA68C8", "draw": "#FFF59D", "data": "#64B5F6",
            "file": "#4A148C", "danger": "#E91E63", "success": "#AED581", "meta": "#80CBC4"
        },
        "ocean": {
            "nav": "#90E0EF", "tool": "#48CAE4", "draw": "#ADE8F4", "data": "#0077B6",
            "file": "#415A77", "danger": "#FF6B6B", "success": "#52B788", "meta": "#023E8A"
        },
        "dopamine": {
            "nav": "#FF85A2", "tool": "#FFD93D", "draw": "#6BCB77", "data": "#4D96FF",
            "file": "#9B5DE5", "danger": "#FF6B6B", "success": "#00F5FF", "meta": "#FF8F5E"
        },
        "macaron": {
            "nav": "#FFB7B2", "tool": "#B5EAD7", "draw": "#C7CEEA", "data": "#FFDAC1",
            "file": "#E2F0CB", "danger": "#FFB7B2", "success": "#FF9AA2", "meta": "#E0BBE4"
        },
        "eyecare": {
            "nav": "#7E8C9D", "tool": "#8FB596", "draw": "#BFA080", "data": "#8FA6C5",
            "file": "#C4B6A6", "danger": "#C47474", "success": "#7AA87F", "meta": "#757B7E"
        }
    }

    # SVG Path data for common icons
    # {color} is replaced with the current theme color
    SVG_TEMPLATES = {
        "refresh": """
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" 
                      fill="{color}" stroke="{color}" stroke-width="1.2"/>
            </svg>
        """,
        "undo": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 75 80 Q 75 25 35 30 L 35 10 L 5 35 L 35 60 L 35 40 Q 55 40 60 80 Z" fill="{color}" stroke="{color}" stroke-width="12"/>
            </svg>
        """,
        "redo": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 25 80 Q 25 25 65 30 L 65 10 L 95 35 L 65 60 L 65 40 Q 45 40 40 80 Z" fill="{color}" stroke="{color}" stroke-width="12"/>
            </svg>
        """,
        "select": """
            <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <!-- Core selection box (Dashed Cross Style) -->
                <!-- Use fill="none" to prevent black fill -->
                <rect x="20" y="20" width="60" height="60" rx="4" ry="4" 
                      fill="none" 
                      stroke="{color}" 
                      stroke-width="9" 
                      stroke-dasharray="8,8"
                      stroke-linecap="round"
                      stroke-linejoin="round"/>
                
                <!-- Cross lines -->
                <line x1="50" y1="30" x2="50" y2="70" stroke="{color}" stroke-width="9" stroke-linecap="round" />
                <line x1="30" y1="50" x2="70" y2="50" stroke="{color}" stroke-width="9" stroke-linecap="round" />
                
                <!-- Corner handles -->
                <rect x="15" y="15" width="10" height="10" rx="2" fill="{color}" />
                <rect x="75" y="15" width="10" height="10" rx="2" fill="{color}" />
                <rect x="75" y="75" width="10" height="10" rx="2" fill="{color}" />
                <rect x="15" y="75" width="10" height="10" rx="2" fill="{color}" />
            </svg>
        """,
        "batch_select": """
            <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <!-- Dashed Cross Style for Batch Selection -->
                <rect x="15" y="15" width="40" height="40" rx="2" 
                      fill="none" stroke="{color}" stroke-width="6.75" stroke-dasharray="4,4"/>
                <rect x="45" y="45" width="40" height="40" rx="2" 
                      fill="none" stroke="{color}" stroke-width="6.75" stroke-dasharray="4,4"/>
                
                <!-- Selection Crosshairs -->
                <line x1="35" y1="25" x2="35" y2="45" stroke="{color}" stroke-width="4.5"/>
                <line x1="25" y1="35" x2="45" y2="35" stroke="{color}" stroke-width="4.5"/>
                
                <line x1="65" y1="55" x2="65" y2="75" stroke="{color}" stroke-width="4.5"/>
                <line x1="55" y1="65" x2="75" y2="65" stroke="{color}" stroke-width="4.5"/>
            </svg>
        """,
        "hand": """
            <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 50 15 
                         Q 50 10 55 10 Q 60 10 60 15 
                         L 60 55 
                         L 60 20 
                         Q 60 15 65 15 Q 70 15 70 20 
                         L 70 55 
                         L 70 25 
                         Q 70 20 75 20 Q 80 20 80 25 
                         L 80 65 
                         Q 80 85 60 90 
                         L 40 90 
                         Q 25 85 25 65 
                         L 25 45 
                         Q 25 40 30 40 Q 35 40 35 45 
                         L 35 55 
                         L 40 55 
                         L 40 30 
                         Q 40 25 45 25 Q 50 25 50 30 
                         L 50 55 
                         L 50 15 Z" 
                      fill="none" 
                      stroke="{color}" 
                      stroke-width="7.5" 
                      stroke-linecap="round" 
                      stroke-linejoin="round"/>
            </svg>
        """,
        "crop": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 15 35 L 85 35 M 35 15 L 35 85" stroke="{color}" stroke-width="15" fill="none" stroke-linecap="round"/>
                <path d="M 25 75 L 95 75 M 75 25 L 75 95" stroke="{color}" stroke-width="15" fill="none" stroke-linecap="round"/>
            </svg>
        """,
        "wand": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 80 L 70 30" stroke="{color}" stroke-width="15" stroke-linecap="round"/>
                <circle cx="75" cy="25" r="10" fill="{color}"/>
                <path d="M 75 5 L 75 15 M 85 25 L 95 25 M 75 35 L 75 45 M 55 25 L 65 25" stroke="{color}" stroke-width="7.5"/>
            </svg>
        """,
        "delete": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 25 L 80 25 M 30 25 L 35 85 L 65 85 L 70 25 M 40 25 L 40 15 L 60 15 L 60 25 M 45 40 L 45 70 M 55 40 L 55 70" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "clear": """
            <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <!-- 垃圾桶顶部盖子 -->
                <rect x="25" y="20" width="50" height="8" rx="2" fill="{color}" />
                
                <!-- 垃圾桶主体 -->
                <path d="M 32 30  
                         L 35 80  
                         Q 36 85 50 85  
                         Q 64 85 65 80  
                         L 68 30 Z"  
                      fill="none"  
                      stroke="{color}"  
                      stroke-width="12"  
                      stroke-linecap="round"  
                      stroke-linejoin="round"/>
                
                <!-- 垃圾桶内的X标记 -->
                <path d="M 40 45 L 60 65 M 60 45 L 40 65"  
                      stroke="{color}"  
                      stroke-width="12"  
                      stroke-linecap="round"  
                      stroke-linejoin="round"/>
                
                <!-- 顶部提手 -->
                <path d="M 38 20 Q 38 12 50 12 Q 62 12 62 20"  
                      fill="none"  
                      stroke="{color}"  
                      stroke-width="12"  
                      stroke-linecap="round"/>
            </svg>
        """,
        "export_img": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <rect x="15" y="20" width="70" height="60" rx="5" fill="none" stroke="{color}" stroke-width="12"/>
                <circle cx="35" cy="40" r="8" fill="{color}"/>
                <path d="M 15 70 L 40 45 L 60 65 L 75 50 L 85 60" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "measure": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 20 L 80 20 L 80 80 L 20 80 Z" fill="none" stroke="{color}" stroke-width="12"/>
                <path d="M 20 40 L 40 40 M 20 60 L 40 60 M 60 40 L 80 40 M 60 60 L 80 60" stroke="{color}" stroke-width="12"/>
                <circle cx="50" cy="50" r="10" stroke="{color}" stroke-width="12" fill="none"/>
            </svg>
        """,
        "stats": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 80 L 20 20 M 20 80 L 80 80" stroke="{color}" stroke-width="12" stroke-linecap="round"/>
                <rect x="30" y="50" width="12" height="30" fill="{color}"/>
                <rect x="50" y="30" width="12" height="50" fill="{color}"/>
                <rect x="70" y="60" width="12" height="20" fill="{color}"/>
            </svg>
        """,
        "grid": """
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="3" width="7" height="7" rx="1" fill="none" stroke="{color}" stroke-width="2"/>
                <rect x="14" y="3" width="7" height="7" rx="1" fill="none" stroke="{color}" stroke-width="2"/>
                <rect x="3" y="14" width="7" height="7" rx="1" fill="none" stroke="{color}" stroke-width="2"/>
                <rect x="14" y="14" width="7" height="7" rx="1" fill="none" stroke="{color}" stroke-width="2"/>
            </svg>
        """,
        "filmstrip": """
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <rect x="3" y="5" width="18" height="14" rx="1" fill="none" stroke="{color}" stroke-width="2"/>
                <line x1="3" y1="9" x2="21" y2="9" stroke="{color}" stroke-width="1.5" stroke-dasharray="2,2"/>
                <line x1="3" y1="15" x2="21" y2="15" stroke="{color}" stroke-width="1.5" stroke-dasharray="2,2"/>
                <rect x="7" y="10" width="10" height="4" rx="0.5" fill="{color}" opacity="0.6"/>
            </svg>
        """,
        "scale": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 50 L 90 50 M 10 40 L 10 60 M 90 40 L 90 60 M 30 45 L 30 55 M 50 40 L 50 60 M 70 45 L 70 55" stroke="{color}" stroke-width="12" stroke-linecap="round"/>
            </svg>
        """,
        "info": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="40" stroke="{color}" stroke-width="12" fill="none"/>
                <circle cx="50" cy="30" r="6" fill="{color}"/>
                <path d="M 50 45 L 50 75" stroke="{color}" stroke-width="12" stroke-linecap="round"/>
            </svg>
        """,
        "shortcuts": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <rect x="15" y="25" width="70" height="50" rx="5" fill="none" stroke="{color}" stroke-width="12"/>
                <path d="M 25 40 L 35 40 M 45 40 L 55 40 M 65 40 L 75 40 M 25 60 L 75 60" stroke="{color}" stroke-width="12" stroke-linecap="round"/>
            </svg>
        """,
        "add": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 50 20 L 50 80 M 20 50 L 80 50" stroke="{color}" stroke-width="18" stroke-linecap="round"/>
            </svg>
        """,
        "help": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="40" stroke="{color}" stroke-width="12" fill="none"/>
                <text x="50" y="70" font-family="Arial" font-size="60" font-weight="bold" text-anchor="middle" fill="{color}">?</text>
            </svg>
        """,
        "settings": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 50 35 A 15 15 0 1 0 50 65 A 15 15 0 1 0 50 35 Z" fill="none" stroke="{color}" stroke-width="15"/>
                <path d="M 50 10 L 50 25 M 50 75 L 50 90 M 10 50 L 25 50 M 75 50 L 90 50" stroke="{color}" stroke-width="18" stroke-linecap="round"/>
                <path d="M 22 22 L 32 32 M 68 68 L 78 78 M 22 78 L 32 68 M 68 32 L 78 22" stroke="{color}" stroke-width="18" stroke-linecap="round"/>
            </svg>
        """,
        "folder": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 20 L 40 20 L 50 30 L 90 30 L 90 80 L 10 80 Z" fill="none" stroke="{color}" stroke-width="15" stroke-linejoin="round"/>
            </svg>
        """,
        "save": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 10 L 70 10 L 85 25 L 85 90 L 20 90 Z" fill="none" stroke="{color}" stroke-width="15" stroke-linejoin="round"/>
                <rect x="35" y="10" width="30" height="25" fill="none" stroke="{color}" stroke-width="9"/>
                <rect x="30" y="55" width="40" height="35" fill="none" stroke="{color}" stroke-width="9"/>
            </svg>
        """,
        "import": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 30 50 L 70 50 M 55 35 L 70 50 L 55 65" fill="none" stroke="{color}" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M 20 20 L 80 20 L 80 80 L 20 80 Z" fill="none" stroke="{color}" stroke-width="9"/>
            </svg>
        """,
        "export": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 70 50 L 30 50 M 45 35 L 30 50 L 45 65" fill="none" stroke="{color}" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M 20 20 L 80 20 L 80 80 L 20 80 Z" fill="none" stroke="{color}" stroke-width="9"/>
            </svg>
        """,
        "chart": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 90 L 10 10 M 10 90 L 90 90" stroke="{color}" stroke-width="15" fill="none"/>
                <path d="M 10 70 L 40 40 L 60 60 L 90 20" stroke="{color}" stroke-width="12" fill="none"/>
            </svg>
        """,
        "table": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <rect x="10" y="20" width="80" height="60" rx="4" fill="none" stroke="{color}" stroke-width="15"/>
                <path d="M 10 40 L 90 40 M 10 60 L 90 60 M 35 20 L 35 80 M 65 20 L 65 80" stroke="{color}" stroke-width="9"/>
            </svg>
        """,
        "count": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="35" fill="none" stroke="{color}" stroke-width="15"/>
                <circle cx="50" cy="50" r="10" fill="{color}"/>
                <path d="M 50 5 L 50 25 M 50 75 L 50 95 M 5 50 L 25 50 M 75 50 L 95 50" stroke="{color}" stroke-width="15"/>
            </svg>
        """,
        "sort": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 25 L 80 25 M 20 50 L 60 50 M 20 75 L 40 75" stroke="{color}" stroke-width="15" stroke-linecap="round"/>
                <path d="M 80 45 L 80 85 M 72 75 L 80 85 L 88 75" stroke="{color}" stroke-width="15" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "expand": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <rect x="20" y="20" width="50" height="35" fill="none" stroke="{color}" stroke-width="15"/>
                <rect x="35" y="40" width="50" height="35" fill="none" stroke="{color}" stroke-width="15"/>
            </svg>
        """,
        "coloc": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="40" cy="50" r="25" fill="none" stroke="{color}" stroke-width="15"/>
                <circle cx="60" cy="50" r="25" fill="none" stroke="{color}" stroke-width="15"/>
                <path d="M 50 28 A 25 25 0 0 1 50 72 A 25 25 0 0 1 50 28" fill="{color}"/>
            </svg>
        """,
        "arrow": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 80 L 70 30 M 50 30 L 70 30 L 70 50" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "line": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <line x1="20" y1="80" x2="80" y2="20" stroke="{color}" stroke-width="12" stroke-linecap="round"/>
                <circle cx="20" cy="80" r="6" fill="{color}"/>
                <circle cx="80" cy="20" r="6" fill="{color}"/>
            </svg>
        """,
        "rect": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <rect x="20" y="25" width="60" height="50" rx="4" stroke="{color}" stroke-width="12" fill="none"/>
            </svg>
        """,
        "circle": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="35" stroke="{color}" stroke-width="12" fill="none"/>
            </svg>
        """,
        "ellipse": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <ellipse cx="50" cy="50" rx="40" ry="25" stroke="{color}" stroke-width="12" fill="none"/>
            </svg>
        """,
        "polygon": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 50 15 L 85 40 L 75 80 L 25 80 L 15 40 Z" stroke="{color}" stroke-width="12" fill="none" stroke-linejoin="round"/>
            </svg>
        """,
        "text": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 25 25 L 75 25 M 50 25 L 50 75 M 35 75 L 65 75" stroke="{color}" stroke-width="15" fill="none" stroke-linecap="round"/>
            </svg>
        """,
        "align_left": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 20 L 90 20 M 10 40 L 60 40 M 10 60 L 90 60 M 10 80 L 60 80" stroke="{color}" stroke-width="15" stroke-linecap="round"/>
            </svg>
        """,
        "align_center": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 20 L 90 20 M 25 40 L 75 40 M 10 60 L 90 60 M 25 80 L 75 80" stroke="{color}" stroke-width="15" stroke-linecap="round"/>
            </svg>
        """,
        "align_right": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 20 L 90 20 M 40 40 L 90 40 M 10 60 L 90 60 M 40 80 L 90 80" stroke="{color}" stroke-width="15" stroke-linecap="round"/>
            </svg>
        """,
        "theme": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <circle cx="50" cy="50" r="40" stroke="{color}" stroke-width="12" fill="none"/>
                <path d="M 50 10 A 40 40 0 0 1 50 90 Z" fill="{color}"/>
            </svg>
        """,
        "fit-width": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 10 20 L 10 80 M 90 20 L 90 80 M 10 50 L 90 50 M 30 35 L 10 50 L 30 65 M 70 35 L 90 50 L 70 65" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "log": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 80 L 80 80 M 20 80 L 20 20 M 20 80 Q 50 75 80 20" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round"/>
            </svg>
        """,
        "auto": """
            <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <path d="M 20 80 L 40 20 L 60 80 M 30 55 L 50 55" stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round"/>
                <circle cx="75" cy="30" r="15" stroke="{color}" stroke-width="8" fill="none"/>
                <path d="M 75 10 L 75 18 M 75 42 L 75 50 M 55 30 L 63 30 M 87 30 L 95 30" stroke="{color}" stroke-width="8"/>
            </svg>
        """
    }

    @classmethod
    def init(cls, resource_dir):
        """Initialize the manager with the resource directory path."""
        cls._resource_dir = resource_dir

    @classmethod
    def get_icon(cls, name, theme_name=None):
        """
        Get a QIcon by name. 
        If theme_name is provided, it tries to load from system theme first.
        If not found, it tries local resources, and then falls back to generated icons.
        """
        cache_key = (name, theme_name)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        icon = QIcon()

        # 1. For specific icons where we want guaranteed alignment/styling and theme awareness, use generated
        if name in cls.SVG_TEMPLATES or name in ["undo", "redo", "hand", "crop", "delete", "clear", "add", "import", "export", "save", "folder", "settings", "wand", "help", "count", "select", "batch_select", "refresh", "export_img", "info", "shortcuts", "stats", "scale", "measure", "theme", "fit-width", "log", "auto", "grid", "filmstrip"]:
            generated_pixmap = cls._generate_pixmap(name)
            if not generated_pixmap.isNull():
                icon = QIcon(generated_pixmap)
                cls._cache[cache_key] = icon
                return icon

        # 2. Try local resource for others
        if cls._resource_dir:
            for ext in ['.png', '.ico', '.svg']:
                local_path = os.path.join(cls._resource_dir, name + ext)
                if os.path.exists(local_path):
                    icon = QIcon(local_path)
                    break

        # 2. Try generated icon if still null
        if icon.isNull():
            generated_pixmap = cls._generate_pixmap(name)
            if not generated_pixmap.isNull():
                icon = QIcon(generated_pixmap)

        # 3. Try system theme only as a last resort fallback
        if icon.isNull() and theme_name:
            icon = QIcon.fromTheme(theme_name)

        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def _generate_pixmap(cls, name, size=QSize(64, 64)):
        """Generates a simple geometric icon pixmap on the fly."""
        # 1. Try SVG first if available
        if HAS_SVG and name in cls.SVG_TEMPLATES:
            # Determine color based on theme and category
            try:
                from src.gui.theme_manager import ThemeManager
                current_theme = ThemeManager.instance().get_current_theme()
            except Exception:
                current_theme = "light"
            
            category = cls.ICON_CATEGORIES.get(name, "nav") # Default to nav
            
            # Get color from theme mapping, fallback to system window text if not found
            theme_colors = cls.THEME_ICON_COLORS.get(current_theme, cls.THEME_ICON_COLORS["light"])
            color_str = theme_colors.get(category)
            
            if not color_str:
                palette = QApplication.palette()
                color_str = palette.color(QPalette.ColorRole.WindowText).name()
            
            svg_data = cls.SVG_TEMPLATES[name].format(color=color_str)
            pixmap = cls._render_svg_to_pixmap(svg_data, size)
            if not pixmap.isNull():
                return pixmap

        # 2. Fallback to QPainterPath logic (legacy)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Determine color based on system text color for better theme support
        palette = QApplication.palette()
        color = palette.color(QPalette.ColorRole.WindowText)
        
        pen = QPen(color, 15 if name in ["undo", "redo"] else 9, 
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        w, h = size.width(), size.height()
        margin = w * 0.2
        inner_w = w - 2 * margin
        inner_h = h - 2 * margin
        
        if name == "sort":
            painter.drawLine(margin, margin + inner_h * 0.2, margin + inner_w * 0.8, margin + inner_h * 0.2)
            painter.drawLine(margin, margin + inner_h * 0.5, margin + inner_w * 0.5, margin + inner_h * 0.5)
            painter.drawLine(margin, margin + inner_h * 0.8, margin + inner_w * 0.3, margin + inner_h * 0.8)
            arrow_x = margin + inner_w * 0.8
            painter.drawLine(arrow_x, margin + inner_h * 0.4, arrow_x, margin + inner_h * 0.9)
            painter.drawLine(arrow_x - 8, margin + inner_h * 0.7, arrow_x, margin + inner_h * 0.9)
            painter.drawLine(arrow_x + 8, margin + inner_h * 0.7, arrow_x, margin + inner_h * 0.9)
            
        elif name == "expand":
            painter.drawRect(QRectF(margin, margin, inner_w * 0.8, inner_h * 0.5))
            painter.drawRect(QRectF(margin + inner_w * 0.2, margin + inner_h * 0.3, inner_w * 0.8, inner_h * 0.5))
            
        elif name == "add":
            painter.drawLine(w/2, margin, w/2, h-margin)
            painter.drawLine(margin, h/2, w-margin, h/2)
            
        elif name == "delete":
            painter.drawLine(margin, margin, w-margin, h-margin)
            painter.drawLine(w-margin, margin, margin, h-margin)
            
        elif name == "undo":
            path = QPainterPath()
            path.moveTo(w * 0.75, h * 0.8)
            path.quadTo(w * 0.75, h * 0.25, w * 0.35, h * 0.3)
            path.lineTo(w * 0.35, h * 0.1)
            path.lineTo(w * 0.05, h * 0.35)
            path.lineTo(w * 0.35, h * 0.6)
            path.lineTo(w * 0.35, h * 0.4)
            path.quadTo(w * 0.55, h * 0.4, w * 0.6, h * 0.8)
            path.closeSubpath()
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

        elif name == "redo":
            path = QPainterPath()
            path.moveTo(w * 0.25, h * 0.8)
            path.quadTo(w * 0.25, h * 0.25, w * 0.65, h * 0.3)
            path.lineTo(w * 0.65, h * 0.1)
            path.lineTo(w * 0.95, h * 0.35)
            path.lineTo(w * 0.65, h * 0.6)
            path.lineTo(w * 0.65, h * 0.4)
            path.quadTo(w * 0.45, h * 0.4, w * 0.4, h * 0.8)
            path.closeSubpath()
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

        elif name == "folder":
            painter.drawPolyline([
                QPointF(margin, margin + 10),
                QPointF(margin + 15, margin + 10),
                QPointF(margin + 20, margin),
                QPointF(w - margin, margin),
                QPointF(w - margin, h - margin),
                QPointF(margin, h - margin),
                QPointF(margin, margin + 10)
            ])
            
        elif name == "hand":
            path = QPainterPath()
            finger_w = inner_w * 0.14
            finger_spacing = inner_w * 0.04
            for i in range(4):
                height_factors = [0.55, 0.65, 0.6, 0.45]
                f_h = inner_h * height_factors[i]
                f_x = margin + inner_w * 0.32 + i * (finger_w + finger_spacing)
                f_y = margin + (inner_h * 0.55 - f_h)
                path.addRoundedRect(f_x, f_y, finger_w, f_h + inner_h * 0.2, finger_w/2, finger_w/2)
            t_w = finger_w
            t_h = inner_h * 0.35
            t_x = margin + inner_w * 0.08
            t_y = margin + inner_h * 0.42
            painter.save()
            painter.translate(t_x + t_w/2, t_y + t_h/2)
            painter.rotate(-35)
            thumb_path = QPainterPath()
            thumb_path.addRoundedRect(-t_w/2, -t_h/2, t_w, t_h, t_w/2, t_w/2)
            painter.fillPath(thumb_path, QBrush(color))
            painter.restore()
            path.addRoundedRect(margin + inner_w * 0.22, margin + inner_h * 0.45, inner_w * 0.68, inner_h * 0.45, finger_w, finger_w)
            painter.fillPath(path, QBrush(color))

        elif name == "crop":
            crop_pen = QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin)
            painter.setPen(crop_pen)
            ext = inner_w * 0.15
            painter.drawLine(margin, margin + ext, margin + inner_w * 0.8, margin + ext)
            painter.drawLine(margin + ext, margin, margin + ext, margin + inner_h * 0.8)
            painter.drawLine(w - margin - inner_w * 0.8, h - margin - ext, w - margin, h - margin - ext)
            painter.drawLine(w - margin - ext, h - margin - inner_h * 0.8, w - margin - ext, h - margin)

        painter.end()
        return pixmap

    @classmethod
    def _render_svg_to_pixmap(cls, svg_data, size):
        """Helper to render SVG string to QPixmap."""
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
        if not renderer.isValid():
            return QPixmap()
            
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap

    @classmethod
    def get_pixmap(cls, name, size=QSize(24, 24)):
        """Get a scaled pixmap for high DPI displays."""
        icon = cls.get_icon(name)
        if icon.isNull():
            return QPixmap()
        
        # Use QIcon.pixmap which handles device pixel ratio automatically in Qt6
        return icon.pixmap(size)

def get_icon(name, theme_name=None):
    """Helper function for easier access."""
    return IconManager.get_icon(name, theme_name)
