import re

def parse_size_to_bytes(size_str: str | None) -> int | None:
    if not size_str:
        return None
        
    match = re.match(r'^([\d\.]+)\s*([a-zA-Z]*)$', size_str.strip())
    if not match:
        raise ValueError(f"解析檔案大小參數錯誤: {size_str}，請使用如 500KB, 2MB 等格式")
        
    number = float(match.group(1))
    unit = match.group(2).upper()
    
    if unit in ('', 'K', 'KB'):
        return int(number * 1024)
    elif unit in ('M', 'MB'):
        return int(number * 1024 * 1024)
    elif unit in ('G', 'GB'):
        return int(number * 1024 * 1024 * 1024)
    elif unit in ('B', 'BYTE', 'BYTES'):
        return int(number)
    else:
        raise ValueError(f"未知的單位: {unit}")

print(f"1.0MB -> {parse_size_to_bytes('1.0MB')}")
print(f"1MB -> {parse_size_to_bytes('1MB')}")
print(f"1024KB -> {parse_size_to_bytes('1024KB')}")
