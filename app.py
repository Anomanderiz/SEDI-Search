from __future__ import annotations
import io, traceback
from pathlib import Path
import pandas as pd
from shiny import App, ui, render, reactive

# ---------- Paths ----------
APP_DIR = Path(__file__).parent.resolve()
STATIC_DIR = APP_DIR / "www"
CONFIG_DIR = APP_DIR / "config"

app_title = "SEDI Insider Monitor"

page = ui.page_navbar(
    ui.head_content(ui.tags.link(rel="stylesheet", href="styles.css")),
    ui.nav_panel(
        "Upload & Parse",
        ui.layout_columns(
            ui.card(
                ui.h3(app_title, class_="card-title"),
                ui.p("Upload a donor roster (CSV/XLSX) and the SEDI Weekly Summary PDF. Then click Parse."),
                ui.input_file("donor_file", "Donor roster (CSV or XLSX)", multiple=False, accept=[".csv", ".xlsx"], width="100%"),
                ui.input_file("sedi_pdf", "SEDI Weekly PDF", multiple=False, accept=[".pdf"], width="100%"),
                ui.input_action_button("parse", "Parse PDF & Match", class_="btn-primary"),
                class_="glass",
            ),
            ui.card(
                ui.h4("Parsing summary", class_="card-title"),
                ui.output_text("summary_text"),
                class_="glass",
            ),
            col_widths=(6, 6),
        ),
    ),
    ui.nav_panel(
        "Matches",
        ui.layout_columns(
            ui.card(
                ui.h4("Thresholds", class_="card-title"),
                ui.input_slider("thr_high", "High (likely) threshold", min=70, max=100, value=90),
                ui.input_slider("thr_review", "Review threshold", min=60, max=99, value=80),
                ui.input_checkbox("show_low", "Show low-confidence", value=False),
                class_="glass",
            ),
            ui.card(
                ui.h4("Candidate matches", class_="card-title"),
                ui.output_table("tbl_matches"),
                class_="glass",
            ),
            col_widths=(3, 9),
        ),
    ),
    ui.nav_panel(
        "About",
        ui.layout_columns(
            ui.card(
                ui.h4("About this tool", class_="card-title"),
                ui.markdown(
                    "This prototype parses the weekly SEDI PDF and performs fuzzy name matching "
                    "against your donor roster.\n- Uses `pdfplumber` for text extraction.\n"
                    "- Uses `rapidfuzz` for composite scoring with strong last-name weight.\n"
                    "- Parsing heuristics for transaction rows can be further improved."
                ),
                class_="glass",
            ),
            col_widths=(12,),
        ),
    ),
    title=app_title,
)

def server(input, output, session):
    from parsers.sedi_weekly_pdf import parse_sedi_pdf
    from matching.matcher import match_transactions_to_donors, Thresholds

    donors_df = reactive.value(pd.DataFrame())
    transactions_df = reactive.value(pd.DataFrame())
    matches_df = reactive.value(pd.DataFrame())
    status_txt = reactive.value("Awaiting files.")

    # --- CLICK HANDLER --------------------------------------------------------
    @reactive.event(input.parse)
    def _do_parse():
        try:
            status_txt.set("🔎 Parse clicked — starting…")

            # -- Donor roster ---------------------------------------------------
            dfile = input.donor_file()
            if not dfile:
                donors = pd.DataFrame(columns=["name", "donor_id", "aliases"])
                status_txt.set("No donor file selected — continuing with 0 donors.")
            else:
                uf = dfile[0]
                content = uf.read()
                try:
                    donors = pd.read_csv(io.BytesIO(content))
                except Exception:
                    # Fall back to Excel
                    donors = pd.read_excel(io.BytesIO(content))
                donors.columns = [str(c).strip().lower().replace(" ", "_") for c in donors.columns]
                alias_map = {"donor_name": "name", "full_name": "name", "fullname": "name", "id": "donor_id"}
                donors.rename(columns={k: v for k, v in alias_map.items() if k in donors.columns}, inplace=True)
                if "name" not in donors.columns:
                    raise ValueError("Donor roster is missing a 'name' column. Required: name. Optional: donor_id, aliases")
                if "donor_id" not in donors.columns:
                    donors["donor_id"] = donors.index.astype(str)
                if "aliases" not in donors.columns:
                    donors["aliases"] = ""
                status_txt.set(f"Loaded {len(donors)} donors…")

            donors_df.set(donors)

            # -- SEDI PDF -------------------------------------------------------
            pfile = input.sedi_pdf()
            if not pfile:
                tx = pd.DataFrame()
                status_txt.set("No PDF selected — continuing with 0 transactions.")
            else:
                try:
                    pdfbytes = pfile[0].read()
                    tx = parse_sedi_pdf(pdfbytes) or pd.DataFrame()
                    status_txt.set(f"Parsed {len(tx)} transactions from PDF…")
                except Exception as e:
                    status_txt.set(f"⚠️ PDF parse error: {e}")
                    tx = pd.DataFrame()

            transactions_df.set(tx)

            # -- Matching -------------------------------------------------------
            if donors.empty or tx.empty:
                matches_df.set(pd.DataFrame(columns=["tx_id", "insider_name", "donor_id", "donor_name", "score", "status"]))
                status_txt.set(f"Parsed {len(tx)} transactions; donors={len(donors)}. Nothing to match.")
                return

            status_txt.set("Running fuzzy matching…")
            thr = Thresholds(high=input.thr_high(), review=input.thr_review())
            matches = match_transactions_to_donors(
                tx,
                donors,
                CONFIG_DIR / "titles.txt",
                CONFIG_DIR / "nicknames.json",
                thr,
            )
            matches_df.set(matches)
            status_txt.set(
                f"Done. Donors: {len(donors)} | Transactions: {len(tx)} | Candidate matches: {len(matches)}"
            )
        except Exception as e:
            # Don’t go silent — surface the error both in UI and logs
            status_txt.set(f"⚠️ Error: {type(e).__name__}: {e}")
            print("SERVER ERROR:\n" + traceback.format_exc())
            matches_df.set(pd.DataFrame())

    # --- OUTPUTS --------------------------------------------------------------
    @render.text
    def summary_text():
        # Always reflect the latest status line
        return status_txt()

    @render.table
    def tbl_matches():
        m = matches_df()
        if m.empty:
            return pd.DataFrame()
        df = m.copy()
        if not input.show_low():
            if "status" in df.columns:
                df = df[df["status"] != "low"]
        cols = [
            "status",
            "score",
            "insider_name",
            "donor_name",
            "issuer",
            "date_tx",
            "nature",
            "security",
            "qty_or_value",
            "tx_id",
        ]
        cols = [c for c in cols if c in df.columns]
        return df[cols].sort_values(["status", "score"], ascending=[True, False])

app = App(page, server, static_assets=str(STATIC_DIR))
