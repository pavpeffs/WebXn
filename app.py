import streamlit as st
import pandas as pd
import io
import textwrap
from fpdf import FPDF
from tabulate import tabulate
import xlsxwriter  # Ensure this is installed

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
    Converts a Pandas DataFrame into a PDF.
    Uses tabulate to produce a grid-formatted, monospaced table string.
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
    Each cell gets a border and text wrapping.
    The font size is set to 9.
    The columns are given fixed widths (in character units) as follows:
       location: 7, sublocation: 7, time: 10, type: 12, booker: 16, details: 30.
    This function handles a single-sheet export.
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
        'bold': True,
        'text_wrap': True,
        'border': 1,
        'align': 'center',
        'font_size': 9
    })
    cell_format = workbook.add_format({
        'text_wrap': True,
        'border': 1,
        'valign': 'top',
        'font_size': 9
    })
    
    for col_num, header in enumerate(df.columns):
        worksheet.write(0, col_num, header, header_format)
        width = col_widths.get(header.lower(), 12)
        worksheet.set_column(col_num, col_num, width, cell_format)
    
    for row_num, row_data in enumerate(df.values, start=1):
        for col_num, cell_value in enumerate(row_data):
            worksheet.write(row_num, col_num, cell_value, cell_format)
    
    workbook.close()
    processed_data = output.getvalue()
    return processed_data

def export_aggregated_excel_by_date(aggregated_all):
    """
    Exports aggregated data (which contains a 'date' column) to an Excel workbook
    with a separate worksheet for each unique date. The 'date' column is dropped in the export.
    """
    output = io.BytesIO()
    col_widths = {
        'location': 7,
        'sublocation': 7,
        'time': 10,
        'type': 12,
        'booker': 16,
        'details': 30
    }
    workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'nan_inf_to_errors': True})
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'border': 1,
        'align': 'center',
        'font_size': 9
    })
    cell_format = workbook.add_format({
        'text_wrap': True,
        'border': 1,
        'valign': 'top',
        'font_size': 9
    })
    unique_dates = aggregated_all['date'].unique()
    for d in unique_dates:
        # Subset for this date and drop the 'date' column
        sheet_data = aggregated_all[aggregated_all['date'] == d]
        sheet_data = sheet_data[['location','sublocation','time','type','booker','details']]
        sheet_name = str(d)[:31]  # Sheet name max 31 characters
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
    For the filtered DataFrame (for a given date) and location, group rows by 
    time, type, booker, and details.
    If multiple rows differ only in sublocation, check:
      - If there is only one unique sublocation, display it.
      - If there are multiple sublocations, return "ALL" if the number
        of unique sublocations equals the expected count for the location.
      - Otherwise, compile and list the unique sublocations as a comma-separated string.
    Returns an aggregated DataFrame with columns:
      [date, location, sublocation, time, type, booker, details]
    """
    # Define expected sublocation counts for each location, as provided.
    expected_sub_count = {
        "Fives": 6,
        "3g-1": 2,
        "3g-2": 2,
        "Cameron Bank": 2,
        "East (winter)": 4,
        "South": 3
    }

    aggregated_rows = []
    # Process each location within each date.
    for d in sorted(df['date'].unique()):
        df_date = df[df['date'] == d]
        for loc in sorted(df_date['location'].unique()):
            sub_df = df_date[df_date['location'] == loc]
            agg = sub_df.groupby(['time', 'type', 'booker', 'details'], as_index=False).agg({
                'sublocation': lambda x: (x.iloc[0] if x.nunique() == 1 
                                          else ("ALL" if (expected_sub_count.get(loc) is not None 
                                                         and x.nunique() == expected_sub_count[loc])
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

#########################################################
# Main App
#########################################################

st.title("Booking Viewer")

# -- Upload and Process CSV --
# (Using 'latin-1' decoding as needed)
uploaded_file = st.file_uploader("Upload your caretakers CSV file", type="csv")

if uploaded_file is not None:
    try:
        df = pd.read_csv(io.StringIO(uploaded_file.getvalue().decode('latin-1')), header=None)
        
        # Extract columns 24 to 30 (Python indices 23 to 29)
        df_extract = df.iloc[:, 23:30].copy()
        
        # Split the first column (which contains "[date] - [booking location]") into two.
        split_col = df_extract.iloc[:, 0].str.split(' - ', expand=True)
        split_col.columns = ['date', 'location']
        
        # Rearranging: date, location, sublocation, time, type, booker, details.
        df_processed = pd.concat([split_col,
                                  df_extract.iloc[:, [3, 2, 4, 5, 6]].reset_index(drop=True)], axis=1)
        df_processed.columns = ['date','location','sublocation','time','type','booker','details']
        
        # -- Sidebar Filters for Daily Overview & Full Processed Data --
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
        
        # -- Tabs --
        # Tab order: Daily Overview, Grass, then Full Processed Data.
        tabs = st.tabs(["Daily Overview", "Grass", "Full Processed Data"])
        
        ##########################
        # Daily Overview Tab
        ##########################
        with tabs[0]:
            st.header("Daily Overview")
            if filtered_df.empty:
                st.write("No bookings found for the selected criteria.")
            else:
                agg_list = []
                # Group by date and aggregate bookings.
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
                    # For export, drop the 'date' column as it's not needed.
                    aggregated_export = aggregated_all.drop(columns=["date"])
                    
                    st.markdown("### Export Daily Overview Data")
                    # Excel export: if more than one date is selected, export multi-sheet;
                    # otherwise, export a single sheet.
                    if len(selected_dates) > 1:
                        excel_daily = export_aggregated_excel_by_date(aggregated_all)
                    else:
                        excel_daily = dataframe_to_excel(aggregated_export)
                    st.download_button(
                        label="Download Daily Overview as Excel",
                        data=excel_daily,
                        file_name="daily_overview.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    # PDF export: if more than one date is selected, provide a separate download button for each date.
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
        
        ##########################
        # Grass Tab
        ##########################
        with tabs[1]:
            st.header("Grass Weekly Overview")
            # Fixed list of Grass locations.
            grass_locations = ["East (summer)", "South", "East (winter)", "3g-1", "3g-2", "Cameron Bank"]
            df_grass = df_processed[df_processed['location'].isin(grass_locations)]
            df_grass = df_grass.sort_values(by=['location','sublocation','date','time','type','booker'])
            if df_grass.empty:
                st.write("No bookings found for the Grass locations in this file.")
            else:
                for loc in grass_locations:
                    group_df = df_grass[df_grass['location'] == loc]
                    if not group_df.empty:
                        st.subheader(f"Location: {loc}")
                        display_df = group_df[['sublocation','date','time','type','booker','details']]
                        st.dataframe(display_df.reset_index(drop=True))
                        if loc in ["3g-1", "3g-2"]:
                            st.subheader(f"{loc} Activity Begins")
                            df_loc = group_df.copy()
                            df_loc["start_time"] = df_loc["time"].str.split(" to ").str[0]
                            activity_df = df_loc.groupby("date", as_index=False)["start_time"].min()
                            activity_df.rename(columns={"start_time": "activity begins"}, inplace=True)
                            st.dataframe(activity_df)
                    else:
                        st.write(f"No bookings for Location: {loc}")
        
        ##########################
        # Full Processed Data Tab
        ##########################
        with tabs[2]:
            st.header("Full Processed Data")
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
            
    except Exception as e:
        st.error(f"Error processing CSV file: {e}")
else:
    st.info("Awaiting CSV file upload.")
