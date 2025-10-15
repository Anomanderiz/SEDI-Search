from shiny import App, ui, render, reactive
from parsers.sedi_weekly_pdf import parse_sedi_pdf
from matching.matcher import match_transactions_to_donors, Thresholds

app_title = "SEDI Insider Monitor"

# Global CSS include (file should be at www/styles.css)
page_head = ui.head_content(
    ui.tags.link(rel="stylesheet", href="styles.css")
)

page = ui.page_navbar(
    ui.nav_panel("Upload & Parse", ui.layout_columns(
        ui.card(
            # REMOVED: ui.tags.link(...) here
            ui.h3(app_title, class_='card-title'),
            ui.p("Upload a donor roster (CSV/XLSX) and the SEDI Weekly Summary PDF. Then click Parse."),
            ui.input_file("donor_file", "Donor roster (CSV or XLSX)", multiple=False, accept=[".csv", ".xlsx"], width="100%"),
            ui.input_file("sedi_pdf", "SEDI Weekly PDF", multiple=False, accept=[".pdf"], width="100%"),
            ui.input_action_button("parse", "Parse PDF & Match", class_="btn-primary"),
            class_="glass",
            title=app_title,    # ok to keep if you want a card header
            # REMOVED: head=page_head
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
            ui.markdown("""
This prototype parses the weekly SEDI PDF and performs fuzzy name matching against your donor roster.
- Uses `pdfplumber` for text extraction.
- Uses `rapidfuzz` for composite scoring with strong last-name weight.
- This is a starting point—parsing heuristics for transaction rows can be further improved.
"""),
            class_="glass",
        ),
        col_widths=(12,)
    )),
    title=app_title,
    head=page_head,   # ← moved here
)


# ---- Server ----

def server(input, output, session):
    donors_df = reactive.value(pd.DataFrame())
    transactions_df = reactive.value(pd.DataFrame())
    matches_df = reactive.value(pd.DataFrame())

    @reactive.event(input.parse)
    def _do_parse():
        # Donors
        dfile = input.donor_file()
        if not dfile:
            donors = pd.DataFrame(columns=['donor_id', 'name', 'aliases'])
        else:
            uf = dfile[0]
            content = uf.read()
            try:
                donors = pd.read_csv(io.BytesIO(content))
            except Exception:
                donors = pd.read_excel(io.BytesIO(content))
            if 'donor_id' not in donors.columns:
                donors['donor_id'] = donors.index.astype(str)
            if 'aliases' not in donors.columns:
                donors['aliases'] = ''
        donors_df.set(donors)

        # PDF
        pfile = input.sedi_pdf()
        if not pfile:
            tx = pd.DataFrame(columns=['tx_id','insider_name','issuer','relationship','date_tx','nature','security','qty_or_value'])
        else:
            uf = pfile[0]
            pdfbytes = uf.read()
            tx = parse_sedi_pdf(pdfbytes)
        transactions_df.set(tx)

        # Matching
        thr = Thresholds(high=input.thr_high(), review=input.thr_review())
        if not tx.empty and not donors.empty:
            matches = match_transactions_to_donors(tx, donors, 'config/titles.txt', 'config/nicknames.json', thr)
        else:
            matches = pd.DataFrame(columns=['tx_id','insider_name','donor_id','donor_name','score','status','issuer','date_tx'])
        matches_df.set(matches)

    @render.text
    def summary_text():
        d = donors_df()
        t = transactions_df()
        m = matches_df()
        if t.empty:
            return "Awaiting files."
        return f"Donors: {len(d)} | Transactions parsed: {len(t)} | Candidate matches: {len(m)}"

    @render.table
    def tbl_matches():
        m = matches_df()
        if m.empty:
            return pd.DataFrame()
        df = m.copy()
        if not input.show_low():
            df = df[df['status'] != 'low']
        cols = ['status','score','insider_name','donor_name','issuer','date_tx','nature','security','qty_or_value','tx_id']
        cols = [c for c in cols if c in df.columns]
        return df[cols].sort_values(['status','score'], ascending=[True, False])

app = App(page, server)
