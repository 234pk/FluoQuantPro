
import sys
import os
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsLineItem, QGraphicsRectItem, QGraphicsPathItem
from PySide6.QtCore import QPointF, Qt

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from gui.tools import LineScanTool, RectangleSelectionTool, PolygonSelectionTool
from core.data_model import Session

def reproduce():
    app = QApplication(sys.argv)
    
    # Mock objects
    session = Session()
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    
    print("--- Starting LineScanTool Test ---")
    tool = LineScanTool(session)
    tool._get_active_view = lambda: view
    tool.mouse_press(QPointF(10, 10), 0)
    tool.mouse_move(QPointF(100, 100), Qt.KeyboardModifier.NoModifier)
    
    print(f"\nScene Items Count: {len(scene.items())}")
    for item in scene.items():
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            print(f"Line Scan Preview: P1=({line.x1()}, {line.y1()}), P2=({line.x2()}, {line.y2()})")

    print("\n--- Starting RectangleSelectionTool Test ---")
    rect_tool = RectangleSelectionTool(session)
    rect_tool._get_active_view = lambda: view
    rect_tool.mouse_press(QPointF(20, 20), 0)
    rect_tool.mouse_move(QPointF(120, 120), Qt.KeyboardModifier.NoModifier)

    for item in scene.items():
        if isinstance(item, QGraphicsRectItem):
            rect = item.rect()
            print(f"Rect Selection Preview: x={rect.x()}, y={rect.y()}, w={rect.width()}, h={rect.height()}")

    print("\n--- Starting PolygonSelectionTool Test ---")
    poly_tool = PolygonSelectionTool(session)
    poly_tool._get_active_view = lambda: view
    # Polygon is click-click
    poly_tool.mouse_press(QPointF(30, 30), 0)
    poly_tool.mouse_move(QPointF(50, 50), Qt.KeyboardModifier.NoModifier)
    poly_tool.mouse_press(QPointF(50, 50), 0)
    poly_tool.mouse_move(QPointF(70, 30), Qt.KeyboardModifier.NoModifier)

    for item in scene.items():
        if isinstance(item, QGraphicsPathItem):
            path = item.path()
            print(f"Polygon Selection Preview: Bounds={path.boundingRect()}, Points={path.elementCount()}")
    
    print("--- Test Finished ---")

if __name__ == "__main__":
    reproduce()
