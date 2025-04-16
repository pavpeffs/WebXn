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
        "Muga": 3, "Astro 1": 2, "Astro 2": 2
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

def merge_rows_by_sublocations(df_location, expected_sublocations):
    """
    Group bookings such that rows are combined only if every column
    except 'sublocation' is identical. The function aggregates the unique 
    sublocations for each group. If the count matches the expected number 
    for that location, then the sublocation is set to "ALL"; otherwise, 
    a comma-separated list of sublocations is returned.
    """
    # Group by every column except 'sublocation'
    group_cols = ['date', 'location', 'time', 'type', 'booker', 'details']
    grouped = df_location.groupby(group_cols, as_index=False)['sublocation'].agg(lambda x: sorted(set(x)))
    
    def process_sublocations(row):
        loc = row['location']
        sublocs = row['sublocation']
        if loc in expected_sublocations and len(sublocs) == expected_sublocations[loc]:
            return "ALL"
        else:
            return ", ".join(sublocs)
    
    grouped['sublocation'] = grouped.apply(process_sublocations, axis=1)
    return grouped

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
with tabs[1]:
    st.header("Grass Weekly Overview")
    if df is None:
        st.info("No CSV loaded.")
    else:
        # Updated order of locations
        grass_locations = ["East (summer)", "East (winter)", "Cameron Bank", "South", "3g-1", "3g-2"]
        df_extract = df.iloc[:, 23:30].copy()
        split_col = df_extract.iloc[:, 0].str.split(' - ', expand=True)
        split_col.columns = ['date', 'location']
        df_processed = pd.concat([split_col,
                                  df_extract.iloc[:, [3, 2, 4, 5, 6]].reset_index(drop=True)], axis=1)
        df_processed.columns = ['date', 'location', 'sublocation', 'time', 'type', 'booker', 'details']
        df_grass = df_processed[df_processed['location'].isin(grass_locations)]
        df_grass = df_grass.sort_values(by=['location', 'sublocation', 'date', 'time', 'type', 'booker'])
        
        if df_grass.empty:
            st.write("No bookings found for the Grass locations in this file.")
        else:
            for loc in grass_locations:
                group_df = df_grass[df_grass['location'] == loc]
                if not group_df.empty:
                    # For 3g-1 and 3g-2, show the Activity Begins table first in an expander.
                    if loc in ["3g-1", "3g-2"]:
                        with st.expander(f"{loc} Activity Begins"):
                            df_loc = group_df.copy()
                            df_loc["start_time"] = df_loc["time"].str.split(" to ").str[0]
                            activity_df = df_loc.groupby("date", as_index=False)["start_time"].min()
                            activity_df.rename(columns={"start_time": "activity begins"}, inplace=True)
                            st.dataframe(activity_df.reset_index(drop=True))
                    
                    # Merge rows using the grouping function defined above.
                    merged_df = merge_rows_by_sublocations(group_df, expected_sublocations)
                    with st.expander(f"Location: {loc} Bookings"):
                        display_df = merged_df[['sublocation', 'date', 'time', 'type', 'booker', 'details']]
                        styled_df = display_df.reset_index(drop=True).style.apply(highlight_rows, axis=1)
                        st.dataframe(styled_df)
                else:
                    st.write(f"No bookings for Location: {loc}")


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
