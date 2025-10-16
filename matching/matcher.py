from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
import json
import pandas as pd
from rapidfuzz import fuzz
from .normalise import normalise_name, load_titles, split_first_last

@dataclass
class Thresholds:
    high: int = 90
    review: int = 80

def load_nicknames(path: str) -> Dict[str, List[str]]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def token_firsts(name: str, nicknames: Dict[str, List[str]]) -> List[str]:
    if not name:
        return []
    first = name.split()[0]
    variants = {first}
    # add nickname expansions if any
    if first in nicknames:
        variants.update(nicknames[first])
    return list(variants)

def score_pair(insider_norm: str, donor_norm: str, donor_alias_firsts: List[str]) -> Tuple[int, Dict]:
    ins_first, ins_last = split_first_last(insider_norm)
    dn_first, dn_last = split_first_last(donor_norm)

    last_exact = int(ins_last == dn_last) * 100
    first_ratio = fuzz.WRatio(ins_first, dn_first)

    alias_bonus = 0
    if ins_first in donor_alias_firsts:
        alias_bonus += 10

    overall = int(0.55 * last_exact + 0.25 * first_ratio + alias_bonus)
    return overall, {
        'last_exact': last_exact,
        'first_ratio': first_ratio,
        'alias_bonus': alias_bonus,
    }

def match_transactions_to_donors(transactions: pd.DataFrame, donors: pd.DataFrame, titles_path: str, nicknames_path: str, thresholds: Thresholds) -> pd.DataFrame:
    titles = load_titles(titles_path)
    nick = load_nicknames(nicknames_path)

    # Prepare donors

    donors = donors.copy()
    donors['name_norm'] = donors['name'].apply(lambda s: normalise_name(str(s), titles))
    donors['alias_firsts'] = donors.get('aliases', pd.Series([''] * len(donors))).fillna('').apply(lambda s: [a.strip().lower() for a in str(s).split(';') if a.strip()])

    # Precompute alias expansions into first tokens

    donors['alias_firsts'] = donors.apply(lambda r: list(set([*(r['alias_firsts']), *(token_firsts(r['name_norm'].split()[0] if r['name_norm'] else '', nick))])), axis=1)

    # Prepare transactions

    tx = transactions.copy()
    tx['insider_norm'] = tx['insider_name'].apply(lambda s: normalise_name(str(s), titles))

    rows = []
    for _, t in tx.iterrows():
        best_score = -1
        best = None
        best_breakdown = {}
        for _, d in donors.iterrows():
            s, breakdown = score_pair(t['insider_norm'], d['name_norm'], d['alias_firsts'])
            if s > best_score:
                best_score = s
                best = d
                best_breakdown = breakdown
        status = 'low'
        if best_score >= thresholds.high:
            status = 'likely'
        elif best_score >= thresholds.review:
            status = 'review'
        rows.append({
            'tx_id': t.get('tx_id'),
            'insider_name': t.get('insider_name'),
            'insider_norm': t.get('insider_norm'),
            'donor_id': best.get('donor_id') if best is not None else None,
            'donor_name': best.get('name') if best is not None else None,
            'score': best_score,
            'status': status,
            'issuer': t.get('issuer'),
            'date_tx': t.get('date_tx'),
            'nature': t.get('nature'),
            'security': t.get('security'),
            'qty_or_value': t.get('qty_or_value'),
            'breakdown': best_breakdown,
            'unit_or_exercise_price': t.get('unit_or_exercise_price'),

        })
    return pd.DataFrame(rows)
