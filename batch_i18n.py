import os
import re
import json
from src.core.language_manager import tr

# Configuration
target_dirs = [
    r'f:\ubuntu\IF_analyzer\FluoQuantPro\src',
    r'f:\ubuntu\IF_analyzer\FluoQuantPro' # Also scan root for main.py
]
translations_path = r'f:\ubuntu\IF_analyzer\FluoQuantPro\src\resources\translations.json'

# Patterns to match: Widget("Text") or method("Text")
# Added more methods and static calls
patterns = [
    # tr("...") already present
    r'tr\(\s*\"([^"\'\n]{2,})\"\s*\)',
    r'tr\(\s*\'([^\'\"\n]{2,})\'\s*\)',

    # Basic widget constructors and methods
    r'(QLabel|QPushButton|QCheckBox|QRadioButton|QGroupBox|QDockWidget|QMenu|QAction|setWindowTitle|setToolTip|setText|addItem|insertItem|addTab|setTabText|addAction|setPlaceholderText|setStatusTip|setWhatsThis|update_splash)\(\s*\"([^"\'\n]{2,})\"\s*',
    r'(QLabel|QPushButton|QCheckBox|QRadioButton|QGroupBox|QDockWidget|QMenu|QAction|setWindowTitle|setToolTip|setText|addItem|insertItem|addTab|setTabText|addAction|setPlaceholderText|setStatusTip|setWhatsThis|update_splash)\(\s*\'([^\'\"\n]{2,})\'\s*',
    
    # QMessageBox static methods (matches title and message if they are simple strings)
    r'QMessageBox\.(information|warning|critical|question)\(\s*([^,]+),\s*\"([^"\'\n]{2,})\",\s*\"([^"\'\n]{2,})\"',
    r'QMessageBox\.(information|warning|critical|question)\(\s*([^,]+),\s*\'([^\'\"\n]{2,})\',\s*\'([^\'\"\n]{2,})\'',
    
    # QInputDialog static methods
    r'QInputDialog\.(getText|getInt|getDouble|getItem)\(\s*([^,]+),\s*\"([^"\'\n]{2,})\",\s*\"([^"\'\n]{2,})\"',
    r'QInputDialog\.(getText|getInt|getDouble|getItem)\(\s*([^,]+),\s*\'([^\'\"\n]{2,})\',\s*\'([^\'\"\n]{2,})\''
]

def migrate_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_strings = set()
    modified = False

    def replace_tr(match):
        text = match.group(1)
        new_strings.add(text)
        return match.group(0)

    def replace_simple(match):
        nonlocal modified
        func_name = match.group(1)
        text = match.group(2)
        
        technical_terms = {
            'CSV', 'JSON', 'OK', 'Cancel', 'Apply', 'zh', 'en', '0%', '100%', 'True', 'False', 'None',
            'ROI', 'DAPI', 'GFP', 'RFP', 'YFP', 'CY5', 'RGB', 'TIFF', 'PCC', 'M1', 'M2', 'Catmull-Rom',
            'sigma', 'px', 'bits', 'ms', 's', 'min', 'max', 'Gamma', 'Raw', 'Undo', 'Redo', 'Macro'
        }
        if text in technical_terms or text.startswith('qt_') or text.endswith(('.png', '.jpg', '.ico', '.svg')):
            return match.group(0)

        modified = True
        new_strings.add(text)
        return f'{func_name}(tr("{text}")'

    def replace_static_msg(match):
        nonlocal modified
        method = match.group(1)
        parent = match.group(2)
        title = match.group(3)
        message = match.group(4)
        
        modified = True
        new_strings.add(title)
        new_strings.add(message)
        return f'QMessageBox.{method}({parent}, tr("{title}"), tr("{message}")'

    def replace_static_input(match):
        nonlocal modified
        method = match.group(1)
        parent = match.group(2)
        title = match.group(3)
        label = match.group(4)
        
        modified = True
        new_strings.add(title)
        new_strings.add(label)
        return f'QInputDialog.{method}({parent}, tr("{title}"), tr("{label}")'

    new_content = content
    # Collect existing tr strings first
    re.sub(patterns[0], replace_tr, new_content)
    re.sub(patterns[1], replace_tr, new_content)

    # Simple methods
    new_content = re.sub(patterns[2], replace_simple, new_content)
    new_content = re.sub(patterns[3], replace_simple, new_content)
    
    # Static methods
    new_content = re.sub(patterns[4], replace_static_msg, new_content)
    new_content = re.sub(patterns[5], replace_static_msg, new_content)
    new_content = re.sub(patterns[6], replace_static_input, new_content)
    new_content = re.sub(patterns[7], replace_static_input, new_content)

    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return new_strings
    return set()

def update_translations(new_strings):
    if not os.path.exists(translations_path):
        data = {}
    else:
        with open(translations_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    # Added count
    added_count = 0
    
    # Technical terms that should stay in English
    technical_terms = {
        'ROI', 'DAPI', 'GFP', 'RFP', 'YFP', 'CY5', 'RGB', 'TIFF', 'PCC', 'M1', 'M2', 'Catmull-Rom',
        'CSV', 'JSON', 'OK', 'Cancel', 'Apply', 'Gamma', 'Raw', 'Undo', 'Redo', 'Macro',
        'FluoQuant Pro', 'FluoQuantPro', 'px', 'ms', 's', 'min', 'max', 'sigma', 'bits'
    }

    # Add new strings
    for s in new_strings:
        if s not in data:
            # If it's a technical term, keep it in English for Chinese translation
            if s in technical_terms:
                data[s] = {"zh": s}
            else:
                data[s] = {"zh": s} 
            added_count += 1

    # Enforcement: Ensure existing technical terms are in English in the "zh" field
    for term in technical_terms:
        if term in data:
            data[term]["zh"] = term
        # Also check for variations or containing the term if appropriate, 
        # but be careful not to overwrite descriptive strings.
        # For now, just exact matches for the core terms.

    with open(translations_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return added_count

all_new_strings = set()
processed_files = 0

for target_dir in target_dirs:
    for root, dirs, files in os.walk(target_dir):
        # Don't recurse into src if we are scanning root and src is already in target_dirs
        # Actually, let's just be careful not to process same files twice
        if target_dir == r'f:\ubuntu\IF_analyzer\FluoQuantPro' and 'src' in dirs:
            dirs.remove('src')
        
        for file in files:
            if file.endswith('.py') and file != 'batch_i18n.py' and file != 'clean_json.py' and file != 'find_untranslated.py':
                file_path = os.path.join(root, file)
                new_strs = migrate_file(file_path)
                if new_strs:
                    all_new_strings.update(new_strs)
                    processed_files += 1

added_to_json = update_translations(all_new_strings)

print(f"Processed {processed_files} files.")
print(f"Found {len(all_new_strings)} unique strings.")
print(f"Added {added_to_json} new entries to translations.json.")
