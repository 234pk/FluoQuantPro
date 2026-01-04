import ast
import os
import sys

def get_imports(root):
    imports = []
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append((n.name, n.asname or n.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for n in node.names:
                full_name = f"{module}.{n.name}" if module else n.name
                imports.append((full_name, n.asname or n.name, node.lineno))
    return imports

def check_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        # print(f"Error parsing {filepath}: {e}")
        return

    imports = get_imports(tree)
    
    # Collect all Name ids used in the code
    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # For 'os.path', 'os' is a Name(id='os').
            pass
            
    unused_imports = []
    for full_name, as_name, lineno in imports:
        if as_name not in used_names:
            # Special case: __init__.py
            if os.path.basename(filepath) == '__init__.py':
                continue
            # Special case: 'cv2' often used but sometimes false positive if only referenced in strings? No.
            # Special case: logic that uses globals() or similar? Rare.
            
            unused_imports.append((as_name, lineno))

    if unused_imports:
        print(f"File: {filepath}")
        for name, lineno in unused_imports:
            print(f"  Line {lineno}: Unused import '{name}'")

def scan_project(root_dir):
    print(f"Scanning {root_dir} for redundancy...")
    for root, dirs, files in os.walk(root_dir):
        # Exclude common non-project dirs
        if 'venv' in dirs: dirs.remove('venv')
        if '.git' in dirs: dirs.remove('.git')
        if '__pycache__' in dirs: dirs.remove('__pycache__')
        if 'build' in dirs: dirs.remove('build')
        if 'dist' in dirs: dirs.remove('dist')
        if '.trae' in dirs: dirs.remove('.trae')
        
        for file in files:
            if file.endswith('.py'):
                check_file(os.path.join(root, file))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = os.getcwd()
    scan_project(root)
