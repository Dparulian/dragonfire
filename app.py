import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime
import urllib.parse
import io

# ══════════════════════════════════════════════════════
# 1. PAGE CONFIG
# ══════════════════════════════════════════════════════
st.set_page_config(
    page_title="Dragon Fire Dashboard",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
    --bg-base:       #080c10;
    --bg-card:       #0f1419;
    --bg-card2:      #141c24;
    --border:        #1e2d3d;
    --border-bright: #2a3f55;
    --fire:          #ff5722;
    --fire-dim:      rgba(255,87,34,.12);
    --green:         #00e676;
    --green-dim:     rgba(0,230,118,.10);
    --red:           #ff1744;
    --red-dim:       rgba(255,23,68,.10);
    --amber:         #ffab00;
    --amber-dim:     rgba(255,171,0,.10);
    --blue:          #40c4ff;
    --blue-dim:      rgba(64,196,255,.10);
    --purple:        #e040fb;
    --text:          #cdd9e5;
    --text-2:        #768390;
    --text-3:        #3d4f61;
    --font:          'Inter', 'Segoe UI', sans-serif;
    --mono:          'JetBrains Mono', 'Consolas', monospace;
}

/* ── RESET ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"] {
    background: var(--bg-base) !important;
    color: var(--text) !important;
    font-family: var(--font) !important;
}
[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
}
.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
section[data-testid="stSidebar"] > div { padding-top: 1rem; }

/* ── SIDEBAR ── */
.sb-logo {
    font-size: 20px; font-weight: 800; color: var(--fire);
    letter-spacing: -0.5px; padding: 0 4px 12px;
    border-bottom: 1px solid var(--border); margin-bottom: 14px;
}
.sb-stat {
    background: var(--bg-base); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
}
.sb-stat .lbl { color: var(--text-2); font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .8px; }
.sb-stat .val { font-size: 20px; font-weight: 800; margin-top: 2px; }
.sb-sect { color: var(--text-3); font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; padding: 10px 0 4px; border-top: 1px solid var(--border); margin-top: 6px; }

/* ── HEADER ── */
.hdr {
    background: linear-gradient(135deg, #120600 0%, var(--bg-card) 55%, #071220 100%);
    border: 1px solid var(--border); border-left: 3px solid var(--fire);
    border-radius: 12px; padding: 18px 24px; margin-bottom: 16px;
    display: flex; align-items: center; gap: 16px;
}
.hdr-icon { font-size: 36px; line-height: 1; }
.hdr-title { font-size: 24px; font-weight: 800; color: var(--fire); letter-spacing: -0.5px; margin: 0; }
.hdr-sub { font-size: 12px; color: var(--text-2); margin: 2px 0 0; }

/* ── METRIC STRIP ── */
.mstrip { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.mcard {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 16px; flex: 1; min-width: 130px;
}
.mcard .lbl { color: var(--text-2); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; }
.mcard .val { font-size: 22px; font-weight: 800; margin-top: 3px; font-family: var(--mono); }
.mcard .sub { font-size: 11px; color: var(--text-2); margin-top: 2px; }

/* ── PICK CARDS ── */
.pick {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px; position: relative; overflow: hidden;
    transition: border-color .2s, box-shadow .2s;
    height: 100%;
}
.pick:hover { border-color: var(--border-bright); box-shadow: 0 0 20px rgba(255,87,34,.06); }
.pick::after { content:''; position:absolute; top:0; left:0; right:0; height:2px; }
.pick.g1::after { background: linear-gradient(90deg,#ffab00,#ffe57f); }
.pick.g2::after { background: linear-gradient(90deg,#90a4ae,#cfd8dc); }
.pick.g3::after { background: linear-gradient(90deg,#a05a2c,#d4884a); }
.pick-medal { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--text-2); }
.pick-name  { font-size: 28px; font-weight: 800; color: var(--text); font-family: var(--mono); margin: 4px 0 2px; }
.pick-price { font-size: 16px; font-weight: 700; color: var(--blue); }
.pick-meta  { font-size: 11px; color: var(--text-2); margin-top: 6px; line-height: 1.6; }

/* ── BADGES ── */
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 30px;
    font-size: 10px; font-weight: 700; letter-spacing: .6px; margin-top: 8px;
    font-family: var(--mono);
}
.b-buy     { background: var(--green-dim);  color: var(--green);  border: 1px solid rgba(0,230,118,.3); }
.b-scalp   { background: var(--fire-dim);   color: var(--fire);   border: 1px solid rgba(255,87,34,.3); }
.b-watch   { background: var(--amber-dim);  color: var(--amber);  border: 1px solid rgba(255,171,0,.3); }
.b-hold    { background: var(--blue-dim);   color: var(--blue);   border: 1px solid rgba(64,196,255,.3); }
.b-wait    { background: rgba(120,120,120,.1); color: var(--text-2); border: 1px solid rgba(120,120,120,.2); }

/* ── SECTION LABEL ── */
.slabel {
    color: var(--text-3); font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1.2px;
    padding-bottom: 6px; border-bottom: 1px solid var(--border);
    margin: 14px 0 10px;
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-card) !important;
    border-bottom: 1px solid var(--border) !important;
    border-radius: 10px 10px 0 0; padding: 0 12px; gap: 0;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: var(--text-2) !important; padding: 12px 16px !important;
    border-bottom: 2px solid transparent !important; background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: var(--fire) !important;
    border-bottom-color: var(--fire) !important;
}
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 8px; overflow: hidden; }

/* ── DIAG CARDS ── */
.dg { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap: 8px; margin: 12px 0; }
.dc {
    background: var(--bg-card2); border: 1px solid var(--border);
    border-radius: 8px; padding: 11px 14px;
}
.dc .k { color: var(--text-2); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; }
.dc .v { font-size: 17px; font-weight: 800; margin-top: 3px; font-family: var(--mono); }
.dc .h { font-size: 10px; color: var(--text-3); margin-top: 1px; }

/* ── ALERT BOXES ── */
.abox {
    border-radius: 8px; padding: 11px 16px; font-size: 12px; margin: 8px 0;
    display: flex; align-items: flex-start; gap: 10px;
}
.abox-info   { background: var(--blue-dim);  border: 1px solid rgba(64,196,255,.25);  color: var(--blue); }
.abox-warn   { background: var(--amber-dim); border: 1px solid rgba(255,171,0,.25);   color: var(--amber); }
.abox-ok     { background: var(--green-dim); border: 1px solid rgba(0,230,118,.25);   color: var(--green); }
.abox-err    { background: var(--red-dim);   border: 1px solid rgba(255,23,68,.25);   color: var(--red); }

/* ── INPUTS ── */
.stTextInput input, .stSelectbox > div > div { background: var(--bg-card) !important; border-color: var(--border) !important; color: var(--text) !important; border-radius: 6px !important; }
.stMultiSelect [data-baseweb="tag"] { background: rgba(255,87,34,.3) !important; }
[data-testid="stDownloadButton"] button { background: var(--bg-card2) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 6px !important; }
[data-testid="stDownloadButton"] button:hover { border-color: var(--fire) !important; color: var(--fire) !important; }
div[data-testid="stMetricValue"] { font-family: var(--mono) !important; font-size: 20px !important; }

/* ── TICKER HEADER ── */
.tick-hdr {
    background: linear-gradient(135deg, #0a1a08, var(--bg-card));
    border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 20px; margin: 12px 0; display: flex;
    align-items: center; gap: 14px; flex-wrap: wrap;
}
.tick-sym { font-size: 30px; font-weight: 800; font-family: var(--mono); color: var(--text); }
.tick-src { font-size: 11px; color: var(--text-2); background: var(--bg-card2);
    border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; }

/* ── KESIMPULAN BOX ── */
.konk {
    background: var(--bg-card2); border: 1px solid var(--border);
    border-left: 3px solid var(--fire); border-radius: 8px;
    padding: 14px 18px; margin: 10px 0;
}
.konk .kt { color: var(--text-2); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.konk .kv { color: var(--text); font-size: 13px; line-height: 1.5; }

#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════
# 2. DB CONNECTION
# ══════════════════════════════════════════════════════
def sanitize_db_url(url):
    if not url: return url
    prefix = "postgresql://"
    if url.startswith("postgres://"): url = url.replace("postgres://", prefix, 1)
    if url.startswith(prefix):
        rem = url[len(prefix):]
        auth_part, path_part = rem.rsplit('/', 1) if '/' in rem else (rem, "")
        if '@' in auth_part:
            creds, host_port = auth_part.rsplit('@', 1)
            if ':' in creds:
                user, pw = creds.split(':', 1)
                return f"{prefix}{user}:{urllib.parse.quote_plus(pw)}@{host_port}/{path_part}"
    return url

@st.cache_resource
def init_connection():
    return create_engine(sanitize_db_url(st.secrets["DATABASE_URL"]))

try:
    engine = init_connection()
except Exception as e:
    st.error(f"❌ Gagal koneksi database: {e}")
    st.stop()

# ══════════════════════════════════════════════════════
# 3. DATA LOADING — ROBUST NORMALIZE
# ══════════════════════════════════════════════════════
# ── PERBAIKAN BUG #1: normalize_columns diperkuat ──
# Kolom dari PostgreSQL selalu lowercase. Kita peta dengan case-insensitive matching.
TARGET_COLS = {
    'ticker', 'close', 'support', 'resistance', 'bb_width_str',
    'vol_ratio', 'vol_velocity', 'cmf', 'ud_vol_ratio',
    'hari_ke_breakout', 'potensial_upsize', 'cvi',
    'analisis_kesimpulan', 'rekomendasi_action', 'tanggal_scan'
}
DISPLAY_MAP = {
    'ticker':'Ticker','close':'Close','support':'Support','resistance':'Resistance',
    'bb_width_str':'BB_Width_Str','vol_ratio':'Vol_Ratio','vol_velocity':'Vol_Velocity',
    'cmf':'CMF','ud_vol_ratio':'UD_Vol_Ratio','hari_ke_breakout':'Hari_Ke_Breakout',
    'potensial_upsize':'Potensial_Upsize','cvi':'CVI',
    'analisis_kesimpulan':'Analisis_Kesimpulan','rekomendasi_action':'Rekomendasi_Action',
    'tanggal_scan':'Tanggal_Scan'
}

def normalize_columns(df):
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns=DISPLAY_MAP)
    # ── PERBAIKAN BUG #3: pastikan Ticker selalu UPPERCASE string bersih ──
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
    # ── Pastikan Close numerik, bukan string ──
    if 'Close' in df.columns:
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    if 'CVI' in df.columns:
        df['CVI'] = pd.to_numeric(df['CVI'], errors='coerce')
    return df

@st.cache_data(ttl=600)
def fetch_cloud_data(table_name):
    try:
        return pd.read_sql(f'SELECT * FROM "{table_name}"', engine)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def fetch_chart_data(ticker):
    try:
        import yfinance as yf
        df = yf.Ticker(f"{ticker}.JK").history(period="90d")
        if df.empty: return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[['Open','High','Low','Close','Volume']].dropna()
    except Exception:
        return pd.DataFrame()

df_screener  = normalize_columns(fetch_cloud_data('screener_live'))
df_watchlist = normalize_columns(fetch_cloud_data('watchlist_live'))
df_history   = normalize_columns(fetch_cloud_data('screener_history'))

# ── PERBAIKAN BUG #2: all_stocks_live mungkin belum ada di DB (script lama) ──
# Kalau kosong, kita gabungkan screener + history sebagai fallback komprehensif
_all_raw = normalize_columns(fetch_cloud_data('all_stocks_live'))
if _all_raw.empty:
    # Gabung screener live + history (ambil baris terbaru per ticker)
    frames = []
    if not df_screener.empty:  frames.append(df_screener)
    if not df_history.empty:
        hist_latest = (df_history.sort_values('Tanggal_Scan', ascending=False)
                       .drop_duplicates(subset='Ticker', keep='first')
                       .drop(columns=['Tanggal_Scan'], errors='ignore'))
        frames.append(hist_latest)
    if frames:
        _combined = pd.concat(frames, ignore_index=True)
        df_all_stocks = _combined.drop_duplicates(subset='Ticker', keep='first').reset_index(drop=True)
    else:
        df_all_stocks = pd.DataFrame()
else:
    df_all_stocks = _all_raw

# ══════════════════════════════════════════════════════
# 4. HELPERS
# ══════════════════════════════════════════════════════
def classify_action(s):
    a = str(s).upper()
    if any(x in a for x in ["BUY","ACCUMULATION","NYICIL"]):  return "buy",   s
    if "SCALP" in a:                                            return "scalp", "SCALPING"
    if any(x in a for x in ["WATCH","PANTAU","TIDUR"]):        return "watch", s
    if "HOLD" in a:                                             return "hold",  "HOLD"
    return "wait", s

def badge(s):
    cls, lbl = classify_action(s)
    return f'<span class="badge b-{cls}">{lbl}</span>'

def fmt_price(v):
    """Format harga — aman untuk float atau string."""
    try: return f"Rp {float(v):,.0f}"
    except: return str(v) if v else "—"

def fmt_val(v):
    """Format nilai generic — tidak crash pada None/NaN."""
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    return str(v)

def to_excel(df, sheet="Data"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name=sheet)
    return buf.getvalue()

def render_chart(ticker, row=None):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        st.info("Tambahkan `plotly` ke requirements.txt untuk chart.")
        return

    with st.spinner(f"Memuat chart {ticker} dari Yahoo Finance..."):
        df = fetch_chart_data(ticker)

    if df.empty:
        st.markdown('<div class="abox abox-warn">⚠ Data chart tidak tersedia di Yahoo Finance untuk emiten ini.</div>', unsafe_allow_html=True)
        return

    df['MA20']  = df['Close'].rolling(20).mean()
    df['Bstd']  = df['Close'].rolling(20).std()
    df['BBu']   = df['MA20'] + 2*df['Bstd']
    df['BBl']   = df['MA20'] - 2*df['Bstd']
    df['VMA20'] = df['Volume'].rolling(20).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.70, 0.30], vertical_spacing=0.02)

    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name=ticker,
        increasing=dict(line=dict(color='#00e676',width=1), fillcolor='rgba(0,230,118,.75)'),
        decreasing=dict(line=dict(color='#ff1744',width=1), fillcolor='rgba(255,23,68,.75)'),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['BBu'], line=dict(color='rgba(255,171,0,.35)',width=1,dash='dot'),
        name='BB Upper', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BBl'], line=dict(color='rgba(255,171,0,.35)',width=1,dash='dot'),
        fill='tonexty', fillcolor='rgba(255,171,0,.04)', name='BB Lower', showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='rgba(64,196,255,.8)',width=1.5),
        name='MA20', showlegend=False), row=1, col=1)

    if row:
        try:
            sup = float(str(row.get('Support','')).replace(',','').replace('Rp','').strip())
            res = float(str(row.get('Resistance','')).replace(',','').replace('Rp','').strip())
            fig.add_hline(y=sup, line=dict(color='rgba(0,230,118,.5)',width=1,dash='dash'),
                          annotation_text="S", annotation_font=dict(color='#00e676',size=10), row=1, col=1)
            fig.add_hline(y=res, line=dict(color='rgba(255,23,68,.5)',width=1,dash='dash'),
                          annotation_text="R", annotation_font=dict(color='#ff1744',size=10), row=1, col=1)
        except: pass

    vc = ['#00e676' if c>=o else '#ff1744' for c,o in zip(df['Close'],df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vc, opacity=.65,
        name='Volume', showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['VMA20'],
        line=dict(color='rgba(255,171,0,.9)',width=1.5), name='V MA20', showlegend=False), row=2, col=1)

    fig.update_layout(
        height=500, margin=dict(l=0,r=0,t=24,b=0),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='#080c10',
        font=dict(color='#768390',size=11,family='JetBrains Mono,monospace'),
        xaxis_rangeslider_visible=False, showlegend=False,
        xaxis=dict(gridcolor='#1e2d3d',zeroline=False),
        yaxis=dict(gridcolor='#1e2d3d',zeroline=False,tickformat=',.0f',tickprefix='Rp '),
        xaxis2=dict(gridcolor='#1e2d3d',zeroline=False),
        yaxis2=dict(gridcolor='#1e2d3d',zeroline=False,tickformat='.2s'),
    )
    fig.update_xaxes(showspikes=True, spikecolor="#2a3f55", spikethickness=1)
    fig.update_yaxes(showspikes=True, spikecolor="#2a3f55", spikethickness=1)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})

# ══════════════════════════════════════════════════════
# 5. HEADER + SIDEBAR
# ══════════════════════════════════════════════════════
now_str = datetime.now().strftime('%d %b %Y · %H:%M WIB')

st.markdown(f"""
<div class="hdr">
  <div class="hdr-icon">🐉</div>
  <div>
    <div class="hdr-title">Dragon Fire Quant Dashboard</div>
    <div class="hdr-sub">Pusat Komando Velositas Modal & Detektor Akumulasi Bandar &nbsp;·&nbsp; {now_str}</div>
  </div>
</div>
""", unsafe_allow_html=True)

n_sc   = len(df_screener)
n_wl   = len(df_watchlist)
n_all  = len(df_all_stocks)
n_buy  = len(df_screener[df_screener['Rekomendasi_Action'].str.contains("BUY|ACCUMULATION|NYICIL", na=False)]) if n_sc else 0
n_hist = df_history['Tanggal_Scan'].nunique() if not df_history.empty and 'Tanggal_Scan' in df_history.columns else 0

cm1,cm2,cm3,cm4,cm5,cm6 = st.columns([1.2,1.2,1.2,1.2,2,1.4])
with cm1:
    st.markdown(f'<div class="mcard"><div class="lbl">Screener Live</div><div class="val" style="color:var(--fire)">{n_sc}</div><div class="sub">Emiten aktif hari ini</div></div>', unsafe_allow_html=True)
with cm2:
    st.markdown(f'<div class="mcard"><div class="lbl">Sinyal BUY</div><div class="val" style="color:var(--green)">{n_buy}</div><div class="sub">Akumulasi terdeteksi</div></div>', unsafe_allow_html=True)
with cm3:
    st.markdown(f'<div class="mcard"><div class="lbl">Watchlist</div><div class="val" style="color:var(--blue)">{n_wl}</div><div class="sub">Saham dipantau</div></div>', unsafe_allow_html=True)
with cm4:
    st.markdown(f'<div class="mcard"><div class="lbl">Master DB</div><div class="val">{n_all}</div><div class="sub">Total emiten tersimpan</div></div>', unsafe_allow_html=True)
with cm5:
    if n_sc > 0 and 'CVI' in df_screener.columns:
        top = df_screener.sort_values('CVI',ascending=False).iloc[0]
        st.markdown(f"""<div class="mcard">
            <div class="lbl">🥇 Top CVI Hari Ini</div>
            <div class="val" style="color:var(--amber);font-size:17px;">{top.get('Ticker','—')}</div>
            <div class="sub">CVI {fmt_val(top.get('CVI','—'))} · {fmt_val(top.get('Potensial_Upsize','—'))}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="mcard"><div class="lbl">Top CVI</div><div class="val">—</div></div>', unsafe_allow_html=True)
with cm6:
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# Sidebar
with st.sidebar:
    st.markdown('<div class="sb-logo">🐉 Dragon Fire</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sect">STATUS LIVE</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Screener Aktif</div><div class="val" style="color:var(--fire)">{n_sc}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Sinyal BUY</div><div class="val" style="color:var(--green)">{n_buy}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Master Database</div><div class="val">{n_all} emiten</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Riwayat Tersimpan</div><div class="val">{n_hist} hari</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sect" style="margin-top:10px">NAVIGASI CEPAT</div>', unsafe_allow_html=True)
    st.caption("Gunakan tab di atas untuk berpindah antar modul.")
    st.markdown("---")
    st.caption(f"Dragon Fire v3.0 · KangTao Cari Cuan\n\n{now_str}")

# ══════════════════════════════════════════════════════
# 6. MAIN TABS
# ══════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📊  LIVE SCREENER",
    "📋  WATCHLIST",
    "🔍  DIAGNOSTIK TICKER",
    "📅  HISTORI HARIAN"
])

# ─────────────────────────────────────────────────────
# TAB 1 · LIVE SCREENER
# ─────────────────────────────────────────────────────
with tab1:
    if df_screener.empty:
        st.markdown('<div class="abox abox-warn">⚠ Belum ada data screener_live. Jalankan dragon_fire.py terlebih dahulu.</div>', unsafe_allow_html=True)
    else:
        # Top 3 cards
        st.markdown('<div class="slabel">🏆 Top Alpha Velocity Picks — CVI Tertinggi Hari Ini</div>', unsafe_allow_html=True)
        top3   = df_screener.sort_values('CVI', ascending=False).head(3)
        medals = ['g1','g2','g3']
        ranks  = ['🥇 Alpha #1','🥈 Runner Up','🥉 Momentum']
        cols3  = st.columns(min(len(top3),3))
        for i,(_, r) in enumerate(top3.iterrows()):
            with cols3[i]:
                st.markdown(f"""
                <div class="pick {medals[i]}">
                  <div class="pick-medal">{ranks[i]}</div>
                  <div class="pick-name">{r.get('Ticker','—')}</div>
                  <div class="pick-price">{fmt_price(r.get('Close'))}</div>
                  <div class="pick-meta">
                    CVI <strong style="color:var(--amber)">{fmt_val(r.get('CVI'))}</strong>
                    &nbsp;·&nbsp; Upside <strong style="color:var(--green)">{fmt_val(r.get('Potensial_Upsize'))}</strong><br>
                    ⏱ {fmt_val(r.get('Hari_Ke_Breakout'))}
                  </div>
                  {badge(r.get('Rekomendasi_Action',''))}
                </div>
                """, unsafe_allow_html=True)

        st.write("")
        cf1, cf2, cf3 = st.columns([3,2,1.5])
        with cf1:
            opts = sorted(df_screener['Rekomendasi_Action'].dropna().unique().tolist())
            defs = [a for a in opts if any(x in a.upper() for x in ["BUY","SCALP","ACCUMULATION","PANTAU","TIDUR"])] or opts
            sel  = st.multiselect("⚡ Filter Rekomendasi", options=opts, default=defs)
        with cf2:
            srt_col = st.selectbox("🔃 Urutkan berdasarkan", ['CVI','Close','Vol_Ratio','CMF'], index=0)
        with cf3:
            srt_dir = st.selectbox("Arah", ["Tertinggi ↓","Terendah ↑"], index=0)

        df_d = df_screener.copy()
        if sel: df_d = df_d[df_d['Rekomendasi_Action'].isin(sel)]
        df_d = df_d.sort_values(srt_col, ascending=(srt_dir=="Terendah ↑"))

        st.markdown(f'<div class="slabel">TABEL SCREENER — {len(df_d)} Emiten Lolos Filter</div>', unsafe_allow_html=True)
        dcols = [c for c in ['Ticker','Close','Support','Resistance','BB_Width_Str',
                              'Vol_Ratio','Vol_Velocity','CMF','UD_Vol_Ratio',
                              'Hari_Ke_Breakout','Potensial_Upsize','CVI',
                              'Analisis_Kesimpulan','Rekomendasi_Action'] if c in df_d.columns]
        st.dataframe(df_d[dcols].reset_index(drop=True), use_container_width=True, height=380,
            column_config={
                "Ticker":             st.column_config.TextColumn("Ticker",  width=80),
                "Close":              st.column_config.NumberColumn("Close",  format="Rp %,.0f"),
                "CVI":                st.column_config.NumberColumn("CVI",    format="%.3f"),
                "Vol_Ratio":          st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
                "Potensial_Upsize":   st.column_config.TextColumn("Upside",  width=80),
                "Rekomendasi_Action": st.column_config.TextColumn("Action",  width=150),
            })
        st.download_button("⬇️ Download Screener Hari Ini (.xlsx)",
            data=to_excel(df_d[dcols], "Screener_Live"),
            file_name=f"DragonFire_Screener_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────────────
# TAB 2 · WATCHLIST
# ─────────────────────────────────────────────────────
with tab2:
    if df_watchlist.empty:
        st.markdown('<div class="abox abox-info">💡 Belum ada data watchlist_live. Pastikan file Excel watchlist sudah di folder WATCHLIST dan dragon_fire.py sudah berjalan.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="slabel">📋 Status Real-Time Portofolio / Watchlist</div>', unsafe_allow_html=True)
        n_wb = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("BUY|ACCUMULATION", na=False)])
        n_wh = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("HOLD", na=False)])
        n_ww = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("WATCH|PANTAU", na=False)])
        w1,w2,w3,w4 = st.columns(4)
        w1.metric("Total Watchlist", n_wl)
        w2.metric("Sinyal BUY", n_wb, delta="Beli" if n_wb else None)
        w3.metric("Hold", n_wh)
        w4.metric("Watch/Pantau", n_ww)
        wcols = [c for c in ['Ticker','Close','Support','Resistance','BB_Width_Str',
                              'Vol_Ratio','CMF','UD_Vol_Ratio','Hari_Ke_Breakout',
                              'Potensial_Upsize','CVI','Analisis_Kesimpulan','Rekomendasi_Action']
                 if c in df_watchlist.columns]
        df_ws = df_watchlist.sort_values('CVI', ascending=False)
        st.dataframe(df_ws[wcols].reset_index(drop=True), use_container_width=True, height=420,
            column_config={
                "Close":     st.column_config.NumberColumn("Close",     format="Rp %,.0f"),
                "CVI":       st.column_config.NumberColumn("CVI",       format="%.3f"),
                "Vol_Ratio": st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
            })
        st.download_button("⬇️ Download Watchlist (.xlsx)",
            data=to_excel(df_ws[wcols], "Watchlist_Live"),
            file_name=f"DragonFire_Watchlist_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────────────
# TAB 3 · DIAGNOSTIK TICKER  ← PERBAIKAN UTAMA
# ─────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="slabel">🔍 Diagnostik & Chart Per Emiten</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="abox abox-info">
      📡 Basis data pencarian: <strong>{n_all} emiten</strong> (Master DB + Screener + Histori).
      Ketik kode saham BEI — termasuk yang tidak lolos screener hari ini.
    </div>""", unsafe_allow_html=True)

    ci, cb = st.columns([4, 1])
    with ci:
        search_ticker = st.text_input("", placeholder="Contoh: BBCA · GLVA · MASB · TLKM ...",
                                      label_visibility="collapsed").strip().upper()
    with cb:
        st.write("")
        st.button("🔍 Cari", use_container_width=True)

    if search_ticker:
        # ── PERBAIKAN BUG #2: cascade search 3 level ──
        match = pd.DataFrame()
        src_lbl = ""

        # Level 1: master all_stocks (terlengkap)
        if not df_all_stocks.empty and 'Ticker' in df_all_stocks.columns:
            m = df_all_stocks[df_all_stocks['Ticker'] == search_ticker]
            if not m.empty: match, src_lbl = m, "Master DB"

        # Level 2: screener live (jika lebih fresh)
        if match.empty and not df_screener.empty and 'Ticker' in df_screener.columns:
            m = df_screener[df_screener['Ticker'] == search_ticker]
            if not m.empty: match, src_lbl = m, "Screener Live"

        # Level 3: watchlist
        if match.empty and not df_watchlist.empty and 'Ticker' in df_watchlist.columns:
            m = df_watchlist[df_watchlist['Ticker'] == search_ticker]
            if not m.empty: match, src_lbl = m, "Watchlist"

        # Level 4: histori (baris terbaru)
        if match.empty and not df_history.empty and 'Ticker' in df_history.columns:
            m = (df_history[df_history['Ticker'] == search_ticker]
                 .sort_values('Tanggal_Scan', ascending=False)
                 .head(1)
                 .drop(columns=['Tanggal_Scan'], errors='ignore'))
            if not m.empty: match, src_lbl = m, "Histori"

        if not match.empty:
            row = match.iloc[0].to_dict()
            act_cls, act_lbl = classify_action(row.get('Rekomendasi_Action',''))

            st.markdown(f"""
            <div class="tick-hdr">
              <span class="tick-sym">{search_ticker}</span>
              <span class="badge b-{act_cls}" style="font-size:12px;padding:4px 14px;">{act_lbl}</span>
              <span class="tick-src">{src_lbl}</span>
            </div>""", unsafe_allow_html=True)

            # Metric grid — pakai fmt_price / fmt_val agar tidak crash
            st.markdown(f"""
            <div class="dg">
              <div class="dc">
                <div class="k">Harga Terakhir</div>
                <div class="v" style="color:var(--blue)">{fmt_price(row.get('Close'))}</div>
                <div class="h">Harga penutupan</div>
              </div>
              <div class="dc">
                <div class="k">Skor CVI</div>
                <div class="v" style="color:var(--fire)">{fmt_val(row.get('CVI'))}</div>
                <div class="h">Capital Velocity Index</div>
              </div>
              <div class="dc">
                <div class="k">Est. Breakout</div>
                <div class="v">{fmt_val(row.get('Hari_Ke_Breakout'))}</div>
                <div class="h">Prediksi ML (Random Forest)</div>
              </div>
              <div class="dc">
                <div class="k">Proyeksi Upside</div>
                <div class="v" style="color:var(--green)">{fmt_val(row.get('Potensial_Upsize'))}</div>
                <div class="h">Target kenaikan harga</div>
              </div>
              <div class="dc">
                <div class="k">Support</div>
                <div class="v" style="color:var(--green)">{fmt_price(row.get('Support'))}</div>
                <div class="h">Low 20 hari terakhir</div>
              </div>
              <div class="dc">
                <div class="k">Resistance</div>
                <div class="v" style="color:var(--red)">{fmt_price(row.get('Resistance'))}</div>
                <div class="h">High 20 hari terakhir</div>
              </div>
              <div class="dc">
                <div class="k">Vol Ratio</div>
                <div class="v">{fmt_val(row.get('Vol_Ratio'))}</div>
                <div class="h">Volume vs MA20 Volume</div>
              </div>
              <div class="dc">
                <div class="k">CMF</div>
                <div class="v">{fmt_val(row.get('CMF'))}</div>
                <div class="h">Chaikin Money Flow</div>
              </div>
              <div class="dc">
                <div class="k">UD Vol Ratio</div>
                <div class="v">{fmt_val(row.get('UD_Vol_Ratio'))}</div>
                <div class="h">Up / Down Volume</div>
              </div>
              <div class="dc">
                <div class="k">BB Width</div>
                <div class="v">{fmt_val(row.get('BB_Width_Str'))}</div>
                <div class="h">Volatilitas squeeze</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class="konk">
              <div class="kt">Kesimpulan Analisis Kuantitatif Dragon Fire AI</div>
              <div class="kv">{fmt_val(row.get('Analisis_Kesimpulan'))}</div>
            </div>""", unsafe_allow_html=True)

            st.markdown('<div class="slabel">📈 Chart Candlestick · Bollinger Bands · Volume (90 Hari Terakhir)</div>', unsafe_allow_html=True)
            render_chart(search_ticker, row)

        else:
            st.markdown(f'<div class="abox abox-err">❌ Kode saham <strong>{search_ticker}</strong> tidak ditemukan di seluruh database (master, screener, watchlist, histori).</div>', unsafe_allow_html=True)
            st.markdown('<div class="abox abox-info">💡 Pastikan kode 4 huruf (tanpa .JK), atau jalankan dragon_fire.py untuk update master database.</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="slabel">📈 Chart Live {search_ticker} dari Yahoo Finance</div>', unsafe_allow_html=True)
            render_chart(search_ticker)

# ─────────────────────────────────────────────────────
# TAB 4 · HISTORI HARIAN
# ─────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="slabel">📅 Arsip Histori Pemindaian Pasar BEI</div>', unsafe_allow_html=True)
    if df_history.empty or 'Tanggal_Scan' not in df_history.columns:
        st.markdown('<div class="abox abox-info">💡 Belum ada rekam histori. Data akan terkumpul otomatis setiap kali dragon_fire.py berjalan.</div>', unsafe_allow_html=True)
    else:
        avail = sorted(df_history['Tanggal_Scan'].unique().tolist(), reverse=True)
        hc1, hc2 = st.columns([3, 2])
        with hc1:
            sel_date = st.selectbox("📅 Pilih Tanggal Laporan:", options=avail)
        df_hd = (df_history[df_history['Tanggal_Scan'] == sel_date]
                 .drop(columns=['Tanggal_Scan'], errors='ignore')
                 .reset_index(drop=True))
        with hc2:
            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
            st.download_button(f"⬇️ Download {sel_date} (.xlsx)",
                data=to_excel(df_hd, f"Histori_{sel_date}"),
                file_name=f"DragonFire_Histori_{sel_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)

        n_hb = len(df_hd[df_hd['Rekomendasi_Action'].str.contains("BUY|ACCUMULATION", na=False)]) if 'Rekomendasi_Action' in df_hd.columns else 0
        h1,h2,h3 = st.columns(3)
        h1.metric("Total Emiten Scan", len(df_hd))
        h2.metric("Sinyal BUY", n_hb)
        h3.metric("Tanggal", str(sel_date))

        srch = st.text_input("🔍 Cari Ticker dalam Arsip:", placeholder="Contoh: BBCA, GLVA ...", key="hist_search").strip().upper()
        if srch:
            df_hd = df_hd[df_hd['Ticker'] == srch].reset_index(drop=True)

        st.dataframe(df_hd, use_container_width=True, height=420,
            column_config={
                "Close": st.column_config.NumberColumn("Close", format="Rp %,.0f"),
                "CVI":   st.column_config.NumberColumn("CVI",   format="%.3f"),
            })
