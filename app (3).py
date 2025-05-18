import streamlit as st
import pandas as pd
import io
import xlsxwriter  # Ensure this is installed
import os
import uuid
import streamlit.components.v1 as components
from datetime import date, timedelta

# Set up an ephemeral shared file folder (stored locally on the app)
SHARED_FOLDER = "shared_csvs"
os.makedirs(SHARED_FOLDER, exist_ok=True)

today_date = date.today().strftime('%d.%m.%Y')

#########################################################
# Helper Functions
#########################################################

def dataframe_to_excel(df):
    df = df.fillna("")
    col_widths = {'location':7,'sublocation':7,'time':10,'type':12,'booker':16,'details':30}
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory':True,'nan_inf_to_errors':True})
    worksheet = workbook.add_worksheet("Sheet1")
    header_fmt = workbook.add_format({'bold':True,'text_wrap':True,'border':1,'align':'center','font_size':9})
    cell_fmt = workbook.add_format({'text_wrap':True,'border':1,'valign':'top','font_size':9})
    for i, col in enumerate(df.columns):
        worksheet.write(0, i, col, header_fmt)
        worksheet.set_column(i, i, col_widths.get(col.lower(),12), cell_fmt)
    for r, row in enumerate(df.values, start=1):
        for c, val in enumerate(row):
            worksheet.write(r, c, val, cell_fmt)
    workbook.close()
    return output.getvalue()


def export_aggregated_excel_by_date(all_df):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory':True,'nan_inf_to_errors':True})
    header_fmt = workbook.add_format({'bold':True,'text_wrap':True,'border':1,'align':'center','font_size':9})
    cell_fmt = workbook.add_format({'text_wrap':True,'border':1,'valign':'top','font_size':9})
    for d in sorted(all_df['date'].unique()):
        ws = workbook.add_worksheet(d.strftime('%d.%m.%Y')[:31])
        sub = all_df[all_df['date']==d][['location','sublocation','time','type','booker','details']]
        for i, col in enumerate(sub.columns):
            ws.write(0, i, col, header_fmt)
            ws.set_column(i, i, {'location':7,'sublocation':7,'time':10,'type':12,'booker':16,'details':30}.get(col.lower(),12), cell_fmt)
        for r, row in enumerate(sub.values, start=1):
            for c, val in enumerate(row): ws.write(r, c, val, cell_fmt)
    workbook.close()
    return output.getvalue()


def aggregate_bookings(df):
    expected = {"Fives":6,"3g-1":2,"3g-2":2,"Cameron Bank":2,"East (winter)":4,"South":3,
                "Muga":3,"Astro 1":2,"Astro 2":2,"Cricket Nets":4,"Track Lanes 1-4":4}
    rows=[]
    for d in sorted(df['date'].unique()):
        for loc in sorted(df[df['date']==d]['location'].unique()):
            grp = df[(df['date']==d)&(df['location']==loc)]
            agg = grp.groupby(['time','type','booker','details'],as_index=False).agg({
                'sublocation':lambda x: x.iloc[0] if x.nunique()==1 else(
                    'ALL' if expected.get(loc)==x.nunique() else ', '.join(sorted(x.unique()))
                )
            })
            agg['date'], agg['location'] = d, loc
            rows.append(agg[['date','location','sublocation','time','type','booker','details']])
    return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=['date','location','sublocation','time','type','booker','details'])


def highlight_rows(r): return ['background-color:#00B050']*len(r) if r['type']=='Grounds-15' else(['background-color:#F2B800']*len(r) if '(game)' in r['type'] else ['']*len(r))

def agggrass(df):
    thr={'3g-1':2,'3g-2':2,'Cameron Bank':2,'South':3}
    out=[]
    df=df.fillna({'details':''})
    for loc,g in df.groupby('location',sort=False):
        if loc in thr:
            a=g.groupby(['date','time','type','booker','details'],as_index=False).agg(
                sublocation=lambda x:'ALL' if len(x)==thr[loc] else ', '.join(sorted(x.unique()))
            )
            a['location']=loc; out.append(a)
        else: out.append(g)
    return pd.concat(out,ignore_index=True)

st.title('Booking Viewer')

# Load CSV
df=None
with st.expander('Load CSV or Enter Share Code'):
    code=st.text_input('Share Code:')
    if code:
        p=os.path.join(SHARED_FOLDER,f'{code}.csv')
        if os.path.exists(p):
            t=open(p,'r',encoding='latin-1').read(); st.success('Loaded');
            st.download_button('Download',t,f'shared_{today_date}.csv','text/csv')
        else: st.error('Not found')
    up=st.file_uploader('Upload CSV',type='csv')
    if up: df=pd.read_csv(io.StringIO(up.getvalue().decode('latin-1')),header=None)

if df is None: st.stop()

tabs=st.tabs(['Daily','Grass','Full','Sharing','How‑To'])

# Daily
with tabs[0]:
    st.header('Daily Overview')
    ext=df.iloc[:,23:30].copy()
    sc=ext.iloc[:,0].str.split(' - ',expand=True); sc.columns=['date','location']
    proc=pd.concat([sc,ext.iloc[:,[3,2,4,5,6]].reset_index(drop=True)],axis=1)
    proc.columns=['date','location','sublocation','time','type','booker','details']
    proc['date']=pd.to_datetime(proc['date'],dayfirst=True,infer_datetime_format=True)
    proc['date_str']=proc['date'].dt.strftime('%d.%m.%Y')
    proc['details']=proc['details'].fillna('')
    excl=['Chainey','T R 1','T R 2']; proc=proc[~proc['sublocation'].isin(excl)]
    dates=sorted(proc['date_str'].unique()); sel_dates=st.multiselect('Select Date',['ALL']+dates,default=['ALL'])
    if 'ALL' in sel_dates: sdates=dates
    else: sdates=sel_dates
    locs=sorted(proc['location'].unique()); sel_locs=st.multiselect('Select Loc',['ALL']+locs,default=['ALL'])
    if 'ALL' in sel_locs: slocs=locs
    else: slocs=sel_locs
    filt=proc[(proc['date_str'].isin(sdates))&(proc['location'].isin(slocs))]
    if filt.empty: st.write('No bookings')
    else:
        agg_list=[]
        for ds in sorted(filt['date_str'].unique()):
            st.subheader(f'Date: {ds}')
            d=pd.to_datetime(ds,dayfirst=True, infer_datetime_format=True)
            subset=filt[filt['date']==d]
            ad=aggregate_bookings(subset); agg_list.append(ad)
            for L in sorted(ad['location'].unique()):
                st.subheader(f'Location: {L}')
                dfL=ad[ad['location']==L].reset_index(drop=True)
                for _,r in dfL.iterrows():
                    hdr=f"Sublocation: {r['sublocation']} | Time: {r['time']} | Type: {r['type']} | Booker: {r['booker']}"
                    with st.expander(hdr): st.write(f"Details: {r['details']}")
        if agg_list:
            all_a=pd.concat(agg_list,ignore_index=True)
            st.markdown('### Export')
            if len(filt['date_str'].unique())>1: data=export_aggregated_excel_by_date(all_a)
            else: data=dataframe_to_excel(all_a.drop(columns=['date']))
            st.download_button('Download Excel',data,'daily_overview.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# Grass
with tabs[1]:
    st.header('Grass Weekly Overview')
    ext=df.iloc[:,23:30].copy()
    sc=ext.iloc[:,0].str.split(' - ',expand=True); sc.columns=['date','location']
    proc=pd.concat([sc,ext.iloc[:,[3,2,4,5,6]].reset_index(drop=True)],axis=1)
    proc.columns=['date','location','sublocation','time','type','booker','details']
    proc['date']=pd.to_datetime(proc['date'],dayfirst=True,infer_datetime_format=True)
    grass_locs=["East (summer)","East (winter)","Cameron Bank","South","3g-1","3g-2"]
    gdf=proc[proc['location'].isin(grass_locs)].sort_values(['location','sublocation','date','time','type','booker'],ignore_index=True)
    gdf['date_str']=gdf['date'].dt.strftime('%d.%m.%Y')
    if gdf.empty: st.write('No Grass bookings')
    else:
        act_src={}
        for loc in grass_locs:
            grp=gdf[gdf['location']==loc]
            if grp.empty: st.write(f'No {loc}')
            else:
                if loc in ['3g-1','3g-2']: act_src[loc]=grp.copy()
                with st.expander(f'{loc} Bookings'):
                    if loc in ['3g-1','3g-2','Cameron Bank','South']: display=agggrass(grp)
                    else: display=grp
                    display['date']=display['date'].dt.strftime('%d.%m.%Y')
                    st.dataframe(display[['date','sublocation','time','type','booker','details']].style.apply(highlight_rows,axis=1))
        st.subheader('3G Activity Begins'); c1,c2=st.columns(2)
        for col,loc in zip((c1,c2),['3g-1','3g-2']):
            with col:
                src=act_src.get(loc)
                if src is None: st.write(f'No data for {loc}')
                else:
                    with st.expander(f'{loc} Activity Begins'):
                        tmp=src.copy(); tmp['start']=tmp['time'].str.split(' to ').str[0]
                        act=tmp.groupby('date',as_index=False)['start'].min().rename(columns={'start':'activity begins'})
                        act['date']=act['date'].dt.strftime('%d.%m.%Y')
                        st.dataframe(act)
        # AutoGS export
        df_dates=gdf.copy(); earliest=df_dates['date'].min()
        if earliest.weekday()!=0: st.error(f"Earliest date {earliest.strftime('%A %d/%m/%Y')} not Monday")
        else:
            mon=earliest; week=[mon+timedelta(days=i) for i in range(7)]
            activity={loc:grp.groupby('date',as_index=False)['time'].apply(lambda s: s.iloc[0].split(' to ')[0]).set_index('date')['time'].to_dict() for loc,grp in df_dates[df_dates['location'].isin(['3g-1','3g-2'])].groupby('location')}
            pitch_map=[('East (winter)','Pitch 1','East 1'),('East (winter)','Pitch 2','East 2'),('East (winter)','Pitch 3','East 3'),('East (winter)','Training','East Training'),('East (summer)','Pitch 1','Cricket'),('South','S 1','South 1'),('South','S 2','South 2'),('South','S 3','South 3'),('Cameron Bank','C B 1','CB1'),('Cameron Bank','C B 2','CB2')]
            names=[m[2] for m in pitch_map]+['3g-1','3g-2']
            out=io.BytesIO()
            with pd.ExcelWriter(out,engine='xlsxwriter') as writer:
                wb=writer.book; ws=wb.add_worksheet('AutoGS'); writer.sheets['AutoGS']=ws
                fmt_date=wb.add_format({'num_format':'dddd\n dd/mm/yyyy','align':'center','valign':'vcenter','text_wrap':True})
                fmt=wb.add_format({'align':'center','valign':'vcenter','text_wrap':True})
                for c,dt in enumerate(week,start=1): ws.write_datetime(0,c,dt,fmt_date)
                for r,name in enumerate(names,start=1): ws.write(r,0,name,fmt)
                for r,name in enumerate(names,start=1):
                    for c,dt in enumerate(week,start=1):
                        if name in activity: cell=f"Activity starts {activity[name].get(dt,'')}"
                        else:
                            loc,subl,_=next(m for m in pitch_map if m[2]==name)
                            bk=gdf[(gdf['location']==loc)&(gdf['sublocation']==subl)&(gdf['date']==dt)]
                            lines=[f"{d['details']}\n{d['time'].replace(':','').replace(' to ','-')}" for _,d in bk.iterrows()]
                            cell='\n'.join(lines)
                        ws.write(r,c,cell,fmt)
            out.seek(0)
            st.download_button('Launch AutoGS',out.getvalue(),f'AutoGS_{mon.strftime("%Y%m%d")}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# Full Processed Data
with tabs[2]:
    st.header('Full Processed Data')
    ext=df.iloc[:,23:30].copy()
    sc=ext.iloc[:,0].str.split(' - ',expand=True); sc.columns=['date','location']
    proc=pd.concat([sc,ext.iloc[:,[3,2,4,5,6]].reset_index(drop=True)],axis=1)
    proc.columns=['date','location','sublocation','time','type','booker','details']
    proc['date']=pd.to_datetime(proc['date'],dayfirst=True,infer_datetime_format=True)
    proc['date']=proc['date'].dt.strftime('%d.%m.%Y')
    st.dataframe(proc)
    st.download_button('Download Full Processed Data',dataframe_to_excel(proc),'full_processed_data.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# Sharing
with tabs[3]:
    st.header('Sharing Facilities')
    if df is None: st.warning('Load CSV first')
    else:
        if st.button('Generate Shareable Code'):
            uid=str(uuid.uuid4()); p=os.path.join(SHARED_FOLDER,f'{uid}.csv')
            open(p,'w',encoding='latin-1').write(df.to_csv(header=False,index=False))
            st.info('CSV shared!')
            components.html(f"<input value='{uid}' readonly/><button onclick='navigator.clipboard.writeText(this.previousElementSibling.value)'>Copy</button>",height=100)

# How-To
with tabs[4]:
    st.header('How‑To Guides')
    guides={'User Guide – Overview':'webxnguide.pdf','Pulling CSV from Xn':'csvpullfile.pdf'}
    for title,path in guides.items():
        try:
            data=open(path,'rb').read()
            st.download_button(f'📄 Download {title}',data,path,'application/pdf')
        except FileNotFoundError:
            st.error(f'Missing {path}')
