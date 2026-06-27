import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import pytz
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
    --bg-base:#080c10;--bg-card:#0f1419;--bg-card2:#141c24;
    --border:#1e2d3d;--border-bright:#2a3f55;
    --fire:#ff5722;--fire-dim:rgba(255,87,34,.12);
    --green:#00e676;--green-dim:rgba(0,230,118,.10);
    --red:#ff1744;--red-dim:rgba(255,23,68,.10);
    --amber:#ffab00;--amber-dim:rgba(255,171,0,.10);
    --blue:#40c4ff;--blue-dim:rgba(64,196,255,.10);
    --purple:#c084fc;--purple-dim:rgba(192,132,252,.12);
    --tiger:#f97316;--tiger-dim:rgba(249,115,22,.12);   /* Tiger orange */
    --tiger-dark:#7c2d12;
    --text:#cdd9e5;--text-2:#768390;--text-3:#3d4f61;
    --font:'Inter','Segoe UI',sans-serif;
    --mono:'JetBrains Mono','Consolas',monospace;
}
html,body,[data-testid="stAppViewContainer"],[data-testid="stAppViewBlockContainer"]{
    background:var(--bg-base)!important;color:var(--text)!important;font-family:var(--font)!important;}
[data-testid="stSidebar"]{background:var(--bg-card)!important;border-right:1px solid var(--border)!important;}
.block-container{padding-top:1rem!important;padding-bottom:2rem!important;}
section[data-testid="stSidebar"]>div{padding-top:1rem;}
.sb-logo{font-size:20px;font-weight:800;color:var(--fire);letter-spacing:-.5px;padding:0 4px 12px;border-bottom:1px solid var(--border);margin-bottom:14px;}
.sb-stat{background:var(--bg-base);border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:8px;}
.sb-stat .lbl{color:var(--text-2);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;}
.sb-stat .val{font-size:20px;font-weight:800;margin-top:2px;}
.sb-sect{color:var(--text-3);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:10px 0 4px;border-top:1px solid var(--border);margin-top:6px;}
.hdr{background:linear-gradient(135deg,#120600 0%,var(--bg-card) 55%,#071220 100%);
    border:1px solid var(--border);border-left:3px solid var(--fire);border-radius:12px;
    padding:18px 24px;margin-bottom:16px;display:flex;align-items:center;gap:16px;}
.hdr-icon{font-size:36px;line-height:1;}
.hdr-title{font-size:24px;font-weight:800;color:var(--fire);letter-spacing:-.5px;margin:0;}
.hdr-sub{font-size:12px;color:var(--text-2);margin:2px 0 0;}
.mcard{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:12px 16px;flex:1;min-width:130px;}
.mcard .lbl{color:var(--text-2);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;}
.mcard .val{font-size:22px;font-weight:800;margin-top:3px;font-family:var(--mono);}
.mcard .sub{font-size:11px;color:var(--text-2);margin-top:2px;}
.pick{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;position:relative;overflow:hidden;transition:border-color .2s,box-shadow .2s;height:100%;}
.pick:hover{border-color:var(--border-bright);box-shadow:0 0 20px rgba(255,87,34,.06);}
.pick::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;}
.pick.g1::after{background:linear-gradient(90deg,#ffab00,#ffe57f);}
.pick.g2::after{background:linear-gradient(90deg,#90a4ae,#cfd8dc);}
.pick.g3::after{background:linear-gradient(90deg,#a05a2c,#d4884a);}
.pick.macd-pick{border-color:rgba(192,132,252,.4)!important;}
.pick.macd-pick::after{background:linear-gradient(90deg,var(--purple),#e879f9)!important;}
.pick-medal{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text-2);}
.pick-name{font-size:28px;font-weight:800;color:var(--text);font-family:var(--mono);margin:4px 0 2px;}
.pick-price{font-size:16px;font-weight:700;color:var(--blue);}
.pick-meta{font-size:11px;color:var(--text-2);margin-top:6px;line-height:1.6;}
.badge{display:inline-block;padding:2px 10px;border-radius:30px;font-size:10px;font-weight:700;letter-spacing:.6px;margin-top:8px;font-family:var(--mono);}
.b-buy{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,230,118,.3);}
.b-scalp{background:var(--fire-dim);color:var(--fire);border:1px solid rgba(255,87,34,.3);}
.b-watch{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(255,171,0,.3);}
.b-hold{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(64,196,255,.3);}
.b-wait{background:rgba(120,120,120,.1);color:var(--text-2);border:1px solid rgba(120,120,120,.2);}
.b-macd{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(192,132,252,.3);}
.b-alert{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,23,68,.3);}
.slabel{color:var(--text-3);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
    padding-bottom:6px;border-bottom:1px solid var(--border);margin:14px 0 10px;}
.stTabs [data-baseweb="tab-list"]{background:var(--bg-card)!important;border-bottom:1px solid var(--border)!important;border-radius:10px 10px 0 0;padding:0 12px;gap:0;}
.stTabs [data-baseweb="tab"]{font-size:12px!important;font-weight:600!important;color:var(--text-2)!important;
    padding:12px 16px!important;border-bottom:2px solid transparent!important;background:transparent!important;}
.stTabs [aria-selected="true"]{color:var(--fire)!important;border-bottom-color:var(--fire)!important;}
[data-testid="stDataFrame"]{border:1px solid var(--border)!important;border-radius:8px;overflow:hidden;}
.dg{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin:12px 0;}
.dc{background:var(--bg-card2);border:1px solid var(--border);border-radius:8px;padding:11px 14px;}
.dc .k{color:var(--text-2);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;}
.dc .v{font-size:17px;font-weight:800;margin-top:3px;font-family:var(--mono);}
.dc .h{font-size:10px;color:var(--text-3);margin-top:1px;}
.abox{border-radius:8px;padding:11px 16px;font-size:12px;margin:8px 0;display:flex;align-items:flex-start;gap:10px;}
.abox-info{background:var(--blue-dim);border:1px solid rgba(64,196,255,.25);color:var(--blue);}
.abox-warn{background:var(--amber-dim);border:1px solid rgba(255,171,0,.25);color:var(--amber);}
.abox-ok{background:var(--green-dim);border:1px solid rgba(0,230,118,.25);color:var(--green);}
.abox-err{background:var(--red-dim);border:1px solid rgba(255,23,68,.25);color:var(--red);}
.abox-macd{background:var(--purple-dim);border:1px solid rgba(192,132,252,.25);color:var(--purple);}
.stTextInput input,.stSelectbox>div>div{background:var(--bg-card)!important;border-color:var(--border)!important;color:var(--text)!important;border-radius:6px!important;}
.stMultiSelect [data-baseweb="tag"]{background:rgba(255,87,34,.3)!important;}
[data-testid="stDownloadButton"] button{background:var(--bg-card2)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:6px!important;}
[data-testid="stDownloadButton"] button:hover{border-color:var(--fire)!important;color:var(--fire)!important;}
div[data-testid="stMetricValue"]{font-family:var(--mono)!important;font-size:20px!important;}
.tick-hdr{background:linear-gradient(135deg,#0a1a08,var(--bg-card));border:1px solid var(--border);
    border-radius:10px;padding:16px 20px;margin:12px 0;display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.tick-sym{font-size:30px;font-weight:800;font-family:var(--mono);color:var(--text);}
.tick-src{font-size:11px;color:var(--text-2);background:var(--bg-card2);border:1px solid var(--border);border-radius:4px;padding:2px 8px;}
.konk{background:var(--bg-card2);border:1px solid var(--border);border-left:3px solid var(--fire);
    border-radius:8px;padding:14px 18px;margin:10px 0;}
.konk .kt{color:var(--text-2);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;}
.konk .kv{color:var(--text);font-size:13px;line-height:1.5;}
/* ── PORTFOLIO ── */
.port-card{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;
    display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;}
.port-ticker{font-size:18px;font-weight:800;font-family:var(--mono);color:var(--text);min-width:60px;}
.port-price{font-size:14px;font-weight:700;color:var(--blue);font-family:var(--mono);}
.port-alert{padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;font-family:var(--mono);}
.port-alert-ok{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,230,118,.3);}
.port-alert-warn{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(255,171,0,.3);}
.port-alert-danger{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,23,68,.3);}
.port-alert-macd{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(192,132,252,.3);}
/* ── ENGINE SELECTOR ── */
.engine-bar{display:flex;gap:10px;margin-bottom:14px;align-items:center;}
.engine-label{font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.8px;white-space:nowrap;}
.engine-btn{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;
    padding:8px 18px;font-size:13px;font-weight:700;cursor:pointer;transition:all .2s;color:var(--text-2);}
.engine-btn:hover{border-color:var(--border-bright);}
.engine-btn.active-fire{background:var(--fire-dim);border-color:var(--fire);color:var(--fire);}
.engine-btn.active-tiger{background:var(--tiger-dim);border-color:var(--tiger);color:var(--tiger);}
/* Tiger status badges */
.b-breakout{background:rgba(249,115,22,.15);color:var(--tiger);border:1px solid rgba(249,115,22,.4);}
.b-strongbuy{background:rgba(0,230,118,.12);color:var(--green);border:1px solid rgba(0,230,118,.3);}
.b-accum{background:rgba(64,196,255,.12);color:var(--blue);border:1px solid rgba(64,196,255,.3);}
.b-superbull{background:rgba(192,132,252,.12);color:var(--purple);border:1px solid rgba(192,132,252,.3);}
.b-watching{background:rgba(120,120,120,.1);color:var(--text-2);border:1px solid rgba(120,120,120,.2);}
/* Tiger metric cards */
.tiger-card{background:var(--bg-card);border:1px solid rgba(249,115,22,.3);border-radius:10px;padding:14px 16px;position:relative;overflow:hidden;}
.tiger-card::after{content:'';position:absolute;top:0;left:0;right:0;height:2.5px;background:linear-gradient(90deg,var(--tiger),#fb923c);}
#MainMenu,footer,header{visibility:hidden;}

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
# 3. DATA LOADING
# ══════════════════════════════════════════════════════
DISPLAY_MAP = {
    'ticker':'Ticker','close':'Close','support':'Support','resistance':'Resistance',
    'bb_width_str':'BB_Width_Str','vol_ratio':'Vol_Ratio','vol_velocity':'Vol_Velocity',
    'cmf':'CMF','ud_vol_ratio':'UD_Vol_Ratio','hari_ke_breakout':'Hari_Ke_Breakout',
    'potensial_upsize':'Potensial_Upsize','cvi':'CVI',
    'macd':'MACD','macd_slope':'MACD_Slope','macd_precross':'MACD_PreCross',
    'alert_flag':'Alert_Flag',
    'analisis_kesimpulan':'Analisis_Kesimpulan','rekomendasi_action':'Rekomendasi_Action',
    'tanggal_scan':'Tanggal_Scan',
    # ── kolom baru dari improvements B1/B2/B3 ────────────────────
    'profit_target':'Profit_Target','cvi_tier':'CVI_Tier','conf_score':'Conf_Score',
    'adx':'ADX',
    # ── kolom reversal ────────────────────────────────────────────
    'is_reversal':'Is_Reversal','rev_score':'Rev_Score',
    'rev_drawdown':'Rev_Drawdown','rev_rsi':'Rev_RSI',
}

def normalize_columns(df):
    """
    Normalisasi kolom DataFrame dari Supabase ke format yang diharapkan app.
    Robust terhadap: MultiIndex columns, kolom duplikat, nama berbeda case,
    dan kolom yang hilang.
    """
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()

    # Flatten MultiIndex jika ada (kadang terjadi dari pandas read_sql)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join(str(c) for c in col).strip('_')
                      for col in df.columns]

    # Lowercase + strip semua nama kolom
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Hapus kolom duplikat (ambil yang pertama)
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    # Rename ke format proper case
    df = df.rename(columns=DISPLAY_MAP)

    # Pastikan Ticker ada — cek berbagai kemungkinan nama kolom
    if 'Ticker' not in df.columns:
        for alt in ['ticker', 'TICKER', 'kode', 'symbol', 'Symbol']:
            if alt in df.columns:
                df = df.rename(columns={alt: 'Ticker'})
                break

    # Bersihkan nilai
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
    if 'Close' in df.columns:
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    if 'CVI' in df.columns:
        df['CVI'] = pd.to_numeric(df['CVI'], errors='coerce')
    if 'Conf_Score' in df.columns:
        df['Conf_Score'] = pd.to_numeric(df['Conf_Score'], errors='coerce').fillna(0).astype(int)
    if 'Profit_Target' in df.columns:
        df['Profit_Target'] = pd.to_numeric(df['Profit_Target'], errors='coerce').fillna(0).astype(int)
    if 'ADX' in df.columns:
        df['ADX'] = pd.to_numeric(df['ADX'], errors='coerce').fillna(0)
    if 'MACD_PreCross' in df.columns:
        df['MACD_PreCross'] = df['MACD_PreCross'].astype(str).str.lower().isin(['true','1','yes'])
    if 'Is_Reversal' in df.columns:
        df['Is_Reversal'] = df['Is_Reversal'].astype(str).str.lower().isin(['true','1','yes'])
    if 'Alert_Flag' not in df.columns:
        df['Alert_Flag'] = ''
    df['Alert_Flag'] = df['Alert_Flag'].fillna('')
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

# ── Waktu Jakarta (GMT+7) ────────────────────────────────────────
_TZ_JKT = pytz.timezone('Asia/Jakarta')

def now_jkt():
    """Kembalikan datetime sekarang dalam timezone Jakarta (GMT+7)."""
    return datetime.now(_TZ_JKT)

def now_str_jkt():
    return now_jkt().strftime('%d %b %Y · %H:%M WIB')

# ── Portfolio persistence via Supabase ────────────────────────────
def ensure_portfolio_table():
    """Buat tabel portfolio jika belum ada."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS portfolio_tickers (
                    ticker VARCHAR(10) PRIMARY KEY,
                    added_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.commit()
    except Exception:
        pass

def load_portfolio():
    try:
        ensure_portfolio_table()
        df = pd.read_sql('SELECT ticker FROM portfolio_tickers ORDER BY added_at', engine)
        return df['ticker'].str.upper().tolist()
    except Exception:
        return []

def add_portfolio_ticker(ticker):
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO portfolio_tickers (ticker) VALUES (:t) ON CONFLICT DO NOTHING"
            ), {"t": ticker.upper().strip()})
            conn.commit()
        return True
    except Exception:
        return False

def remove_portfolio_ticker(ticker):
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM portfolio_tickers WHERE ticker = :t"), {"t": ticker.upper()})
            conn.commit()
        return True
    except Exception:
        return False

# ── Monitor persistence via Supabase ─────────────────────────────
def ensure_monitor_table():
    """Buat tabel monitor jika belum ada."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monitor_tickers (
                    ticker VARCHAR(10) PRIMARY KEY,
                    added_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.commit()
    except Exception:
        pass

def load_monitor():
    try:
        ensure_monitor_table()
        df = pd.read_sql('SELECT ticker FROM monitor_tickers ORDER BY added_at', engine)
        return df['ticker'].str.upper().tolist()
    except Exception:
        return []

def add_monitor_ticker(ticker):
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO monitor_tickers (ticker) VALUES (:t) ON CONFLICT DO NOTHING"
            ), {"t": ticker.upper().strip()})
            conn.commit()
        return True
    except Exception:
        return False

def remove_monitor_ticker(ticker):
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM monitor_tickers WHERE ticker = :t"), {"t": ticker.upper()})
            conn.commit()
        return True
    except Exception:
        return False

df_screener  = normalize_columns(fetch_cloud_data('screener_live'))
df_watchlist = normalize_columns(fetch_cloud_data('watchlist_live'))
df_history   = normalize_columns(fetch_cloud_data('screener_history'))

_all_raw = normalize_columns(fetch_cloud_data('all_stocks_live'))
if _all_raw.empty:
    frames = []
    if not df_screener.empty:  frames.append(df_screener)
    if not df_history.empty:
        hist_latest = (df_history.sort_values('Tanggal_Scan', ascending=False)
                       .drop_duplicates(subset='Ticker', keep='first')
                       .drop(columns=['Tanggal_Scan'], errors='ignore'))
        frames.append(hist_latest)
    df_all_stocks = pd.concat(frames, ignore_index=True).drop_duplicates(subset='Ticker', keep='first') if frames else pd.DataFrame()
else:
    df_all_stocks = _all_raw

# ── REVERSAL data loading ─────────────────────────────────────────
def normalize_reversal(df):
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    rev_map = {
        'ticker':'Ticker','close':'Close','bb_width_str':'BB_Width_Str',
        'vol_ratio':'Vol_Ratio','cmf':'CMF','ud_vol_ratio':'UD_Vol_Ratio',
        'macd':'MACD','macd_slope':'MACD_Slope',
        'rev_score':'Rev_Score','rev_drawdown':'Rev_Drawdown','rev_rsi':'Rev_RSI',
        'support':'Support','resistance':'Resistance',
    }
    df = df.rename(columns=rev_map)
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
    if 'Close' in df.columns:
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    return df

df_reversal = normalize_reversal(fetch_cloud_data('reversal_live'))

# ══════════════════════════════════════════════════════
# 4. HELPERS
# ══════════════════════════════════════════════════════
def classify_action(s):
    a = str(s).upper()
    if 'MACD PRE-CROSSOVER' in a:
        # Classify base action dulu, tapi tag sebagai macd
        if any(x in a for x in ["BUY","ACCUMULATION","NYICIL"]): return "buy", s
        return "macd", s
    if any(x in a for x in ["BUY","ACCUMULATION","NYICIL"]): return "buy", s
    if "SCALP" in a: return "scalp", "SCALPING"
    if any(x in a for x in ["WATCH","PANTAU","TIDUR"]): return "watch", s
    if "HOLD" in a: return "hold", "HOLD"
    if "HINDARI" in a: return "scalp", s   # merah seperti scalp
    return "wait", s

def badge(s):
    cls, lbl = classify_action(s)
    return f'<span class="badge b-{cls}">{lbl}</span>'

def macd_badge():
    return '<span class="badge b-macd">⚡ MACD PRE-CROSS</span>'

def alert_badge(flag_str):
    if not flag_str: return ''
    labels = {'CMF_DROP':'⚠ CMF Drop','VOL_SPIKE_DIST':'🚨 Vol Spike','STAGNANT_SPIKE':'🚨 Stagnan+Spike'}
    parts  = [labels.get(f, f) for f in str(flag_str).split('|') if f]
    return ' '.join(f'<span class="badge b-alert">{p}</span>' for p in parts)

def fmt_price(v):
    try: return f"Rp {float(v):,.0f}"
    except: return str(v) if v else "—"

def fmt_val(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    return str(v)

def to_excel(df, sheet="Data"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name=sheet)
    return buf.getvalue()

def get_latest_data_for_ticker(ticker):
    """Ambil data terbaru suatu ticker dari semua sumber."""
    for df_src, src_name in [
        (df_all_stocks, "Master DB"),
        (df_screener, "Screener Live"),
        (df_watchlist, "Watchlist"),
    ]:
        if not df_src.empty and 'Ticker' in df_src.columns:
            m = df_src[df_src['Ticker'] == ticker]
            if not m.empty:
                return m.iloc[0].to_dict(), src_name
    if not df_history.empty and 'Ticker' in df_history.columns:
        m = (df_history[df_history['Ticker'] == ticker]
             .sort_values('Tanggal_Scan', ascending=False).head(1)
             .drop(columns=['Tanggal_Scan'], errors='ignore'))
        if not m.empty:
            return m.iloc[0].to_dict(), "Histori"
    return None, None

def render_chart(ticker, row=None):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        st.info("Tambahkan `plotly` ke requirements.txt untuk chart.")
        return
    with st.spinner(f"Memuat chart {ticker}..."):
        df = fetch_chart_data(ticker)
    if df.empty:
        st.markdown('<div class="abox abox-warn">⚠ Data chart tidak tersedia.</div>', unsafe_allow_html=True)
        return

    df['MA20']  = df['Close'].rolling(20).mean()
    df['Bstd']  = df['Close'].rolling(20).std()
    df['BBu']   = df['MA20'] + 2*df['Bstd']
    df['BBl']   = df['MA20'] - 2*df['Bstd']
    df['VMA20'] = df['Volume'].rolling(20).mean()
    # MACD untuk chart
    ema12         = df['Close'].ewm(span=12, adjust=False).mean()
    ema26         = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD']    = ema12 - ema26
    df['MACDSig'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACDHist']= df['MACD'] - df['MACDSig']

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.55, 0.22, 0.23], vertical_spacing=0.02)

    # Candlestick + BB + MA20
    fig.add_trace(go.Candlestick(x=df.index,open=df['Open'],high=df['High'],
        low=df['Low'],close=df['Close'],name=ticker,
        increasing=dict(line=dict(color='#00e676',width=1),fillcolor='rgba(0,230,118,.75)'),
        decreasing=dict(line=dict(color='#ff1744',width=1),fillcolor='rgba(255,23,68,.75)')),row=1,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['BBu'],line=dict(color='rgba(255,171,0,.35)',width=1,dash='dot'),showlegend=False),row=1,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['BBl'],line=dict(color='rgba(255,171,0,.35)',width=1,dash='dot'),fill='tonexty',fillcolor='rgba(255,171,0,.04)',showlegend=False),row=1,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['MA20'],line=dict(color='rgba(64,196,255,.8)',width=1.5),showlegend=False),row=1,col=1)

    if row:
        try:
            sup = float(str(row.get('Support','')).replace(',','').replace('Rp','').strip())
            res = float(str(row.get('Resistance','')).replace(',','').replace('Rp','').strip())
            fig.add_hline(y=sup,line=dict(color='rgba(0,230,118,.5)',width=1,dash='dash'),
                annotation_text="S",annotation_font=dict(color='#00e676',size=10),row=1,col=1)
            fig.add_hline(y=res,line=dict(color='rgba(255,23,68,.5)',width=1,dash='dash'),
                annotation_text="R",annotation_font=dict(color='#ff1744',size=10),row=1,col=1)
        except: pass

    # Volume
    vc = ['#00e676' if c>=o else '#ff1744' for c,o in zip(df['Close'],df['Open'])]
    fig.add_trace(go.Bar(x=df.index,y=df['Volume'],marker_color=vc,opacity=.65,showlegend=False),row=2,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['VMA20'],line=dict(color='rgba(255,171,0,.9)',width=1.5),showlegend=False),row=2,col=1)

    # MACD panel
    fig.add_hline(y=0,line=dict(color='rgba(255,255,255,.15)',width=1),row=3,col=1)
    macd_colors = ['rgba(0,230,118,.7)' if v>=0 else 'rgba(255,23,68,.7)' for v in df['MACDHist']]
    fig.add_trace(go.Bar(x=df.index,y=df['MACDHist'],marker_color=macd_colors,opacity=.8,showlegend=False),row=3,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['MACD'],line=dict(color='#40c4ff',width=1.5),name='MACD',showlegend=False),row=3,col=1)
    fig.add_trace(go.Scatter(x=df.index,y=df['MACDSig'],line=dict(color='#ffab00',width=1,dash='dot'),name='Signal',showlegend=False),row=3,col=1)

    fig.update_layout(height=560,margin=dict(l=0,r=0,t=24,b=0),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='#080c10',
        font=dict(color='#768390',size=11,family='JetBrains Mono,monospace'),
        xaxis_rangeslider_visible=False,showlegend=False,
        xaxis=dict(gridcolor='#1e2d3d',zeroline=False),
        yaxis=dict(gridcolor='#1e2d3d',zeroline=False,tickformat=',.0f',tickprefix='Rp '),
        xaxis2=dict(gridcolor='#1e2d3d',zeroline=False),yaxis2=dict(gridcolor='#1e2d3d',zeroline=False),
        xaxis3=dict(gridcolor='#1e2d3d',zeroline=False),yaxis3=dict(gridcolor='#1e2d3d',zeroline=False))
    fig.update_xaxes(showspikes=True,spikecolor="#2a3f55",spikethickness=1)
    fig.update_yaxes(showspikes=True,spikecolor="#2a3f55",spikethickness=1)
    st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False})

# ══════════════════════════════════════════════════════
# 5. ENGINE SELECTOR + HEADER + SIDEBAR
# ══════════════════════════════════════════════════════
now_str = now_str_jkt()

# ── Header ────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:linear-gradient(135deg,#120600 0%,var(--bg-card) 55%,#071220 100%);
    border:1px solid var(--border);border-left:3px solid var(--fire);border-radius:12px;
    padding:18px 24px;margin-bottom:16px;display:flex;align-items:center;gap:16px;">
  <div style="font-size:36px;line-height:1;">🐉</div>
  <div>
    <div style="font-size:24px;font-weight:800;color:var(--fire);letter-spacing:-.5px;margin:0;">
        Dragon Fire Quant Dashboard</div>
    <div style="font-size:12px;color:var(--text-2);margin:2px 0 0;">
        Pusat Komando Velositas Modal & Detektor Akumulasi Bandar &nbsp;·&nbsp; {now_str}</div>
  </div>
</div>""", unsafe_allow_html=True)

# ── KPI metrics ───────────────────────────────────────────────────
n_sc    = len(df_screener)
n_wl    = len(df_watchlist)
n_all   = len(df_all_stocks)
n_rev   = len(df_reversal)
n_buy   = len(df_screener[df_screener['Rekomendasi_Action'].str.contains(
    'BUY|ACCUMULATION|NYICIL', na=False)]) if n_sc else 0
n_macd  = int(df_screener['MACD_PreCross'].sum()) \
    if n_sc and 'MACD_PreCross' in df_screener.columns else 0
n_alert = int(df_all_stocks['Alert_Flag'].str.len().gt(0).sum()) \
    if n_all and 'Alert_Flag' in df_all_stocks.columns else 0
n_hist  = df_history['Tanggal_Scan'].nunique() \
    if not df_history.empty and 'Tanggal_Scan' in df_history.columns else 0

# Confidence Score 5 count (new B3)
n_conf5 = int((df_screener['Conf_Score'] == 5).sum()) \
    if n_sc and 'Conf_Score' in df_screener.columns else 0

cm1,cm2,cm3,cm4,cm5,cm6,cm7 = st.columns([1,1,1,1,1,2,1.2])
with cm1: st.markdown(f'<div class="mcard"><div class="lbl">Screener Live</div>'
    f'<div class="val" style="color:var(--fire)">{n_sc}</div>'
    f'<div class="sub">Emiten aktif</div></div>', unsafe_allow_html=True)
with cm2: st.markdown(f'<div class="mcard"><div class="lbl">Sinyal BUY</div>'
    f'<div class="val" style="color:var(--green)">{n_buy}</div>'
    f'<div class="sub">Akumulasi terdeteksi</div></div>', unsafe_allow_html=True)
with cm3: st.markdown(f'<div class="mcard"><div class="lbl">⚡ MACD PreCross</div>'
    f'<div class="val" style="color:var(--purple)">{n_macd}</div>'
    f'<div class="sub">Prioritas masuk</div></div>', unsafe_allow_html=True)
with cm4: st.markdown(f'<div class="mcard"><div class="lbl">🔄 Reversal Watch</div>'
    f'<div class="val" style="color:var(--amber)">{n_rev}</div>'
    f'<div class="sub">Pola pembalikan</div></div>', unsafe_allow_html=True)
with cm5: st.markdown(f'<div class="mcard"><div class="lbl">⭐ Conf 5/5</div>'
    f'<div class="val" style="color:var(--green)">{n_conf5}</div>'
    f'<div class="sub">Konfluensi sempurna</div></div>', unsafe_allow_html=True)
with cm6:
    if n_sc > 0 and 'CVI' in df_screener.columns:
        # Prioritas: Conf Score 5 → MACD Pre-Cross → CVI tertinggi
        if n_conf5 > 0:
            top = df_screener[df_screener['Conf_Score'] == 5].sort_values(
                'CVI', ascending=False).iloc[0]
            top_tag = ' ⭐'
        else:
            macd_s = df_screener[df_screener['MACD_PreCross'] == True] \
                if 'MACD_PreCross' in df_screener.columns else pd.DataFrame()
            top = macd_s.sort_values('CVI', ascending=False).iloc[0] \
                if not macd_s.empty else df_screener.sort_values('CVI', ascending=False).iloc[0]
            top_tag = ' ⚡' if not macd_s.empty else ''
        tier  = fmt_val(top.get('CVI_Tier', '—'))
        st.markdown(f"""<div class="mcard">
            <div class="lbl">🥇 Top Priority{top_tag}</div>
            <div class="val" style="color:var(--amber);font-size:17px;">{top.get('Ticker','—')}</div>
            <div class="sub">CVI {fmt_val(top.get('CVI','—'))} [{tier}]
            · {fmt_val(top.get('Potensial_Upsize','—'))}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="mcard"><div class="lbl">Top Priority</div>'
                    '<div class="val">—</div></div>', unsafe_allow_html=True)
with cm7:
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if st.button('🔄 Refresh Data', use_container_width=True, key='refresh_dragon'):
        st.cache_data.clear(); st.rerun()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sb-logo">🐉 Dragon Fire</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sect">STATUS LIVE</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Screener Aktif</div>'
        f'<div class="val" style="color:var(--fire)">{n_sc}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Sinyal BUY</div>'
        f'<div class="val" style="color:var(--green)">{n_buy}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">⚡ MACD PreCross</div>'
        f'<div class="val" style="color:var(--purple)">{n_macd}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">🔄 Reversal Watch</div>'
        f'<div class="val" style="color:var(--amber)">{n_rev}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">⭐ Conf Score 5/5</div>'
        f'<div class="val" style="color:var(--green)">{n_conf5}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">🚨 Alert Aktif</div>'
        f'<div class="val" style="color:var(--red)">{n_alert}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Master Database</div>'
        f'<div class="val">{n_all} emiten</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sb-stat"><div class="lbl">Riwayat Tersimpan</div>'
        f'<div class="val">{n_hist} hari</div></div>', unsafe_allow_html=True)
    st.markdown('---')
    st.caption(f'Dragon Fire v5.0 · KangTao Cari Cuan\n\n{now_str}')

# ══════════════════════════════════════════════════════
# 6. MAIN TABS
# ══════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    '📊  LIVE SCREENER',
    '📋  WATCHLIST',
    '💼  PORTOFOLIO SAYA',
    '👁  MONITOR',
    '🔍  DIAGNOSTIK TICKER',
    '📅  HISTORI HARIAN'
])

col_eng_lbl, col_fire, col_tiger, col_spacer = st.columns([1.5, 1.5, 1.5, 8])
with col_eng_lbl:
    st.markdown("<div style='padding-top:10px;font-size:11px;font-weight:700;"
                "color:#768390;text-transform:uppercase;letter-spacing:.8px;"
                "'>Pilih Mesin</div>", unsafe_allow_html=True)
with col_fire:
    if st.button("🐉 Dragon Fire", use_container_width=True,
                 type="primary" if st.session_state.active_engine == 'dragon' else "secondary"):
        st.session_state.active_engine = 'dragon'; st.rerun()

# TAB 1 · LIVE SCREENER
# ─────────────────────────────────────────────────────
with tab1:
  if df_screener.empty:
      st.markdown('<div class="abox abox-warn">⚠ Belum ada data screener_live. Jalankan dragon_fire.py terlebih dahulu.</div>', unsafe_allow_html=True)
  else:
      # Pisahkan MACD pre-crossover dulu
      has_macd_col = 'MACD_PreCross' in df_screener.columns
      df_macd_picks = df_screener[df_screener['MACD_PreCross'] == True].sort_values('CVI', ascending=False) if has_macd_col else pd.DataFrame()
      df_normal     = df_screener[df_screener['MACD_PreCross'] != True].sort_values('CVI', ascending=False) if has_macd_col else df_screener.sort_values('CVI', ascending=False)

      # MACD Pre-Crossover highlight section
      if not df_macd_picks.empty:
          st.markdown('<div class="abox abox-macd">⚡ Saham berikut memiliki MACD Fast Line hampir crossing zero — potensi momentum terkuat hari ini, diprioritaskan untuk masuk posisi.</div>', unsafe_allow_html=True)
          st.markdown('<div class="slabel">⚡ MACD PRE-CROSSOVER PICKS — PRIORITAS TERTINGGI</div>', unsafe_allow_html=True)
          macd_cols = st.columns(min(len(df_macd_picks), 4))
          for i, (_, r) in enumerate(df_macd_picks.head(4).iterrows()):
              with macd_cols[i]:
                  af = alert_badge(r.get('Alert_Flag',''))
                  st.markdown(f"""
                  <div class="pick macd-pick">
                    <div class="pick-medal">⚡ MACD Pre-Cross #{i+1}</div>
                    <div class="pick-name">{r.get('Ticker','—')}</div>
                    <div class="pick-price">{fmt_price(r.get('Close'))}</div>
                    <div class="pick-meta">
                      CVI <strong style="color:var(--amber)">{fmt_val(r.get('CVI'))}</strong>
                      &nbsp;·&nbsp; {fmt_val(r.get('Potensial_Upsize'))}<br>
                      ⏱ {fmt_val(r.get('Hari_Ke_Breakout'))}
                    </div>
                    {macd_badge()}
                    {badge(r.get('Rekomendasi_Action',''))}
                    {af}
                  </div>""", unsafe_allow_html=True)
          st.write("")

      # Top 3 regular picks
      st.markdown('<div class="slabel">🏆 Top CVI Picks — Ranking Hari Ini</div>', unsafe_allow_html=True)
      top3   = df_normal.head(3)
      medals = ['g1','g2','g3']
      ranks  = ['🥇 Alpha #1','🥈 Runner Up','🥉 Momentum']
      cols3  = st.columns(min(len(top3),3))
      for i, (_, r) in enumerate(top3.iterrows()):
          with cols3[i]:
              af = alert_badge(r.get('Alert_Flag',''))
              st.markdown(f"""
              <div class="pick {medals[i]}">
                <div class="pick-medal">{ranks[i]}</div>
                <div class="pick-name">{r.get('Ticker','—')}</div>
                <div class="pick-price">{fmt_price(r.get('Close'))}</div>
                <div class="pick-meta">CVI <strong style="color:var(--amber)">{fmt_val(r.get('CVI'))}</strong>
                  &nbsp;·&nbsp; {fmt_val(r.get('Potensial_Upsize'))}<br>⏱ {fmt_val(r.get('Hari_Ke_Breakout'))}</div>
                {badge(r.get('Rekomendasi_Action',''))}{af}
              </div>""", unsafe_allow_html=True)

      st.write("")
      cf1, cf2, cf3 = st.columns([3,2,1.5])
      with cf1:
          opts = sorted(df_screener['Rekomendasi_Action'].dropna().unique().tolist())
          defs = [a for a in opts if any(x in a.upper() for x in ["BUY","SCALP","ACCUMULATION","PANTAU","TIDUR","MACD"])] or opts
          sel  = st.multiselect("⚡ Filter Rekomendasi", options=opts, default=defs)
      with cf2:
          srt_col = st.selectbox("🔃 Urutkan", ['CVI','Close','Vol_Ratio','CMF','MACD'], index=0)
      with cf3:
          srt_dir = st.selectbox("Arah", ["Tertinggi ↓","Terendah ↑"], index=0)

      df_d = df_screener.copy()
      if sel: df_d = df_d[df_d['Rekomendasi_Action'].isin(sel)]
      if srt_col in df_d.columns:
          df_d = df_d.sort_values(srt_col, ascending=(srt_dir=="Terendah ↑"))

      # Show alert rows highlighted
      if 'Alert_Flag' in df_d.columns:
          n_flagged = df_d['Alert_Flag'].str.len().gt(0).sum()
          if n_flagged > 0:
              st.markdown(f'<div class="abox abox-warn">🚨 {n_flagged} emiten dalam tabel ini memiliki alert anti-trap aktif — perhatikan kolom Alert_Flag.</div>', unsafe_allow_html=True)

      st.markdown(f'<div class="slabel">TABEL SCREENER — {len(df_d)} Emiten</div>', unsafe_allow_html=True)
      dcols = [c for c in ['Ticker','Close','Support','Resistance','BB_Width_Str',
                            'Vol_Ratio','Vol_Velocity','CMF','UD_Vol_Ratio',
                            'Hari_Ke_Breakout','Potensial_Upsize','CVI',
                            'CVI_Tier','Conf_Score','Profit_Target',
                            'MACD','MACD_PreCross','Alert_Flag',
                            'Analisis_Kesimpulan','Rekomendasi_Action'] if c in df_d.columns]
      st.dataframe(df_d[dcols].reset_index(drop=True), use_container_width=True, height=400,
          column_config={
              "Ticker":         st.column_config.TextColumn("Ticker", width=70, pinned=True),
              "Close":          st.column_config.NumberColumn("Close", format="Rp %,.0f"),
              "CVI":            st.column_config.NumberColumn("CVI", format="%.3f"),
              "CVI_Tier":       st.column_config.TextColumn("CVI Tier", width=80),
              "Conf_Score":     st.column_config.ProgressColumn("⭐ Conf", min_value=0, max_value=5, format="%.0f"),
              "Profit_Target":  st.column_config.NumberColumn("Target Profit", format="Rp %,.0f"),
              "Vol_Ratio":      st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
              "MACD_PreCross":  st.column_config.CheckboxColumn("⚡ MACD"),
              "Alert_Flag":     st.column_config.TextColumn("🚨 Alert", width=120),
              "Rekomendasi_Action": st.column_config.TextColumn("Action", width=200),
          })
      st.download_button("⬇️ Download Screener (.xlsx)",
          data=to_excel(df_d[dcols], "Screener_Live"),
          file_name=f"DragonFire_Screener_{now_jkt().strftime('%Y%m%d')}.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

      # ── REVERSAL WATCH SECTION ────────────────────────────────
      st.write("")
      st.markdown('<div class="section">🔄 REVERSAL WATCH — Saham Pola Pembalikan (di luar screener utama)</div>', unsafe_allow_html=True)
      if df_reversal.empty:
          st.markdown('<div class="abox abox-info">💡 Belum ada data reversal_live. Jalankan dragon_fire.py terbaru untuk mengaktifkan fitur ini.</div>', unsafe_allow_html=True)
      else:
          st.markdown('<div class="abox abox-warn">🔄 Saham-saham berikut <strong>tidak lolos screener utama</strong> (BB Width terlalu lebar = sudah dalam koreksi besar), namun menunjukkan sinyal teknikal pembalikan: RSI oversold, CMF mulai membalik, MACD histogram divergence bullish, dan volume pembeli kembali aktif. Gunakan sebagai watchlist reversal — entry <strong>hanya setelah ada konfirmasi candle hijau kuat + volume di atas rata-rata.</strong></div>', unsafe_allow_html=True)

          # Sort by Rev_Score desc
          df_rev_show = df_reversal.sort_values('Rev_Score', ascending=False) if 'Rev_Score' in df_reversal.columns else df_reversal

          # Top 3 reversal cards
          rev_top = df_rev_show.head(3)
          if len(rev_top) > 0:
              rev_cols_card = st.columns(min(3, len(rev_top)))
              for i, (_, r) in enumerate(rev_top.iterrows()):
                  with rev_cols_card[i]:
                      drw = fmt_val(r.get('Rev_Drawdown', '—'))
                      rsi = fmt_val(r.get('Rev_RSI', '—'))
                      scr = fmt_val(r.get('Rev_Score', '—'))
                      st.markdown(f"""
                      <div style="background:var(--bg-card);border:1px solid rgba(255,171,0,.35);
                          border-radius:10px;padding:14px 16px;position:relative;overflow:hidden;">
                        <div style="position:absolute;top:0;left:0;right:0;height:2.5px;
                            background:linear-gradient(90deg,var(--amber),#ffd740);"></div>
                        <div style="font-size:22px;font-weight:800;font-family:var(--mono)">{r.get('Ticker','—')}</div>
                        <div style="font-size:13px;font-weight:700;color:var(--blue)">Rp {fmt_price(r.get('Close','—'))}</div>
                        <div style="font-size:11px;color:var(--muted);margin-top:7px;line-height:1.8;">
                          Koreksi dari High <strong style="color:var(--red)">{drw}%</strong><br>
                          RSI <strong style="color:var(--amber)">{rsi}</strong>
                          &nbsp;·&nbsp; Skor <strong style="color:var(--amber)">{scr}/5</strong><br>
                          CMF <strong>{fmt_val(r.get('CMF','—'))}</strong>
                          &nbsp;·&nbsp; UD Vol <strong>{fmt_val(r.get('UD_Vol_Ratio','—'))}</strong>
                        </div>
                        <span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;font-family:var(--mono);background:rgba(255,171,0,.12);color:var(--amber);border:1px solid rgba(255,171,0,.3);margin-top:8px;">🔄 REVERSAL WATCH</span>
                      </div>""", unsafe_allow_html=True)

          # Tabel reversal lengkap
          rev_tbl_cols = [c for c in ['Ticker','Close','BB_Width_Str','Vol_Ratio',
                                       'CMF','UD_Vol_Ratio','MACD','MACD_Slope',
                                       'Rev_Score','Rev_Drawdown','Rev_RSI',
                                       'Support','Resistance']
                          if c in df_rev_show.columns]
          if rev_tbl_cols:
              st.write("")
              st.dataframe(df_rev_show[rev_tbl_cols].reset_index(drop=True),
                  use_container_width=True, height=300,
                  column_config={
                      "Ticker":      st.column_config.TextColumn("Ticker", width=70, pinned=True),
                      "Close":       st.column_config.NumberColumn("Close",     format="Rp %,.0f"),
                      "Support":     st.column_config.NumberColumn("Support",   format="Rp %,.0f"),
                      "Resistance":  st.column_config.NumberColumn("Resistance",format="Rp %,.0f"),
                      "Rev_Score":   st.column_config.ProgressColumn("Rev Score", min_value=0, max_value=5, format="%.0f"),
                      "Rev_Drawdown":st.column_config.NumberColumn("Koreksi %", format="%.1f%%"),
                      "Rev_RSI":     st.column_config.NumberColumn("RSI", format="%.1f"),
                  })
              st.download_button("⬇️ Download Reversal Watch (.xlsx)",
                  data=to_excel(df_rev_show[rev_tbl_cols], "Reversal_Watch"),
                  file_name=f"DragonFire_Reversal_{now_jkt().strftime('%Y%m%d')}.xlsx",
                  mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────────────
# TAB 2 · WATCHLIST — Upload file harian saja
# ─────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="slabel">📋 Watchlist — Upload File Harian</div>', unsafe_allow_html=True)

    # Upload file watchlist harian
    st.markdown('<div class="abox abox-info">Upload file watchlist harian Anda (.xlsx). Dashboard akan mencocokkan setiap ticker dengan data screener terbaru dari database secara otomatis.</div>', unsafe_allow_html=True)

    uploaded_wl = st.file_uploader("Upload Watchlist Excel (.xlsx)", type=['xlsx'], key="wl_upload",
                                   label_visibility="collapsed")

    if uploaded_wl is not None:
        try:
            df_wl_upload = pd.read_excel(uploaded_wl)
            df_wl_upload.columns = df_wl_upload.columns.str.strip().str.upper()
            w_col_candidates = [c for c in df_wl_upload.columns if c in ['TICKER','KODE','KODE SAHAM']]
            if not w_col_candidates:
                st.markdown('<div class="abox abox-err">❌ Kolom TICKER tidak ditemukan di file upload.</div>', unsafe_allow_html=True)
            else:
                w_col       = w_col_candidates[0]
                # Bersihkan ticker
                wl_tickers  = [str(t).split('.')[0].strip().upper()
                                for t in df_wl_upload[w_col].dropna()]
                wl_tickers  = [t for t in wl_tickers if t]

                # Cocokkan dengan all_stocks_live (data screener terbaru)
                wl_results = []
                not_found  = []
                for t in wl_tickers:
                    row_data, src = get_latest_data_for_ticker(t)
                    if row_data:
                        row_data['_source'] = src
                        wl_results.append(row_data)
                    else:
                        not_found.append(t)

                if wl_results:
                    df_wl_result = pd.DataFrame(wl_results)
                    # Sort: alert + MACD dulu
                    has_pc = 'MACD_PreCross' in df_wl_result.columns
                    has_af = 'Alert_Flag' in df_wl_result.columns
                    has_cv = 'CVI' in df_wl_result.columns
                    if has_pc and has_cv:
                        df_wl_result['_sort_macd'] = df_wl_result['MACD_PreCross'].astype(int)
                        df_wl_result = df_wl_result.sort_values(['_sort_macd','CVI'], ascending=[False,False])
                        df_wl_result = df_wl_result.drop(columns=['_sort_macd'])

                    # Summary stats
                    n_wl_buy  = df_wl_result['Rekomendasi_Action'].str.contains("BUY|ACCUMULATION", na=False).sum() if 'Rekomendasi_Action' in df_wl_result.columns else 0
                    n_wl_macd = int(df_wl_result['MACD_PreCross'].sum()) if has_pc else 0
                    n_wl_alert= df_wl_result['Alert_Flag'].str.len().gt(0).sum() if has_af else 0
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("Total Watchlist", len(wl_tickers))
                    c2.metric("Sinyal BUY", n_wl_buy)
                    c3.metric("⚡ MACD PreCross", n_wl_macd)
                    c4.metric("🚨 Alert Aktif", n_wl_alert)

                    if n_wl_alert > 0:
                        st.markdown(f'<div class="abox abox-err">🚨 {n_wl_alert} saham watchlist Anda memiliki alert anti-trap! Periksa kolom Alert_Flag segera.</div>', unsafe_allow_html=True)

                    # Support & Resistance ditambahkan
                    show_cols = [c for c in ['Ticker','Close','Support','Resistance','CMF','UD_Vol_Ratio',
                                             'BB_Width_Str','Vol_Ratio','Vol_Velocity','Hari_Ke_Breakout',
                                             'Potensial_Upsize','CVI','MACD','MACD_PreCross',
                                             'Alert_Flag','Analisis_Kesimpulan','Rekomendasi_Action']
                                 if c in df_wl_result.columns]
                    st.dataframe(df_wl_result[show_cols].reset_index(drop=True),
                        use_container_width=True, height=420,
                        column_config={
                            "Ticker":        st.column_config.TextColumn("Ticker",      width=70, pinned=True),
                            "Close":         st.column_config.NumberColumn("Close",      format="Rp %,.0f"),
                            "Support":       st.column_config.NumberColumn("Support",    format="Rp %,.0f"),
                            "Resistance":    st.column_config.NumberColumn("Resistance", format="Rp %,.0f"),
                            "CVI":           st.column_config.NumberColumn("CVI",        format="%.3f"),
                            "Vol_Ratio":     st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
                            "MACD_PreCross": st.column_config.CheckboxColumn("⚡ MACD"),
                            "Alert_Flag":    st.column_config.TextColumn("🚨 Alert",    width=130),
                            "Rekomendasi_Action": st.column_config.TextColumn("Action",  width=200),
                        })
                    if not_found:
                        st.markdown(f'<div class="abox abox-warn">⚠ {len(not_found)} ticker tidak ditemukan di database: {", ".join(not_found[:10])}{"..." if len(not_found)>10 else ""}</div>', unsafe_allow_html=True)
                    st.download_button("⬇️ Download Hasil Watchlist (.xlsx)",
                        data=to_excel(df_wl_result[show_cols], "Watchlist_Analisis"),
                        file_name=f"DragonFire_Watchlist_{now_jkt().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.markdown('<div class="abox abox-warn">⚠ Tidak ada ticker dari watchlist yang ditemukan di database. Pastikan dragon_fire.py sudah dijalankan hari ini.</div>', unsafe_allow_html=True)
        except Exception as ex:
            st.markdown(f'<div class="abox abox-err">❌ Gagal membaca file: {ex}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="abox abox-warn">💡 Belum ada file yang diupload. Upload file watchlist harian Anda di atas.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────
# TAB 3 · PORTOFOLIO SAYA
# ─────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="slabel">💼 Portofolio Saya — Saham yang Sudah Dipegang</div>', unsafe_allow_html=True)
    st.markdown('<div class="abox abox-info">Ticker yang Anda tambahkan di sini akan tersimpan permanen di database dan dipantau setiap hari. Peringatan distribusi akan muncul secara otomatis.</div>', unsafe_allow_html=True)

    # Input tambah ticker
    p_col1, p_col2 = st.columns([3, 1])
    with p_col1:
        new_ticker = st.text_input("", placeholder="Ketik kode saham lalu klik Tambah (misal: BBCA)",
                                   key="port_input", label_visibility="collapsed").strip().upper()
    with p_col2:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        add_btn = st.button("➕ Tambah ke Portofolio", use_container_width=True)

    if add_btn and new_ticker:
        if add_portfolio_ticker(new_ticker):
            st.success(f"✅ {new_ticker} berhasil ditambahkan ke portofolio.")
            st.rerun()
        else:
            st.warning(f"⚠ Gagal menambahkan {new_ticker}. Mungkin sudah ada atau terjadi error database.")

    # Load dan tampilkan portofolio
    portfolio_tickers = load_portfolio()

    if not portfolio_tickers:
        st.markdown('<div class="abox abox-warn">💡 Portofolio Anda masih kosong. Tambahkan ticker saham yang sudah Anda beli di atas.</div>', unsafe_allow_html=True)
    else:
        # Cek setiap ticker untuk data terbaru + alerts
        port_data   = []
        danger_list = []
        macd_list   = []

        for t in portfolio_tickers:
            row_data, src = get_latest_data_for_ticker(t)
            if row_data:
                row_data['_src'] = src
                port_data.append((t, row_data))
                action    = str(row_data.get('Rekomendasi_Action', ''))
                alert_flag= str(row_data.get('Alert_Flag', ''))
                if 'HINDARI' in action.upper() or 'DISTRIBUSI' in action.upper() or alert_flag:
                    danger_list.append(t)
                if row_data.get('MACD_PreCross', False):
                    macd_list.append(t)
            else:
                port_data.append((t, None))

        # Summary
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Dipegang", len(portfolio_tickers))
        c2.metric("🚨 Perlu Perhatian", len(danger_list))
        c3.metric("⚡ MACD Naik", len(macd_list))
        c4.metric("Tidak Ada Data", sum(1 for _, r in port_data if r is None))

        if danger_list:
            st.markdown(f'<div class="abox abox-err">🚨 <strong>PERINGATAN DISTRIBUSI</strong> — Saham berikut menunjukkan sinyal berbahaya: <strong>{", ".join(danger_list)}</strong>. Pertimbangkan untuk cut loss atau kurangi posisi.</div>', unsafe_allow_html=True)

        if macd_list:
            st.markdown(f'<div class="abox abox-macd">⚡ Saham berikut dalam portofolio Anda memiliki MACD mendekati crossing zero (momentum membaik): <strong>{", ".join(macd_list)}</strong></div>', unsafe_allow_html=True)

        st.markdown('<div class="slabel">STATUS TIAP SAHAM</div>', unsafe_allow_html=True)

        # Kartu per saham
        for ticker, row_data in port_data:
            if row_data is None:
                st.markdown(f"""
                <div class="port-card">
                  <span class="port-ticker">{ticker}</span>
                  <span style="color:var(--text-2);font-size:12px;">Data tidak ditemukan di DB</span>
                  <span class="port-alert port-alert-warn">NO DATA</span>
                </div>""", unsafe_allow_html=True)
                continue

            action      = str(row_data.get('Rekomendasi_Action', '—'))
            alert_flag  = str(row_data.get('Alert_Flag', ''))
            is_macd     = row_data.get('MACD_PreCross', False)
            is_danger   = 'HINDARI' in action.upper() or 'DISTRIBUSI' in action.upper() or bool(alert_flag)
            close_price = fmt_price(row_data.get('Close'))
            cvi_val     = fmt_val(row_data.get('CVI'))
            est_hari    = fmt_val(row_data.get('Hari_Ke_Breakout'))
            cmf_val     = fmt_val(row_data.get('CMF'))
            ud_val      = fmt_val(row_data.get('UD_Vol_Ratio'))

            # Tentukan warna alert card
            if is_danger:
                alert_class, alert_text = "port-alert-danger", "⚠ WASPADAI"
            elif is_macd:
                alert_class, alert_text = "port-alert-macd", "⚡ MACD ↑"
            elif 'BUY' in action.upper() or 'ACCUMULATION' in action.upper():
                alert_class, alert_text = "port-alert-ok", "HOLD"
            else:
                alert_class, alert_text = "port-alert-warn", "PANTAU"

            # Alert detail badges
            alert_detail = ""
            if alert_flag:
                labels = {'CMF_DROP':'CMF Drop','VOL_SPIKE_DIST':'Vol Spike','STAGNANT_SPIKE':'Stagnan+Spike'}
                for f in alert_flag.split('|'):
                    if f: alert_detail += f' <span class="badge b-alert">{labels.get(f,f)}</span>'
            if is_macd:
                alert_detail += ' <span class="badge b-macd">⚡ MACD PreCross</span>'

            st.markdown(f"""
            <div class="port-card" style="{'border-color:rgba(255,23,68,.4);' if is_danger else ('border-color:rgba(192,132,252,.35);' if is_macd else '')}">
              <div>
                <span class="port-ticker">{ticker}</span>
                <span style="color:var(--text-2);font-size:11px;margin-left:8px;">{row_data.get('_src','')}</span>
              </div>
              <div style="flex:1;padding:0 12px;">
                <div style="font-size:12px;color:var(--text-2);line-height:1.7;">
                  CMF <strong style="color:var(--text)">{cmf_val}</strong>
                  &nbsp;·&nbsp; UD Vol <strong style="color:var(--text)">{ud_val}</strong>
                  &nbsp;·&nbsp; Est. <strong style="color:var(--text)">{est_hari}</strong>
                  &nbsp;·&nbsp; CVI <strong style="color:var(--amber)">{cvi_val}</strong>
                </div>
                <div style="font-size:11px;color:var(--text-2);margin-top:2px;">
                  {action[:80]}{'…' if len(action)>80 else ''}
                </div>
                {f'<div style="margin-top:4px">{alert_detail}</div>' if alert_detail else ''}
              </div>
              <div style="text-align:right;">
                <div class="port-price">{close_price}</div>
                <span class="port-alert {alert_class}">{alert_text}</span>
              </div>
            </div>""", unsafe_allow_html=True)

            # Tombol hapus per saham
            if st.button(f"🗑 Hapus {ticker} dari portofolio", key=f"del_{ticker}"):
                remove_portfolio_ticker(ticker)
                st.rerun()

        # Download snapshot portofolio
        if port_data:
            snap_rows = [r for _, r in port_data if r is not None]
            if snap_rows:
                df_snap = pd.DataFrame(snap_rows)
                df_snap = df_snap.drop(columns=['_src'], errors='ignore')
                snap_cols = [c for c in ['Ticker','Close','CMF','UD_Vol_Ratio','BB_Width_Str',
                                          'Vol_Ratio','Hari_Ke_Breakout','Potensial_Upsize',
                                          'CVI','MACD','MACD_PreCross','Alert_Flag',
                                          'Analisis_Kesimpulan','Rekomendasi_Action']
                              if c in df_snap.columns]
                st.write("")
                st.download_button("⬇️ Download Snapshot Portofolio (.xlsx)",
                    data=to_excel(df_snap[snap_cols], "Portofolio"),
                    file_name=f"DragonFire_Portfolio_{now_jkt().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────────────
# TAB 4 · MONITOR — Saham Pantau Manual
# ─────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="slabel">👁 Monitor — Daftar Saham Pantau Manual</div>', unsafe_allow_html=True)
    st.markdown('<div class="abox abox-info">Tambahkan ticker saham yang ingin Anda pantau secara khusus — bisa dari hasil screening, rekomendasi eksternal, atau saham yang sedang dalam radar Anda. Data diperbarui otomatis setiap kali dragon_fire.py dijalankan.</div>', unsafe_allow_html=True)

    # Input tambah ticker
    m_col1, m_col2 = st.columns([3, 1])
    with m_col1:
        new_mon_ticker = st.text_input("", placeholder="Ketik kode saham lalu klik Tambah (misal: BBCA, GDYR, CMPP)",
                                       key="mon_input", label_visibility="collapsed").strip().upper()
    with m_col2:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        add_mon_btn = st.button("➕ Tambah ke Monitor", use_container_width=True)

    if add_mon_btn and new_mon_ticker:
        if add_monitor_ticker(new_mon_ticker):
            st.success(f"✅ {new_mon_ticker} berhasil ditambahkan ke daftar monitor.")
            st.rerun()
        else:
            st.warning(f"⚠ Gagal menambahkan {new_mon_ticker}. Mungkin sudah ada atau terjadi error database.")

    monitor_tickers = load_monitor()

    if not monitor_tickers:
        st.markdown('<div class="abox abox-warn">💡 Daftar monitor masih kosong. Tambahkan ticker yang ingin dipantau di atas.</div>', unsafe_allow_html=True)
    else:
        # Ambil data terbaru untuk semua ticker monitor
        mon_data   = []
        danger_list_m = []
        macd_list_m   = []

        for t in monitor_tickers:
            row_data, src = get_latest_data_for_ticker(t)
            if row_data:
                row_data['_src'] = src
                mon_data.append((t, row_data))
                action     = str(row_data.get('Rekomendasi_Action', ''))
                alert_flag = str(row_data.get('Alert_Flag', ''))
                if 'HINDARI' in action.upper() or 'DISTRIBUSI' in action.upper() or alert_flag:
                    danger_list_m.append(t)
                if row_data.get('MACD_PreCross', False):
                    macd_list_m.append(t)
            else:
                mon_data.append((t, None))

        # Summary metrics
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Monitor",    len(monitor_tickers))
        c2.metric("🚨 Perlu Perhatian", len(danger_list_m))
        c3.metric("⚡ MACD Naik",      len(macd_list_m))
        c4.metric("Tidak Ada Data",   sum(1 for _, r in mon_data if r is None))

        if danger_list_m:
            st.markdown(f'<div class="abox abox-err">🚨 <strong>PERINGATAN</strong> — Saham berikut menunjukkan sinyal distribusi: <strong>{", ".join(danger_list_m)}</strong>. Evaluasi segera.</div>', unsafe_allow_html=True)
        if macd_list_m:
            st.markdown(f'<div class="abox abox-macd">⚡ Saham berikut memiliki MACD mendekati crossing zero: <strong>{", ".join(macd_list_m)}</strong></div>', unsafe_allow_html=True)

        st.markdown('<div class="slabel">TABEL STATUS REAL-TIME</div>', unsafe_allow_html=True)

        # Susun sebagai tabel (bukan kartu seperti portfolio)
        valid_rows = [(t, r) for t, r in mon_data if r is not None]
        if valid_rows:
            tbl_data = []
            for t, r in valid_rows:
                action     = str(r.get('Rekomendasi_Action', '—'))
                alert_flag = str(r.get('Alert_Flag', ''))
                is_danger  = 'HINDARI' in action.upper() or 'DISTRIBUSI' in action.upper() or bool(alert_flag)
                is_macd    = r.get('MACD_PreCross', False)
                tbl_data.append({
                    'Ticker':              t,
                    'Close':               r.get('Close'),
                    'Support':             r.get('Support'),
                    'Resistance':          r.get('Resistance'),
                    'CMF':                 r.get('CMF'),
                    'UD_Vol_Ratio':        r.get('UD_Vol_Ratio'),
                    'BB_Width_Str':        r.get('BB_Width_Str'),
                    'Vol_Ratio':           r.get('Vol_Ratio'),
                    'Hari_Ke_Breakout':    r.get('Hari_Ke_Breakout'),
                    'Potensial_Upsize':    r.get('Potensial_Upsize'),
                    'CVI':                 r.get('CVI'),
                    'MACD':                r.get('MACD'),
                    'MACD_PreCross':       is_macd,
                    'Alert_Flag':          alert_flag,
                    'Analisis_Kesimpulan': r.get('Analisis_Kesimpulan'),
                    'Rekomendasi_Action':  action,
                    '_src':                r.get('_src', ''),
                })

            df_mon_tbl = pd.DataFrame(tbl_data)
            # Sort: danger atas, lalu MACD, lalu CVI
            df_mon_tbl['_danger'] = df_mon_tbl['Ticker'].isin(danger_list_m).astype(int)
            df_mon_tbl['_macd']   = df_mon_tbl['MACD_PreCross'].astype(int)
            if 'CVI' in df_mon_tbl.columns:
                df_mon_tbl = df_mon_tbl.sort_values(['_danger','_macd','CVI'], ascending=[False,False,False])
            df_mon_tbl = df_mon_tbl.drop(columns=['_danger','_macd','_src'], errors='ignore')

            disp_cols = [c for c in ['Ticker','Close','Support','Resistance','CMF','UD_Vol_Ratio',
                                      'BB_Width_Str','Vol_Ratio','Hari_Ke_Breakout','Potensial_Upsize',
                                      'CVI','MACD','MACD_PreCross','Alert_Flag',
                                      'Analisis_Kesimpulan','Rekomendasi_Action']
                         if c in df_mon_tbl.columns]
            st.dataframe(df_mon_tbl[disp_cols].reset_index(drop=True),
                use_container_width=True, height=420,
                column_config={
                    "Ticker":        st.column_config.TextColumn("Ticker",      width=70, pinned=True),
                    "Close":         st.column_config.NumberColumn("Close",      format="Rp %,.0f"),
                    "Support":       st.column_config.NumberColumn("Support",    format="Rp %,.0f"),
                    "Resistance":    st.column_config.NumberColumn("Resistance", format="Rp %,.0f"),
                    "CVI":           st.column_config.NumberColumn("CVI",        format="%.3f"),
                    "Vol_Ratio":     st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
                    "MACD_PreCross": st.column_config.CheckboxColumn("⚡ MACD"),
                    "Alert_Flag":    st.column_config.TextColumn("🚨 Alert",    width=130),
                    "Rekomendasi_Action": st.column_config.TextColumn("Action",  width=200),
                })

            # Download snapshot
            st.download_button("⬇️ Download Snapshot Monitor (.xlsx)",
                data=to_excel(df_mon_tbl[disp_cols], "Monitor"),
                file_name=f"DragonFire_Monitor_{now_jkt().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Ticker tidak ada data
        no_data_tickers = [t for t, r in mon_data if r is None]
        if no_data_tickers:
            st.markdown(f'<div class="abox abox-warn">⚠ Ticker berikut tidak ditemukan di database: <strong>{", ".join(no_data_tickers)}</strong></div>', unsafe_allow_html=True)

        # Hapus ticker dari monitor
        st.markdown('<div class="slabel" style="margin-top:14px">KELOLA DAFTAR MONITOR</div>', unsafe_allow_html=True)
        cols_del = st.columns(min(len(monitor_tickers), 6))
        for i, t in enumerate(monitor_tickers):
            with cols_del[i % 6]:
                if st.button(f"🗑 {t}", key=f"del_mon_{t}", use_container_width=True):
                    remove_monitor_ticker(t)
                    st.rerun()

# ─────────────────────────────────────────────────────
# TAB 5 · DIAGNOSTIK TICKER
# ─────────────────────────────────────────────────────
with tab5:
  st.markdown('<div class="slabel">🔍 Diagnostik & Chart Per Emiten</div>', unsafe_allow_html=True)
  st.markdown(f'<div class="abox abox-info">📡 Basis data: <strong>{n_all} emiten</strong>. Ketik kode saham BEI (tanpa .JK).</div>', unsafe_allow_html=True)

  ci, cb = st.columns([4, 1])
  with ci:
      search_ticker = st.text_input("", placeholder="Contoh: BBCA · GLVA · MASB · TLKM ...",
                                    label_visibility="collapsed").strip().upper()
  with cb:
      st.write("")
      st.button("🔍 Cari", use_container_width=True)

  if search_ticker:
      row, src_lbl = get_latest_data_for_ticker(search_ticker)

      if row:
          act_cls, act_lbl = classify_action(row.get('Rekomendasi_Action',''))
          is_macd  = row.get('MACD_PreCross', False)
          alert_f  = str(row.get('Alert_Flag', ''))

          st.markdown(f"""
          <div class="tick-hdr">
            <span class="tick-sym">{search_ticker}</span>
            <span class="badge b-{act_cls}" style="font-size:12px;padding:4px 14px;">{act_lbl}</span>
            {macd_badge() if is_macd else ''}
            {alert_badge(alert_f)}
            <span class="tick-src">{src_lbl}</span>
          </div>""", unsafe_allow_html=True)

          # Alert boxes
          if 'HINDARI' in str(row.get('Rekomendasi_Action','')).upper() or alert_f:
              flag_messages = {
                  'CMF_DROP':       'CMF turun tajam dalam 3 hari — arus uang melemah cepat',
                  'VOL_SPIKE_DIST': 'Volume meledak disertai CMF negatif — tanda distribusi bandar',
                  'STAGNANT_SPIKE': 'Harga stagnan lalu volume spike — pola distribusi klasik (seperti GLVA)',
              }
              for flag in alert_f.split('|'):
                  if flag and flag in flag_messages:
                      st.markdown(f'<div class="abox abox-err">🚨 <strong>ANTI-TRAP ALERT:</strong> {flag_messages[flag]}</div>', unsafe_allow_html=True)

          if is_macd:
              st.markdown(f'<div class="abox abox-macd">⚡ <strong>MACD Pre-Crossover:</strong> Fast line hampir crossing zero dengan slope positif — momentum breakout semakin dekat. Saham ini diprioritaskan untuk entry.</div>', unsafe_allow_html=True)

          st.markdown(f"""
          <div class="dg">
            <div class="dc"><div class="k">Harga Terakhir</div><div class="v" style="color:var(--blue)">{fmt_price(row.get('Close'))}</div><div class="h">Harga penutupan</div></div>
            <div class="dc"><div class="k">Support</div><div class="v" style="color:var(--green)">{fmt_price(row.get('Support'))}</div><div class="h">Low 20 hari</div></div>
            <div class="dc"><div class="k">Resistance</div><div class="v" style="color:var(--red)">{fmt_price(row.get('Resistance'))}</div><div class="h">High 20 hari</div></div>
            <div class="dc"><div class="k">BB Width</div><div class="v">{fmt_val(row.get('BB_Width_Str'))}</div><div class="h">Squeeze indicator</div></div>
            <div class="dc"><div class="k">Vol Ratio</div><div class="v">{fmt_val(row.get('Vol_Ratio'))}</div><div class="h">Vol vs MA20</div></div>
            <div class="dc"><div class="k">Vol Velocity</div><div class="v">{fmt_val(row.get('Vol_Velocity'))}</div><div class="h">Kecepatan Vol 5h/20h</div></div>
            <div class="dc"><div class="k">CMF</div><div class="v" style="color:{'var(--green)' if str(row.get('CMF','0')).replace('-','').replace('.','').isdigit() and float(str(row.get('CMF',0)))>0 else 'var(--red)'}">{fmt_val(row.get('CMF'))}</div><div class="h">Chaikin Money Flow</div></div>
            <div class="dc"><div class="k">UD Vol Ratio</div><div class="v">{fmt_val(row.get('UD_Vol_Ratio'))}</div><div class="h">Up/Down Volume 20h</div></div>
            <div class="dc"><div class="k">Est. Breakout</div><div class="v">{fmt_val(row.get('Hari_Ke_Breakout'))}</div><div class="h">Prediksi ML</div></div>
            <div class="dc"><div class="k">Proyeksi Upside</div><div class="v" style="color:var(--green)">{fmt_val(row.get('Potensial_Upsize'))}</div><div class="h">Target kenaikan</div></div>
            <div class="dc"><div class="k">Skor CVI</div><div class="v" style="color:var(--fire)">{fmt_val(row.get('CVI'))}</div><div class="h">Capital Velocity Index</div></div>
            <div class="dc"><div class="k">MACD</div><div class="v" style="color:{'var(--purple)' if is_macd else 'var(--text)'}">{fmt_val(row.get('MACD'))}</div><div class="h">{'⚡ Pre-Cross Zero!' if is_macd else 'Fast line'}</div></div>
            <div class="dc"><div class="k">MACD Slope</div><div class="v">{fmt_val(row.get('MACD_Slope'))}</div><div class="h">Arah 3 hari</div></div>
              <div class="dc"><div class="k">⭐ Conf Score</div><div class="v" style="color:{'var(--green)' if int(row.get('Conf_Score',0) or 0)>=4 else 'var(--amber)' if int(row.get('Conf_Score',0) or 0)==3 else 'var(--text)'}">{fmt_val(row.get('Conf_Score','—'))}/5</div><div class="h">Konfluensi indikator</div></div>
              <div class="dc"><div class="k">CVI Tier</div><div class="v" style="color:{'var(--green)' if str(row.get('CVI_Tier',''))=='Tinggi' else 'var(--amber)' if str(row.get('CVI_Tier',''))=='Sedang' else 'var(--text)'}">{fmt_val(row.get('CVI_Tier','—'))}</div><div class="h">Efisiensi modal</div></div>
              <div class="dc"><div class="k">💰 Target Profit</div><div class="v" style="color:var(--green)">{fmt_price(row.get('Profit_Target'))}</div><div class="h">Dinamis (75% pred ML)</div></div>
              <div class="dc"><div class="k">ADX</div><div class="v" style="color:{'var(--green)' if float(row.get('ADX',0) or 0)>=25 else 'var(--text)'}">{fmt_val(row.get('ADX','—'))}</div><div class="h">{'Trend kuat' if float(row.get('ADX',0) or 0)>=25 else 'Sideways/lemah'}</div></div>
          </div>""", unsafe_allow_html=True)

          st.markdown(f"""
          <div class="konk">
            <div class="kt">Kesimpulan Analisis Kuantitatif Dragon Fire AI</div>
            <div class="kv">{fmt_val(row.get('Analisis_Kesimpulan'))}</div>
          </div>""", unsafe_allow_html=True)

          st.markdown('<div class="slabel">📈 Chart Candlestick · BB · Volume · MACD (90 Hari)</div>', unsafe_allow_html=True)
          render_chart(search_ticker, row)
      else:
          st.markdown(f'<div class="abox abox-err">❌ Kode <strong>{search_ticker}</strong> tidak ditemukan.</div>', unsafe_allow_html=True)
          render_chart(search_ticker)

# ─────────────────────────────────────────────────────
# TAB 6 · HISTORI HARIAN
# ─────────────────────────────────────────────────────
with tab6:
  st.markdown('<div class="slabel">📅 Arsip Histori Pemindaian Pasar BEI</div>', unsafe_allow_html=True)
  if df_history.empty or 'Tanggal_Scan' not in df_history.columns:
      st.markdown('<div class="abox abox-info">💡 Belum ada rekam histori.</div>', unsafe_allow_html=True)
  else:
      avail = sorted(df_history['Tanggal_Scan'].unique().tolist(), reverse=True)
      hc1, hc2 = st.columns([3, 2])
      with hc1:
          sel_date = st.selectbox("📅 Pilih Tanggal:", options=avail)
      df_hd = (df_history[df_history['Tanggal_Scan'] == sel_date]
               .drop(columns=['Tanggal_Scan'], errors='ignore').reset_index(drop=True))
      with hc2:
          st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
          st.download_button(f"⬇️ Download {sel_date} (.xlsx)",
              data=to_excel(df_hd, f"Histori_{sel_date}"),
              file_name=f"DragonFire_Histori_{sel_date}.xlsx",
              mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              use_container_width=True)

      n_hb = len(df_hd[df_hd['Rekomendasi_Action'].str.contains("BUY|ACCUMULATION", na=False)]) if 'Rekomendasi_Action' in df_hd.columns else 0
      n_hm = int(df_hd['MACD_PreCross'].sum()) if 'MACD_PreCross' in df_hd.columns else 0
      n_ha = int(df_hd['Alert_Flag'].str.len().gt(0).sum()) if 'Alert_Flag' in df_hd.columns else 0
      h1,h2,h3,h4 = st.columns(4)
      h1.metric("Total Emiten", len(df_hd))
      h2.metric("Sinyal BUY", n_hb)
      h3.metric("⚡ MACD PreCross", n_hm)
      h4.metric("🚨 Alert", n_ha)

      srch = st.text_input("🔍 Cari Ticker:", placeholder="Contoh: BBCA, GLVA ...", key="hist_search").strip().upper()
      if srch:
          df_hd = df_hd[df_hd['Ticker'] == srch].reset_index(drop=True)

      hcols = [c for c in ['Ticker','Close','CMF','UD_Vol_Ratio','BB_Width_Str','Vol_Ratio',
                            'Hari_Ke_Breakout','Potensial_Upsize','CVI','MACD','MACD_PreCross',
                            'Alert_Flag','Analisis_Kesimpulan','Rekomendasi_Action'] if c in df_hd.columns]
      st.dataframe(df_hd[hcols], use_container_width=True, height=420,
          column_config={
              "Ticker":        st.column_config.TextColumn("Ticker",  width=70, pinned=True),
              "Close":         st.column_config.NumberColumn("Close", format="Rp %,.0f"),
              "CVI":           st.column_config.NumberColumn("CVI", format="%.3f"),
              "MACD_PreCross": st.column_config.CheckboxColumn("⚡ MACD"),
              "Alert_Flag":    st.column_config.TextColumn("🚨 Alert", width=130),
          })
