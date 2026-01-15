
import json
import os

def cleanup_translations(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            return

    # JSON keys are already unique in a dict, but we want to ensure 
    # the structure is clean and sorted for better maintainability.
    
    # Sort by key to make it easier to find and diff
    sorted_data = dict(sorted(data.items()))
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)
    
    print(f"Cleaned up and sorted {file_path}")

if __name__ == "__main__":
    root_dir = r"f:\ubuntu\IF_analyzer\FluoQuantPro"
    trans_file = os.path.join(root_dir, "src", "resources", "translations.json")
    cleanup_translations(trans_file)
