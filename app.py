import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import urllib.parse

# ==========================================
# 1. KONFIGURASI HALAMAN DASBOR WEB
# ==========================================
st.set_page_config(
    page_title="Dragon Fire Dashboard Live",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    h1 {color: #FF4B4B; font-weight: 800;}
    .stTabs [data-baseweb="tab"] {font-size: 16px; font-weight: 600;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SISTEM KONEKSI DATABASE CLOUD AMAN
# ==========================================
@st.cache_resource
def init_connection():
    db_url = st.secrets["DATABASE_URL"]
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return create_engine(db_url)

try:
    engine = init_connection()
except Exception as e:
    st.error(f"❌ Gagal Terkoneksi ke Cloud Database: {e}")
    st.stop()

# ==========================================
# 3. LOADER DATA CACHING VIA AWAN
# ==========================================
@st.cache_data(ttl=300)
def fetch_cloud_data(table_name):
    try:
        query = f'SELECT * FROM "{table_name}"'
        df = pd.read_sql(query, engine)
        return df
    except Exception:
        return pd.DataFrame()

df_screener = fetch_cloud_data('screener_live')
df_watchlist = fetch_cloud_data('watchlist_live')

# ==========================================
# 4. STRUKTUR UTAMA ANTARMUKA WEB
# ==========================================
st.title("🐉 Dragon Fire Quant Dashboard")
st.subheader("Sistem Pemantauan Velositas Modal & Akumulasi Smart Money")

# ℹ️ INFO SIDEBAR DIKUNCI PERMANEN AGAR TIDAK BLANK
st.sidebar.header("🎛️ Pusat Kontrol Dasbor")
st.sidebar.info("💡 Filter tindakan dan parameter akan otomatis muncul di panel utama setelah database awan menerima pasokan data dari robot AI.")

tab1, tab2 = st.tabs(["📊 1. LIVE BURSA SCREENER", "📋 2. WATCHLIST ANALISIS"])

# --- TAB 1: SCREENER LIVE BURSA ---
with tab1:
    if df_screener.empty:
        st.warning("⚠️ STATUS DATABASE: KOSONG. Server awan belum menerima data hasil scan 'screener_live'. Silakan jalankan skrip 'dragon_fire.py' di terminal komputer/server Anda untuk mengisi data pasar pertama kali.")
    else:
        st.markdown("### 🏆 Top Alpha Velocity Picks (Skor CVI Tertinggi)")
        top_3 = df_screener.head(3)
        cols = st.columns(len(top_3) if len(top_3) > 0 else 1)
        
        for i, (_, row) in enumerate(top_3.iterrows()):
            with cols[i]:
                st.metric(
                    label=f"#{i+1} {row['Ticker']} - {row['Rekomendasi_Action']}",
                    value=f"Rp {row['Close']}",
                    delta=f"CVI: {row['CVI']} | Proyeksi: {row['Potensial_Upsize']}"
                )
        st.write("---")
        
        # Filter dipindahkan ke area halaman utama agar ramah navigasi iPhone layar sentuh
        all_actions = df_screener['Rekomendasi_Action'].unique().tolist()
        selected_actions = st.multiselect(
            "⚡ Saring Saham Berdasarkan Rekomendasi Tindakan:",
            options=all_actions,
            default=[a for a in all_actions if "BUY" in a or "SCALPING" in a]
        )
        
        df_display_screener = df_screener[df_screener['Rekomendasi_Action'].isin(selected_actions)] if selected_actions else df_screener
            
        st.markdown(f"**Menampilkan {len(df_display_screener)} Emiten Lolos Parameter Squeeze**")
        st.dataframe(df_display_screener.reset_index(drop=True), use_container_width=True, height=450)

# --- TAB 2: PORTFOLIO WATCHLIST ---
with tab2:
    if df_watchlist.empty:
        st.info("💡 STATUS WATCHLIST: KOSONG. Belum ada rekam jejak portofolio yang dikirim. Jalankan menu perintah 'WATCH' pada terminal komputer Anda untuk memproses analisa saham genggaman.")
    else:
        st.markdown("### 📋 Evaluasi Kesehatan Real-Time Portofolio & Incaran")
        watchlist_actions = df_watchlist['Rekomendasi_Action'].unique().tolist()
        selected_wl_actions = st.multiselect(
            "Saring Berdasarkan Status Saham Genggaman:",
            options=watchlist_actions,
            default=watchlist_actions
        )
        
        df_display_wl = df_watchlist[df_watchlist['Rekomendasi_Action'].isin(selected_wl_actions)] if selected_wl_actions else df_watchlist
        st.dataframe(df_display_wl.reset_index(drop=True), use_container_width=True, height=500)

# Footer Info Sinkronisasi Server
st.sidebar.write("---")
st.sidebar.caption(f"🕒 Sinkronisasi Terakhir: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
