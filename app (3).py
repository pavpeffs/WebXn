import streamlit as st
import pandas as pd
import io
import textwrap
from fpdf import FPDF
from tabulate import tabulate
import xlsxwriter  # Ensure this is installed
import os
import uuid
import streamlit.components.v1 as components
from datetime import date  # To get today's date for the download filename

# Set up an ephemeral shared file folder (stored locally on the app)
SHARED_FOLDER = "shared_csvs"
if not os.path.exists(SHARED_FOLDER):
    os.makedirs(SHARED_FOLDER)


#########################################################
# Helper Functions
#########################################################

def wrap_text(text, width=50):
    """Wrap text using newlines at the given width."""
    if isinstance(text, str):
        return "\n".join(textwrap.wrap(text, width=width))
    return text

def prepare_for_pdf(df, wrap_columns=None, wrap_width=50):
    """Apply text wrapping to specified columns of a DataFrame."""
    df_copy = df.copy()
    if wrap_columns:
        for col in wrap_columns:
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(lambda x: wrap_text(x, width=wrap_width))
    return df_copy

def dataframe_to_pdf(df, title="Table"):
    """
    Converts a Pandas DataFrame into a PDF using a monospaced grid.
    """
    table_str = tabulate(df, headers="keys", tablefmt="grid", showindex=False)
    pdf = FPDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Courier", size=10)
    pdf.cell(0, 10, txt=title, ln=True, align="C")
    pdf.ln(5)
    pdf.multi_cell(0, 5, table_str)
    return pdf.output(dest='S').encode('latin1')

def dataframe_to_excel(df):
    """
    Converts a DataFrame to an Excel file using xlsxwriter.
    """
    df = df.fillna("")
    col_widths = {
        'location': 7,
        'sublocation': 7,
        'time': 10,
        'type': 12,
        'booker': 16,
        'details': 30
    }
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'nan_inf_to_errors': True})
    worksheet = workbook.add_worksheet("Sheet1")
    header_format = workbook.add_format({
        'bold': True, 'text_wrap': True, 'border': 1,
        'align': 'center', 'font_size': 9
    })
    cell_format = workbook.add_format({
        'text_wrap': True, 'border': 1, 'valign': 'top', 'font_size': 9
    })
    for col_num, header in enumerate(df.columns):
        worksheet.write(0, col_num, header, header_format)
        width = col_widths.get(header.lower(), 12)
        worksheet.set_column(col_num, col_num, width, cell_format)
    for row_num, row_data in enumerate(df.values, start=1):
        for col_num, cell_value in enumerate(row_data):
            worksheet.write(row_num, col_num, cell_value, cell_format)
    workbook.close()
    return output.getvalue()

def export_aggregated_excel_by_date(aggregated_all):
    """
    Exports aggregated data (with a 'date' column) to an Excel workbook,
    each unique date getting its own worksheet.
    """
    output = io.BytesIO()
    col_widths = {
        'location': 7, 'sublocation': 7, 'time': 10,
        'type': 12, 'booker': 16, 'details': 30
    }
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'nan_inf_to_errors': True})
    header_format = workbook.add_format({
        'bold': True, 'text_wrap': True, 'border': 1,
        'align': 'center', 'font_size': 9
    })
    cell_format = workbook.add_format({
        'text_wrap': True, 'border': 1, 'valign': 'top', 'font_size': 9
    })
    unique_dates = aggregated_all['date'].unique()
    for d in unique_dates:
        sheet_data = aggregated_all[aggregated_all['date'] == d]
        sheet_data = sheet_data[['location','sublocation','time','type','booker','details']]
        sheet_name = str(d)[:31]
        worksheet = workbook.add_worksheet(sheet_name)
        for col_num, header in enumerate(sheet_data.columns):
            worksheet.write(0, col_num, header, header_format)
            width = col_widths.get(header.lower(), 12)
            worksheet.set_column(col_num, col_num, width, cell_format)
        for row_num, row in enumerate(sheet_data.values, start=1):
            for col_num, cell in enumerate(row):
                worksheet.write(row_num, col_num, cell, cell_format)
    workbook.close()
    return output.getvalue()

def aggregate_bookings(df):
    """
    Groups bookings by time, type, booker, and details.
    Returns an aggregated DataFrame with columns:
    [date, location, sublocation, time, type, booker, details].
    """
    expected_sub_count = {
        "Fives": 6, "3g-1": 2, "3g-2": 2,
        "Cameron Bank": 2, "East (winter)": 4, "South": 3,
        "Muga": 3, "Astro 1": 2, "Astro 2": 2, "Cricket Nets": 4, "Track Lanes 1-4": 4
    }
    aggregated_rows = []
    for d in sorted(df['date'].unique()):
        df_date = df[df['date'] == d]
        for loc in sorted(df_date['location'].unique()):
            sub_df = df_date[df_date['location'] == loc]
            agg = sub_df.groupby(['time', 'type', 'booker', 'details'], as_index=False).agg({
                'sublocation': lambda x: (x.iloc[0] if x.nunique() == 1
                                          else ("ALL" if (expected_sub_count.get(loc) is not None and x.nunique() == expected_sub_count[loc])
                                                else ", ".join(sorted(x.unique()))))
            })
            agg['location'] = loc
            agg['date'] = d
            agg = agg[['date', 'location', 'sublocation', 'time', 'type', 'booker', 'details']]
            aggregated_rows.append(agg)
    if aggregated_rows:
        return pd.concat(aggregated_rows, ignore_index=True)
    else:
        return pd.DataFrame(columns=['date', 'location', 'sublocation', 'time', 'type', 'booker', 'details'])

def highlight_rows(row):
    # Priority: if type is exactly "Grounds-15", use blue; else, if it contains "(game)", use yellow.
    if row['type'] == "Grounds-15":
        return ['background-color: #80D4ED'] * len(row)
    elif "(game)" in row['type']:
        return ['background-color: lightyellow'] * len(row)
    else:
        return [''] * len(row)

def agggrass(df):
    """
    Condense rows for specific locations:
    - "3g-1", "3g-2", "Cameron Bank": merge when exactly 2 matching rows → sublocation = "ALL"
    - "South": merge when exactly 3 matching rows → sublocation = "ALL"
    Always include rows even if details are empty.
    """
    thresholds = {"3g-1": 2, "3g-2": 2, "Cameron Bank": 2, "South": 3}
    out = []

    # Make sure empty details (or any column) aren’t dropped by groupby
    df = df.fillna({'date':'', 'time':'', 'type':'', 'booker':'', 'details':''})

    for loc, group in df.groupby("location", sort=False):
        if loc in thresholds:
            thr = thresholds[loc]
            # group by all _other_ columns
            agg = (
                group
                .groupby(["date", "time", "type", "booker", "details"], as_index=False)
                .agg({"sublocation": lambda x: "ALL" if len(x) == thr else ", ".join(sorted(x.unique()))})
            )
            agg["location"] = loc
            out.append(agg[["date","location","sublocation","time","type","booker","details"]])
        else:
            # no condensation
            out.append(group[["date","location","sublocation","time","type","booker","details"]])

    return pd.concat(out, ignore_index=True)

#########################################################
# Main App
#########################################################

st.title("Booking Viewer")

# ---------------------------------------------
# Share Code Input for Recipients
# ---------------------------------------------
share_code_input = st.text_input("Enter Share Code (if you have one) to load a shared CSV file:")

csv_data_from_shared_code = None
if share_code_input:
    shared_file_path = os.path.join(SHARED_FOLDER, share_code_input + ".csv")
    if os.path.exists(shared_file_path):
        try:
            with open(shared_file_path, "r", encoding="latin-1") as f:
                csv_data_from_shared_code = f.read()
            st.success("CSV file loaded from share code.")
        except Exception as e:
            st.error(f"Error reading CSV file from share code: {e}")
    else:
        st.error("The shared CSV file was not found. It may have expired. Please ask for a new share code.")

# ---------------------------------------------
# CSV Upload or Shared CSV Loading
# ---------------------------------------------
csv_data = None
if csv_data_from_shared_code:
    csv_data = csv_data_from_shared_code
else:
    uploaded_file = st.file_uploader("Upload your caretakers CSV file", type="csv")
    if uploaded_file is not None:
        try:
            csv_data = uploaded_file.getvalue().decode('latin-1')
        except Exception as e:
            st.error(f"Error processing CSV file: {e}")
            csv_data = None

if csv_data:
    try:
        df = pd.read_csv(io.StringIO(csv_data), header=None)
    except Exception as e:
        st.error(f"Error processing CSV data: {e}")
        df = None
else:
    df = None

# ---------------------------------------------
# Create Tabs for the App Content
# ---------------------------------------------
tabs = st.tabs(["Daily Overview", "Grass", "Full Processed Data", "Sharing"])

# Daily Overview Tab
with tabs[0]:
    st.header("Daily Overview")
    if df is None:
        st.info("No CSV loaded.")
    else:
        # Process for Daily Overview
        df_extract = df.iloc[:, 23:30].copy()
        split_col = df_extract.iloc[:, 0].str.split(' - ', expand=True)
        split_col.columns = ['date', 'location']
        df_processed = pd.concat([split_col,
                                  df_extract.iloc[:, [3, 2, 4, 5, 6]].reset_index(drop=True)], axis=1)
        df_processed.columns = ['date', 'location', 'sublocation', 'time', 'type', 'booker', 'details']
        # Add filter selections from sidebar
        date_options = sorted(df_processed['date'].unique())
        options_for_dates = ["ALL"] + date_options
        selected_dates = st.sidebar.multiselect("Select Date(s)", options=options_for_dates, default=["ALL"])
        if "ALL" in selected_dates or not selected_dates:
            selected_dates = date_options

        location_options = sorted(df_processed['location'].unique())
        options_for_locations = ["ALL"] + location_options
        selected_locations = st.sidebar.multiselect("Select Location(s)", options=options_for_locations, default=["ALL"])
        if "ALL" in selected_locations or not selected_locations:
            selected_locations = location_options

        filtered_df = df_processed[
            (df_processed['date'].isin(selected_dates)) &
            (df_processed['location'].isin(selected_locations))
        ]
        
        if filtered_df.empty:
            st.write("No bookings found for the selected criteria.")
        else:
            agg_list = []
            for d in sorted(filtered_df['date'].unique()):
                st.subheader(f"Date: {d}")
                data_for_date = filtered_df[filtered_df['date'] == d]
                aggregated_df = aggregate_bookings(data_for_date)
                agg_list.append(aggregated_df)
                for loc in sorted(aggregated_df['location'].unique()):
                    st.subheader(f"Location: {loc}")
                    group_df = aggregated_df[aggregated_df['location'] == loc].reset_index(drop=True)
                    display_df = group_df[['sublocation','time','type','booker','details']]
                    for idx, row in display_df.iterrows():
                        summary = (f"**Sublocation:** {row['sublocation']} | "
                                   f"**Time:** {row['time']} | "
                                   f"**Type:** {row['type']} | "
                                   f"**Booker:** {row['booker']}")
                        with st.expander(summary):
                            st.write(f"**Details:** {row['details']}")
            if agg_list:
                aggregated_all = pd.concat(agg_list, ignore_index=True)
                aggregated_export = aggregated_all.drop(columns=["date"])
                st.markdown("### Export Daily Overview Data")
                if len(filtered_df['date'].unique()) > 1:
                    excel_daily = export_aggregated_excel_by_date(aggregated_all)
                else:
                    excel_daily = dataframe_to_excel(aggregated_export)
                st.download_button(
                    label="Download Daily Overview as Excel",
                    data=excel_daily,
                    file_name="daily_overview.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                unique_export_dates = aggregated_all['date'].unique()
                if len(unique_export_dates) > 1:
                    for d in unique_export_dates:
                        pdf_df = aggregated_all[aggregated_all['date'] == d].drop(columns=["date"])
                        pdf_data = dataframe_to_pdf(prepare_for_pdf(pdf_df, wrap_columns=['details'], wrap_width=50),
                                                    title=f"Daily Overview for {d}")
                        st.download_button(
                            label=f"Download Daily Overview PDF for {d}",
                            data=pdf_data,
                            file_name=f"daily_overview_{d}.pdf",
                            mime="application/pdf"
                        )
                else:
                    pdf_df = aggregated_export
                    pdf_data = dataframe_to_pdf(prepare_for_pdf(pdf_df, wrap_columns=['details'], wrap_width=50),
                                                title="Daily Overview")
                    st.download_button(
                        label="Download Daily Overview as PDF",
                        data=pdf_data,
                        file_name="daily_overview.pdf",
                        mime="application/pdf"
                    )

# Grass Tab
# (keep your existing highlight_rows and agggrass definitions)
with tabs[1]:
    st.header("Grass Weekly Overview")
    if df is None:
        st.info("No CSV loaded.")
    else:
        # 1) Prepare DataFrame
        grass_locations = ["East (summer)", "East (winter)", "Cameron Bank", "South", "3g-1", "3g-2"]
        df_extract = df.iloc[:, 23:30].copy()
        split_col = df_extract.iloc[:, 0].str.split(" - ", expand=True)
        split_col.columns = ["date", "location"]
        df_processed = pd.concat([
            split_col,
            df_extract.iloc[:, [3,2,4,5,6]].reset_index(drop=True)
        ], axis=1)
        df_processed.columns = ["date","location","sublocation","time","type","booker","details"]
        df_processed["details"] = df_processed["details"].fillna("")

        df_grass = df_processed[df_processed["location"].isin(grass_locations)]
        df_grass = df_grass.sort_values(
            by=["location","sublocation","date","time","type","booker"],
            ignore_index=True
        )

        if df_grass.empty:
            st.write("No bookings found for the Grass locations in this file.")
        else:
            # 2) Display each location’s bookings (no Activity Begins here for 3g)
            activity_sources = {}
            for loc in grass_locations:
                grp = df_grass[df_grass["location"] == loc]
                if grp.empty:
                    st.write(f"No bookings for Location: {loc}")
                    continue
            
                # stash 3g data aside as before…
                if loc in ["3g-1", "3g-2"]:
                    activity_sources[loc] = grp.copy()
            
                with st.expander(f"Location: {loc} Bookings"):
                    if loc in ["3g-1", "3g-2", "Cameron Bank", "South"]:
                        df_to_show = agggrass(grp)
                    else:
                        df_to_show = grp
                    
                    # **Drop 'location' here**
                    display_df = df_to_show[["date", "sublocation", "time", "type", "booker", "details"]]
                    styled = display_df.reset_index(drop=True).style.apply(highlight_rows, axis=1)
                    st.dataframe(styled)
                    
            # 3) Side-by-side collapsible 3G Activity Begins
            st.subheader("3G Pitches: Activity Begins")
            col1, col2 = st.columns(2)
            for column, loc in zip((col1, col2), ["3g-1", "3g-2"]):
                with column:
                    src = activity_sources.get(loc)
                    if src is not None:
                        with st.expander(f"{loc} Activity Begins"):
                            tmp = src.copy()
                            tmp["start_time"] = tmp["time"].str.split(" to ").str[0]
                            act = (
                                tmp
                                .groupby("date", as_index=False)["start_time"]
                                .min()
                                .rename(columns={"start_time":"activity begins"})
                            )
                            # shorter height to compress rows
                            st.dataframe(act.reset_index(drop=True), height=200)
                    else:
                        st.write(f"No data for {loc}")

if not df_grass.empty:
    # ensure dates are datetimes
    df_grass["date"] = pd.to_datetime(df_grass["date"], dayfirst=True)
    earliest = df_grass["date"].min()

    if earliest.weekday() != 0:
        st.error(f"Earliest date {earliest.strftime('%A %d/%m/%Y')} is not a Monday.")
    else:
        monday = earliest
        week_dates = [monday + timedelta(days=i) for i in range(7)]

        # 3G activity‑starts per day
        activity = {}
        for loc in ["3g-1", "3g-2"]:
            grp = df_grass[df_grass["location"] == loc].copy()
            if not grp.empty:
                grp["start_time"] = grp["time"].str.split(" to ").str[0]
                act = grp.groupby("date", as_index=False)["start_time"].min()
                activity[loc] = dict(zip(act["date"], act["start_time"]))

        # pitch mappings
        pitch_mappings = [
            ("East (winter)", "Pitch 1",  "East 1"),
            ("East (winter)", "Pitch 2",  "East 2"),
            ("East (winter)", "Pitch 3",  "East 3"),
            ("East (winter)", "Training", "East Training"),
            ("East (summer)", "Pitch 1",  "Cricket"),
            ("South",         "S 1",       "South 1"),
            ("South",         "S 2",       "South 2"),
            ("South",         "S 3",       "South 3"),
            ("Cameron Bank",  "C B 1",     "CB1"),
            ("Cameron Bank",  "C B 2",     "CB2"),
        ]
        pitch_names = [m[2] for m in pitch_mappings] + ["3g-1", "3g-2"]

        # Build the Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            wb = writer.book
            ws = wb.add_worksheet("AutoGS")
            writer.sheets["AutoGS"] = ws

            # Formats
            date_fmt = wb.add_format({
                "num_format": "dddd\n dd/mm/yyyy",
                "align": "center", "valign": "vcenter", "text_wrap": True
            })
            cell_fmt = wb.add_format({
                "align": "center", "valign": "vcenter", "text_wrap": True
            })

            # 1) Date headers (B1→H1)
            for col, dt in enumerate(week_dates, start=1):
                ws.write_datetime(0, col, dt, date_fmt)

            # 2) Pitch names down column A (A2→A13)
            for row, name in enumerate(pitch_names, start=1):
                ws.write(row, 0, name, cell_fmt)

            # 3) Fill in bookings / activity
            for row_idx, name in enumerate(pitch_names, start=1):
                for col_idx, dt in enumerate(week_dates, start=1):
                    if name in ["3g-1", "3g-2"]:
                        t = activity.get(name, {}).get(dt)
                        cell = f"Activity starts {t}" if t else ""
                    else:
                        loc, subloc, _ = next(m for m in pitch_mappings if m[2] == name)
                        bookings = df_grass[
                            (df_grass["location"] == loc) &
                            (df_grass["sublocation"] == subloc) &
                            (df_grass["date"] == dt)
                        ]
                        lines = []
                        for _, r in bookings.iterrows():
                            start, end = r["time"].split(" to ")
                            tm = f"{start.replace(':','')}-{end.replace(':','')}"
                            lines.append(f"{r['details']}\n{tm}")
                        cell = "\n".join(lines)
                    ws.write(row_idx, col_idx, cell, cell_fmt)

        output.seek(0)
        # 4) Single button that generates & downloads
        st.download_button(
            label="Launch AutoGS",
            data=output.getvalue(),
            file_name=f"AutoGS_{monday.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.error("No grass bookings to process.")


# Full Processed Data Tab
with tabs[2]:
    st.header("Full Processed Data")
    if df is None:
        st.info("No CSV loaded.")
    else:
        df_extract = df.iloc[:, 23:30].copy()
        split_col = df_extract.iloc[:, 0].str.split(' - ', expand=True)
        split_col.columns = ['date', 'location']
        df_processed = pd.concat([split_col,
                                  df_extract.iloc[:, [3, 2, 4, 5, 6]].reset_index(drop=True)], axis=1)
        df_processed.columns = ['date', 'location', 'sublocation', 'time', 'type', 'booker', 'details']
        st.dataframe(df_processed.reset_index(drop=True))
        excel_full = dataframe_to_excel(df_processed)
        st.download_button(
            label="Download Full Processed Data as Excel",
            data=excel_full,
            file_name="full_processed_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        pdf_full = dataframe_to_pdf(prepare_for_pdf(df_processed, wrap_columns=['details'], wrap_width=50),
                                    title="Full Processed Data")
        st.download_button(
            label="Download Full Processed Data as PDF",
            data=pdf_full,
            file_name="full_processed_data.pdf",
            mime="application/pdf"
        )

# Sharing Tab
with tabs[3]:
    st.header("Sharing Facilities")
    if df is None:
        st.warning("Please upload a CSV file first to enable sharing.")
    else:
        st.subheader("Generate Shareable Code")
        if st.button("Generate Shareable Code"):
            try:
                unique_id = str(uuid.uuid4())
                file_path = os.path.join(SHARED_FOLDER, unique_id + ".csv")
                with open(file_path, "w", encoding="latin-1") as f:
                    f.write(csv_data)
                st.info("CSV shared successfully!")
                # Create an HTML/JS block for the share code with a copy-to-clipboard button.
                copy_button_html = f"""
                <div style="display: flex; align-items: center;">
                    <input type="text" id="share_code_input" value="{unique_id}" readonly style="width: 400px; margin-right: 10px;"/>
                    <button onclick="copyCode()">Copy to Clipboard</button>
                </div>
                <script>
                function copyCode() {{
                    var copyText = document.getElementById('share_code_input');
                    copyText.select();
                    copyText.setSelectionRange(0, 99999); // For mobile devices
                    navigator.clipboard.writeText(copyText.value).then(function() {{
                        alert('Code copied to clipboard!');
                    }}, function(err) {{
                        alert('Error copying: ' + err);
                    }});
                }}
                </script>
                """
                components.html(copy_button_html, height=100)
            except Exception as e:
                st.error(f"Error generating shareable code: {e}")
        # If a CSV was loaded via share code, offer a download button.
        if csv_data_from_shared_code:
            st.subheader("Download Shared CSV File")
            today = date.today().strftime("%Y-%m-%d")
            st.download_button(
                label="Download Shared CSV",
                data=csv_data_from_shared_code,
                file_name=f"webifyXn-sharedfile-{today}.csv",
                mime="text/csv"
            )
