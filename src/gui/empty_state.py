import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                               QFrame, QMenu, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, QSettings, QSize, Signal
from src.gui.icon_manager import get_icon
from src.core.language_manager import tr

class EmptyStateWidget(QWidget):
    """
    Widget displayed when no images are loaded.
    """
    import_requested = Signal()
    new_project_requested = Signal()
    open_project_requested = Signal()
    open_recent_requested = Signal(str)
    import_folder_requested = Signal()
    import_merge_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        # Icon
        self.icon_label = QLabel()
        self.icon_label.setObjectName("empty_icon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Title
        self.title_label = QLabel(tr("No Sample Selected"))
        self.title_label.setObjectName("empty_title")
        self.title_label.setProperty("role", "title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Subtitle
        self.subtitle_label = QLabel(tr("Start by creating a new project or opening an existing one."))
        self.subtitle_label.setObjectName("empty_subtitle")
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_label)
        
        # Action Buttons Container
        self.btn_container = QWidget()
        # Use a more adaptive max width based on content but allow it to shrink
        from PySide6.QtWidgets import QSizePolicy
        self.btn_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.btn_container.setMinimumWidth(300)
        self.btn_container.setMaximumWidth(600) 
        btn_layout = QVBoxLayout(self.btn_container)
        btn_layout.setSpacing(12)
        btn_layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self.btn_container, 0, Qt.AlignmentFlag.AlignCenter)
        
        # New Project
        self.btn_new = QPushButton(tr("New Project"))
        self.btn_new.setIcon(get_icon("new", "document-new"))
        self.btn_new.setIconSize(QSize(28, 28))
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setProperty("role", "success")
        self.btn_new.setMinimumHeight(50)
        btn_layout.addWidget(self.btn_new)

        # Open Project
        self.btn_open = QPushButton(tr("Open Project"))
        self.btn_open.setIcon(get_icon("open", "document-open"))
        self.btn_open.setIconSize(QSize(28, 28))
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setProperty("role", "info")
        self.btn_open.setMinimumHeight(50)
        btn_layout.addWidget(self.btn_open)

        # Separator for secondary actions
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 60); margin: 10px 0;")
        btn_layout.addWidget(sep)

        # Secondary Actions Row 1
        sec_layout1 = QVBoxLayout()
        sec_layout1.setSpacing(8)
        btn_layout.addLayout(sec_layout1)

        # Import Images
        self.btn_import = QPushButton(tr("Import Images"))
        self.btn_import.setIcon(get_icon("import", "document-import"))
        self.btn_import.setIconSize(QSize(24, 24))
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setProperty("role", "warning")
        self.btn_import.setMinimumHeight(40)
        sec_layout1.addWidget(self.btn_import)
        
        # Import Folder
        self.btn_import_folder = QPushButton(tr("Import Folder"))
        self.btn_import_folder.setIcon(get_icon("folder", "folder-open"))
        self.btn_import_folder.setIconSize(QSize(24, 24))
        self.btn_import_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_folder.setProperty("role", "warning")
        self.btn_import_folder.setMinimumHeight(40)
        sec_layout1.addWidget(self.btn_import_folder)
        
        # Import Merge
        self.btn_import_merge = QPushButton(tr("Import Merge (RGB Split)"))
        self.btn_import_merge.setIcon(get_icon("import", "document-import"))
        self.btn_import_merge.setIconSize(QSize(24, 24))
        self.btn_import_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_merge.setProperty("role", "warning")
        self.btn_import_merge.setMinimumHeight(40)
        sec_layout1.addWidget(self.btn_import_merge)
        
        # Recent Projects Button
        self.btn_recent = QPushButton(tr("Recent Projects"))
        self.btn_recent.setIcon(get_icon("open", "document-open-recent"))
        self.btn_recent.setIconSize(QSize(24, 24))
        self.btn_recent.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_recent.setMinimumHeight(40)
        btn_layout.addWidget(self.btn_recent)
        
        # Recent Projects List Section (Keep for quick access)
        self.lbl_recent = QLabel(tr("Recent Projects:"))
        self.lbl_recent.setProperty("role", "title")
        self.lbl_recent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_recent.hide() # Hidden by default
        btn_layout.addWidget(self.lbl_recent)
        
        self.list_recent = QListWidget()
        self.list_recent.setProperty("role", "recent")
        self.list_recent.setMinimumHeight(60)
        self.list_recent.setMaximumHeight(150)
        self.list_recent.hide()
        btn_layout.addWidget(self.list_recent)
        
        self._load_recent_projects()
        
        # Connect signals
        self.btn_import.clicked.connect(self.import_requested.emit)
        self.btn_new.clicked.connect(self.new_project_requested.emit)
        self.btn_open.clicked.connect(self.open_project_requested.emit)
        self.btn_import_folder.clicked.connect(self.import_folder_requested.emit)
        self.btn_import_merge.clicked.connect(self.import_merge_requested.emit)
        self.list_recent.itemClicked.connect(lambda item: self.open_recent_requested.emit(item.text()))
        
        # Connect button to show menu
        self.btn_recent.clicked.connect(self._show_recent_menu)
        
        self.retranslate_ui()

    def resizeEvent(self, event):
        """Adapt icon and font sizes based on widget dimensions."""
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        
        # Calculate dynamic scale factor based on width
        # Base width for 1.0 scale is 1000px
        scale = max(0.6, min(1.4, w / 1000.0))
        
        # 1. Update Icon Size
        if hasattr(self, 'icon_label'):
            # Standard icon size 128, min 64, max 180
            icon_size = int(128 * scale)
            if h < 400:
                icon_size = int(64 * scale)
            icon = get_icon("import", "document-import")
            self.icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
            self.icon_label.setVisible(h > 250)
        
        # 2. Update Font Sizes
        # We use setStyleSheet to ensure it overrides any global QSS fixed sizes
        if hasattr(self, 'title_label'):
            font_size = max(16, int(28 * scale))
            self.title_label.setStyleSheet(f"font-size: {font_size}px; font-weight: bold;")
            self.title_label.setVisible(h > 180)
        
        if hasattr(self, 'subtitle_label'):
            sub_font_size = max(12, int(16 * scale))
            self.subtitle_label.setStyleSheet(f"font-size: {sub_font_size}px; font-weight: normal;")
            self.subtitle_label.setVisible(h > 120)
        
        # 3. Update Button Container Width and Margins
        if hasattr(self, 'btn_container'):
            container_width = int(min(600, max(320, w * 0.45)))
            self.btn_container.setFixedWidth(container_width)
            
            # Use a more relaxed height constraint - only limit if h is very small
            # and allow the container to use more space if available.
            if h < 600:
                # When space is tight, hide elements instead of squashing the container
                self.btn_container.setMaximumHeight(h - 50 if h > 100 else 50)
            else:
                self.btn_container.setMaximumHeight(16777215) # QWIDGETSIZE_MAX
            
            self.btn_container.setVisible(h > 150)
        
        # 4. Update Button Heights and Icons
        # Reduced base sizes slightly to prevent overcrowding on smaller screens
        btn_height = max(32, int(48 * scale))
        sec_btn_height = max(28, int(38 * scale))
        icon_dim = max(20, int(24 * scale))
        sec_icon_dim = max(18, int(20 * scale))

        if hasattr(self, 'btn_new'):
            self.btn_new.setMinimumHeight(btn_height)
            self.btn_new.setIconSize(QSize(icon_dim, icon_dim))
        if hasattr(self, 'btn_open'):
            self.btn_open.setMinimumHeight(btn_height)
            self.btn_open.setIconSize(QSize(icon_dim, icon_dim))
        
        # Direct access is safer
        # More aggressive hiding of secondary elements when height is low
        if hasattr(self, 'btn_import'):
            self.btn_import.setMinimumHeight(sec_btn_height)
            self.btn_import.setIconSize(QSize(sec_icon_dim, sec_icon_dim))
            self.btn_import.setVisible(h > 400) 
        if hasattr(self, 'btn_import_folder'):
            self.btn_import_folder.setMinimumHeight(sec_btn_height)
            self.btn_import_folder.setIconSize(QSize(sec_icon_dim, sec_icon_dim))
            self.btn_import_folder.setVisible(h > 450)
        if hasattr(self, 'btn_import_merge'):
            self.btn_import_merge.setMinimumHeight(sec_btn_height)
            self.btn_import_merge.setIconSize(QSize(sec_icon_dim, sec_icon_dim))
            self.btn_import_merge.setVisible(h > 500)
        if hasattr(self, 'btn_recent'):
            self.btn_recent.setMinimumHeight(sec_btn_height)
            self.btn_recent.setIconSize(QSize(sec_icon_dim, sec_icon_dim))
            self.btn_recent.setVisible(h > 350)
            
        if hasattr(self, 'list_recent'):
            self.list_recent.setVisible(h > 550 and self.list_recent.count() > 0)
            self.lbl_recent.setVisible(h > 550 and self.list_recent.count() > 0)

    def retranslate_ui(self):
        # Already handled by main window for now, but good to have
        pass

    def _show_recent_menu(self):
        """Shows the recent projects menu at the button location."""
        menu = QMenu(self)
        
        settings = QSettings("FluoQuantPro", "AppSettings")
        recent = settings.value("recentProjects", [])
        if not isinstance(recent, list):
            recent = [recent] if recent else []
            
        if not recent:
            action = menu.addAction(tr("No Recent Projects"))
            action.setEnabled(False)
        else:
            for path in recent:
                if os.path.exists(path):
                    action = menu.addAction(os.path.basename(path))
                    action.setData(path)
                    action.setToolTip(path)
                    action.triggered.connect(lambda checked=False, p=path: self.open_recent_requested.emit(p))
            
            menu.addSeparator()
            clear_action = menu.addAction(tr("Clear Recent Projects"))
            clear_action.triggered.connect(self._clear_recent)
            
        # Show menu below the button
        menu.exec(self.btn_recent.mapToGlobal(self.btn_recent.rect().bottomLeft()))

    def _clear_recent(self):
        """Clears recent projects list and refreshes UI."""
        settings = QSettings("FluoQuantPro", "AppSettings")
        settings.setValue("recentProjects", [])
        self._load_recent_projects()

    def _load_recent_projects(self):
        settings = QSettings("FluoQuantPro", "AppSettings")
        recent = settings.value("recentProjects", [])
        if not isinstance(recent, list):
            recent = [recent] if recent else []
            
        if recent:
            self.lbl_recent.show()
            self.list_recent.show()
            self.list_recent.clear()
            for path in recent:
                if path and isinstance(path, str) and os.path.exists(path):
                    item = QListWidgetItem(path)
                    item.setToolTip(path)
                    self.list_recent.addItem(item)
        else:
            self.lbl_recent.hide()
            self.list_recent.hide()
