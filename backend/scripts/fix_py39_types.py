
#!/usr/bin/env python3
"""
Replace Python 3.10+ type annotations (Optional[str], list[str], dict[K,V])
with Python 3.9 compatible versions (Optional[str], List[str], Dict[K,V]).
Adds from typing import Optional, List, Dict, Any where needed.
"""
import os
import re
import sys


def fix_file(filepath):
    with open(filepath) as f:
        content = f.read()

    original = content

    # Replace TYPE | None -> Optional[TYPE]
    content = re.sub(r'\b(str|int|float|bool|dict|list|tuple|set|frozenset|bytes|object)\s*\|\s*None\b',
                     r'Optional[\1]', content)
    content = re.sub(r'\b(list\[.+?\])\s*\|\s*None\b', r'Optional[\1]', content)
    content = re.sub(r'\b(dict\[.+?\])\s*\|\s*None\b', r'Optional[\1]', content)
    content = re.sub(r'\b(tuple\[.+?\])\s*\|\s*None\b', r'Optional[\1]', content)

    if content == original:
        return False

    # Ensure Optional is in typing import
    typing_match = re.search(r'^from typing import (.+)$', content, flags=re.MULTILINE)
    if typing_match:
        imports = typing_match.group(1).replace(' ', '')
        if 'Optional' not in imports:
            new_import = 'from typing import Optional, ' + typing_match.group(1)
            content = content[:typing_match.start()] + new_import + content[typing_match.end():]
    elif not re.search(r'^from typing import', content, flags=re.MULTILINE):
        # Check if there is a from __future__ import
        future_match = re.search(r'^from __future__ import .+$', content, flags=re.MULTILINE)
        if future_match:
            insert_pos = future_match.end()
            content = content[:insert_pos] + '\nfrom typing import Optional' + content[insert_pos:]
        else:
            # Insert after docstring
            match = re.match(r'(^""".*?"""\n+)', content, re.DOTALL)
            insert_pos = match.end() if match else 0
            content = content[:insert_pos] + 'from typing import Optional\n\n' + content[insert_pos:]

    with open(filepath, 'w') as f:
        f.write(content)
    return True

if __name__ == '__main__':
    for filepath in sys.argv[1:]:
        if not os.path.exists(filepath):
            print(f"SKIP: {filepath} not found")
            continue
        changed = fix_file(filepath)
        print(f"{'FIXED' if changed else 'OK'}: {filepath}")
