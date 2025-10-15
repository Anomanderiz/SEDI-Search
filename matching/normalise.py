from __future__ import annotations
import re
import unicodedata
from typing import List, Tuple, Set

def strip_diacritics(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def load_titles(path: str) -> Set[str]:
    titles = set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            t = line.strip().lower().strip(',')
            if t:
                titles.add(t)
    return titles

def normalise_name(name: str, titles: Set[str]) -> str:
    if not name:
        return ''
    s = strip_diacritics(name).replace('’', "'")
    s = re.sub(r"[.,]", ' ', s)
    s = re.sub(r"\s+", ' ', s).strip().lower()

    # Remove post-nominals/honorifics tokens
    tokens = [tok for tok in s.split(' ') if tok not in titles]
    s = ' '.join(tokens)

    # Convert 'Last, First' -> 'First Last'
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            s = f"{parts[1].lower()} {parts[0].lower()}"
            s = re.sub(r"\s+", ' ', s).strip()
    return s

def split_first_last(n: str) -> Tuple[str, str]:
    if not n:
        return '', ''
    toks = n.split()
    if len(toks) == 1:
        return toks[0], toks[0]
    return toks[0], toks[-1]
