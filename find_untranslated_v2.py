
import os
import re
import json

def find_untranslated_strings(root_dir, translation_file):
    # Load existing translations
    with open(translation_file, 'r', encoding='utf-8') as f:
        translations = json.load(f)
    
    # Patterns to find strings in common UI methods
    # 1. Strings wrapped in tr()
    tr_pattern = re.compile(r'tr\((["\'])(.*?)\1\)')
    
    # 2. Hardcoded strings in common UI methods (not wrapped in tr)
    ui_methods = [
        'setText', 'setWindowTitle', 'setToolTip', 'setStatusTip', 
        'setPlaceholderText', 'setTabText', 'setHeaderLabels',
        'information', 'warning', 'critical', 'question', 'addItem',
        'addAction', 'QPushButton', 'QLabel', 'QAction', 'QGroupBox',
        'QCheckBox', 'QRadioButton', 'QMenu', 'setTitle', 'QMessageBox'
    ]
    
    hardcoded_patterns = [
        re.compile(rf'{method}\(\s*(["\'])(.*?)\1\s*[,)]') 
        for method in ui_methods
    ]

    results = {
        "missing_from_json": set(), 
        "hardcoded_no_tr": []      
    }

    for root, dirs, files in os.walk(root_dir):
        if 'venv' in dirs: dirs.remove('venv')
        if '.git' in dirs: dirs.remove('.git')
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Check tr() usage
                    for match in tr_pattern.finditer(content):
                        string = match.group(2)
                        if string not in translations:
                            results["missing_from_json"].add((string, file_path))
                    
                    # Check hardcoded strings (no tr)
                    for pattern in hardcoded_patterns:
                        for match in pattern.finditer(content):
                            full_match = match.group(0)
                            string = match.group(2)
                            
                            if 'tr(' in full_match:
                                continue
                            if len(string) < 2:
                                continue
                            if ' ' not in string and (string.islower() or string.isupper()):
                                if string not in ["OK", "Cancel", "Save", "Add", "Edit", "View", "Help", "Yes", "No"]:
                                    continue

                            results["hardcoded_no_tr"].append({
                                "string": string,
                                "file": file_path,
                                "line": content.count('\n', 0, match.start()) + 1,
                                "context": full_match.strip()
                            })

    return results

if __name__ == "__main__":
    root = r"f:\ubuntu\IF_analyzer\FluoQuantPro\src"
    trans_file = r"f:\ubuntu\IF_analyzer\FluoQuantPro\src\resources\translations.json"
    
    findings = find_untranslated_strings(root, trans_file)
    
    output_file = r"f:\ubuntu\IF_analyzer\FluoQuantPro\untranslated_report.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("--- Missing from translations.json (Wrapped in tr() but no translation) ---\n")
        for s, file_path in sorted(findings["missing_from_json"]):
            f.write(f"[{os.path.basename(file_path)}] {s}\n")
            
        f.write("\n--- Hardcoded strings (NOT wrapped in tr()) ---\n")
        for item in findings["hardcoded_no_tr"]:
            f.write(f"[{os.path.basename(item['file'])}:{item['line']}] {item['string']}  --> {item['context']}\n")
            
    print(f"Report written to {output_file}")
