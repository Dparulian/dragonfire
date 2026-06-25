import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import glob
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta, timezone

# ── Waktu Jakarta (GMT+7) — digunakan untuk Tanggal_Scan ──────────
# GitHub Actions runner berjalan di UTC. datetime.now() tanpa timezone
# akan menulis tanggal UTC, bukan WIB, sehingga histori muncul 1 hari
# lebih awal dari yang seharusnya (contoh: skrip jalan 06:00 WIB =
# 23:00 UTC hari sebelumnya → Tanggal_Scan salah satu hari).
_WIB = timezone(timedelta(hours=7))

def now_wib():
    """Kembalikan datetime sekarang dalam WIB (UTC+7)."""
    return datetime.now(tz=_WIB)

def today_wib_str():
    """Tanggal hari ini dalam format YYYY-MM-DD sesuai WIB."""
    return now_wib().strftime('%Y-%m-%d')
import warnings
import mplfinance as mpf
from sqlalchemy import create_engine, text
import urllib.parse

warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════════
# 1. KONFIGURASI PARAMETER MASTER & CLOUD DETECTOR
# ══════════════════════════════════════════════════════════════════
TARGET_PROFIT    = 1.10
DAYS_LOOKAHEAD   = 40
BB_WIDTH_MAX     = 0.15
FOLDER_OUTPUT    = 'LAPORAN HARIAN'
FOLDER_CHART     = 'CHART_HASIL'
FOLDER_WATCHLIST = 'WATCHLIST'

MIN_CMF      = -0.05
MIN_UD_RATIO =  1.20
# Filter likuiditas minimum — mencegah anomali CVI meledak pada saham tidak
# diperdagangkan seperti BKDP (Vol_Ratio=0 → BB_Width=0 → CVI=tak terhingga)
MIN_VOL_RATIO = 0.01

# Threshold MACD Pre-Crossover: MACD fast line masih negatif tapi
# sudah dalam jarak <= MACD_PROXIMITY_PCT dari zero line
MACD_PROXIMITY_PCT = 0.005   # 0.5% dari harga = "sangat dekat zero"

# Threshold alert anti-trap
CMF_3D_DROP_THRESHOLD   = -0.15   # CMF turun >0.15 dalam 3 hari → alert
VOL_SPIKE_THRESHOLD     =  5.0    # Volume >5x VMA20 → cek distribusi
PRICE_STAGNANT_DAYS     =  10     # Harga stagnan dalam ±2% selama 10 hari
STAGNANT_RANGE_PCT      =  0.02

os.makedirs(FOLDER_OUTPUT,    exist_ok=True)
os.makedirs(FOLDER_CHART,     exist_ok=True)
os.makedirs(FOLDER_WATCHLIST, exist_ok=True)

FILE_MASTER_EXCEL = os.path.join(FOLDER_OUTPUT, 'Dragon_Screener_Master.xlsx')

# ── DATABASE CLOUD CONNECTOR ──────────────────────────────────────
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

    high_low  = (df['High'] - df['Low']).replace(0, 1e-10)
    mfm       = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low
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

    # ── NEW: MACD (12,26,9) ──────────────────────────────────────
    ema12          = df['Close'].ewm(span=12, adjust=False).mean()
    ema26          = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD']     = ema12 - ema26                                  # fast line
    df['MACD_Sig'] = df['MACD'].ewm(span=9, adjust=False).mean()   # signal line
    df['MACD_Hist']= df['MACD'] - df['MACD_Sig']                   # histogram
    # Berapa jauh MACD dari zero, dinormalisasi dengan harga
    df['MACD_Dist_Zero'] = df['MACD'] / df['Close'].replace(0, 1e-10)
    # Slope MACD 3 hari terakhir (positif = heading up toward zero)
    df['MACD_Slope'] = df['MACD'].diff(periods=3)

    # ── NEW: CMF 3-day change (untuk alert distribusi) ────────────
    df['CMF_3d_Change'] = df['CMF'].diff(periods=3)

    days_to_target  = np.full(len(df), float(DAYS_LOOKAHEAD + 20))
    upsize_target   = np.zeros(len(df))

    for i in range(len(df)):
        close_p      = df['Close'].iloc[i]
        target_p     = close_p * TARGET_PROFIT
        future_highs = df['High'].iloc[i+1 : i+1+DAYS_LOOKAHEAD]
        if not future_highs.empty:
            upsize_target[i] = float((future_highs.max() - close_p) / close_p)
            triggered = future_highs >= target_p
            if triggered.any():
                days_to_target[i] = float(triggered.values.argmax() + 1)

    df['Target_Days']  = days_to_target
    df['Target_Upsize']= upsize_target
    return df


# ── DETECTOR: MACD PRE-CROSSOVER ─────────────────────────────────
def detect_macd_pre_crossover(row):
    """
    Kondisi MACD Pre-Crossover zero line:
    1. MACD fast line masih negatif (belum crossing)
    2. MACD dalam jarak <= MACD_PROXIMITY_PCT dari zero
    3. MACD_Slope positif (fast line bergerak naik menuju zero)
    Return: True jika semua kondisi terpenuhi
    """
    try:
        macd_val    = float(row.get('MACD', 0))
        macd_slope  = float(row.get('MACD_Slope', 0))
        macd_dist   = float(row.get('MACD_Dist_Zero', 0))  # sudah dinormalisasi
        # MACD masih negatif tapi sangat dekat zero dan bergerak naik
        return (macd_val < 0) and (abs(macd_dist) <= MACD_PROXIMITY_PCT) and (macd_slope > 0)
    except:
        return False


# ── DETECTOR: ANTI-TRAP ALERT FLAGS ──────────────────────────────
def compute_alert_flags(df_latest, dict_df_full):
    """
    Hitung 3 alert anti-trap untuk setiap ticker:
    1. CMF Velocity Alert: CMF turun >0.15 dalam 3 hari
    2. Volume Spike + CMF Negatif: Vol >5x dan CMF negatif
    3. Stagnant + Spike: harga stagnan 10 hari lalu volume meledak
    Return: dict {ticker: alert_string}
    """
    alerts = {}
    for _, row in df_latest.iterrows():
        ticker = row.get('Ticker', '')
        if not ticker or ticker not in dict_df_full:
            alerts[ticker] = ''
            continue

        df_hist  = dict_df_full[ticker]
        if len(df_hist) < PRICE_STAGNANT_DAYS + 3:
            alerts[ticker] = ''
            continue

        flags = []

        # Alert 1: CMF 3-day velocity drop
        cmf_change = row.get('CMF_3d_Change', 0)
        if pd.notna(cmf_change) and cmf_change < CMF_3D_DROP_THRESHOLD:
            flags.append('CMF_DROP')

        # Alert 2: Volume spike + CMF negatif
        vol_ratio = row.get('Vol_Ratio', 0)
        cmf_now   = row.get('CMF', 0)
        if pd.notna(vol_ratio) and pd.notna(cmf_now):
            if vol_ratio > VOL_SPIKE_THRESHOLD and cmf_now < -0.05:
                flags.append('VOL_SPIKE_DIST')

        # Alert 3: Harga stagnan 10 hari lalu spike
        recent = df_hist.tail(PRICE_STAGNANT_DAYS + 1)
        if len(recent) >= PRICE_STAGNANT_DAYS:
            past_closes  = recent['Close'].iloc[:-1]
            close_mean   = past_closes.mean()
            close_std    = past_closes.std()
            is_stagnant  = (close_std / close_mean) <= STAGNANT_RANGE_PCT if close_mean > 0 else False
            today_vol    = recent['Volume'].iloc[-1]
            vma20_val    = recent['Volume'].mean()
            vol_spike_today = (today_vol / vma20_val > VOL_SPIKE_THRESHOLD) if vma20_val > 0 else False
            cmf_neg_today   = cmf_now < -0.05 if pd.notna(cmf_now) else False
            if is_stagnant and vol_spike_today and cmf_neg_today:
                flags.append('STAGNANT_SPIKE')

        alerts[ticker] = '|'.join(flags)

    return alerts


# ── LABEL BUILDER: tambahkan MACD PRE-CROSSOVER ke label ─────────
def build_macd_label(base_action, is_macd_pre):
    """
    Jika MACD Pre-Crossover terdeteksi dan saham sudah punya label positif,
    tambahkan suffix ⚡ MACD PRE-CROSSOVER untuk prioritas visual.
    """
    if not is_macd_pre:
        return base_action
    positive = ['ACCUMULATION BUY', 'STEALTH BUY', 'PANTAU', 'FAST TRADE']
    if any(p in base_action for p in positive):
        return base_action + ' ⚡ MACD PRE-CROSSOVER'
    return base_action


def apply_historical_feedback_loop(df_train, folder_output, dict_df_full):
    report_files = glob.glob(os.path.join(folder_output, "Dragon_Screener_Master*.csv"))
    if not report_files:
        return df_train
    print(f"🔄 Feedback Loop: Menyerap data kegagalan dari {len(report_files)} laporan historis...")
    past_records = []
    for file in report_files:
        try:
            df_past = pd.read_csv(file)
            if 'Ticker' in df_past.columns and 'Rekomendasi_Action' in df_past.columns:
                past_records.append(df_past[['Ticker', 'Close', 'Rekomendasi_Action']])
        except: continue
    if not past_records:
        return df_train
    df_past_compiled = pd.concat(past_records, ignore_index=True)
    premium_past     = df_past_compiled[df_past_compiled['Rekomendasi_Action'].str.contains('BUY', na=False, case=False)]
    if premium_past.empty:
        return df_train
    penalized_tickers = []
    for ticker in df_train['Ticker'].unique():
        if ticker in dict_df_full:
            ticker_past = premium_past[premium_past['Ticker'] == ticker]
            if not ticker_past.empty:
                avg_past_price     = ticker_past['Close'].mean()
                current_real_price = dict_df_full[ticker]['Close'].iloc[-1]
                if current_real_price < (avg_past_price * 0.95):
                    penalized_tickers.append(ticker)
    if penalized_tickers:
        print(f"⚠️  Pinalti anti-trap: {len(penalized_tickers)} emiten jebakan: {penalized_tickers}")
        df_train.loc[df_train['Ticker'].isin(penalized_tickers), 'Target_Days']  = 999.0
        df_train.loc[df_train['Ticker'].isin(penalized_tickers), 'Target_Upsize']= 0.0
    return df_train


def generate_kesimpulan(row):
    status  = ""
    status += "Volum Kering. "  if row['Vol_Ratio'] < 0.5  else \
              "Volum Tinggi. "  if row['Vol_Ratio'] > 1.5  else "Volum Normal. "
    status += "Akumulasi Kuat. "    if row['CMF'] >  0.05 else \
              "Akumulasi Siluman. " if row['CMF'] > -0.05 else "Distribusi Terdeteksi. "
    return status


def rekomendasi_action_mendalam(row):
    est_days = row['Expected_Days']

    if est_days > 55.0:
        return "HINDARI (DISTRIBUSI / TRAP TERDETEKSI)"

    if row['BB_Width'] <= 0.15 and row['CMF'] > 0.05 and row['UD_Vol_Ratio'] >= 1.5:
        if est_days <= 36.0:
            base = "ACCUMULATION BUY (NAGA TERBAIK)"
        elif est_days <= 46.0:
            base = "STEALTH BUY (NYICIL SILUMAN)"
        else:
            base = "PANTAU (NAGA TIDUR PULAS)"
    elif row['BB_Width'] <= 0.15 and -0.05 <= row['CMF'] <= 0.05 and row['UD_Vol_Ratio'] >= 2.0:
        base = "STEALTH BUY (NYICIL SILUMAN)"
    elif row['BB_Width'] > 0.20 and row['Vol_Ratio'] >= 2.0 and row['CMF'] > 0.10:
        base = "FAST TRADE / BREAKOUT SCALPING"
    elif row['Vol_Ratio'] > 1.5 and row['CMF'] < -0.10:
        base = "HINDARI (BANDAR DISTRIBUSI / DUMP)"
    else:
        base = "WAIT & SEE (NANTI DULU)"

    # Tambahkan label MACD Pre-Crossover jika terdeteksi
    return build_macd_label(base, detect_macd_pre_crossover(row))


def simpan_grafik(df_plot, ticker, kategori):
    try:
        data_plot = df_plot.tail(90).copy()
        apds = [
            mpf.make_addplot(data_plot['BB_Upper'], color='red',   alpha=0.6),
            mpf.make_addplot(data_plot['BB_Lower'], color='green', alpha=0.6),
            mpf.make_addplot(data_plot['MA20'],     color='blue',  alpha=0.6),
        ]
        filename = f"{ticker}_{kategori}_{now_wib().strftime('%Y%m%d')}.png"
        filepath = os.path.join(FOLDER_CHART, filename)
        mc = mpf.make_marketcolors(up='g', down='r', edge='inherit', wick='inherit', volume='in')
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False)
        mpf.plot(data_plot, type='candle', volume=True, addplot=apds, style=s, savefig=filepath)
        return filepath
    except Exception:
        return "Gagal membuat visual"


# ══════════════════════════════════════════════════════════════════
# 3. PEMBACA DAFTAR SAHAM
# ══════════════════════════════════════════════════════════════════
FILE_TICKER = 'daftar_saham.csv'
if not os.path.exists(FILE_TICKER):
    for alt in ['Ticker Saham.csv', 'TIcker Saham.csv']:
        if os.path.exists(alt):
            FILE_TICKER = alt
            break

if not os.path.exists(FILE_TICKER):
    print(f"❌ Master file ticker '{FILE_TICKER}' tidak ditemukan.")
    sys.exit()

print(f"📂 Membaca master list database dari {FILE_TICKER}...")
DAFTAR_SAHAM = []
with open(FILE_TICKER, encoding='utf-8-sig') as f:
    for line in f:
        kode = line.strip().upper().split('.')[0].strip()
        if 2 <= len(kode) <= 4 and kode.isalpha():
            DAFTAR_SAHAM.append(kode)

DAFTAR_SAHAM  = sorted(list(set(DAFTAR_SAHAM)))
tickers_jk    = [t + '.JK' for t in DAFTAR_SAHAM]
total_tickers = len(DAFTAR_SAHAM)

print(f"🐉 Berhasil menemukan {total_tickers} emiten bursa unik dalam file CSV.")
print(f"📋 Sampel 10 emiten pertama: {DAFTAR_SAHAM[:10]}")

# ══════════════════════════════════════════════════════════════════
# 4. DOWNLOAD DATA HISTORIS
# ══════════════════════════════════════════════════════════════════
print("🌐 Mengunduh data historis bursa secara aman dari Yahoo Finance...")
batch_size  = 100
all_raw_dfs = []
for i in range(0, len(tickers_jk), batch_size):
    batch = tickers_jk[i:i+batch_size]
    print(f"   ⏳ Mendownload Batch {i//batch_size + 1} ({len(batch)} emiten)...")
    try:
        data = yf.download(batch, period="2y", group_by='ticker', auto_adjust=True, progress=False)
        all_raw_dfs.append(data)
    except Exception as e:
        print(f"   ⚠️  Batch {i//batch_size + 1} gagal: {e}")

raw_data = pd.concat(all_raw_dfs, axis=1)

# ══════════════════════════════════════════════════════════════════
# 5. FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════
print("\n🛠️  Mengekstrak dan menyusun kalkulasi fitur advanced harian...")
master_train, latest_data, dict_df_full = [], [], {}

for idx, ticker in enumerate(DAFTAR_SAHAM, 1):
    t_jk = ticker + '.JK'
    try:
        if t_jk not in raw_data.columns.get_level_values(0): continue
        df_raw = raw_data[t_jk].dropna(subset=['Close'])
        df_t   = build_features(df_raw, ticker)
        if df_t is None or df_t.empty: continue

        df_t = df_t.reset_index()
        if 'Date' not in df_t.columns and 'index' in df_t.columns:
            df_t.rename(columns={'index': 'Date'}, inplace=True)

        dict_df_full[ticker] = df_t
        master_train.append(df_t.iloc[:-DAYS_LOOKAHEAD])
        latest_data.append(df_t.iloc[[-1]])
    except Exception: continue

    if idx % 100 == 0 or idx == total_tickers:
        print(f"   ⏳ Progress Fitur: {idx}/{total_tickers} emiten selesai disusun...")

# ══════════════════════════════════════════════════════════════════
# 6. MODEL TRAINING
# ══════════════════════════════════════════════════════════════════
print("🧹 Menggabungkan seluruh matriks bursa global...")
df_train_global  = pd.concat(master_train, axis=0, ignore_index=True)
df_latest_global = pd.concat(latest_data,  axis=0, ignore_index=True)

if 'Ticker' in df_train_global.columns and 'Date' in df_train_global.columns:
    df_train_global = df_train_global.sort_values(['Ticker', 'Date']).reset_index(drop=True)

features = [
    'BB_Width', 'Vol_Ratio', 'Dist_to_MA20', 'Returns',
    'CMF', 'UD_Vol_Ratio', 'CMF_Slope', 'Vol_Velocity',
    'BB_Width_Delta', 'Box_Position'
]
df_train_global.dropna(subset=features + ['Target_Days', 'Target_Upsize'], inplace=True)

df_train_global = apply_historical_feedback_loop(df_train_global, FOLDER_OUTPUT, dict_df_full)

print(f"\n🧠 Melatih Otak AI Kesatu (Target Waktu Breakout) dengan {len(df_train_global)} baris harian...")
model_days = RandomForestRegressor(n_estimators=250, max_depth=12, min_samples_leaf=3, random_state=42)
model_days.fit(df_train_global[features], df_train_global['Target_Days'])
print("   ✅ Otak AI Kesatu selesai dilatih.")

print(f"🧠 Melatih Otak AI Kedua (Target Potensial Upsize) dengan {len(df_train_global)} baris harian...")
model_upsize = RandomForestRegressor(n_estimators=250, max_depth=12, min_samples_leaf=3, random_state=42)
model_upsize.fit(df_train_global[features], df_train_global['Target_Upsize'])
print("   ✅ Otak AI Kedua selesai dilatih.")

# ══════════════════════════════════════════════════════════════════
# 7. SCORING, MACD LABELING, ANTI-TRAP ALERTS
# ══════════════════════════════════════════════════════════════════
print("🔮 Menghitung proyeksi akhir bursa harian...")
df_latest_global['Expected_Days']  = model_days.predict(df_latest_global[features])
df_latest_global['Expected_Upsize']= model_upsize.predict(df_latest_global[features])

# Hitung alert flags anti-trap
print("🛡️  Menghitung alert anti-trap (CMF velocity, volume spike, stagnant detector)...")
alert_map = compute_alert_flags(df_latest_global, dict_df_full)
df_latest_global['Alert_Flag'] = df_latest_global['Ticker'].map(alert_map).fillna('')

# Hitung MACD Pre-Crossover flag
df_latest_global['MACD_PreCross'] = df_latest_global.apply(detect_macd_pre_crossover, axis=1)
n_macd = df_latest_global['MACD_PreCross'].sum()
print(f"   ⚡ MACD Pre-Crossover terdeteksi: {n_macd} emiten")

# Hitung alert stats
n_cmf_drop    = df_latest_global['Alert_Flag'].str.contains('CMF_DROP', na=False).sum()
n_vol_spike   = df_latest_global['Alert_Flag'].str.contains('VOL_SPIKE_DIST', na=False).sum()
n_stag_spike  = df_latest_global['Alert_Flag'].str.contains('STAGNANT_SPIKE', na=False).sum()
print(f"   ⚠️  Alert CMF Drop: {n_cmf_drop} | Vol Spike Dist: {n_vol_spike} | Stagnant Spike: {n_stag_spike}")

# Master kolom output
df_latest_global['CVI_raw']                = (
    df_latest_global['Expected_Upsize'] /
    (df_latest_global['Expected_Days'].replace(0, 1e-5) *
     df_latest_global['BB_Width'].replace(0, 1e-5))
).round(3)
df_latest_global['Analisis_Kesimpulan_raw']= df_latest_global.apply(generate_kesimpulan, axis=1)
df_latest_global['Rekomendasi_Action_raw'] = df_latest_global.apply(rekomendasi_action_mendalam, axis=1)
df_latest_global['Support_raw']            = df_latest_global['Support'].round(0).astype(int)
df_latest_global['Resistance_raw']         = df_latest_global['Resistance'].round(0).astype(int)
df_latest_global['Hari_Ke_Breakout_raw']   = df_latest_global['Expected_Days'].round(1).astype(str) + ' Hari'
df_latest_global['Potensial_Upsize_raw']   = '+' + (df_latest_global['Expected_Upsize'] * 100).round(2).astype(str) + '%'
df_latest_global['BB_Width_Str_raw']       = (df_latest_global['BB_Width'] * 100).round(2).astype(str) + '%'
df_latest_global['MACD_raw']               = df_latest_global['MACD'].round(4)
df_latest_global['MACD_Slope_raw']         = df_latest_global['MACD_Slope'].round(4)

cols_final = [
    'Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str',
    'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio',
    'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI',
    'MACD', 'MACD_Slope', 'MACD_PreCross',
    'Alert_Flag', 'Analisis_Kesimpulan', 'Rekomendasi_Action'
]

# Master semua emiten
df_all_export = df_latest_global[[
    'Ticker', 'Close',
    'Support_raw', 'Resistance_raw',
    'BB_Width_Str_raw', 'Vol_Ratio', 'Vol_Velocity',
    'CMF', 'UD_Vol_Ratio',
    'Hari_Ke_Breakout_raw', 'Potensial_Upsize_raw',
    'CVI_raw', 'MACD_raw', 'MACD_Slope_raw', 'MACD_PreCross',
    'Alert_Flag', 'Analisis_Kesimpulan_raw', 'Rekomendasi_Action_raw'
]].copy()
df_all_export.columns = cols_final

# Screener: filter original + filter likuiditas anti-anomali (BKDP fix)
dragon_candidates = df_latest_global[
    (df_latest_global['BB_Width']     <= BB_WIDTH_MAX) &
    (df_latest_global['CMF']          >= MIN_CMF) &
    (df_latest_global['UD_Vol_Ratio'] >= MIN_UD_RATIO) &
    (df_latest_global['Vol_Ratio']    >= MIN_VOL_RATIO)   # ← filter baru: min likuiditas
].copy()

if not dragon_candidates.empty:
    dragon_candidates['Analisis_Kesimpulan'] = dragon_candidates.apply(generate_kesimpulan, axis=1)
    dragon_candidates['Rekomendasi_Action']  = dragon_candidates.apply(rekomendasi_action_mendalam, axis=1)
    dragon_candidates['Support']          = dragon_candidates['Support'].round(0).astype(int)
    dragon_candidates['Resistance']       = dragon_candidates['Resistance'].round(0).astype(int)
    dragon_candidates['Hari_Ke_Breakout'] = dragon_candidates['Expected_Days'].round(1).astype(str) + ' Hari'
    dragon_candidates['Potensial_Upsize'] = '+' + (dragon_candidates['Expected_Upsize'] * 100).round(2).astype(str) + '%'
    dragon_candidates['BB_Width_Str']     = (dragon_candidates['BB_Width'] * 100).round(2).astype(str) + '%'
    dragon_candidates['CMF']              = dragon_candidates['CMF'].round(3)
    dragon_candidates['UD_Vol_Ratio']     = dragon_candidates['UD_Vol_Ratio'].round(2)
    dragon_candidates['Vol_Velocity']     = dragon_candidates['Vol_Velocity'].round(2)
    dragon_candidates['CVI']              = (
        dragon_candidates['Expected_Upsize'] /
        (dragon_candidates['Expected_Days'].replace(0, 1e-5) *
         dragon_candidates['BB_Width'].replace(0, 1e-5))
    ).round(3)
    dragon_candidates['MACD']       = dragon_candidates['MACD'].round(4)
    dragon_candidates['MACD_Slope'] = dragon_candidates['MACD_Slope'].round(4)

    # Sort: MACD Pre-Crossover diprioritaskan dulu, lalu CVI tertinggi
    dragon_candidates['_sort_macd'] = dragon_candidates['MACD_PreCross'].astype(int)
    df_excel_simple = dragon_candidates.sort_values(
        ['_sort_macd', 'CVI'], ascending=[False, False]
    )[cols_final].copy()

    # Cetak ke terminal dengan highlight MACD
    print("\n" + "="*210)
    print("🐉 THE SLEEPING DRAGON — DUAL-BRAIN + CVI + MACD PRE-CROSSOVER PRIORITY SORT")
    print("="*210)
    n_macd_screen = df_excel_simple['MACD_PreCross'].sum()
    if n_macd_screen > 0:
        print(f"⚡ {n_macd_screen} saham dengan MACD Pre-Crossover (diprioritaskan di atas):")
        macd_tickers = df_excel_simple[df_excel_simple['MACD_PreCross'] == True]['Ticker'].tolist()
        print(f"   {macd_tickers}")
    print(df_excel_simple[['Ticker','Close','CVI','MACD','MACD_PreCross','Alert_Flag',
                            'Hari_Ke_Breakout','Potensial_Upsize','Rekomendasi_Action']].to_string(index=False))

    # ── SIMPAN KE CLOUD DATABASE ──────────────────────────────────
    if IS_CLOUD:
        try:
            df_excel_simple.to_sql('screener_live', db_engine, if_exists='replace', index=False)
            df_all_export.to_sql('all_stocks_live', db_engine, if_exists='replace', index=False)
            df_histori = df_all_export.copy()
            df_histori['Tanggal_Scan'] = today_wib_str()
            df_histori.to_sql('screener_history', db_engine, if_exists='append', index=False)
            print(f"\n🚀 DATABASE SUCCESS:")
            print(f"   → screener_live   : {len(df_excel_simple)} baris")
            print(f"   → all_stocks_live : {len(df_all_export)} baris")
            print(f"   → screener_history: +{len(df_histori)} baris")
        except Exception as e:
            print(f"❌ DATABASE ERROR: {e}")

    # ── SIMPAN EXCEL LOKAL ────────────────────────────────────────
    sheet_name_hari_ini = now_wib().strftime('%Y-%B-%d')
    try:
        if os.path.exists(FILE_MASTER_EXCEL):
            with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_excel_simple.to_excel(writer, sheet_name=sheet_name_hari_ini, index=False)
        else:
            with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl') as writer:
                df_excel_simple.to_excel(writer, sheet_name=sheet_name_hari_ini, index=False)
        print(f"\n✅ Sheet '{sheet_name_hari_ini}' berhasil diperbarui.")
    except PermissionError:
        err_time    = now_wib().strftime("%H%M%S")
        backup_file = os.path.join(FOLDER_OUTPUT, f'Dragon_Screener_Master_LOCKED_{err_time}.xlsx')
        df_excel_simple.to_excel(backup_file, sheet_name=sheet_name_hari_ini, index=False)
        print(f"   💾 Diselamatkan ke: {backup_file}")

    for idx, row in dragon_candidates.iterrows():
        if "BUY" in str(row['Rekomendasi_Action']):
            simpan_grafik(dict_df_full[row['Ticker']], row['Ticker'], "Screener_Lolos")

else:
    print("\n⚠️ Hari ini tidak ditemukan saham yang lolos parameter screener.")
    if IS_CLOUD:
        try:
            df_all_export.to_sql('all_stocks_live', db_engine, if_exists='replace', index=False)
            df_histori = df_all_export.copy()
            df_histori['Tanggal_Scan'] = today_wib_str()
            df_histori.to_sql('screener_history', db_engine, if_exists='append', index=False)
            print("🚀 Master DB tetap diupdate.")
        except Exception as e:
            print(f"❌ DATABASE ERROR: {e}")

# ══════════════════════════════════════════════════════════════════
# 8. MODE OTOMATIS — GITHUB ACTIONS / CLOUD (WATCHLIST)
# ══════════════════════════════════════════════════════════════════
RUN_AUTOMATED_WATCHLIST = os.getenv("GITHUB_ACTIONS") == "true" or IS_CLOUD

def _process_one_watchlist_ticker(clean_t):
    """Helper: hitung semua metrik untuk satu ticker watchlist."""
    if clean_t not in dict_df_full: return None
    last_row = dict_df_full[clean_t].iloc[[-1]].copy()
    last_row['Expected_Days']  = model_days.predict(last_row[features])
    last_row['Expected_Upsize']= model_upsize.predict(last_row[features])
    est_days_val   = last_row['Expected_Days'].values[0]
    est_upsize_val = last_row['Expected_Upsize'].values[0]
    bb_w_val       = last_row['BB_Width'].values[0]
    cvi_val        = round(est_upsize_val / (est_days_val * bb_w_val), 3) \
                     if est_days_val > 0 and bb_w_val > 0 else 0.0
    action         = rekomendasi_action_mendalam(last_row.iloc[0])
    # Alert flag untuk watchlist juga
    ticker_alerts  = alert_map.get(clean_t, '')
    return {
        'Ticker':              clean_t,
        'Close':               last_row['Close'].values[0],
        'Support':             int(round(last_row['Support'].values[0])),
        'Resistance':          int(round(last_row['Resistance'].values[0])),
        'BB_Width_Str':        f"{bb_w_val*100:.2f}%",
        'Vol_Ratio':           round(last_row['Vol_Ratio'].values[0], 2),
        'Vol_Velocity':        round(last_row['Vol_Velocity'].values[0], 2),
        'CMF':                 round(last_row['CMF'].values[0], 3),
        'UD_Vol_Ratio':        round(last_row['UD_Vol_Ratio'].values[0], 2),
        'Hari_Ke_Breakout':    f"{est_days_val:.1f} Hari",
        'Potensial_Upsize':    f"+{est_upsize_val*100:.2f}%",
        'CVI':                 cvi_val,
        'MACD':                round(float(last_row['MACD'].values[0]), 4),
        'MACD_Slope':          round(float(last_row['MACD_Slope'].values[0]), 4),
        'MACD_PreCross':       bool(detect_macd_pre_crossover(last_row.iloc[0])),
        'Alert_Flag':          ticker_alerts,
        'Analisis_Kesimpulan': generate_kesimpulan(last_row.iloc[0]).strip(),
        'Rekomendasi_Action':  action,
    }

if RUN_AUTOMATED_WATCHLIST:
    print("\n🤖 Mode Otomatis: Memproses file Watchlist ke Cloud Database...")
    xlsx_files = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))
    path_w     = xlsx_files[0] if xlsx_files else ""

    if path_w and os.path.exists(path_w):
        try:
            df_watch = pd.read_excel(path_w)
            df_watch.columns = df_watch.columns.str.strip().str.upper()
            w_col_candidates = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']]
            if not w_col_candidates:
                print("⚠️  Kolom ticker tidak ditemukan.")
            else:
                w_col            = w_col_candidates[0]
                watchlist_results= []
                for t in df_watch[w_col].dropna():
                    clean_t = str(t).split('.')[0].strip().upper()
                    result  = _process_one_watchlist_ticker(clean_t)
                    if result: watchlist_results.append(result)

                if watchlist_results:
                    df_watch_export = pd.DataFrame(watchlist_results).sort_values(
                        ['MACD_PreCross','CVI'], ascending=[False, False]
                    )
                    if IS_CLOUD:
                        try:
                            df_watch_export.to_sql('watchlist_live', db_engine, if_exists='replace', index=False)
                            print(f"🚀 WATCHLIST SUCCESS: {len(df_watch_export)} saham diupdate.")
                        except Exception as e:
                            print(f"❌ Gagal upload watchlist: {e}")
                else:
                    print("⚠️  Tidak ada ticker watchlist yang ditemukan.")
        except Exception as e:
            print(f"❌ Gagal membaca file watchlist: {e}")
    else:
        print("⚠️  File watchlist tidak ditemukan. Proses watchlist dilewati.")

    print("💤 Seluruh proses cloud selesai.")
    sys.exit()

# ══════════════════════════════════════════════════════════════════
# 9. COMMAND CENTER INTERAKTIF (LOCAL MODE)
# ══════════════════════════════════════════════════════════════════
print("\n" + "="*90)
print("💻 COMMAND CENTER INTERAKTIF (10 FEATURES + MACD + CVI + ANTI-TRAP)")
print("• Ketik 'WATCH'  : Evaluasi watchlist massal")
print("• Ketik 'TICKER' : Diagnostik satu emiten")
print("• Ketik 'EXIT'   : Keluar")
print("="*90)

while True:
    try:
        pilihan = input("\n👉 Masukkan Perintah (WATCH/TICKER/EXIT): ").strip().upper()
        if pilihan == 'EXIT':
            print("Terminal ditutup. Sukses untuk trading Anda!")
            break

        elif pilihan == 'WATCH':
            xlsx_files = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))
            if not xlsx_files:
                print(f"❌ File watchlist tidak ditemukan."); continue
            df_watch = pd.read_excel(xlsx_files[0])
            df_watch.columns = df_watch.columns.str.strip().str.upper()
            w_col = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']][0]
            print(f"⏳ Memproses {xlsx_files[0]}...")
            watchlist_results = []
            for t in df_watch[w_col].dropna():
                clean_t = str(t).split('.')[0].strip().upper()
                result  = _process_one_watchlist_ticker(clean_t)
                if result:
                    macd_tag   = " ⚡MACD" if result['MACD_PreCross'] else ""
                    alert_tag  = f" 🚨{result['Alert_Flag']}" if result['Alert_Flag'] else ""
                    print(f"  [{clean_t}] Close: {result['Close']:>8,.0f} | CVI: {result['CVI']} | "
                          f"Est: {result['Hari_Ke_Breakout']} | {result['Rekomendasi_Action']}"
                          f"{macd_tag}{alert_tag}")
                    watchlist_results.append(result)
            if watchlist_results:
                df_we = pd.DataFrame(watchlist_results).sort_values(['MACD_PreCross','CVI'], ascending=[False,False])
                try:
                    with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                        df_we.to_excel(writer, sheet_name='Watchlist_Analisis', index=False)
                    print(f"\n🚀 Sukses tersimpan ke sheet 'Watchlist_Analisis'.")
                except PermissionError:
                    err_time = now_wib().strftime("%H%M%S")
                    backup_w = os.path.join(FOLDER_OUTPUT, f'Watchlist_LOCKED_{err_time}.xlsx')
                    df_we.to_excel(backup_w, index=False)
                    print(f"⚠️  Diselamatkan ke: {backup_w}")

        elif pilihan == 'TICKER':
            target_t = input("   Masukkan kode saham (misal: BBCA): ").strip().upper()
            result   = _process_one_watchlist_ticker(target_t)
            if result:
                print(f"\n📊 --- DIAGNOSTIK: {target_t} ---")
                print(f"   Harga Terakhir  : Rp {result['Close']:,.0f}")
                print(f"   Support/Resist  : Rp {result['Support']:,} / Rp {result['Resistance']:,}")
                print(f"   Estimasi Hari   : {result['Hari_Ke_Breakout']}")
                print(f"   Proyeksi Upsize : {result['Potensial_Upsize']}")
                print(f"   Skor CVI        : {result['CVI']}")
                print(f"   MACD            : {result['MACD']} (Slope: {result['MACD_Slope']})")
                print(f"   MACD PreCross   : {'⚡ YA — hampir crossing zero!' if result['MACD_PreCross'] else 'Tidak'}")
                print(f"   Alert Flag      : {result['Alert_Flag'] if result['Alert_Flag'] else 'Aman'}")
                print(f"   CMF             : {result['CMF']}")
                print(f"   Vol Ratio       : {result['Vol_Ratio']}")
                print(f"   🎯 Tindakan     : {result['Rekomendasi_Action']}")
                simpan_grafik(dict_df_full[target_t], target_t, "Manual_Check")
            else:
                print(f"❌ '{target_t}' tidak ditemukan.")

    except KeyboardInterrupt:
        print("\nSistem interaktif diputus.")
        break
    except Exception as e:
        print(f"⚠️  Error: {e}")
