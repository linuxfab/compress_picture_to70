
from pathlib import Path

def test_relative_to_case():
    p1 = Path("Y:/test")
    p2 = Path("y:/test/sub")
    try:
        print(f"p2.relative_to(p1): {p2.relative_to(p1)}")
    except ValueError as e:
        print(f"ValueError: {e}")

if __name__ == "__main__":
    test_relative_to_case()
