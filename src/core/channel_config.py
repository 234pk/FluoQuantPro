"""
Configuration for biological fluorescence channels and their RGB mapping rules.
"""

# Biological Fluorescence Channel Mappings:
# Index 0: Red, Index 1: Green, Index 2: Blue
# 1 means the channel is active, 0 means inactive.
CHANNEL_RGB_MAPPING = {
    "DAPI": [0, 0, 1],       # Only Blue
    "Hoechst": [0, 0, 1],    # Only Blue
    "GFP": [0, 1, 0],        # Only Green
    "FITC": [0, 1, 0],       # Only Green
    "RFP": [1, 0, 0],        # Only Red
    "mCherry": [1, 0, 0],    # Only Red
    "CY5": [1, 0, 1],        # Red + Blue (Magenta)
    "TRITC": [1, 0, 0],      # Only Red
    "CY3": [1, 0, 0],        # Only Red
    "YFP": [1, 1, 0],        # Red + Green (Yellow)
    "Phase": [0, 1, 0],      # Gray-associated Green
    "Brightfield": [0, 1, 0], # Gray-associated Green
    "Alexa488": [0, 1, 0],
    "Alexa555": [1, 0, 0],
    "Alexa568": [1, 0, 0],
    "Alexa594": [1, 0, 0],
    "Alexa647": [1, 0, 1],   # Red + Blue
}

def get_rgb_mapping(channel_name: str):
    """
    Returns the RGB mapping for a given channel name.
    Falls back to a default (White/Gray mapping) if not found.
    """
    if not channel_name:
        return [1, 1, 1]
        
    name_upper = channel_name.upper()
    for key, mapping in CHANNEL_RGB_MAPPING.items():
        if key.upper() in name_upper:
            return mapping
            
    return None # Signal to use default logic

# Biological Fluorescence Channel Colors (Hex):
CHANNEL_COLORS = {
    "DAPI": "#0000FF",        # Blue
    "HOECHST": "#0000FF",     # Blue
    "GFP": "#00FF00",         # Green
    "FITC": "#00FF00",        # Green
    "RFP": "#FF0000",         # Red
    "MCHERRY": "#FF0000",      # Red
    "CY5": "#FF00FF",         # Magenta (Standard for Far-Red)
    "ALEXA647": "#FF00FF",    # Magenta
    "TRITC": "#FF0000",       # Red
    "CY3": "#FF0000",         # Red
    "YFP": "#FFFF00",         # Yellow
    "PHASE": "#808080",       # Gray
    "BRIGHTFIELD": "#C0C0C0",  # Light Gray
    "ALEXA488": "#00FF00",
    "ALEXA555": "#FF0000",
    "ALEXA568": "#FF0000",
    "ALEXA594": "#FF0000",
}

def get_channel_color(channel_name: str) -> str:
    """
    Returns a hex color string based on the predefined channel colors.
    """
    if not channel_name:
        return "#FFFFFF"
        
    name_upper = channel_name.upper()
    for key, color in CHANNEL_COLORS.items():
        if key in name_upper:
            return color
            
    return "#FFFFFF"
