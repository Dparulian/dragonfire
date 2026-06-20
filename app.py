import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime  # <--- PASTIKAN BARIS INI ADA DI PALING ATAS
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

# Kustomisasi Style CSS Minimalis untuk Mode Ponsel & Desktop
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
    """Membuka koneksi tunggal ke SQL Database Awan"""
    # Memanggil link URL Rahasia dari Streamlit Secrets
    db_url = st.secrets["DATABASE_URL"]
    # Proteksi konversi dialek standard postgresql jika diperlukan
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return create_engine(db_url)

try:
    engine = init_connection()
except Exception as e:
    st.error(f"❌ Gagal Terkoneksi ke Cloud Database: {e}")
    st.stop()

# ==========================================
# 3. LOADER DATA CACHING (ANTI-LEMOT & HEMAT KUOTA API)
# ==========================================
@st.cache_data(ttl=600)  # Data dikunci di memori selama 10 menit sebelum query ulang
def fetch_cloud_data(table_name):
    """Menarik data matang hasil kompilasi skrip dragon_fire.py"""
    try:
        query = f'SELECT * FROM "{table_name}"'
        df = pd.read_sql(query, engine)
        return df
    except Exception:
        # Kembalikan DataFrame kosong jika tabel belum terbentuk di awan
        return pd.DataFrame()

# Load Data dari Kedua Tabel Inti Awan
df_screener = fetch_cloud_data('screener_live')
df_watchlist = fetch_cloud_data('watchlist_live')

# ==========================================
# 4. STRUKTUR MENU UTAMA ANTARMUKA WEB
# ==========================================
st.title("🐉 Dragon Fire Quant Dashboard")
st.subheader("Sistem Pemantauan Velositas Modal & Akumulasi Smart Money")

# Pembuatan Sistem Tab Taktis
tab1, tab2 = st.tabs(["📊 1. LIVE BURSA SCREENER", "📋 2. WATCHLIST ANALISIS"])

# --- TAB 1: HASIL SCREENING MASAL BURSA BEI ---
with tab1:
    if df_screener.empty:
        st.warning("⚠️ Belum ada data 'screener_live' di database awan. Jalankan skrip produksi Anda terlebih dahulu.")
    else:
        # Komponen Statistik Cepat (Cards) di Baris Atas Dasbor
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
        
        # Pengendali Filter Interaktif Sidebar Khusus Tab 1
        st.sidebar.header("🎛️ Filter Kontrol Screener")
        all_actions = df_screener['Rekomendasi_Action'].unique().tolist()
        selected_actions = st.sidebar.multiselect(
            "Saring Berdasarkan Tindakan:",
            options=all_actions,
            default=[a for a in all_actions if "BUY" in a or "SCALPING" in a]
        )
        
        # Eksekusi Filter Harga
        if selected_actions:
            df_display_screener = df_screener[df_screener['Rekomendasi_Action'].isin(selected_actions)]
        else:
            df_display_screener = df_screener
            
        # Pencetakan Tabel Utama Komprehensif
        st.markdown(f"**Menampilkan {len(df_display_screener)} Emiten Lolos Parameter Squeeze**")
        st.dataframe(
            df_display_screener.reset_index(drop=True),
            use_container_width=True,
            height=450
        )

# --- TAB 2: MONITOR EVALUASI WATCHLIST / PORTFOLIO ---
with tab2:
    if df_watchlist.empty:
        st.info("💡 Belum ada data 'watchlist_live' di awan. Jalankan perintah 'WATCH' pada skrip lokal Anda.")
    else:
        st.markdown("### 📋 Evaluasi Kesehatan Real-Time Portofolio & Incarn")
        
        # Penyaringan Cepat Tipe Aksi Khusus Watchlist
        watchlist_actions = df_watchlist['Rekomendasi_Action'].unique().tolist()
        selected_wl_actions = st.multiselect(
            "Filter Status Saham Genggaman:",
            options=watchlist_actions,
            default=watchlist_actions
        )
        
        df_display_wl = df_watchlist[df_watchlist['Rekomendasi_Action'].isin(selected_wl_actions)]
        
        # Tampilkan Tabel Evaluasi Watchlist Terurut CVI Terbesar
        st.dataframe(
            df_display_wl.reset_index(drop=True),
            use_container_width=True,
            height=500
        )

# Footer Otomatis Catatan Waktu Server
st.sidebar.write("---")
st.sidebar.caption(f"🕒 Terakhir Diperbarui: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
