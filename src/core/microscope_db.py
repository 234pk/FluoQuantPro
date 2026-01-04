
from typing import Dict

class MicroscopeSpecs:
    def __init__(self, name: str, objectives: Dict[str, float]):
        self.name = name
        self.objectives = objectives  # Name -> Typical Pixel Size (um/px) assumption

# Typical pixel sizes assuming 6.5um sensor and 1x adapter
# 4x: ~1.625 um
# 10x: ~0.65 um
# 20x: ~0.325 um
# 40x: ~0.1625 um
# 60x: ~0.108 um
# 100x: ~0.065 um

MICROSCOPE_DB = {
    "Generic": {
        "4x": 1.625,
        "10x": 0.65,
        "20x": 0.325,
        "40x": 0.1625,
        "60x": 0.108,
        "100x": 0.065
    },
    "Olympus (IX83/FV3000)": {
        "4x (PlanN)": 1.61,
        "10x (UPlanSApo)": 0.645,
        "20x (UPlanSApo)": 0.322,
        "40x (UPlanSApo)": 0.161,
        "60x (PlanApo N)": 0.107,
        "100x (UPlanSApo)": 0.064
    },
    "Zeiss (Axio Observer)": {
        "5x (Fluar)": 1.29,
        "10x (Plan-Apo)": 0.645,
        "20x (Plan-Apo)": 0.323,
        "40x (Plan-Apo)": 0.161,
        "63x (Plan-Apo)": 0.102,
        "100x (Plan-Apo)": 0.065
    },
    "Nikon (Ti2)": {
        "4x (Plan Apo)": 1.63,
        "10x (Plan Apo)": 0.65,
        "20x (Plan Apo)": 0.325,
        "40x (Plan Apo)": 0.163,
        "60x (Plan Apo)": 0.108,
        "100x (Plan Apo)": 0.065
    }
}

def get_recommended_bar_length(pixel_size: float, image_width_px: int) -> int:
    """
    Returns a recommended scale bar length (in um) based on FOV.
    Target: Bar should be roughly 1/5 to 1/10 of the image width.
    """
    fov_width_um = image_width_px * pixel_size
    target_len = fov_width_um / 6.0
    
    # Snap to standard values
    standards = [1000, 500, 200, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.1]
    
    for s in standards:
        if target_len >= s:
            return s
    return 1 # Fallback
