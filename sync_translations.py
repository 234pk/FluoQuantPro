
import json
import os
import shutil

def sync_translations():
    root_dir = r"f:\ubuntu\IF_analyzer\FluoQuantPro"
    src_file = os.path.join(root_dir, "src", "resources", "translations.json")
    mac_file = os.path.join(root_dir, "macversion", "src", "resources", "translations.json")

    if not os.path.exists(src_file):
        print(f"Error: Source file {src_file} not found")
        return

    # 1. Clean and sort source file
    with open(src_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    sorted_data = dict(sorted(data.items()))
    
    with open(src_file, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)
    print(f"Cleaned and sorted source translations.")

    # 2. Copy to macversion
    os.makedirs(os.path.dirname(mac_file), exist_ok=True)
    shutil.copy2(src_file, mac_file)
    print(f"Synced to {mac_file}")

if __name__ == "__main__":
    sync_translations()
