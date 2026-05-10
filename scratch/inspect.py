from pathlib import Path
fp = Path(__file__).parent.parent / "utils.py"
lines = fp.read_text(encoding='utf-8').splitlines(keepends=True)
for i in range(41, 45):
    print(i+1, repr(lines[i]))
