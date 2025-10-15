from __future__ import annotations
import pandas as pd

def digest_by_donor(matches: pd.DataFrame) -> pd.DataFrame:
    cols = ['donor_id', 'donor_name', 'insider_name', 'score', 'status', 'issuer', 'date_tx', 'nature', 'security', 'qty_or_value', 'tx_id']
    df = matches[cols].copy()
    df = df.sort_values(['donor_name', 'date_tx'], ascending=[True, False])
    return df
