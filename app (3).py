import streamlit as st
import pandas as pd
import io
import textwrap
from tabulate import tabulate
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection  # st-gsheets-connection
import xlsxwriter

st.set_page_config(layout="wide")
st.title("Booking Viewer (Google Sheets–Backed)")

# ─────────────────────────────────────────────────────────────────────────────
# 1) Establish GSheets connection
conn = st.connection("gsheets", type=GSheetsConnection)
# Reads your spreadsheet URL from st.secrets["connections"]["gsheets"]["spreadsheet"]

# ─────────────────────────────────────────────────────────────────────────────
# 2) Upload CSV and sync to Google Sheets
uploaded_file = st.file_uploader("Upload caretakers CSV file", type="csv")
if uploaded_file:
    try:
        df_upload = pd.read_csv(uploaded_file, encoding="latin-1")
        # Overwrite sheet with new data
        conn.update(worksheet="Sheet1", data=df_upload)
        st.success("CSV uploaded and Google Sheet updated!")
    except Exception as e:
        st.error(f"Upload failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 3) Read current bookings from Google Sheets
try:
    df = conn.read(worksheet="Sheet1")
except Exception as e:
    st.error(f"Error reading from Google Sheets: {e}")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Helper functions (unchanged from your original code)
def wrap_text(text, width=50):
    if isinstance(text, str):
        return "\n".join(textwrap.wrap(text, width=width))
    return text

def prepare_for_pdf(df, wrap_columns=None, wrap_width=50):
    df_copy = df.copy()
    if wrap_columns:
        for col in wrap_columns:
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(lambda x: wrap_text(x, width=wrap_width))
    return df_copy

def dataframe_to_excel(df):
    df = df.fillna("")
    col_widths = {
        'location': 7, 'sublocation': 7, 'time': 10,
        'type': 12, 'booker': 16, 'details': 30
    }
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Sheet1")
    fmt_hdr = workbook.add_format({'bold': True, 'text_wrap': True, 'border':1, 'align':'center', 'font_size':9})
    fmt_cell = workbook.add_format({'text_wrap': True, 'border':1, 'valign':'top', 'font_size':9})
    for c, h in enumerate(df.columns):
        worksheet.write(0, c, h, fmt_hdr)
        worksheet.set_column(c, c, col_widths.get(h.lower(), 12), fmt_cell)
    for r, row in enumerate(df.values, start=1):
        for c, val in enumerate(row):
            worksheet.write(r, c, val, fmt_cell)
    workbook.close()
    return output.getvalue()

def aggregate_bookings(df):
    expected = {"Fives":6,"3g-1":2,"3g-2":2,"Cameron Bank":2,"East (winter)":4,"South":3,
                "Muga":3,"Astro 1":2,"Astro 2":2,"Cricket Nets":4,"Track Lanes 1-4":4}
    rows=[]
    for d in sorted(df['date'].unique()):
        df_d = df[df['date']==d]
        for loc in sorted(df_d['location'].unique()):
            sub = df_d[df_d['location']==loc]
            agg = sub.groupby(['time','type','booker','details'], as_index=False).agg({
                'sublocation': lambda x: x.iloc[0] if x.nunique()==1 else
                    ("ALL" if expected.get(loc)==x.nunique() else ", ".join(sorted(x.unique())))
            })
            agg['location']=loc; agg['date']=d
            rows.append(agg[['date','location','sublocation','time','type','booker','details']])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=df.columns)

def highlight_rows(row):
    if row['type']=="Grounds-15":
        return ['background-color: #80D4ED']*len(row)
    if "(game)" in row['type']:
        return ['background-color: lightyellow']*len(row)
    return ['']*len(row)

def agggrass(df):
    thr_map={"3g-1":2,"3g-2":2,"Cameron Bank":2,"South":3}
    out=[]
    df = df.fillna({'details':""})
    for loc, grp in df.groupby("location", sort=False):
        if loc in thr_map:
            thr=thr_map[loc]
            agg = (grp.groupby(["date","time","type","booker","details"], as_index=False)
                      .agg({"sublocation": lambda x: "ALL" if len(x)==thr else ", ".join(sorted(x.unique()))}))
            agg["location"]=loc; out.append(agg)
        else:
            out.append(grp)
    return pd.concat(out, ignore_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# 4) Tabs: Daily Overview, Grass, Full Data, Edit Bookings
tabs = st.tabs(["Daily Overview", "Grass", "Full Processed Data", "Edit Bookings"])

# --- Daily Overview ---
with tabs[0]:
    st.header("Daily Overview")
    df_ex = df.iloc[:,23:30].copy()
    parts = df_ex.iloc[:,0].str.split(" - ", expand=True)
    parts.columns=['date','location']
    df_p = pd.concat([parts, df_ex.iloc[:,[3,2,4,5,6]].reset_index(drop=True)], axis=1)
    df_p.columns=['date','location','sublocation','time','type','booker','details']

    dates = sorted(df_p['date'].unique())
    sel_dates = st.multiselect("Dates", ["ALL"]+dates, default=["ALL"])
    if "ALL" in sel_dates: sel_dates=dates

    locs = sorted(df_p['location'].unique())
    sel_locs = st.multiselect("Locations", ["ALL"]+locs, default=["ALL"])
    if "ALL" in sel_locs: sel_locs=locs

    filt = df_p[df_p['date'].isin(sel_dates)&df_p['location'].isin(sel_locs)]
    if filt.empty:
        st.write("No bookings for these filters.")
    else:
        for d in sorted(filt['date'].unique()):
            st.subheader(f"Date: {d}")
            agg = aggregate_bookings(filt[filt['date']==d])
            for loc in sorted(agg['location'].unique()):
                st.subheader(f"Location: {loc}")
                disp = agg[agg['location']==loc][['sublocation','time','type','booker','details']]
                for _, r in disp.reset_index(drop=True).iterrows():
                    summary = (f"**Sublocation:** {r.sublocation} | **Time:** {r.time} | "
                               f"**Type:** {r.type} | **Booker:** {r.booker}")
                    with st.expander(summary):
                        st.write(f"**Details:** {r.details}")
        # Excel Download only
        st.download_button(
            "Download Daily Overview (Excel)",
            data=dataframe_to_excel(pd.concat([aggregate_bookings(filt[filt['date']==d]).assign(date=d) 
                                                for d in filt['date'].unique()]),),
            file_name="daily_overview.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- Grass Weekly Overview ---
with tabs[1]:
    st.header("Grass Weekly Overview")
    grass_locs = ["East (summer)","East (winter)","Cameron Bank","South","3g-1","3g-2"]
    df_ex = df.iloc[:,23:30].copy()
    parts = df_ex.iloc[:,0].str.split(" - ", expand=True)
    parts.columns=['date','location']
    df_g = pd.concat([parts, df_ex.iloc[:,[3,2,4,5,6]].reset_index(drop=True)], axis=1)
    df_g.columns=['date','location','sublocation','time','type','booker','details']
    df_g = df_g[df_g['location'].isin(grass_locs)]

    if df_g.empty:
        st.write("No grass bookings.")
    else:
        act_src={}
        for loc in grass_locs:
            grp = df_g[df_g['location']==loc]
            if loc in ["3g-1","3g-2"]: act_src[loc]=grp
            with st.expander(f"{loc} Bookings"):
                df_show = agggrass(grp) if loc in ["3g-1","3g-2","Cameron Bank","South"] else grp
                st.dataframe(df_show.reset_index(drop=True).style.apply(highlight_rows, axis=1))
        st.subheader("3G Pitches: Activity Begins")
        c1, c2 = st.columns(2)
        for col, loc in zip((c1,c2), ["3g-1","3g-2"]):
            with col:
                src = act_src.get(loc)
                if src is not None:
                    with st.expander(f"{loc} Activity Begins"):
                        tmp = src.copy()
                        tmp["start_time"] = tmp["time"].str.split(" to ").str[0]
                        act = tmp.groupby("date", as_index=False)["start_time"].min().rename(columns={"start_time":"activity begins"})
                        st.dataframe(act)

# --- Full Processed Data ---
with tabs[2]:
    st.header("Full Processed Data")
    df_ex = df.iloc[:,23:30].copy()
    parts = df_ex.iloc[:,0].str.split(" - ", expand=True)
    parts.columns=['date','location']
    full = pd.concat([parts, df_ex.iloc[:,[3,2,4,5,6]].reset_index(drop=True)], axis=1)
    full.columns=['date','location','sublocation','time','type','booker','details']
    st.dataframe(full)
    st.download_button(
        "Download Full Data (Excel)",
        data=dataframe_to_excel(full),
        file_name="full_processed_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- Edit Bookings (new tab) ---
with tabs[3]:
    st.header("Edit Bookings")
    edited = st.data_editor(df, num_rows="dynamic")
    if st.button("Save Changes to Google Sheet"):
        conn.update(worksheet="Sheet1", data=edited)
        st.success("Google Sheet updated with your edits!")
