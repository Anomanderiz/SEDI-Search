# SEDI Insider Monitor (Shiny for Python on Posit Cloud)

This is a starter scaffold. It lets you upload:
1) A donor roster (CSV/XLSX) with columns: `donor_id`, `name`, optional `aliases` (semicolon-separated).
2) The weekly SEDI "Weekly Summary by Insider" PDF.

It extracts Insider + Issuer blocks and transaction rows (best-effort), runs fuzzy matching against donors,
and shows a review table with confidence scores.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Then visit http://127.0.0.1:8000

## Deploy on Posit Cloud
- Create a new Shiny for Python project.
- Upload all files in this repo.
- Ensure the `requirements.txt` is used to install packages.
- Set the entrypoint to `app.py`.
