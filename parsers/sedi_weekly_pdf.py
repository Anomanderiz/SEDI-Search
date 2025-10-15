from __future__ import annotations

import io
import re
from typing import List, Dict
import pdfplumber
import pandas as pd

INSIDER_RE = re.compile(r"^Insider:\s*(.+)$", re.IGNORECASE)
ISSUER_RE = re.compile(r"^Issuer:\s*(.+)$", re.IGNORECASE)
REL_RE = re.compile(r"^Insider[’']s Relationship to Issuer:\s*(.+)$", re.IGNORECASE)
TXLINE_RE = re.compile(r"^(?P<txid>\d{6,9})\s+(?P<rest>.*)$")  # start of a transaction row
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

def parse_sedi_pdf(pdf_bytes: bytes) -> pd.DataFrame:
    """Best-effort parser for SEDI Weekly Summary by Insider.
    Returns a DataFrame with columns:
    tx_id, insider_name, issuer, relationship, date_tx, nature, security, qty_or_value
    """
    records: List[Dict] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if not text:
                continue
            issuer = None
            insider = None
            relationship = None

            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue

                m_issuer = ISSUER_RE.match(line)
                if m_issuer:
                    issuer = m_issuer.group(1).strip()
                    continue

                m_ins = INSIDER_RE.match(line)
                if m_ins:
                    insider = m_ins.group(1).strip()
                    # reset relationship for each insider block
                    relationship = None
                    continue

                m_rel = REL_RE.match(line)
                if m_rel:
                    relationship = m_rel.group(1).strip()
                    continue

                m_tx = TXLINE_RE.match(line)
                if m_tx and insider:
                    tx_id = m_tx.group("txid")
                    rest = m_tx.group("rest")
                    # Attempt to pull first date occurrence as date of transaction
                    date_match = DATE_RE.search(rest)
                    date_tx = date_match.group(1) if date_match else None

                    # Nature/security/qty try naive splits; these may be improved later
                    nature = None
                    security = None
                    qty_or_value = None

                    # heuristic: look for 'Common Shares' or 'Warrants' or 'Options'
                    if 'Common Shares' in rest:
                        security = 'Common Shares'
                    elif 'Warrants' in rest:
                        security = 'Warrants'
                    elif 'Options' in rest:
                        security = 'Options'

                    # try to extract a '+number' like +200,000
                    m_qty = re.search(r"([+-]?\d{1,3}(?:,\d{3})+)", rest)
                    if m_qty:
                        qty_or_value = m_qty.group(1)

                    # try to extract a nature code like '16 - Acquisition ...' or '50 - Grant of options'
                    m_nat = re.search(r"(\d{2}\s*-\s*[^\d]+)$", rest)
                    if m_nat:
                        nature = m_nat.group(1).strip()

                    records.append({
                        'tx_id': tx_id,
                        'insider_name': insider,
                        'issuer': issuer,
                        'relationship': relationship,
                        'date_tx': date_tx,
                        'nature': nature,
                        'security': security,
                        'qty_or_value': qty_or_value,
                    })
    df = pd.DataFrame.from_records(records)
    # Drop obvious empties and de-duplicate
    if not df.empty:
        df = df.drop_duplicates(subset=['tx_id', 'insider_name', 'issuer'], keep='first')
    return df
