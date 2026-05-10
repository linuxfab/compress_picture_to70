
from pathlib import Path
import os

def test_paths():
    dir_str = r"Y:\ortho完成\111年"
    directory = Path(dir_str)
    print(f"Directory: {directory}")
    
    # Simulate os.walk behavior
    root = dir_str
    root_path = Path(root)
    print(f"Root: {root_path}")
    
    try:
        rel = root_path.relative_to(directory)
        print(f"Relative: {rel}")
        print(f"Parts: {rel.parts}")
        print(f"Depth: {len(rel.parts)}")
    except ValueError as e:
        print(f"ValueError: {e}")

if __name__ == "__main__":
    test_paths()
