from __future__ import annotations
import io, pandas as pd
from shiny import App, ui, render, reactive
from parsers.sedi_weekly_pdf import parse_sedi_pdf
from matching.matcher import match_transactions_to_donors, Thresholds
from pathlib import Path
# --- add near the top (below imports) ---
from pathlib import Path
import io, os

def _read_upload(uf) -> bytes:
    """Accept Shiny FileInfo or a plain dict and return bytes."""
    # Newer Shiny: FileInfo object with .read()
    if hasattr(uf, "read"):
        return uf.read()
    # Older/bare: dict with a temp file path
    if isinstance(uf, dict):
        for key in ("datapath", "path"):
            p = uf.get(key)
            if p and os.path.exists(p):
                with open(p, "rb") as f:
                    return f.read()
    raise TypeError(f"Unsupported upload object: {type(uf)!r}")

def _first_existing(*paths: str | Path) -> str:
    for p in map(Path, paths):
        if p.exists():
            return str(p)
    raise FileNotFoundError("Could not locate titles/nicknames config files.")

APP_DIR = Path(__file__).parent.resolve()
STATIC_DIR = APP_DIR / "www"   # absolute path to your static folder

app_title = "SEDI Insider Monitor"

page = ui.page_navbar(
    ui.head_content(ui.tags.link(rel="stylesheet", href="styles.css")),
    ui.nav_panel("Upload & Parse", ui.layout_columns(
        ui.card(
            ui.h3(app_title, class_='card-title'),
            ui.p("Upload a donor roster (CSV/XLSX) and the SEDI Weekly Summary PDF. Then click Parse."),
            ui.input_file("donor_file", "Donor roster (CSV or XLSX)", multiple=False, accept=[".csv", ".xlsx"], width="100%"),
            ui.input_file("sedi_pdf", "SEDI Weekly PDF", multiple=False, accept=[".pdf"], width="100%"),
            ui.input_action_button("parse", "Parse PDF & Match", class_="btn-primary"),
            class_="glass",
        ),
        ui.card(
            ui.h4("Parsing summary", class_='card-title'),
            ui.output_text("summary_text"),
            class_="glass",
        ),
        col_widths=(6,6)
    )),
    ui.nav_panel("Matches", ui.layout_columns(
        ui.card(
            ui.h4("Thresholds", class_='card-title'),
            ui.input_slider("thr_high", "High (likely) threshold", min=70, max=100, value=90),
            ui.input_slider("thr_review", "Review threshold", min=60, max=99, value=80),
            ui.input_checkbox("show_low", "Show low-confidence", value=False),
            class_="glass"
        ),
        ui.card(
            ui.h4("Candidate matches", class_='card-title'),
            ui.output_table("tbl_matches"),
            class_="glass",
        ),
        col_widths=(3,9)
    )),
    ui.nav_panel("About", ui.layout_columns(
        ui.card(
            ui.h4("About this tool", class_='card-title'),
            ui.markdown("This app, brought to you by the genius of the Prospect Research Team, analyses weekly summaries of insider transactions ppublished by SEDI Canada and highlights transactions made by a roster of people of interest.\nIdenitifying potential donors who have made large sales of stock quickly will enable our fundraisers to solicit them at the right moment and thereby increase our rates of success for major gifts."),
            class_="glass",
        ),
        col_widths=(12,)
    )),
    title=app_title,
)
def server(input, output, session):
    donors_df = reactive.value(pd.DataFrame())
    transactions_df = reactive.value(pd.DataFrame())
    matches_df = reactive.value(pd.DataFrame())
    status_txt = reactive.value("Awaiting files.")
    
    @reactive.effect
    @reactive.event(input.parse)
    def _do_parse():
        try:
            # ---------- Donor roster ----------
            status_txt.set("Reading donor file…")
            dfile = input.donor_file()
            if not dfile:
                status_txt.set("No donor file selected."); donors = pd.DataFrame()
            else:
                uf = dfile[0]
                content = _read_upload(uf)
                try:
                    donors = pd.read_csv(io.BytesIO(content))
                except Exception:
                    donors = pd.read_excel(io.BytesIO(content))

                # Normalise headers and map common aliases
                donors.columns = [str(c).strip().lower().replace(" ", "_") for c in donors.columns]
                alias_map = {
                    "donor_name": "name",
                    "full_name": "name",
                    "fullname": "name",
                    "id": "donor_id",
                }
                donors.rename(columns={k: v for k, v in alias_map.items() if k in donors.columns}, inplace=True)

                # Ensure required columns
                if "name" not in donors.columns:
                    raise ValueError("Donor roster is missing a 'name' column. Required: name. Optional: donor_id, aliases")

                if "donor_id" not in donors.columns:
                    donors["donor_id"] = donors.index.astype(str)
                if "aliases" not in donors.columns:
                    donors["aliases"] = ""

            donors_df.set(donors)
            status_txt.set(f"Loaded {len(donors)} donors.")

            # ---------- SEDI PDF ----------
            status_txt.set("Parsing SEDI PDF…")
            pfile = input.sedi_pdf()
            if not pfile:
                status_txt.set("No PDF selected."); tx = pd.DataFrame()
            else:
                uf = pfile[0]
                pdfbytes = _read_upload(uf)
                tx = parse_sedi_pdf(pdfbytes)
            transactions_df.set(tx)

            # ---------- Matching ----------
            if tx.empty or donors.empty:
                matches = pd.DataFrame(columns=['tx_id','insider_name','donor_id','donor_name','score','status','issuer','date_tx'])
                matches_df.set(matches)
                status_txt.set(f"Parsed {len(tx)} transactions; no matching run (missing donors or transactions).")
                return

            status_txt.set("Running fuzzy matching…")
            thr = Thresholds(high=input.thr_high(), review=input.thr_review())
            matches = match_transactions_to_donors(tx, donors, 'config/titles.txt', 'config/nicknames.json', thr)
            matches_df.set(matches)
            status_txt.set(f"Done. Donors: {len(donors)} | Transactions: {len(tx)} | Candidate matches: {len(matches)}")

        except Exception as e:
            # Surface the error to the UI and keep the app alive
            status_txt.set(f"⚠️ Error: {type(e).__name__}: {e}")
            matches_df.set(pd.DataFrame())

    @render.text
    def summary_text():
        return status_txt()
        d = donors_df(); t = transactions_df(); m = matches_df()
        if t.empty: return "Awaiting files."
        return f"Donors: {len(d)} | Transactions parsed: {len(t)} | Candidate matches: {len(m)}"
    @render.table
    def tbl_matches():
        m = matches_df()
        if m.empty: return pd.DataFrame()
        df = m.copy()
        if not input.show_low(): df = df[df['status'] != 'low']
        cols = ['status','score','insider_name','donor_name','issuer','date_tx','nature','security','qty_or_value','tx_id']
        cols = [c for c in cols if c in df.columns]
        return df[cols].sort_values(['status','score'], ascending=[True, False])
app = App(page, server, static_assets=str(STATIC_DIR))
