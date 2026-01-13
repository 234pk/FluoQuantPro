import json
import os

translations_path = r'f:\ubuntu\IF_analyzer\FluoQuantPro\src\resources\translations.json'

technical_terms = {
    'ROI', 'DAPI', 'GFP', 'RFP', 'YFP', 'CY5', 'RGB', 'TIFF', 'PCC', 'M1', 'M2', 'Catmull-Rom',
    'CSV', 'JSON', 'OK', 'Cancel', 'Apply', 'Gamma', 'Raw', 'Undo', 'Redo', 'Macro',
    'FluoQuant Pro', 'FluoQuantPro', 'px', 'ms', 's', 'min', 'max', 'sigma', 'bits', 'zh', 'en', '0%', '100%', 'True', 'False', 'None'
}

with open(translations_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

untranslated = []
for key, value in data.items():
    zh = value.get("zh", "")
    if (zh == key or zh == "") and key not in technical_terms:
        # Check if it's a file path or something that shouldn't be translated
        if not (key.endswith(('.png', '.jpg', '.ico', '.svg')) or key.startswith('qt_')):
            untranslated.append(key)

print(f"Found {len(untranslated)} untranslated strings.")
for s in untranslated[:20]:
    print(f"- {s}")
