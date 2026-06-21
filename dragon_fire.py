import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import glob
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime
import warnings
import mplfinance as mpf
from sqlalchemy import create_engine
import urllib.parse

warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════════
# 1. KONFIGURASI PARAMETER MASTER & CLOUD DETECTOR
# ══════════════════════════════════════════════════════════════════
TARGET_PROFIT   = 1.10
DAYS_LOOKAHEAD  = 40
BB_WIDTH_MAX    = 0.15
MIN_CMF         = -0.05
MIN_UD_RATIO    = 1.20

FOLDER_OUTPUT   = 'LAPORAN HARIAN'
FOLDER_CHART    = 'CHART_HASIL'
FOLDER_WATCHLIST= 'WATCHLIST'

os.makedirs(FOLDER_OUTPUT,    exist_ok=True)
os.makedirs(FOLDER_CHART,     exist_ok=True)
os.makedirs(FOLDER_WATCHLIST, exist_ok=True)

FILE_MASTER_EXCEL = os.path.join(FOLDER_OUTPUT, 'Dragon_Screener_Master.xlsx')

def sanitize_db_url(url):
    if not url: return url
    if "=" in url and not url.strip().startswith("postgres"):
        try: url = url.split("=", 1)[1]
        except: pass
    url = url.strip().strip('"').strip("'")
    prefix = "postgresql://"
    if url.startswith("postgres://"): url = url.replace("postgres://", prefix, 1)
    if url.startswith(prefix):
        rem = url[len(prefix):]
        auth_part, path_part = rem.rsplit('/', 1) if '/' in rem else (rem, "")
        if '@' in auth_part:
            creds, host_port = auth_part.rsplit('@', 1)
            if ':' in creds:
                user, password = creds.split(':', 1)
                return f"{prefix}{user}:{urllib.parse.quote_plus(password)}@{host_port}/{path_part}"
    return url

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.strip():
    path_secrets = os.path.join('.streamlit', 'secrets.toml')
    if os.path.exists(path_secrets):
        try:
            with open(path_secrets, 'r') as f:
                for line in f:
                    if 'DATABASE_URL' in line and '=' in line:
                        DATABASE_URL = line.split('=')[1].strip().strip('"').strip("'")
                        break
        except: pass

DATABASE_URL = sanitize_db_url(DATABASE_URL)
IS_CLOUD = bool(DATABASE_URL and DATABASE_URL.strip())

if IS_CLOUD:
    try:
        db_engine = create_engine(DATABASE_URL)
        print("🌐 Cloud Hybrid Mode Terdeteksi: Koneksi Penembakan Data ke Supabase Siap.")
    except Exception as e:
        print(f"❌ Gagal Menginisialisasi Engine Database: {e}")
        IS_CLOUD = False
else:
    print("💻 Local Mode Aktif: Data hanya akan disimpan ke file Excel konvensional.")

# ══════════════════════════════════════════════════════════════════
# 2. ENGINE ANALISIS & ADVANCED ACTION
# ══════════════════════════════════════════════════════════════════
def build_features(df, ticker_name):
    if len(df) < 60: return None
    df = df.copy()
    df['Ticker']       = ticker_name
    df['MA20']         = df['Close'].rolling(window=20).mean()
    df['Returns']      = df['Close'].pct_change()
    df['BB_Std']       = df['Close'].rolling(window=20).std()
    df['BB_Upper']     = df['MA20'] + (df['BB_Std'] * 2)
    df['BB_Lower']     = df['MA20'] - (df['BB_Std'] * 2)
    df['BB_Width']     = (df['BB_Upper'] - df['BB_Lower']) / df['MA20']
    df['VMA20']        = df['Volume'].rolling(window=20).mean()
    df['Vol_Ratio']    = df['Volume'] / df['VMA20'].replace(0, np.nan)
    df['Dist_to_MA20'] = abs(df['Close'] - df['MA20']) / df['MA20']

    high_low = (df['High'] - df['Low']).replace(0, 1e-10)
    mfm      = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low
    df['CMF'] = (mfm * df['Volume']).rolling(window=20).sum() / \
                df['Volume'].rolling(window=20).sum()

    df['Up_Vol']      = np.where(df['Returns'] > 0, df['Volume'], 0)
    df['Down_Vol']    = np.where(df['Returns'] < 0, df['Volume'], 0)
    df['UD_Vol_Ratio']= df['Up_Vol'].rolling(window=20).sum() / \
                        df['Down_Vol'].rolling(window=20).sum().replace(0, 1)

    df['Support']    = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()

    df['CMF_Slope']     = df['CMF'].diff(periods=5)
    df['VMA5']          = df['Volume'].rolling(window=5).mean()
    df['Vol_Velocity']  = df['VMA5'] / df['VMA20'].replace(0, np.nan)
    df['BB_Width_Delta']= df['BB_Width'].diff(periods=5)
    box_range           = (df['Resistance'] - df['Support']).replace(0, 1e-10)
    df['Box_Position']  = (df['Close'] - df['Support']) / box_range

    days_to_target = np.full(len(df), float(DAYS_LOOKAHEAD + 20))
    upsize_target  = np.zeros(len(df))

    for i in range(len(df)):
        close_p       = df['Close'].iloc[i]
        target_p      = close_p * TARGET_PROFIT
        future_highs  = df['High'].iloc[i+1 : i+1+DAYS_LOOKAHEAD]
        if not future_highs.empty:
            max_future_high    = future_highs.max()
            upsize_target[i]   = float((max_future_high - close_p) / close_p)
            triggered          = future_highs >= target_p
            if triggered.any():
                days_to_target[i] = float(triggered.values.argmax() + 1)

    df['Target_Days']  = days_to_target
    df['Target_Upsize']= upsize_target
    return df

def generate_kesimpulan(row):
    kesimpulan = []
    if   row['Vol_Ratio'] > 1.5: kesimpulan.append("Volum Tinggi.")
    elif row['Vol_Ratio'] < 0.6: kesimpulan.append("Volum Kering.")
    else:                         kesimpulan.append("Volum Normal.")
    if   row['CMF'] > 0.1:  kesimpulan.append("Akumulasi Kuat.")
    elif row['CMF'] > 0:    kesimpulan.append("Akumulasi Siluman.")
    elif row['CMF'] < -0.1: kesimpulan.append("Distribusi Masal.")
    else:                    kesimpulan.append("Arus Distribusi Lemah.")
    return " ".join(kesimpulan)

def rekomendasi_action_mendalam(row):
    if row['BB_Width'] <= BB_WIDTH_MAX and row['CMF'] > MIN_CMF and row['UD_Vol_Ratio'] >= MIN_UD_RATIO:
        if row['Vol_Velocity'] > 1.5 and row['Box_Position'] >= 0.7:
            return "ACCUMULATION BUY (NAGA TERBAIK)"
        elif row['CMF'] > 0.15 and row['Vol_Ratio'] < 0.8:
            return "STEALTH BUY (NYICIL SILUMAN)"
        else:
            return "PANTAU (NAGA TIDUR PULAS)"
    return "WAIT & SEE (NANTI DULU)"

def simpan_grafik(df, ticker, kategori):
    try:
        df_chart = df.tail(60).copy()
        df_chart.set_index('Date', inplace=True)
        apds = [
            mpf.make_addplot(df_chart['BB_Upper'], color='red',  linestyle='--'),
            mpf.make_addplot(df_chart['BB_Lower'], color='red',  linestyle='--'),
            mpf.make_addplot(df_chart['MA20'],     color='blue'),
        ]
        filename = f"{ticker}_{kategori}_{datetime.now().strftime('%Y%m%d')}.png"
        filepath = os.path.join(FOLDER_CHART, filename)
        mc = mpf.make_marketcolors(up='g', down='r', edge='inherit', wick='inherit', volume='in')
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False)
        mpf.plot(df_chart, type='candle', volume=True, addplot=apds, style=s, savefig=filepath)
        return filepath
    except:
        return "Gagal membuat visual"

# ══════════════════════════════════════════════════════════════════
# 3. PEMBACA DAFTAR SAHAM — PERBAIKAN UTAMA
# ══════════════════════════════════════════════════════════════════
#
# ❌ BUG LAMA (menyebabkan hanya 587 dari 958 emiten terbaca):
#
#   pd.read_csv('daftar_saham.csv', header=None, sep=None, engine='python')
#
#   MENGAPA SALAH:
#   • sep=None + engine='python' mengaktifkan sniffer otomatis yang menebak
#     delimiter dari baris pertama file.
#   • File BOM UTF-8 (dimulai \ufeff) + huruf-huruf awal seperti 'A' membuat
#     sniffer secara keliru menyimpulkan 'A' sebagai delimiter.
#   • Akibatnya: "AADI" dipotong menjadi 3 kolom: ['', 'ADI', ''], dan seterusnya
#     untuk setiap ticker yang mengandung huruf 'A'.
#   • Filter len==4 kemudian membuang semua fragmen (<4 huruf) ini.
#   • Hasilnya: 877 baris terbaca tapi hanya 587 yang lolos — 371 emiten hilang!
#
# ✅ SOLUSI: Baca baris-per-baris dengan encoding='utf-8-sig' (otomatis buang BOM)
#
FILE_TICKER = 'daftar_saham.csv'
if not os.path.exists(FILE_TICKER):
    print(f"❌ Master file ticker '{FILE_TICKER}' tidak ditemukan.")
    sys.exit()

print(f"📂 Membaca daftar saham dari: {FILE_TICKER}")

DAFTAR_SAHAM = []
ticker_dibuang = []

with open(FILE_TICKER, encoding='utf-8-sig') as f:
    for line in f:
        # Bersihkan whitespace, newline, dan karakter invisible
        raw = line.strip()
        if not raw:
            continue
        # Ambil bagian sebelum titik (buang sufiks .JK jika ada)
        kode = raw.upper().split('.')[0].strip()
        # Filter: hanya huruf alfabet, panjang 2-4 karakter (semua valid di BEI)
        if 2 <= len(kode) <= 4 and kode.isalpha():
            DAFTAR_SAHAM.append(kode)
        else:
            if kode and kode != 'GOTOM':   # GOTOM = entry tidak valid di CSV
                ticker_dibuang.append(kode)

# Deduplikasi dan urutkan
DAFTAR_SAHAM = sorted(list(set(DAFTAR_SAHAM)))
tickers_jk   = [t + '.JK' for t in DAFTAR_SAHAM]
total_tickers = len(DAFTAR_SAHAM)

print(f"🐉 Berhasil membaca {total_tickers} emiten bursa unik dari CSV.")
if ticker_dibuang:
    print(f"⚠️  {len(ticker_dibuang)} entri dibuang (bukan kode ticker valid): {ticker_dibuang[:10]}")
print(f"📋 Sampel 10 emiten pertama: {DAFTAR_SAHAM[:10]}")
print(f"📋 Sampel 10 emiten terakhir: {DAFTAR_SAHAM[-10:]}")

# ══════════════════════════════════════════════════════════════════
# 4. DOWNLOAD DATA HISTORIS — BATCH MODE (Anti-Rate-Limit)
# ══════════════════════════════════════════════════════════════════
print("\n🌐 Mengunduh data historis bursa secara aman dari Yahoo Finance...")
batch_size  = 100
all_raw_dfs = []

for i in range(0, len(tickers_jk), batch_size):
    batch   = tickers_jk[i:i+batch_size]
    batch_n = i // batch_size + 1
    print(f"   ⏳ Batch {batch_n} ({len(batch)} emiten)...")
    try:
        data = yf.download(batch, period="2y", group_by='ticker',
                           auto_adjust=True, progress=False)
        all_raw_dfs.append(data)
    except Exception as e:
        print(f"   ⚠️  Batch {batch_n} gagal download: {e}")

raw_data = pd.concat(all_raw_dfs, axis=1)
print(f"✅ Download selesai. Kolom level-0 diterima: {len(raw_data.columns.get_level_values(0).unique())} ticker.")

# ══════════════════════════════════════════════════════════════════
# 5. FEATURE ENGINEERING & MODEL TRAINING
# ══════════════════════════════════════════════════════════════════
print("\n🛠️  Menyusun kalkulasi 10 fitur advanced per emiten...")
master_train, latest_data, dict_df_full = [], [], {}
ticker_berhasil = 0
ticker_gagal    = []

for idx, ticker in enumerate(DAFTAR_SAHAM, 1):
    t_jk = ticker + '.JK'
    try:
        if t_jk not in raw_data.columns.get_level_values(0):
            ticker_gagal.append((ticker, 'Tidak ada di data Yahoo'))
            continue
        df_raw = raw_data[t_jk].dropna(subset=['Close'])
        if df_raw.empty:
            ticker_gagal.append((ticker, 'Data kosong'))
            continue
        df_t = build_features(df_raw, ticker)
        if df_t is None or df_t.empty:
            ticker_gagal.append((ticker, 'Data historis <60 hari'))
            continue

        df_t = df_t.reset_index()
        if 'Date' not in df_t.columns and 'index' in df_t.columns:
            df_t.rename(columns={'index': 'Date'}, inplace=True)

        dict_df_full[ticker] = df_t
        master_train.append(df_t.iloc[:-DAYS_LOOKAHEAD])
        latest_data.append(df_t.iloc[[-1]])
        ticker_berhasil += 1

    except Exception as e:
        ticker_gagal.append((ticker, str(e)[:60]))

    if idx % 100 == 0 or idx == total_tickers:
        print(f"   ⏳ Progress: {idx}/{total_tickers} diproses | "
              f"Berhasil: {ticker_berhasil} | Gagal: {len(ticker_gagal)}")

print(f"\n✅ Feature engineering selesai.")
print(f"   → Berhasil diproses : {ticker_berhasil} emiten")
print(f"   → Tidak ada data   : {len(ticker_gagal)} emiten (delisted/data kosong)")
if ticker_gagal:
    print(f"   → Sampel gagal     : {[t for t,_ in ticker_gagal[:10]]}")

if not master_train or not latest_data:
    print("❌ Tidak ada data yang bisa diproses. Script dihentikan.")
    sys.exit()

df_train_global  = pd.concat(master_train, axis=0, ignore_index=True)
df_latest_global = pd.concat(latest_data,  axis=0, ignore_index=True)

features = [
    'BB_Width', 'Vol_Ratio', 'Dist_to_MA20', 'CMF', 'UD_Vol_Ratio',
    'CMF_Slope', 'Vol_Velocity', 'BB_Width_Delta', 'Box_Position'
]

X_train        = df_train_global[features].fillna(0)
y_train_days   = df_train_global['Target_Days'].fillna(DAYS_LOOKAHEAD + 20)
y_train_upsize = df_train_global['Target_Upsize'].fillna(0)

print("🧠 Melatih Otak AI Kesatu & Kedua (Random Forest)...")
model_days   = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_days)
model_upsize = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, y_train_upsize)

# ══════════════════════════════════════════════════════════════════
# 6. SCORING & LABELING SELURUH EMITEN
# ══════════════════════════════════════════════════════════════════
X_latest = df_latest_global[features].fillna(0)
df_latest_global['Expected_Days']  = model_days.predict(X_latest)
df_latest_global['Expected_Upsize']= model_upsize.predict(X_latest)

df_latest_global['CVI'] = (
    df_latest_global['Expected_Upsize'] /
    (df_latest_global['Expected_Days'].replace(0, 1e-5) *
     df_latest_global['BB_Width'].replace(0, 1e-5))
).round(3)

df_latest_global['Analisis_Kesimpulan'] = df_latest_global.apply(generate_kesimpulan, axis=1)
df_latest_global['Rekomendasi_Action']  = df_latest_global.apply(rekomendasi_action_mendalam, axis=1)

df_latest_global['Support']         = df_latest_global['Support'].round(0).astype(int)
df_latest_global['Resistance']      = df_latest_global['Resistance'].round(0).astype(int)
df_latest_global['Hari_Ke_Breakout']= df_latest_global['Expected_Days'].round(1).astype(str) + ' Hari'
df_latest_global['Potensial_Upsize']= '+' + (df_latest_global['Expected_Upsize'] * 100).round(2).astype(str) + '%'
df_latest_global['BB_Width_Str']    = (df_latest_global['BB_Width'] * 100).round(2).astype(str) + '%'
df_latest_global['CMF']             = df_latest_global['CMF'].round(3)
df_latest_global['UD_Vol_Ratio']    = df_latest_global['UD_Vol_Ratio'].round(2)
df_latest_global['Vol_Velocity']    = df_latest_global['Vol_Velocity'].round(2)

cols_final = [
    'Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str',
    'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio',
    'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI',
    'Analisis_Kesimpulan', 'Rekomendasi_Action'
]

# Master lengkap SEMUA emiten yang berhasil diproses → untuk Diagnostik Ticker di app.py
df_all_export = df_latest_global[cols_final].copy()

# Screener: hanya yang lolos kriteria squeeze (bukan WAIT & SEE)
dragon_candidates = df_latest_global[
    df_latest_global['Rekomendasi_Action'] != "WAIT & SEE (NANTI DULU)"
].copy()
df_excel_simple = dragon_candidates.sort_values(by='CVI', ascending=False)[cols_final].copy()

print("\n" + "="*140)
print("🐉 THE SLEEPING DRAGON — HASIL SCREENER HARIAN")
print("="*140)
print(f"📊 Total emiten di-scan  : {ticker_berhasil}")
print(f"🎯 Lolos kriteria squeeze: {len(df_excel_simple)}")
print(f"🌐 Tersimpan master DB   : {len(df_all_export)} emiten (termasuk WAIT & SEE)")
print("="*140)
print(df_excel_simple.to_string(index=False))

# ══════════════════════════════════════════════════════════════════
# 7. SIMPAN KE CLOUD DATABASE
# ══════════════════════════════════════════════════════════════════
if IS_CLOUD:
    try:
        # Tabel 1: Screener live — hanya yang lolos filter harian
        df_excel_simple.to_sql('screener_live', db_engine, if_exists='replace', index=False)

        # Tabel 2: Master semua emiten — untuk pencarian Diagnostik Ticker di app.py
        # Ini yang menjamin BBCA, GLVA, MASB, dll bisa dicari walaupun tidak lolos screener
        df_all_export.to_sql('all_stocks_live', db_engine, if_exists='replace', index=False)

        # Tabel 3: Histori harian — append (tidak ditimpa) agar riwayat terkumpul
        df_histori = df_all_export.copy()
        df_histori['Tanggal_Scan'] = datetime.now().strftime('%Y-%m-%d')
        df_histori.to_sql('screener_history', db_engine, if_exists='append', index=False)

        print(f"\n🚀 DATABASE SUCCESS:")
        print(f"   → screener_live   : {len(df_excel_simple)} baris (saham lolos filter)")
        print(f"   → all_stocks_live : {len(df_all_export)} baris (master semua emiten)")
        print(f"   → screener_history: +{len(df_histori)} baris (histori hari ini ditambahkan)")

    except Exception as e:
        print(f"❌ DATABASE ERROR: {e}")

# Simpan juga ke Excel lokal sebagai backup
sheet_name_hari_ini = datetime.now().strftime('%Y-%B-%d')
try:
    with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df_excel_simple.to_excel(writer, sheet_name=sheet_name_hari_ini, index=False)
except:
    try:
        with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl') as writer:
            df_excel_simple.to_excel(writer, sheet_name=sheet_name_hari_ini, index=False)
    except: pass

for idx, row in dragon_candidates.iterrows():
    if "BUY" in str(row['Rekomendasi_Action']):
        simpan_grafik(dict_df_full[row['Ticker']], row['Ticker'], "Screener_Lolos")

# ══════════════════════════════════════════════════════════════════
# 8. MODE OTOMATIS (GITHUB ACTIONS / CLOUD) — PROSES WATCHLIST
# ══════════════════════════════════════════════════════════════════
RUN_AUTOMATED_WATCHLIST = os.getenv("GITHUB_ACTIONS") == "true" or IS_CLOUD

if RUN_AUTOMATED_WATCHLIST:
    print("\n🤖 Mode Otomatis: Memproses file Watchlist ke Cloud Database...")
    path_w = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))
    path_w = path_w[0] if path_w else ""

    if path_w and os.path.exists(path_w):
        try:
            df_watch = pd.read_excel(path_w)
            df_watch.columns = df_watch.columns.str.strip().str.upper()
            w_col_candidates = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']]
            if not w_col_candidates:
                print("⚠️  Kolom ticker tidak ditemukan di file watchlist.")
            else:
                w_col = w_col_candidates[0]
                watchlist_results = []

                for t in df_watch[w_col].dropna():
                    clean_t = str(t).split('.')[0].strip().upper()
                    if clean_t not in dict_df_full:
                        continue
                    last_row = dict_df_full[clean_t].iloc[[-1]].copy()
                    last_row['Expected_Days']  = model_days.predict(last_row[features])
                    last_row['Expected_Upsize']= model_upsize.predict(last_row[features])
                    est_days_val = last_row['Expected_Days'].values[0]
                    bb_w_val     = last_row['BB_Width'].values[0]
                    cvi_val      = round(
                        last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3
                    ) if est_days_val > 0 and bb_w_val > 0 else 0.0

                    watchlist_results.append({
                        'Ticker':              clean_t,
                        'Close':               last_row['Close'].values[0],
                        'Support':             int(round(last_row['Support'].values[0], 0)),
                        'Resistance':          int(round(last_row['Resistance'].values[0], 0)),
                        'BB_Width_Str':        f"{last_row['BB_Width'].values[0]*100:.2f}%",
                        'Vol_Ratio':           round(last_row['Vol_Ratio'].values[0], 2),
                        'Vol_Velocity':        round(last_row['Vol_Velocity'].values[0], 2),
                        'CMF':                 round(last_row['CMF'].values[0], 3),
                        'UD_Vol_Ratio':        round(last_row['UD_Vol_Ratio'].values[0], 2),
                        'Hari_Ke_Breakout':    f"{est_days_val:.1f} Hari",
                        'Potensial_Upsize':    f"+{last_row['Expected_Upsize'].values[0]*100:.2f}%",
                        'CVI':                 cvi_val,
                        'Analisis_Kesimpulan': generate_kesimpulan(last_row.iloc[0]).strip(),
                        'Rekomendasi_Action':  rekomendasi_action_mendalam(last_row.iloc[0]),
                    })

                if watchlist_results:
                    df_watch_export = pd.DataFrame(watchlist_results).sort_values('CVI', ascending=False)
                    if IS_CLOUD:
                        try:
                            df_watch_export.to_sql('watchlist_live', db_engine, if_exists='replace', index=False)
                            print(f"🚀 WATCHLIST SUCCESS: {len(df_watch_export)} saham diupdate di Cloud.")
                        except Exception as e:
                            print(f"❌ Gagal upload watchlist: {e}")
                else:
                    print("⚠️  Tidak ada ticker watchlist yang ditemukan dalam data bursa hari ini.")
        except Exception as e:
            print(f"❌ Gagal membaca file watchlist: {e}")
    else:
        print("⚠️  File watchlist tidak ditemukan di folder WATCHLIST/. Proses watchlist dilewati.")

    print("💤 Seluruh proses cloud selesai. Sistem otomatisasi dimatikan secara bersih.")
    sys.exit()

# ══════════════════════════════════════════════════════════════════
# 9. COMMAND CENTER INTERAKTIF (LOCAL MODE)
# ══════════════════════════════════════════════════════════════════
print("\n" + "="*90)
print("💻 COMMAND CENTER INTERAKTIF LOCAL MODE")
print("• Ketik 'WATCH'  : Evaluasi massal & ekspor otomatis")
print("• Ketik 'TICKER' : Evaluasi manual satu per satu")
print("• Ketik 'EXIT'   : Keluar dari program")
print("="*90)

while True:
    try:
        pilihan = input("\n👉 Masukkan Perintah (WATCH/TICKER/EXIT): ").strip().upper()
        if pilihan == 'EXIT':
            print("Terminal ditutup."); break

        elif pilihan == 'WATCH':
            path_w = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))
            if not path_w: print("❌ File watchlist tidak ditemukan."); continue
            df_watch = pd.read_excel(path_w[0])
            df_watch.columns = df_watch.columns.str.strip().str.upper()
            w_col = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']][0]
            watchlist_results = []
            for t in df_watch[w_col].dropna():
                clean_t = str(t).split('.')[0].strip().upper()
                if clean_t not in dict_df_full: continue
                last_row = dict_df_full[clean_t].iloc[[-1]].copy()
                last_row['Expected_Days']  = model_days.predict(last_row[features])
                last_row['Expected_Upsize']= model_upsize.predict(last_row[features])
                est_days_val = last_row['Expected_Days'].values[0]
                bb_w_val     = last_row['BB_Width'].values[0]
                cvi_val      = round(last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3) if est_days_val > 0 and bb_w_val > 0 else 0.0
                print(f"  [{clean_t}] Close: {last_row['Close'].values[0]:<8,.0f} | Est: {est_days_val:.1f}h | CVI: {cvi_val} | {rekomendasi_action_mendalam(last_row.iloc[0])}")
                watchlist_results.append({
                    'Ticker': clean_t, 'Close': last_row['Close'].values[0],
                    'Support': int(round(last_row['Support'].values[0])), 'Resistance': int(round(last_row['Resistance'].values[0])),
                    'BB_Width_Str': f"{last_row['BB_Width'].values[0]*100:.2f}%", 'Vol_Ratio': round(last_row['Vol_Ratio'].values[0], 2),
                    'Vol_Velocity': round(last_row['Vol_Velocity'].values[0], 2), 'CMF': round(last_row['CMF'].values[0], 3),
                    'UD_Vol_Ratio': round(last_row['UD_Vol_Ratio'].values[0], 2), 'Hari_Ke_Breakout': f"{est_days_val:.1f} Hari",
                    'Potensial_Upsize': f"+{last_row['Expected_Upsize'].values[0]*100:.2f}%", 'CVI': cvi_val,
                    'Analisis_Kesimpulan': generate_kesimpulan(last_row.iloc[0]).strip(),
                    'Rekomendasi_Action': rekomendasi_action_mendalam(last_row.iloc[0])
                })
            if watchlist_results:
                df_we = pd.DataFrame(watchlist_results).sort_values('CVI', ascending=False)
                try:
                    with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                        df_we[cols_final].to_excel(writer, sheet_name='Watchlist_Analisis', index=False)
                    print("🚀 Sukses ekspor ke sheet 'Watchlist_Analisis'.")
                except: print("⚠️  Gagal menulis ke Excel.")

        elif pilihan == 'TICKER':
            target_t = input("   Masukkan kode saham (misal: BBCA): ").strip().upper()
            if target_t in dict_df_full:
                last_row = dict_df_full[target_t].iloc[[-1]].copy()
                last_row['Expected_Days']  = model_days.predict(last_row[features])
                last_row['Expected_Upsize']= model_upsize.predict(last_row[features])
                est_days_val = last_row['Expected_Days'].values[0]
                bb_w_val     = last_row['BB_Width'].values[0]
                cvi_val      = round(last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3) if est_days_val > 0 and bb_w_val > 0 else 0.0
                print(f"\n📊 --- DIAGNOSTIK KILAT EMITEN: {target_t} ---")
                print(f"   Harga Penutupan : Rp {last_row['Close'].values[0]:,.0f}")
                print(f"   Support / Resist: Rp {int(round(last_row['Support'].values[0])):,} / Rp {int(round(last_row['Resistance'].values[0])):,}")
                print(f"   Estimasi Hari   : {est_days_val:.1f} Hari Bursa")
                print(f"   Proyeksi Upsize : +{last_row['Expected_Upsize'].values[0]*100:.2f}%")
                print(f"   CMF             : {round(last_row['CMF'].values[0],3)}")
                print(f"   Vol Ratio       : {round(last_row['Vol_Ratio'].values[0],2)}")
                print(f"   🎯 SKOR CVI     : {cvi_val}")
                print(f"   🎯 Tindakan     : {rekomendasi_action_mendalam(last_row.iloc[0])}")
            else:
                print(f"❌ Kode emiten '{target_t}' tidak ditemukan dalam data hari ini.")

    except Exception as e:
        print(f"⚠️  Error: {e}")
