import os

def fix_sh_line_endings(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.sh'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    # Replace CRLF with LF
                    fixed_content = content.replace(b'\r\n', b'\n')
                    
                    with open(file_path, 'wb') as f:
                        f.write(fixed_content)
                    print(f"Fixed line endings for {file_path}")
                except Exception as e:
                    print(f"Error fixing {file_path}: {e}")

if __name__ == "__main__":
    fix_sh_line_endings("f:/ubuntu/IF_analyzer/FluoQuantPro/Mac_Version")
