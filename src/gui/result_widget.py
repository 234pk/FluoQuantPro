from pathlib import Path
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QHeaderView, QMenu, QPushButton)
from PySide6.QtCore import Qt
from src.core.language_manager import tr, LanguageManager
from src.core.logger import Logger

class MeasurementResultTree(QTreeWidget):
    """
    Tree widget to display measurement results hierarchically:
    Sample -> ROI -> Channel Data
    Columns: Item, Area, Mean, IntDen, Min, Max, BgMean, CorrectedMean
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define Columns
        self.columns_map = {
            'Item': 0,
            'Area': 1,
            'Mean': 2,
            'IntDen': 3,
            'Min': 4,
            'Max': 5,
            'BgMean': 6,
            'CorrectedMean': 7,
            'Status': 8
        }
        
        self.setHeaderLabels([tr(k) for k in self.columns_map.keys()])
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        
        # Adjust column widths
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Item Name
        for i in range(1, 9):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            
        # Context Menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self):
        self.setHeaderLabels([tr(k) for k in self.columns_map.keys()])
        
        # Update summary items
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            sample_item = root.child(i)
            for j in range(sample_item.childCount()):
                item = sample_item.child(j)
                if item.data(0, Qt.UserRole) == "summary":
                    pass

    def show_context_menu(self, position):
        menu = QMenu()
        
        # Validation Actions
        verify_action = menu.addAction(tr("Mark as Verified"))
        verify_action.triggered.connect(lambda: self.set_selected_status("Verified"))
        
        reject_action = menu.addAction(tr("Mark as Rejected"))
        reject_action.triggered.connect(lambda: self.set_selected_status("Rejected"))
        
        menu.addSeparator()
        
        delete_action = menu.addAction(tr("Delete Selected"))
        delete_action.triggered.connect(self.delete_selected_items)
        
        menu.addSeparator()
        
        # CSV Export (Replaces JSON)
        export_csv_action = menu.addAction(tr("Export Results (CSV)..."))
        export_csv_action.triggered.connect(self.export_csv_data)
        
        menu.exec(self.viewport().mapToGlobal(position))

    def export_csv_data(self):
        """Exports the current tree structure to a CSV file."""
        from PySide6.QtWidgets import QFileDialog
        import csv
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export Results"), "", tr("CSV Files (*.csv)")
        )
        
        if not file_path:
            return
            
        target_path = Path(file_path)
        
        try:
            data = self.get_all_data()
            if not data:
                Logger.warning(tr("No data to export."))
                return

            # Determine all keys (headers) from data
            keys = []
            # Preset order for common keys
            preset_order = ['Sample', 'ROI_Label', 'ROI_ID', 'Channel', 'Area', 'Status', 'Overlap_Entry_ID']
            
            # Add present preset keys
            for k in preset_order:
                # Check if this key exists in any row
                if any(k in row for row in data):
                    keys.append(k)
            
            # Add remaining keys
            all_keys = set().union(*(d.keys() for d in data))
            for k in sorted(list(all_keys)):
                if k not in keys:
                    keys.append(k)
            
            with target_path.open('w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)
                
            Logger.info(f"Result data exported to {file_path}")
        except Exception as e:
            Logger.error(f"Failed to export data: {e}")


    def set_selected_status(self, status):
        from PySide6.QtGui import QColor, QBrush

        def find_roi_item(item: QTreeWidgetItem):
            cur = item
            while cur is not None:
                parent = cur.parent()
                if parent is None:
                    return None
                if parent.parent() is None:
                    return cur
                cur = parent
            return None

        selected = self.selectedItems()
        Logger.debug(f"[Results] set_selected_status: status={status} selected={len(selected)}")
        for item in selected:
            roi_item = find_roi_item(item)
            if roi_item:
                roi_item.setText(self.columns_map['Status'], tr(status))
                
                # Color coding
                col_idx = self.columns_map['Status']
                if status == "Verified":
                    roi_item.setForeground(col_idx, QBrush(QColor("green")))
                elif status == "Rejected":
                    roi_item.setForeground(col_idx, QBrush(QColor("red")))
                else:
                    roi_item.setForeground(col_idx, QBrush(QColor("black")))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_selected_items()
        else:
            super().keyPressEvent(event)

    def delete_selected_items(self):
        """Deletes selected items from the tree."""
        root = self.invisibleRootItem()
        for item in self.selectedItems():
            (item.parent() or root).removeChild(item)
            
    def get_existing_roi_ids(self):
        """Returns a set of ROI IDs currently present in the table."""
        ids = set()
        root = self.invisibleRootItem()
        # Traverse Sample -> ROI
        for i in range(root.childCount()):
            sample_item = root.child(i)
            for j in range(sample_item.childCount()):
                roi_item = sample_item.child(j)
                roi_id = roi_item.data(0, Qt.UserRole)
                if roi_id:
                    ids.add(roi_id)
        return ids

    def get_all_data(self):
        """
        Reconstructs the list of dictionaries from the tree structure for export.
        Flattened format: One row per Channel per ROI.
        """
        data_list = []
        root = self.invisibleRootItem()
        
        for i in range(root.childCount()):
            sample_item = root.child(i)
            sample_name = sample_item.text(0)
            
            for j in range(sample_item.childCount()):
                roi_item = sample_item.child(j)
                roi_label = roi_item.text(0)
                roi_id = roi_item.data(0, Qt.UserRole)
                
                # Check if it's a summary item
                if roi_id == "summary":
                    # Export summary rows
                    for k in range(roi_item.childCount()):
                        ch_count_item = roi_item.child(k)
                        text = ch_count_item.text(0)
                        if ": " in text:
                            ch_name, count = text.split(": ", 1)
                            data_list.append({
                                'Sample': sample_name,
                                'ROI_Label': 'Point Summary',
                                'ROI_ID': 'summary',
                                'Channel': ch_name,
                                'Count': count
                            })
                    continue

                area = roi_item.text(self.columns_map['Area'])
                
                # Each ROI has Channel children
                status = roi_item.text(self.columns_map['Status'])
                
                for k in range(roi_item.childCount()):
                    ch_item = roi_item.child(k)
                    if ch_item.data(0, Qt.UserRole) == "overlap_group":
                        for ov_idx in range(ch_item.childCount()):
                            ov_item = ch_item.child(ov_idx)
                            entry_id = ov_item.data(0, Qt.UserRole)
                            base_row = {
                                'Sample': sample_name,
                                'ROI_Label': roi_label,
                                'ROI_ID': roi_id,
                                'Channel': f"Overlap:{ov_item.text(0)}",
                                'Area': ov_item.text(self.columns_map['Area']),
                                'Status': status,
                                'Overlap_Entry_ID': entry_id
                            }
                            for metric, col_idx in self.columns_map.items():
                                if metric in ['Item', 'Area']:
                                    continue
                                val = ov_item.text(col_idx)
                                if val:
                                    base_row[metric] = val
                            data_list.append(base_row)

                            for child_idx in range(ov_item.childCount()):
                                part_item = ov_item.child(child_idx)
                                part_row = {
                                    'Sample': sample_name,
                                    'ROI_Label': roi_label,
                                    'ROI_ID': roi_id,
                                    'Channel': f"Overlap:{ov_item.text(0)}/{part_item.text(0)}",
                                    'Area': part_item.text(self.columns_map['Area']),
                                    'Status': status,
                                    'Overlap_Entry_ID': entry_id
                                }
                                for metric, col_idx in self.columns_map.items():
                                    if metric in ['Item', 'Area']:
                                        continue
                                    val = part_item.text(col_idx)
                                    if val:
                                        part_row[metric] = val
                                data_list.append(part_row)

                                for g_idx in range(part_item.childCount()):
                                    g_item = part_item.child(g_idx)
                                    g_row = {
                                        'Sample': sample_name,
                                        'ROI_Label': roi_label,
                                        'ROI_ID': roi_id,
                                        'Channel': f"Overlap:{ov_item.text(0)}/{part_item.text(0)}/{g_item.text(0)}",
                                        'Area': g_item.text(self.columns_map['Area']) or part_item.text(self.columns_map['Area']),
                                        'Status': status,
                                        'Overlap_Entry_ID': entry_id
                                    }
                                    for metric, col_idx in self.columns_map.items():
                                        if metric in ['Item', 'Area']:
                                            continue
                                        val = g_item.text(col_idx)
                                        if val:
                                            g_row[metric] = val
                                    data_list.append(g_row)
                        Logger.debug(f"[Results] Exported overlap rows: sample={sample_name} roi_id={roi_id}")
                        continue
                    ch_name = ch_item.text(0)
                    
                    row = {
                        'Sample': sample_name,
                        'ROI_Label': roi_label,
                        'ROI_ID': roi_id,
                        'Channel': ch_name,
                        'Area': area,
                        'Status': status
                    }
                    
                    # Extract metrics
                    for metric, col_idx in self.columns_map.items():
                        if metric in ['Item', 'Area']: continue
                        val = ch_item.text(col_idx)
                        if val:
                            row[metric] = val
                            
                    data_list.append(row)
        return data_list

    def remove_results_for_rois(self, roi_ids):
        """Removes rows corresponding to specific ROI IDs."""
        root = self.invisibleRootItem()
        to_delete = []
        # Traverse Sample -> ROI
        for i in range(root.childCount()):
            sample_item = root.child(i)
            for j in range(sample_item.childCount()):
                roi_item = sample_item.child(j)
                roi_id = roi_item.data(0, Qt.UserRole)
                if roi_id in roi_ids:
                    to_delete.append(roi_item)
        
        for item in to_delete:
            (item.parent() or root).removeChild(item)

    def add_sample_results(self, sample_name, roi_data_list, settings, count_summary=None):
        """
        Adds a sample group with ROI results and optional point counts.
        If sample group already exists, appends to it.
        
        Args:
            sample_name (str): Name of the sample/image.
            roi_data_list (list): List of dicts containing stats.
            settings (dict): Filter for which metrics to show.
            count_summary (dict): Optional dict of {channel_name: count}
        """
        # Update Column Visibility based on Settings
        for metric, col_idx in self.columns_map.items():
            if metric == 'Item': continue
            # If metric is in settings, set visibility
            # Note: keys in settings match column names
            is_visible = settings.get(metric, True)
            self.setColumnHidden(col_idx, not is_visible)

        # Find or Create Root Item for Sample
        sample_item = None
        root = self.invisibleRootItem()
        
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(0) == sample_name:
                sample_item = item
                break
        
        if not sample_item:
            sample_item = QTreeWidgetItem(self)
            sample_item.setText(0, sample_name)
            sample_item.setExpanded(True)
            # Style: Bold for Sample Name
            font = sample_item.font(0)
            font.setBold(True)
            sample_item.setFont(0, font)

        accumulate = settings.get('Accumulate', True)

        # Add Count Summary if provided
        if count_summary:
            total_counts = sum(count_summary.values())
            
            # Find existing summary if not accumulating
            summary_item = None
            if not accumulate:
                for i in range(sample_item.childCount()):
                    item = sample_item.child(i)
                    if item.data(0, Qt.UserRole) == "summary":
                        summary_item = item
                        while summary_item.childCount() > 0:
                            summary_item.removeChild(summary_item.child(0))
                        break
            
            if not summary_item:
                summary_item = QTreeWidgetItem(sample_item)
                summary_item.setData(0, Qt.UserRole, "summary") # Special marker
                font = summary_item.font(0)
                font.setItalic(True)
                summary_item.setFont(0, font)

            summary_item.setText(0, tr("Point Summary (Total: {0})").format(total_counts))
            
            for ch_name, count in sorted(count_summary.items()):
                ch_count_item = QTreeWidgetItem(summary_item)
                ch_count_item.setText(0, f"{ch_name}: {count}")
                # We could put the count in another column too
                # ch_count_item.setText(self.columns_map['Mean'], str(count))
        
        # Map existing ROI IDs to items for quick lookup to prevent duplicates
        existing_roi_items = {}
        for i in range(sample_item.childCount()):
            item = sample_item.child(i)
            rid = item.data(0, Qt.UserRole)
            if rid and rid != "summary":
                existing_roi_items[rid] = item

        for data in roi_data_list:
            roi_label = data.get('Label', 'ROI')
            roi_id = data.get('ROI_ID', '')
            
            # Upsert Logic
            if not accumulate and roi_id in existing_roi_items:
                roi_item = existing_roi_items[roi_id]
                # Clear existing channel children to rebuild
                while roi_item.childCount() > 0:
                    roi_item.removeChild(roi_item.child(0))
            else:
                roi_item = QTreeWidgetItem(sample_item)
                # If accumulating and already exists, add a marker
                if accumulate and roi_id in existing_roi_items:
                    # Find how many measurements exist for this ROI to add a counter
                    count = 0
                    for i in range(sample_item.childCount()):
                        item = sample_item.child(i)
                        if item.data(0, Qt.UserRole) == roi_id:
                            count += 1
                    if count > 1:
                        roi_label = f"{roi_label} ({count})"
            
            roi_item.setText(0, f"{roi_label}")
            roi_item.setData(0, Qt.UserRole, roi_id)
            
            # Set Area for ROI row (if exists)
            if 'Area' in data:
                roi_item.setText(self.columns_map['Area'], f"{data['Area']:.2f}")
            
            # Extract Channel Stats
            # Data keys format: "{ChannelName}_{Metric}"
            channels = set()
            for key in data.keys():
                if '_' in key and key not in ['ROI_ID', 'Label']:
                    ch_name = key.rsplit('_', 1)[0]
                    channels.add(ch_name)
            
            sorted_channels = sorted(list(channels))
            
            for ch in sorted_channels:
                ch_item = QTreeWidgetItem(roi_item)
                ch_item.setText(0, ch)
                
                # Populate Metrics
                for metric, col_idx in self.columns_map.items():
                    if metric == 'Item': continue
                    
                    # For Area, we allow it on channel items if explicitly provided (e.g. for Overlap Analysis)
                    # For standard channels, it usually won't be present in the data dict as "{Channel}_Area"
                    
                    key = f"{ch}_{metric}"
                    if key in data:
                        val = data[key]
                        ch_item.setText(col_idx, f"{val:.2f}")

    def _find_sample_item(self, sample_name: str):
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(0) == sample_name:
                return item
        return None

    def _find_roi_item(self, sample_item: QTreeWidgetItem, roi_id: str):
        if not sample_item:
            return None
        for i in range(sample_item.childCount()):
            item = sample_item.child(i)
            rid = item.data(0, Qt.UserRole)
            if rid == roi_id:
                return item
        return None

    def _get_or_create_overlap_group(self, roi_item: QTreeWidgetItem):
        for i in range(roi_item.childCount()):
            child = roi_item.child(i)
            if child.data(0, Qt.UserRole) == "overlap_group":
                return child

        group = QTreeWidgetItem(roi_item)
        group.setText(0, tr("Overlap"))
        group.setData(0, Qt.UserRole, "overlap_group")
        font = group.font(0)
        font.setItalic(True)
        group.setFont(0, font)
        group.setExpanded(True)
        return group

    def clear_overlap_groups(self, sample_name: str):
        sample_item = self._find_sample_item(sample_name)
        if not sample_item:
            return
        for i in range(sample_item.childCount()):
            roi_item = sample_item.child(i)
            if roi_item.data(0, Qt.UserRole) == "summary":
                continue
            to_remove = []
            for j in range(roi_item.childCount()):
                child = roi_item.child(j)
                if child.data(0, Qt.UserRole) == "overlap_group":
                    to_remove.append(child)
            for child in to_remove:
                roi_item.removeChild(child)

    def add_overlap_entry(self, sample_name: str, roi_id: str, entry_id: str, data: dict):
        sample_item = self._find_sample_item(sample_name)
        roi_item = self._find_roi_item(sample_item, roi_id)
        if not roi_item:
            Logger.debug(f"[Results] add_overlap_entry skipped: sample={sample_name} roi_id={roi_id} entry_id={entry_id}")
            return

        group = self._get_or_create_overlap_group(roi_item)

        existing = None
        for i in range(group.childCount()):
            child = group.child(i)
            if child.data(0, Qt.UserRole) == entry_id:
                existing = child
                break
        if existing:
            group.removeChild(existing)

        entry_item = QTreeWidgetItem(group)
        entry_item.setData(0, Qt.UserRole, entry_id)
        self._populate_overlap_item(entry_item, data)
        Logger.debug(f"[Results] overlap added: sample={sample_name} roi_id={roi_id} entry_id={entry_id}")

    def _populate_overlap_item(self, roi_item: QTreeWidgetItem, data: dict):
        roi_item.setText(0, data.get('Label', 'Overlap'))
        if roi_item.data(0, Qt.UserRole) in (None, ""):
            roi_item.setData(0, Qt.UserRole, data.get('ROI_ID', 'virtual'))

        if 'Area' in data:
            roi_item.setText(self.columns_map['Area'], f"{data['Area']:.2f}")

        intersection_item = QTreeWidgetItem(roi_item)
        intersection_item.setText(0, tr("Intersection"))
        if 'Intersection_Area' in data:
            intersection_item.setText(self.columns_map['Area'], f"{data['Intersection_Area']:.2f}")

        if 'Non_Common_Area' in data:
            part_item = QTreeWidgetItem(roi_item)
            part_item.setText(0, tr("Non-Overlapping (Union-Intersection)"))
            part_item.setText(self.columns_map['Area'], f"{data['Non_Common_Area']:.2f}")

        # 1. Collect and add Intersection stats
        channel_stats = {}
        for key, val in data.items():
            if key.startswith("Intersection (") and ")_" in key:
                prefix, metric = key.rsplit('_', 1)
                ch_name = prefix[14:-1]
                if ch_name not in channel_stats:
                    channel_stats[ch_name] = {}
                channel_stats[ch_name][metric] = val

        for ch_name in sorted(channel_stats.keys()):
            ch_item = QTreeWidgetItem(intersection_item)
            ch_item.setText(0, ch_name)
            stats = channel_stats[ch_name]
            for metric, val in stats.items():
                if metric in self.columns_map:
                    ch_item.setText(self.columns_map[metric], f"{val:.2f}")

        # 2. Collect and add "Only" stats for each ROI
        only_parts = {} # label -> part_item
        for key, val in data.items():
            if key.endswith("_Only_Area"):
                label = key.replace("_Only_Area", "")
                part_item = QTreeWidgetItem(roi_item)
                part_item.setText(0, f"{label} ({tr('Only')})")
                part_item.setText(self.columns_map['Area'], f"{val:.2f}")
                only_parts[label] = part_item

        only_channel_stats = {} # label -> ch_name -> metric -> val
        for key, val in data.items():
            if "_Only (" in key and ")_" in key:
                prefix, metric = key.rsplit('_', 1)
                # Key format: "{label}_Only ({ch_name})_{metric}"
                label_part, ch_part = prefix.split("_Only (", 1)
                ch_name = ch_part[:-1]
                
                if label_part not in only_channel_stats:
                    only_channel_stats[label_part] = {}
                if ch_name not in only_channel_stats[label_part]:
                    only_channel_stats[label_part][ch_name] = {}
                only_channel_stats[label_part][ch_name][metric] = val

        for label, ch_dict in only_channel_stats.items():
            if label in only_parts:
                parent_item = only_parts[label]
                for ch_name in sorted(ch_dict.keys()):
                    ch_item = QTreeWidgetItem(parent_item)
                    ch_item.setText(0, ch_name)
                    stats = ch_dict[ch_name]
                    for metric, val in stats.items():
                        if metric in self.columns_map:
                            ch_item.setText(self.columns_map[metric], f"{val:.2f}")

        if 'Metrics_Mean' in data:
            roi_item.setText(self.columns_map['Mean'], f"IoU: {data['Metrics_Mean']:.3f}")
        if 'Metrics_IntDen' in data:
            roi_item.setText(self.columns_map['IntDen'], f"Ratio: {data['Metrics_IntDen']:.3f}")

    def add_virtual_row(self, data):
        """
        Adds a virtual row for overlap analysis results.
        These rows are not persisted in the ROI manager but shown in the table.
        """
        # We can reuse add_sample_results or implement specific logic
        # Here we just treat it as a special "Overlap Analysis" sample or append to current
        
        # Or simpler: Just append a top-level item if we want it distinct, 
        # OR add to the current sample group.
        
        # Let's add to the tree directly.
        root = self.invisibleRootItem()
        # Find the sample item (assuming it exists, or create a virtual group)
        # For simplicity, let's look for the first item or create "Overlap Analysis"
        
        group_name = tr("Overlap Analysis")
        group_item = None
        for i in range(root.childCount()):
            if root.child(i).text(0) == group_name:
                group_item = root.child(i)
                break
                
        if not group_item:
            group_item = QTreeWidgetItem(self)
            group_item.setText(0, group_name)
            group_item.setExpanded(True)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            
        # Create the ROI item (virtual)
        roi_item = QTreeWidgetItem(group_item)
        self._populate_overlap_item(roi_item, data)

    def update_settings(self, settings):
        """Updates column visibility based on settings."""
        for metric, col_idx in self.columns_map.items():
            if metric == 'Item': continue
            is_visible = settings.get(metric, True)
            self.setColumnHidden(col_idx, not is_visible)

    def clear_results(self):
        self.clear()

class MeasurementResultWidget(QWidget):
    """
    Wrapper widget containing the result tree and a 'Clear All' button.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)
        
        self.tree = MeasurementResultTree()
        self.layout.addWidget(self.tree, 1) # Give tree stretch factor 1
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_export = QPushButton(tr("Export Results (CSV)..."))
        self.btn_export.clicked.connect(self.export_results)
        btn_layout.addWidget(self.btn_export)
        
        self.btn_clear = QPushButton(tr("Clear All Results"))
        self.btn_clear.clicked.connect(self.clear_results)
        btn_layout.addWidget(self.btn_clear)
        
        self.layout.addLayout(btn_layout)
        
    def export_results(self):
        """Exports the current tree structure to a CSV file."""
        self.tree.export_csv_data()
        
    def clear(self):
        """Clears all items from the tree."""
        self.tree.clear()

    def add_sample_results(self, *args, **kwargs):
        self.tree.add_sample_results(*args, **kwargs)
        
    def remove_results_for_rois(self, *args, **kwargs):
        self.tree.remove_results_for_rois(*args, **kwargs)
        
    def get_all_data(self):
        return self.tree.get_all_data()
        
    def clear_results(self):
        self.tree.clear_results()
        
    def update_settings(self, settings):
        self.tree.update_settings(settings)

    def add_virtual_row(self, data):
        self.tree.add_virtual_row(data)

    def clear_overlap_groups(self, sample_name: str):
        self.tree.clear_overlap_groups(sample_name)

    def add_overlap_entry(self, sample_name: str, roi_id: str, entry_id: str, data: dict):
        self.tree.add_overlap_entry(sample_name, roi_id, entry_id, data)
