
import os
from pathlib import Path

def check_dir():
    path_str = r"Y:\ortho完成\111年"
    p = Path(path_str)
    print(f"Checking: {p}")
    
    count = 0
    for root, dirs, files in os.walk(p):
        for f in files:
            full_path = os.path.join(root, f)
            size = os.path.getsize(full_path)
            print(f"File: {f}, Size: {size} bytes ({size/1024/1024:.2f} MB)")
            count += 1
            if count >= 10:
                break
        if count >= 10:
            break

if __name__ == "__main__":
    check_dir()
