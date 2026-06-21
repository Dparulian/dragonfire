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
st.set_page_config(page_title="Dragon Fire Dashboard", page_icon="🐉", layout="wide")

# ... [CSS STYLE TETAP SAMA] ...
st.markdown("""
<style>
/* ... (CSS Anda Sebelumnya) ... */
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. KONEKSI DATABASE
# ==========================================
def sanitize_db_url(url):
    if not url: return url
    url = url.strip().strip('"').strip("'")
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
    st.error(f"❌ Gagal Terkoneksi ke Database: {e}")
    st.stop()

# ==========================================
# 3. DATA LOADER (DEBUGGING ENABLED)
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
    # 🌟 PERBAIKAN: Menghapus try-except agar jika ada eror, Anda bisa melihat eror aslinya di layar!
    query = f'SELECT * FROM "{table_name}"'
    df = pd.read_sql(query, engine)
    return df

def normalize_columns(df):
    if df is None or df.empty: return pd.DataFrame()
    df.columns = df.columns.str.lower()
    mapping = {c.lower(): c for c in ['Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str', 'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio', 'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI', 'Analisis_Kesimpulan', 'Rekomendasi_Action', 'Tanggal_Scan']}
    df = df.rename(columns=mapping)
    if 'Ticker' in df.columns:
        df['Ticker'] = df['Ticker'].astype(str).str.strip().str.upper()
    return df

try:
    df_screener = normalize_columns(fetch_cloud_data('screener_live'))
    df_watchlist = normalize_columns(fetch_cloud_data('watchlist_live'))
    df_history   = normalize_columns(fetch_cloud_data('screener_history'))
    df_all_stocks = normalize_columns(fetch_cloud_data('all_stocks_live'))
except Exception as e:
    st.error(f"❌ Gagal Membaca Tabel Database (Pastikan GitHub Actions sukses dijalankan): {e}")
    st.stop()

# ==========================================
# 4. TAB DIAGNOSTIK TICKER (MODIFIKASI)
# ==========================================
# (Tambahkan kode ini di bawah Tab 3/Diagnostik di file Anda)
# ... [Sisa kode Helper Function & Render Chart sama] ...
