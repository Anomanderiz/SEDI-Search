from __future__ import annotations
import io, traceback
from pathlib import Path
import pandas as pd
from shiny import App, ui, render, reactive

# --- imports unchanged ---

app_title = "SEDI Insider Monitor"

page = ui.page_navbar(
    ui.head_content(
        ui.tags.link(rel="stylesheet", href="styles.css"),
        # Tiny JS logger: if you click the button, we log to the console no matter what
        ui.tags.script("""
document.addEventListener("click", (e)=>{
  const btn = document.getElementById("parse_btn");
  if (btn && (e.target === btn || btn.contains(e.target))) {
    console.log("[SHINY] parse_btn clicked");
  }
});
""")),
    ui.nav_panel(
        "Upload & Parse",
        ui.layout_columns(
            ui.card(
                ui.h3(app_title, class_="card-title"),
                ui.p("Upload a donor roster (CSV/XLSX) and the SEDI Weekly Summary PDF. Then click Parse."),
                ui.input_file("donor_file", "Donor roster (CSV or XLSX)", multiple=False, accept=[".csv", ".xlsx"], width="100%"),
                ui.input_file("sedi_pdf", "SEDI Weekly PDF", multiple=False, accept=[".pdf"], width="100%"),
                # CHANGED: id -> parse_btn
                ui.input_action_button("parse_btn", "Parse PDF & Match", class_="btn-primary"),
                class_="glass",
            ),
            ui.card(
                ui.h4("Parsing summary", class_="card-title"),
                ui.output_text("summary_text"),
                ui.div({"class": "mt-2 small"},
                       ui.tags.code("Raw click count: "),
                       ui.output_text("parse_clicks")),
                class_="glass",
            ),
            col_widths=(6, 6),
        ),
    ),
    # … rest of your navbar unchanged …
)

def server(input, output, session):
    from parsers.sedi_weekly_pdf import parse_sedi_pdf
    from matching.matcher import match_transactions_to_donors, Thresholds
    from pathlib import Path

    APP_DIR = Path(__file__).parent.resolve()
    CONFIG_DIR = APP_DIR / "config"

    donors_df = reactive.value(pd.DataFrame())
    transactions_df = reactive.value(pd.DataFrame())
    matches_df = reactive.value(pd.DataFrame())
    status_txt = reactive.value("Awaiting files.")

    # NEW: always-visible counter; if this doesn’t change, the click never reaches the server
    @render.text
    def parse_clicks():
        return str(input.parse_btn())  # <- should tick 1,2,3…

    # Wire the event to the new id
    @reactive.event(input.parse_btn)
    def _do_parse():
        try:
            status_txt.set("🔎 Parse clicked — starting…")

            # --- Donor roster ---
            dfile = input.donor_file()
            if not dfile:
                status_txt.set("No donor file selected — continuing with 0 donors.")
                donors = pd.DataFrame(columns=["name", "donor_id", "aliases"])
            else:
                uf = dfile[0]; content = uf.read()
                try:
                    donors = pd.read_csv(io.BytesIO(content))
                except Exception:
                    donors = pd.read_excel(io.BytesIO(content))
                donors.columns = [str(c).strip().lower().replace(" ", "_") for c in donors.columns]
                donors.rename(columns={"donor_name": "name", "full_name": "name", "fullname": "name", "id": "donor_id"}, inplace=True)
                if "name" not in donors.columns:
                    raise ValueError("Donor roster must include a 'name' column.")
                donors.setdefault("donor_id", donors.index.astype(str))
                donors.setdefault("aliases", "")
                status_txt.set(f"Loaded {len(donors)} donors…")
            donors_df.set(donors)

            # --- SEDI PDF ---
            pfile = input.sedi_pdf()
            if not pfile:
                status_txt.set("No PDF selected — continuing with 0 transactions.")
                tx = pd.DataFrame()
            else:
                try:
                    pdfbytes = pfile[0].read()
                    tx = parse_sedi_pdf(pdfbytes) or pd.DataFrame()
                    status_txt.set(f"Parsed {len(tx)} transactions from PDF…")
                except Exception as e:
                    status_txt.set(f"⚠️ PDF parse error: {e}")
                    tx = pd.DataFrame()
            transactions_df.set(tx)

            # --- Matching ---
            if donors.empty or tx.empty:
                matches_df.set(pd.DataFrame(columns=["tx_id","insider_name","donor_id","donor_name","score","status"]))
                status_txt.set(f"Parsed {len(tx)} transactions; donors={len(donors)}. Nothing to match.")
                return

            status_txt.set("Running fuzzy matching…")
            thr = Thresholds(high=input.thr_high(), review=input.thr_review())
            matches = match_transactions_to_donors(
                tx, donors, CONFIG_DIR / "titles.txt", CONFIG_DIR / "nicknames.json", thr
            )
            matches_df.set(matches)
            status_txt.set(f"Done. Donors: {len(donors)} | Transactions: {len(tx)} | Candidate matches: {len(matches)}")

        except Exception as e:
            status_txt.set(f"⚠️ Error: {type(e).__name__}: {e}")
            matches_df.set(pd.DataFrame())

    @render.text
    def summary_text():
        return status_txt()

    @render.table
    def tbl_matches():
        m = matches_df()
        if m.empty: return pd.DataFrame()
        df = m.copy()
        if not input.show_low() and "status" in df.columns:
            df = df[df["status"] != "low"]
        keep = [c for c in ["status","score","insider_name","donor_name","issuer","date_tx","nature","security","qty_or_value","tx_id"] if c in df.columns]
        return df[keep].sort_values(["status","score"], ascending=[True, False])

app = App(page, server, static_assets=str((Path(__file__).parent / "www").resolve()))
