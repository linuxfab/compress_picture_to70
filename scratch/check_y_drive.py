
import os
from pathlib import Path

def check_dir():
    path_str = r"Y:\ortho完成\111年"
    p = Path(path_str)
    print(f"Checking: {p}")
    if not p.exists():
        print("Path does not exist!")
        return
    
    count = 0
    extensions = {}
    for root, dirs, files in os.walk(p):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            extensions[ext] = extensions.get(ext, 0) + 1
            count += 1
            if count <= 10:
                print(f"Found: {os.path.join(root, f)}")
        if count > 100: # Don't scan too much
            break
            
    print(f"Total files scanned (sample): {count}")
    print(f"Extensions found: {extensions}")

if __name__ == "__main__":
    check_dir()
