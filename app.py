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
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    h1 {color: #FF4B4B; font-weight: 800;}
    .stTabs [data-baseweb="tab"] {font-size: 16px; font-weight: 600;}
    div[data-testid="stMetricValue"] {font-size: 24px; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SISTEM KONEKSI DATABASE CLOUD AMAN
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
# 3. LOADER DATA SINKRONISASI
# ==========================================
def fetch_table(table_name):
    try:
        return pd.read_sql(f'SELECT * FROM "{table_name}"', engine)
    except:
        return pd.DataFrame()

df_screener = fetch_table('screener_live')
df_watchlist = fetch_table('watchlist_live')
df_history = fetch_table('screener_history')

# ==========================================
# 4. ANTARMUKA UTAMA DASBOR INTERAKTIF
# ==========================================
st.title("🐉 Dragon Fire Quant Dashboard")
st.subheader("Pusat Komando Velositas Modal & Detektor Akumulasi Bandar")

# Pembuatan Tab Menu Web, Memindahkan Perintah VS Terminal ke Web UI
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 LIVE SCREENER BURSA", 
    "📋 EVALUASI WATCHLIST", 
    "🔍 DIAGNOSTIK KILAT TICKER",
    "📅 REKAM HISTORI HARIAN"
])

# --- TAB 1: LIVE BURSA SCREENER ---
with tab1:
    if df_screener.empty:
        st.warning("⚠️ Belum ada data 'screener_live' di database cloud.")
    else:
        st.markdown("### 🏆 Top Alpha Velocity Picks (Skor CVI Tertinggi Hari Ini)")
        top_3 = df_screener.head(3)
        cols = st.columns(len(top_3) if len(top_3) > 0 else 1)
        for i, (_, row) in enumerate(top_3.iterrows()):
            with cols[i]:
                st.metric(
                    label=f"#{i+1} {row['Ticker']} — {row['Rekomendasi_Action']}",
                    value=f"Rp {row['Close']}",
                    delta=f"CVI: {row['CVI']} | Proyeksi: {row['Potensial_Upsize']}"
                )
        st.write("---")
        
        # Pengendali Filter Dinamis
        all_actions = df_screener['Rekomendasi_Action'].unique().tolist()
        selected_actions = st.multiselect(
            "⚡ Filter Saham Berdasarkan Rekomendasi Tindakan:",
            options=all_actions, default=[a for a in all_actions if "BUY" in a or "SCALPING" in a]
        )
        
        df_display = df_screener[df_screener['Rekomendasi_Action'].isin(selected_actions)] if selected_actions else df_screener
        st.markdown(f"**Menampilkan {len(df_display)} Emiten yang Lolos Parameter Squeeze**")
        st.dataframe(df_display.reset_index(drop=True), use_container_width=True, height=400)

# --- TAB 2: PORTFOLIO WATCHLIST ---
with tab2:
    if df_watchlist.empty:
        st.info("💡 Belum ada data 'watchlist_live' di database cloud. Pastikan folder WATCHLIST di GitHub sudah terisi file Excel Anda.")
    else:
        st.markdown("### 📋 Status Kesehatan Real-Time Saham Genggaman / Portofolio")
        st.dataframe(df_watchlist.reset_index(drop=True), use_container_width=True, height=450)

# --- TAB 3: DIAGNOSTIK KILAT TICKER (MENGGANTIKAN PERINTAH 'TICKER' DI VS) ---
with tab3:
    st.markdown("### 🔍 Pusat Informasi & Analisis Mandiri Per Emiten")
    st.info("Ketik kode saham di bawah ini untuk melihat hasil kalkulasi kecerdasan buatan secara instan tanpa membuka terminal laptop.")
    
    # Text Input pengganti fungsi input() terminal
    search_ticker = st.text_input("👉 Masukkan Kode Saham (Misal: MGRO, GLVA, KDSI):", "").strip().upper()
    
    if search_ticker:
        # Cari data di dalam database screener live hari ini
        match_data = df_screener[df_screener['Ticker'] == search_ticker]
        if match_data.empty and not df_watchlist.empty:
            match_data = df_watchlist[df_watchlist['Ticker'] == search_ticker]
            
        if not match_data.empty:
            row = match_data.iloc[0]
            st.success(f"📊 DATA DIAGNOSTIK BERHASIL DITEMUKAN UNTUK EMITEN {search_ticker}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Harga Terakhir", f"Rp {row['Close']}")
            c2.metric("Skor Efisiensi CVI", str(row['CVI']))
            c3.metric("Estimasi Menuju Breakout", str(row['Hari_Ke_Breakout']))
            c4.metric("Proyeksi Kenaikan (Upsize)", str(row['Potensial_Upsize']))
            
            st.write("---")
            st.markdown(f"**🛡️ Garis Pertahanan:** Support Terdekat: **Rp {row['Support']}** | Target Resistance Boks: **Rp {row['Resistance']}**")
            st.markdown(f"**🐳 Arus Bandar:** Rasio Vol: **{row['Vol_Ratio']}** | Aliran Chaikin Money Flow (CMF): **{row['CMF']}**")
            st.markdown(f"**🎯 Kesimpulan Utama Kuantitatif:** `{row['Analisis_Kesimpulan']}`")
            st.info(f"🚨 **REKOMENDASI EKSEKUSI TRADING:** **{row['Rekomendasi_Action']}**")
        else:
            st.error(f"❌ Kode Saham '{search_ticker}' tidak ditemukan dalam daftar scan aktif atau data histori hari ini.")

# --- TAB 4: REKAM HISTORI HARIAN (MENGGANTIKAN FILES HARIAN EXCEL) ---
with tab4:
    st.markdown("### 📅 Arsip Histori Pemindaian Pasar BEI")
    if df_history.empty:
        st.info("💡 Belum ada rekam jejak histori. Data histori akan otomatis terkumpul ke bawah seiring skrip 'dragon_fire.py' Anda dijalankan setiap harinya.")
    else:
        # Kumpulkan semua tanggal unik yang tersedia di database cloud
        available_dates = sorted(df_history['Tanggal_Scan'].unique().tolist(), reverse=True)
        selected_date = st.selectbox("📅 Silakan Pilih Tanggal Laporan Historis yang Ingin Dilihat:", options=available_dates)
        
        df_hist_display = df_history[df_history['Tanggal_Scan'] == selected_date]
        st.markdown(f"📅 **Menampilkan Arsip Laporan Pasar untuk Tanggal: {selected_date}**")
        st.dataframe(df_hist_display.drop(columns=['Tanggal_Scan'], errors='ignore').reset_index(drop=True), use_container_width=True, height=450)

# Sidebar Sinkronisasi Status Server
st.sidebar.write("---")
st.sidebar.caption(f"🕒 Waktu Sinkronisasi Dasbor: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
