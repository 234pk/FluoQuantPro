
import sys
import os

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

from src.core.project_model import ProjectModel, SceneData, ChannelDef
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

def verify_channel_color_update():
    # Create a dummy QApplication as ProjectModel inherits QObject
    app = QApplication(sys.argv)
    
    # Initialize ProjectModel
    undo_stack = QUndoStack()
    model = ProjectModel(undo_stack=undo_stack)
    
    # Create a dummy scene with one channel
    scene_id = "scene_001"
    initial_color = "#FFFFFF"
    target_color = "#FF0000"
    
    channel = ChannelDef(path="dummy.tif", channel_type="DAPI", color=initial_color)
    scene = SceneData(id=scene_id, name="Test Scene", channels=[channel])
    
    # Inject scene into model
    model.scenes.append(scene)
    model._scene_map[scene_id] = scene
    
    print(f"Initial color: {model.scenes[0].channels[0].color}")
    assert model.scenes[0].channels[0].color == initial_color
    
    # Perform update
    print(f"Updating color to {target_color}...")
    model.update_channel_color(scene_id, 0, target_color)
    
    # Verify update
    current_color = model.scenes[0].channels[0].color
    print(f"Current color: {current_color}")
    assert current_color == target_color, f"Expected {target_color}, got {current_color}"
    
    # Test Undo
    print("Undoing...")
    undo_stack.undo()
    current_color = model.scenes[0].channels[0].color
    print(f"Color after undo: {current_color}")
    assert current_color == initial_color, f"Expected {initial_color}, got {current_color}"
    
    # Test Redo
    print("Redoing...")
    undo_stack.redo()
    current_color = model.scenes[0].channels[0].color
    print(f"Color after redo: {current_color}")
    assert current_color == target_color, f"Expected {target_color}, got {current_color}"
    
    print("Verification Successful!")

if __name__ == "__main__":
    verify_channel_color_update()
