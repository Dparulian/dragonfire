import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import urllib.parse
import io

# ==========================================
# 1. KONFIGURASI HALAMAN
# ==========================================
st.set_page_config(
    page_title="Dragon Fire Dashboard",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* ---- GLOBAL PALETTE ---- */
:root {
    --bg-base:      #0d1117;
    --bg-card:      #161b22;
    --bg-hover:     #1c232d;
    --border:       #30363d;
    --accent-fire:  #ff6b35;
    --accent-green: #3fb950;
    --accent-red:   #f85149;
    --accent-amber: #e3b341;
    --accent-blue:  #58a6ff;
    --text-primary: #e6edf3;
    --text-muted:   #8b949e;
    --text-dim:     #484f58;
}

/* ---- BODY / BASE ---- */
html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-base) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', 'Segoe UI', sans-serif;
}
[data-testid="stSidebar"] {
    background-color: var(--bg-card) !important;
    border-right: 1px solid var(--border);
}
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

/* ---- 🌟 PERBAIKAN KONTRAS FONT OTOMATIS (ANTI INVISIBLE TEXT) ---- */
/* Default untuk container gelap: Font wajib putih/terang */
.metric-card, .pick-card, .diag-item, .sidebar-stat, div, p, span, label {
    color: inherit;
}

/* Memaksa elemen input bawaan Streamlit mengikuti tema gelap agar font putih terlihat kontras */
.stTextInput input, .stSelectbox select, .stMultiSelect div, textarea {
    background-color: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

/* KONDISI BALIKAN: Jika komponen dipaksa berlatar belakang putih/terang oleh sistem browser, font dipaksa hitam pekat */
[style*="background-color: white"], [style*="background: white"], .white-bg, .stDataFrame div {
    color: #000000 !important;
}

/* PROTEKSI: Menjaga warna khusus untuk judul Tab Aktif dan Header Utama agar tidak tertimpa rule hitam-putih */
.stTabs [aria-selected="true"] {
    color: var(--accent-fire) !important;
}
.dragon-header h1 {
    color: var(--accent-fire) !important;
}

/* ---- HEADER SPANDUK ---- */
.dragon-header {
    background: linear-gradient(135deg, #1a0a00 0%, #0d1117 60%, #0a1628 100%);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent-fire);
    border-radius: 10px;
    padding: 20px 28px;
    margin-bottom: 20px;
}
.dragon-header h1 {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0;
}
.dragon-header p {
    color: var(--text-muted) !important;
    font-size: 13px;
    margin: 4px 0 0 0;
}

/* ---- METRIC CARDS ---- */
.metric-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 18px;
    flex: 1; min-width: 140px;
}
.metric-card .label { color: var(--text-muted) !important; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; }
.metric-card .value { color: var(--text-primary) !important; font-size: 22px; font-weight: 700; margin-top: 4px; }
.metric-card .delta { font-size: 12px; margin-top: 2px; }
.delta-up   { color: var(--accent-green) !important; }
.delta-down { color: var(--accent-red) !important; }
.delta-neu  { color: var(--text-muted) !important; }

/* ---- TOP PICK CARDS ---- */
.pick-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
    position: relative;
    overflow: hidden;
    transition: border-color .2s;
}
.pick-card:hover { border-color: var(--accent-fire); }
.pick-card::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.pick-card.gold::before   { background: linear-gradient(90deg, #e3b341, #f0c060); }
.pick-card.silver::before { background: linear-gradient(90deg, #8b949e, #b0b8c1); }
.pick-card.bronze::before { background: linear-gradient(90deg, #c46f3c, #e08050); }
.pick-rank { color: var(--text-muted) !important; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
.pick-ticker { color: var(--text-primary) !important; font-size: 26px; font-weight: 800; margin: 2px 0; }
.pick-price { color: var(--accent-blue) !important; font-size: 18px; font-weight: 600; }
.pick-cvi { color: var(--text-muted) !important; font-size: 12px; margin-top: 6px; }

/* ---- ACTION BADGES ---- */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-top: 8px;
}
.badge-buy-now   { background: rgba(63,185,80,.15); color: var(--accent-green) !important; border: 1px solid rgba(63,185,80,.4); }
.badge-scalping  { background: rgba(255,107,53,.15); color: var(--accent-fire) !important;  border: 1px solid rgba(255,107,53,.4); }
.badge-watch     { background: rgba(227,179,65,.15); color: var(--accent-amber) !important; border: 1px solid rgba(227,179,65,.4); }
.badge-hold      { background: rgba(88,166,255,.15); color: var(--accent-blue) !important;  border: 1px solid rgba(88,166,255,.4); }
.badge-avoid     { background: rgba(248,81,73,.15);  color: var(--accent-red) !important;   border: 1px solid rgba(248,81,73,.4); }

/* ---- TABLE OVERRIDE ---- */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 8px;
    overflow: hidden;
}

/* ---- TABS ---- */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    border-radius: 8px 8px 0 0;
    padding: 0 16px;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted) !important;
    padding: 12px 18px;
    border-bottom: 2px solid transparent !important;
}

.stMultiSelect [data-baseweb="tag"] { background: var(--accent-fire) !important; }

/* ---- HIDE STREAMLIT CHROME ---- */
#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. KONEKSI DATABASE
# ==========================================
def sanitize_db_url(url):
    if not url: return url
    prefix = "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", prefix, 1)
    if url.startswith(prefix):
        rem = url[len(prefix):]
        auth_part, path_part = rem.rsplit('/', 1) if '/' in rem else (rem, "")
        if '@' in auth_part:
            creds, host_port = auth_part.rsplit('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
                return f"{prefix}{user}:{urllib.parse.quote_plus(password)}@{host_port}/{path_part}"
    return url

@st.cache_resource
def init_connection():
    db_url = st.secrets["DATABASE_URL"]
    return create_engine(sanitize_db_url(db_url))

try:
    engine = init_connection()
except Exception as e:
    st.error(f"❌ Gagal Terkoneksi ke Cloud Database: {e}")
    st.stop()

# ==========================================
# 3. DATA LOADER
# ==========================================
peta_kolom = {
    'ticker': 'Ticker', 'close': 'Close', 'support': 'Support', 'resistance': 'Resistance',
    'bb_width_str': 'BB_Width_Str', 'vol_ratio': 'Vol_Ratio', 'vol_velocity': 'Vol_Velocity',
    'cmf': 'CMF', 'ud_vol_ratio': 'UD_Vol_Ratio', 'hari_ke_breakout': 'Hari_Ke_Breakout',
    'potensial_upsize': 'Potensial_Upsize', 'cvi': 'CVI',
    'analisis_kesimpulan': 'Analisis_Kesimpulan', 'rekomendasi_action': 'Rekomendasi_Action',
    'tanggal_scan': 'Tanggal_Scan'
}

@st.cache_data(ttl=600)
def fetch_cloud_data(table_name):
    try:
        df = pd.read_sql(f'SELECT * FROM "{table_name}"', engine)
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def fetch_chart_data(ticker):
    """Ambil data OHLCV 90 hari dari Yahoo Finance untuk chart"""
    try:
        import yfinance as yf
        t = yf.Ticker(f"{ticker}.JK")
        df = t.history(period="90d")
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize(None)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    except Exception:
        return pd.DataFrame()

def normalize_columns(df):
    if df is None or df.empty: return pd.DataFrame()
    df.columns = df.columns.str.lower()
    mapping = {c.lower(): c for c in ['Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str', 'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio', 'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI', 'Analisis_Kesimpulan', 'Rekomendasi_Action', 'Tanggal_Scan']}
    df = df.rename(columns=mapping)
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
    return df

df_screener = normalize_columns(fetch_cloud_data('screener_live'))
df_watchlist = normalize_columns(fetch_cloud_data('watchlist_live'))
df_history   = normalize_columns(fetch_cloud_data('screener_history'))
df_all_stocks = normalize_columns(fetch_cloud_data('all_stocks_live'))

# ==========================================
# 4. HELPER FUNCTIONS
# ==========================================
def classify_action(action_str):
    a = str(action_str).upper()
    if "BUY" in a or "STRONG BUY" in a or "ACCUMULATION" in a:  return "buy-now",  action_str
    if "SCALPING" in a:                        return "scalping", "SCALPING"
    if "WATCH" in a or "PANTAU" in a:          return "watch",    action_str
    if "HOLD" in a:                            return "hold",     "HOLD"
    return "avoid", action_str

def make_badge(action_str):
    cls, label = classify_action(action_str)
    return f'<span class="badge badge-{cls}">{label}</span>'

def make_excel_download(df, sheet_name="Data"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buf.getvalue()

def render_chart(ticker, row_data=None):
    """Render candlestick chart dengan BB, Volume, Support/Resistance"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        df = fetch_chart_data(ticker)
        if df.empty:
            st.warning(f"Data chart untuk {ticker} tidak tersedia saat ini.")
            return

        # Hitung Bollinger Bands
        df['MA20']   = df['Close'].rolling(20).mean()
        df['BB_Std'] = df['Close'].rolling(20).std()
        df['BB_Up']  = df['MA20'] + 2 * df['BB_Std']
        df['BB_Lo']  = df['MA20'] - 2 * df['BB_Std']
        df['VMA20']  = df['Volume'].rolling(20).mean()

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.03
        )

        # -- Candlestick --
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            name=ticker,
            increasing=dict(line=dict(color='#3fb950', width=1), fillcolor='rgba(63,185,80,0.7)'),
            decreasing=dict(line=dict(color='#f85149', width=1), fillcolor='rgba(248,81,73,0.7)'),
        ), row=1, col=1)

        # -- Bollinger Bands --
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], name='BB Upper',
            line=dict(color='rgba(255,107,53,0.4)', width=1, dash='dot'), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lo'], name='BB Lower',
            line=dict(color='rgba(255,107,53,0.4)', width=1, dash='dot'),
            fill='tonexty', fillcolor='rgba(255,107,53,0.05)', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name='MA20',
            line=dict(color='rgba(227,179,65,0.7)', width=1.2), showlegend=False), row=1, col=1)

        # -- Support & Resistance dari DB --
        if row_data is not None:
            try:
                sup = float(str(row_data.get('Support', '')).replace(',', ''))
                res = float(str(row_data.get('Resistance', '')).replace(',', ''))
                fig.add_hline(y=sup, line=dict(color='rgba(63,185,80,0.5)', width=1, dash='dash'),
                              annotation_text="Support", annotation_font_color='#3fb950', row=1, col=1)
                fig.add_hline(y=res, line=dict(color='rgba(248,81,73,0.5)', width=1, dash='dash'),
                              annotation_text="Resistance", annotation_font_color='#f85149', row=1, col=1)
            except:
                pass

        # -- Volume bars --
        colors = ['#3fb950' if c >= o else '#f85149'
                  for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume',
            marker_color=colors, opacity=0.7, showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['VMA20'], name='Vol MA20',
            line=dict(color='rgba(227,179,65,0.8)', width=1.2), showlegend=False), row=2, col=1)

        fig.update_layout(
            height=480,
            margin=dict(l=0, r=0, t=28, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='#0d1117',
            font=dict(color='#8b949e', size=11),
            xaxis_rangeslider_visible=False,
            showlegend=False,
            xaxis=dict(gridcolor='#21262d', showgrid=True, zeroline=False),
            yaxis=dict(gridcolor='#21262d', showgrid=True, zeroline=False, tickprefix='Rp '),
            xaxis2=dict(gridcolor='#21262d', showgrid=True, zeroline=False),
            yaxis2=dict(gridcolor='#21262d', showgrid=True, zeroline=False),
        )
        fig.update_xaxes(showspikes=True, spikecolor="#30363d", spikethickness=1)
        fig.update_yaxes(showspikes=True, spikecolor="#30363d", spikethickness=1)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    except Exception as ex:
        st.warning(f"Chart tidak dapat dimuat: {ex}")

# ==========================================
# 5. HEADER & TOP BANNER METRICS (🌟 LAYOUT UTAMA UTK HP & PC)
# ==========================================
now_str = datetime.now().strftime('%d %b %Y, %H:%M WIB')

st.markdown(f"""
<div class="dragon-header">
    <h1>🐉 Dragon Fire Quant Dashboard</h1>
    <p>Pusat Komando Velositas Modal & Detektor Akumulasi Bandar &nbsp;·&nbsp; Sinkronisasi: {now_str}</p>
</div>
""", unsafe_allow_html=True)

# Hitung variabel statistik data bursa Anda
n_screener  = len(df_screener)
n_watchlist = len(df_watchlist)
n_buy       = len(df_screener[df_screener['Rekomendasi_Action'].str.contains("BUY", na=False)]) if n_screener else 0

# Grid Komponen Atas: Membawa status database ke halaman utama agar 100% tampil di HP/Komputer
col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns([1.5, 1.5, 1.5, 2, 1.5])

with col_m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">Screener Live</div>
        <div class="value">{n_screener}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label" style="color:#3fb950">Sinyal BUY Aktif</div>
        <div class="value" style="color:#3fb950">{n_buy}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="label" style="color:#58a6ff">Watchlist Aktif</div>
        <div class="value" style="color:#58a6ff">{n_watchlist}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m4:
    if n_screener > 0 and 'CVI' in df_screener.columns:
        top_cvi = df_screener.sort_values('CVI', ascending=False).iloc[0]
        st.markdown(f"""
        <div class="metric-card">
            <div class="label" style="color:#ff6b35">🥇 TOP CVI HARI INI</div>
            <div class="value" style="color:#ff6b35; font-size:18px;">{top_cvi.get('Ticker','—')} ({top_cvi.get('CVI','—')})</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="metric-card">
            <div class="label">Top CVI</div>
            <div class="value">—</div>
        </div>
        """, unsafe_allow_html=True)

# 🔄 TOMBOL REFRESH DI HALAMAN UTAMA (ANTI CACHE LOCK SERVER)
with col_m5:
    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True, key="main_refresh_action_v4"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 6. TABS LAYOUT
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊   LIVE SCREENER",
    "📋   WATCHLIST",
    "🔍   DIAGNOSTIK TICKER",
    "📅   HISTORI HARIAN"
])

# --- TAB 1 · LIVE SCREENER ---
with tab1:
    if df_screener.empty:
        st.markdown('<div class="warn-box">⚠️ Belum ada data screener_live di database cloud. Jalankan dragon_fire.py terlebih dahulu.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="section-label">🏆 Top Alpha Velocity Picks — CVI Tertinggi Hari Ini</div>', unsafe_allow_html=True)
        top3 = df_screener.sort_values('CVI', ascending=False).head(3)
        medals = ['gold', 'silver', 'bronze']
        ranks  = ['🥇 #1 Alpha Pick', '🥈 #2 Runner Up', '🥉 #3 Momentum']
        
        cols3  = st.columns(len(top3) if len(top3) > 0 else 1)
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols3[i]:
                badge_html = make_badge(row.get('Rekomendasi_Action', ''))
                st.markdown(f"""
                <div class="pick-card {medals[i]}">
                    <div class="pick-rank">{ranks[i]}</div>
                    <div class="pick-ticker">{row.get('Ticker','—')}</div>
                    <div class="pick-price">Rp {row.get('Close','—'):,}</div>
                    <div class="pick-cvi">CVI: <strong>{row.get('CVI','—')}</strong> &nbsp;|&nbsp; Upsize: <strong>{row.get('Potensial_Upsize','—')}</strong></div>
                    <div class="pick-cvi">Estimasi: {row.get('Hari_Ke_Breakout','—')}</div>
                    {badge_html}
                </div>
                """, unsafe_allow_html=True)

        st.write("")

        col_f1, col_f2, col_f3 = st.columns([3, 2, 1.5])
        with col_f1:
            all_actions = sorted(df_screener['Rekomendasi_Action'].dropna().unique().tolist())
            default_sel = [a for a in all_actions if "BUY" in a or "SCALPING" in a or "PANTAU" in a] or all_actions
            selected_actions = st.multiselect("⚡ Filter Rekomendasi", options=all_actions, default=default_sel)
        with col_f2:
            sort_col = st.selectbox("🔃 Urutkan", options=['CVI', 'Close', 'Vol_Ratio', 'CMF'], index=0)
        with col_f3:
            sort_asc = st.selectbox("Arah", ["Tertinggi ↓", "Terendah ↑"], index=0)

        df_disp = df_screener.copy()
        if selected_actions:
            df_disp = df_disp[df_disp['Rekomendasi_Action'].isin(selected_actions)]
        df_disp = df_disp.sort_values(sort_col, ascending=(sort_asc == "Terendah ↑"))

        st.markdown(f'<div class="section-label" style="margin-top:6px">TABEL SCREENER — {len(df_disp)} Emiten Lolos Filter</div>', unsafe_allow_html=True)

        display_cols = [c for c in ['Ticker','Close','Support','Resistance','BB_Width_Str',
                                     'Vol_Ratio','Vol_Velocity','CMF','UD_Vol_Ratio',
                                     'Hari_Ke_Breakout','Potensial_Upsize','CVI',
                                     'Analisis_Kesimpulan','Rekomendasi_Action']
                        if c in df_disp.columns]
        st.dataframe(
            df_disp[display_cols].reset_index(drop=True),
            use_container_width=True, height=380,
            column_config={
                "Ticker":              st.column_config.TextColumn("Ticker", width=80),
                "Close":               st.column_config.NumberColumn("Close", format="Rp %,.0f"),
                "CVI":                 st.column_config.NumberColumn("CVI", format="%.3f"),
                "Vol_Ratio":           st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
                "Potensial_Upsize":    st.column_config.TextColumn("Upsize", width=80),
                "Rekomendasi_Action":  st.column_config.TextColumn("Action", width=120),
            }
        )

        st.write("")
        excel_bytes = make_excel_download(df_disp[display_cols], sheet_name="Screener_Live")
        st.download_button(
            label="⬇️ Download Screener Hari Ini (.xlsx)",
            data=excel_bytes,
            file_name=f"DragonFire_Screener_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=False
        )

# --- TAB 2 · WATCHLIST ---
with tab2:
    if df_watchlist.empty:
        st.markdown('<div class="info-box">💡 Belum ada data watchlist_live. Pastikan file Excel watchlist sudah ada di folder WATCHLIST dan dragon_fire.py sudah dijalankan.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="section-label">📋 Status Real-Time Portofolio / Watchlist</div>', unsafe_allow_html=True)

        n_wl_buy   = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("BUY", na=False)])
        n_wl_hold  = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("HOLD", na=False)])
        n_wl_watch = len(df_watchlist[df_watchlist['Rekomendasi_Action'].str.contains("WATCH|PANTAU", na=False)])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Watchlist", n_watchlist)
        c2.metric("Sinyal BUY",  n_wl_buy,  delta="Beli" if n_wl_buy else None)
        c3.metric("Hold",        n_wl_hold)
        c4.metric("Watch/Wait",  n_wl_watch)

        display_cols_wl = [c for c in ['Ticker','Close','Support','Resistance','BB_Width_Str',
                                        'Vol_Ratio','CMF','UD_Vol_Ratio','Hari_Ke_Breakout',
                                        'Potensial_Upsize','CVI','Analisis_Kesimpulan','Rekomendasi_Action']
                           if c in df_watchlist.columns]
        df_wl_sorted = df_watchlist.sort_values('CVI', ascending=False)
        st.dataframe(
            df_wl_sorted[display_cols_wl].reset_index(drop=True),
            use_container_width=True, height=420,
            column_config={
                "Close":            st.column_config.NumberColumn("Close", format="Rp %,.0f"),
                "CVI":              st.column_config.NumberColumn("CVI", format="%.3f"),
                "Vol_Ratio":        st.column_config.ProgressColumn("Vol Ratio", min_value=0, max_value=5, format="%.2f"),
            }
        )

        excel_wl = make_excel_download(df_wl_sorted[display_cols_wl], sheet_name="Watchlist_Live")
        st.download_button(
            label="⬇️ Download Watchlist (.xlsx)",
            data=excel_wl,
            file_name=f"DragonFire_Watchlist_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- TAB 3 · DIAGNOSTIK TICKER + CHART ---
with tab3:
    st.markdown('<div class="section-label">🔍 Diagnostik & Chart Per Emiten</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">Ketik kode saham IDX untuk melihat analisis kuantitatif lengkap beserta chart candlestick interaktif 90 hari.</div>', unsafe_allow_html=True)

    col_inp, col_btn = st.columns([4, 1])
    with col_inp:
        search_ticker = st.text_input("", placeholder="Contoh: BBCA, TLKM, MGRO, GDYR ...",
                                       label_visibility="collapsed").strip().upper()
    with col_btn:
        st.write("")  
        search_btn = st.button("🔍 Analisis", use_container_width=True)

    if search_ticker:
        # Mencari langsung dari master database bursa lengkap (587 emiten)
        match = df_all_stocks[df_all_stocks['Ticker'] == search_ticker] if not df_all_stocks.empty else pd.DataFrame()
        source_label = "Database Utama BEI (Master Scan)"
        
        if match.empty and not df_watchlist.empty:
            match = df_watchlist[df_watchlist['Ticker'] == search_ticker]
            source_label = "Watchlist"

        if not match.empty:
            row = match.iloc[0].to_dict()
            action_cls, action_label = classify_action(row.get('Rekomendasi_Action', ''))

            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:12px; margin:16px 0 10px 0;">
                <span style="font-size:24px; font-weight:800; color:#e6edf3;">{search_ticker}</span>
                <span class="badge badge-{action_cls}" style="font-size:13px; padding:5px 14px;">{action_label}</span>
                <span style="color:#8b949e; font-size:12px;">Sumber: {source_label}</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class="diag-grid">
                <div class="diag-item">
                    <div class="key">Harga Terakhir</div>
                    <div class="val" style="color:#58a6ff">Rp {row.get('Close','—'):,}</div>
                    <div class="hint">Harga penutupan</div>
                </div>
                <div class="diag-item">
                    <div class="key">Skor CVI</div>
                    <div class="val" style="color:#ff6b35">{row.get('CVI','—')}</div>
                    <div class="hint">Capital Velocity Index</div>
                </div>
                <div class="diag-item">
                    <div class="key">Estimasi Breakout</div>
                    <div class="val">{row.get('Hari_Ke_Breakout','—')}</div>
                    <div class="hint">Prediksi ML Random Forest</div>
                </div>
                <div class="diag-item">
                    <div class="key">Proyeksi Upside</div>
                    <div class="val" style="color:#3fb950">{row.get('Potensial_Upsize','—')}</div>
                    <div class="hint">Target kenaikan harga</div>
                </div>
                <div class="diag-item">
                    <div class="key">Support</div>
                    <div class="val" style="color:#3fb950">Rp {row.get('Support','—'):,}</div>
                    <div class="hint">Low 20 hari terakhir</div>
                </div>
                <div class="diag-item">
                    <div class="key">Resistance</div>
                    <div class="val" style="color:#f85149">Rp {row.get('Resistance','—'):,}</div>
                    <div class="hint">High 20 hari terakhir</div>
                </div>
                <div class="diag-item">
                    <div class="key">Vol Ratio</div>
                    <div class="val">{row.get('Vol_Ratio','—')}</div>
                    <div class="hint">Volume vs MA20 Vol</div>
                </div>
                <div class="diag-item">
                    <div class="key">CMF</div>
                    <div class="val">{row.get('CMF','—')}</div>
                    <div class="hint">Chaikin Money Flow</div>
                </div>
                <div class="diag-item">
                    <div class="key">UD Vol Ratio</div>
                    <div class="val">{row.get('UD_Vol_Ratio','—')}</div>
                    <div class="hint">Up/Down Volume Ratio</div>
                </div>
                <div class="diag-item">
                    <div class="key">BB Width</div>
                    <div class="val">{row.get('BB_Width_Str','—')}</div>
                    <div class="hint">Volatilitas squeeze</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px 18px; margin-bottom:16px;">
                <div style="color:#8b949e; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">Kesimpulan Analisis Kuantitatif</div>
                <div style="color:#e6edf3; font-size:14px;">{row.get('Analisis_Kesimpulan','—')}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="section-label">📈 Chart Candlestick + Bollinger Bands (90 Hari)</div>', unsafe_allow_html=True)
            render_chart(search_ticker, row)
        else:
            st.error(f"❌ Kode saham **{search_ticker}** tidak ditemukan dalam master database bursa aktif harian.")
            render_chart(search_ticker)

# --- TAB 4 · HISTORI HARIAN ---
with tab4:
    st.markdown('<div class="section-label">Arsip Histori Pemindaian Pasar BEI</div>', unsafe_allow_html=True)

    if df_history.empty:
        st.markdown('<div class="info-box">💡 Belum ada rekam jejak histori. Data histori akan terkumpul otomatis setiap kali skrip cloud backend berjalan secara sukses.</div>', unsafe_allow_html=True)
    else:
        available_dates = sorted(df_history['Tanggal_Scan'].unique().tolist(), reverse=True)

        col_date, col_dl = st.columns([3, 2])
        with col_date:
            selected_date = st.selectbox("📅 Pilih Tanggal Laporan:", options=available_dates)

        df_hist_display = df_history[df_history['Tanggal_Scan'] == selected_date]
        df_hist_clean   = df_hist_display.drop(columns=['Tanggal_Scan'], errors='ignore').reset_index(drop=True)

        with col_dl:
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            excel_hist = make_excel_download(df_hist_clean, sheet_name=f"Histori_{selected_date}")
            st.download_button(
                label=f"⬇️ Download Histori (.xlsx)",
                data=excel_hist,
                file_name=f"DragonFire_Histori_{selected_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # Mini stats histori
        n_h = len(df_hist_clean)
        n_h_buy = len(df_hist_clean[df_hist_clean.get('Rekomendasi_Action', pd.Series(dtype=str)).str.contains("BUY", na=False)]) if 'Rekomendasi_Action' in df_hist_clean.columns else 0
        
        st.write("")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Emiten Scan", n_h)
        c2.metric("Sinyal BUY Aktif", n_h_buy)
        c3.metric("Tanggal Laporan", str(selected_date))

        search_hist_ticker = st.text_input("🔍 Cari Ticker Spesifik dalam Arsip Tanggal Ini:", placeholder="Masukkan kode emiten (Contoh: GDYR, BBCA...)", key="hist_srch").strip().upper()
        if search_hist_ticker:
            df_hist_clean = df_hist_clean[df_hist_clean['Ticker'] == search_hist_ticker].reset_index(drop=True)

        st.dataframe(
            df_hist_clean, 
            use_container_width=True, 
            height=420,
            column_config={
                "Close": st.column_config.NumberColumn("Close", format="Rp %,.0f"),
                "CVI":   st.column_config.NumberColumn("CVI",   format="%.3f")
            }
        )
"""
print("DONE VIEWING")}
