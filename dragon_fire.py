import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import glob
from sklearn.ensemble import RandomForestRegressor  # DUAL-BRAIN ENGINE
from datetime import datetime
import warnings
import mplfinance as mpf
from sqlalchemy import create_engine  # 🌟 NEW: KONEKTOR DATABASE AWAN

warnings.filterwarnings('ignore')

# ==========================================
# 1. KONFIGURASI PARAMETER MASTER & CLOUD DETECTOR
# ==========================================
TARGET_PROFIT = 1.10      
DAYS_LOOKAHEAD = 40       
BB_WIDTH_MAX = 0.15       
FOLDER_OUTPUT = 'LAPORAN HARIAN'
FOLDER_CHART = 'CHART_HASIL'
FOLDER_WATCHLIST = 'WATCHLIST'

MIN_CMF = -0.05           
MIN_UD_RATIO = 1.20       

os.makedirs(FOLDER_OUTPUT, exist_ok=True)
os.makedirs(FOLDER_CHART, exist_ok=True)
os.makedirs(FOLDER_WATCHLIST, exist_ok=True)

FILE_MASTER_EXCEL = os.path.join(FOLDER_OUTPUT, 'Dragon_Screener_Master.xlsx')

# 🌟 KONEKSI DATABASE SUPABASE/POSTGRESQL VIA ENVIRONMENT VARIABLE
DATABASE_URL = os.getenv("DATABASE_URL")  # Akan diisi di rahasia GitHub/Cloud Server
IS_CLOUD = DATABASE_URL is not None

if IS_CLOUD:
    # Memastikan format dialek postgresql untuk SQLAlchemy kompatibel
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    db_engine = create_engine(DATABASE_URL)
    print("🌐 Cloud Mode Terdeteksi: Koneksi Database SQL Terjalin Aman.")
else:
    print("💻 Local Mode Aktif: Data akan disimpan ke file Excel konvensional.")

# ==========================================
# 2. ENGINE ANALISIS & ADVANCED ACTION
# ==========================================
def build_features(df, ticker_name):
    if len(df) < 60: return None
    df = df.copy()
    df['Ticker'] = ticker_name
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Returns'] = df['Close'].pct_change()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['BB_Std'] * 2)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['MA20']
    df['VMA20'] = df['Volume'].rolling(window=20).mean()
    df['Vol_Ratio'] = df['Volume'] / df['VMA20'].replace(0, np.nan)
    df['Dist_to_MA20'] = abs(df['Close'] - df['MA20']) / df['MA20']
    
    high_low = (df['High'] - df['Low']).replace(0, 1e-10) 
    mfm = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low
    df['CMF'] = (mfm * df['Volume']).rolling(window=20).sum() / df['Volume'].rolling(window=20).sum()
    
    df['Up_Vol'] = np.where(df['Returns'] > 0, df['Volume'], 0)
    df['Down_Vol'] = np.where(df['Returns'] < 0, df['Volume'], 0)
    df['UD_Vol_Ratio'] = df['Up_Vol'].rolling(window=20).sum() / df['Down_Vol'].rolling(window=20).sum().replace(0, 1)
    
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()

    # 10 ADVANCED ACCELERATION FEATURES
    df['CMF_Slope'] = df['CMF'].diff(periods=5)
    df['VMA5'] = df['Volume'].rolling(window=5).mean()
    df['Vol_Velocity'] = df['VMA5'] / df['VMA20'].replace(0, np.nan)
    df['BB_Width_Delta'] = df['BB_Width'].diff(periods=5)
    box_range = (df['Resistance'] - df['Support']).replace(0, 1e-10)
    df['Box_Position'] = (df['Close'] - df['Support']) / box_range
    
    days_to_target = np.full(len(df), float(DAYS_LOOKAHEAD + 20))
    upsize_target = np.zeros(len(df))
    
    for i in range(len(df)):
        close_p = df['Close'].iloc[i]
        target_p = close_p * TARGET_PROFIT
        future_highs = df['High'].iloc[i+1 : i+1+DAYS_LOOKAHEAD]
        
        if not future_highs.empty:
            max_future_high = future_highs.max()
            upsize_target[i] = float((max_future_high - close_p) / close_p)
            triggered = future_highs >= target_p
            if triggered.any():
                days_to_target[i] = float(triggered.values.argmax() + 1)
                
    df['Target_Days'] = days_to_target
    df['Target_Upsize'] = upsize_target
    return df

def apply_historical_feedback_loop(df_train, folder_output, dict_df_full):
    report_files = glob.glob(os.path.join(folder_output, "Dragon_Screener_Master*.csv"))
    if not report_files: return df_train
    past_records = []
    for file in report_files:
        try:
            df_past = pd.read_csv(file)
            if 'Ticker' in df_past.columns and 'Rekomendasi_Action' in df_past.columns:
                past_records.append(df_past[['Ticker', 'Close', 'Rekomendasi_Action']])
        except: continue
    if not past_records: return df_train
    df_past_compiled = pd.concat(past_records, ignore_index=True)
    premium_past = df_past_compiled[df_past_compiled['Rekomendasi_Action'].str.contains('BUY', na=False, case=False)]
    if premium_past.empty: return df_train
    penalized_tickers = []
    for ticker in df_train['Ticker'].unique():
        if ticker in dict_df_full:
            ticker_past = premium_past[premium_past['Ticker'] == ticker]
            if not ticker_past.empty:
                avg_past_price = ticker_past['Close'].mean()
                current_real_price = dict_df_full[ticker]['Close'].iloc[-1]
                if current_real_price < (avg_past_price * 0.95):
                    penalized_tickers.append(ticker)
    if penalized_tickers:
        df_train.loc[df_train['Ticker'].isin(penalized_tickers), 'Target_Days'] = 999.0
        df_train.loc[df_train['Ticker'].isin(penalized_tickers), 'Target_Upsize'] = 0.0
    return df_train

def generate_kesimpulan(row):
    status = ""
    status += "Volum Kering. " if row['Vol_Ratio'] < 0.5 else ("Volum Tinggi. " if row['Vol_Ratio'] > 1.5 else "Volum Normal. ")
    status += "Akumulasi Kuat. " if row['CMF'] > 0.05 else ("Akumulasi Siluman. " if row['CMF'] > -0.05 else "Distribusi Terdeteksi. ")
    return status

def rekomendasi_action_mendalam(row):
    est_days = row['Expected_Days']
    if est_days > 55.0: return "HINDARI (DISTRIBUSI / TRAP TERDETEKSI)"
    if row['BB_Width'] <= 0.15 and row['CMF'] > 0.05 and row['UD_Vol_Ratio'] >= 1.5:
        if est_days <= 36.0: return "ACCUMULATION BUY (NAGA TERBAIK)"
        elif est_days <= 46.0: return "STEALTH BUY (NYICIL SILUMAN)"
        else: return "PANTAU (NAGA TIDUR PULAS)"
    elif row['BB_Width'] <= 0.15 and -0.05 <= row['CMF'] <= 0.05 and row['UD_Vol_Ratio'] >= 2.0:
        return "STEALTH BUY (NYICIL SILUMAN)"
    elif row['BB_Width'] > 0.20 and row['Vol_Ratio'] >= 2.0 and row['CMF'] > 0.10:
        return "FAST TRADE / BREAKOUT SCALPING"
    elif row['Vol_Ratio'] > 1.5 and row['CMF'] < -0.10:
        return "HINDARI (BANDAR DISTRIBUSI / DUMP)"
    else: return "WAIT & SEE (NANTI DULU)"

def simpan_grafik(df_plot, ticker, kategori):
    if IS_CLOUD: return "Visual chart diskip di server cloud"
    try:
        data_plot = df_plot.tail(90).copy()
        apds = [
            mpf.make_addplot(data_plot['BB_Upper'], color='red', alpha=0.6),
            mpf.make_addplot(data_plot['BB_Lower'], color='green', alpha=0.6),
            mpf.make_addplot(data_plot['MA20'], color='blue', alpha=0.6)
        ]
        filename = f"{ticker}_{kategori}_{datetime.now().strftime('%Y%m%d')}.png"
        filepath = os.path.join(FOLDER_CHART, filename)
        mc = mpf.make_marketcolors(up='g', down='r', edge='inherit', wick='inherit', volume='in')
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False)
        mpf.plot(data_plot, type='candle', volume=True, addplot=apds, style=s, savefig=filepath)
        return filepath
    except Exception: return "Gagal membuat visual"

# ==========================================
# 3. MAIN RUNNING ENGINE & TRAINING LOOP
# ==========================================
FILE_TICKER = 'Ticker Saham.csv'
if not os.path.exists(FILE_TICKER) and os.path.exists('TIcker Saham.csv'):
    FILE_TICKER = 'TIcker Saham.csv'

if not os.path.exists(FILE_TICKER):
    print(f"❌ Master file ticker '{FILE_TICKER}' tidak ditemukan."); sys.exit()

try: df_ticker = pd.read_csv(FILE_TICKER, sep=None, engine='python')
except: df_ticker = pd.read_csv(FILE_TICKER)

df_ticker.columns = df_ticker.columns.str.strip()
target_col = [col for col in df_ticker.columns if str(col).upper() in ['KODE', 'TICKER', 'KODE SAHAM']][0]

DAFTAR_SAHAM = df_ticker[target_col].dropna().astype(str).str.strip().tolist()
DAFTAR_SAHAM = [t for t in DAFTAR_SAHAM if len(t) == 4 and t.isalpha()]
DAFTAR_SAHAM = list(set(DAFTAR_SAHAM))
tickers_jk = [t + '.JK' for t in DAFTAR_SAHAM]

print("🌐 Mengunduh data historis bursa dari Yahoo Finance...")
raw_data = yf.download(tickers_jk, period="2y", group_by='ticker', auto_adjust=True, progress=False)

print("\n🛠️  Mengekstrak dan menyusun kalkulasi 10 fitur advanced harian...")
master_train, latest_data, dict_df_full = [], [], {}
total_tickers = len(DAFTAR_SAHAM)

for idx, ticker in enumerate(DAFTAR_SAHAM, 1):
    t_jk = ticker + '.JK'
    if t_jk not in raw_data.columns.levels[0]: continue
    df_raw = raw_data[t_jk].dropna(subset=['Close'])
    df_t = build_features(df_raw, ticker)
    if df_t is None or df_t.empty: continue
    
    df_t = df_t.reset_index()
    if 'Date' not in df_t.columns and 'index' in df_t.columns:
        df_t.rename(columns={'index': 'Date'}, inplace=True)
        
    dict_df_full[ticker] = df_t
    master_train.append(df_t.iloc[:-DAYS_LOOKAHEAD])
    latest_data.append(df_t.iloc[[-1]])
    if idx % 100 == 0 or idx == total_tickers:
        print(f"   ⏳ Progress Fitur: {idx}/{total_tickers} emiten selesai disusun...")

df_train_global = pd.concat(master_train, axis=0, ignore_index=True)
features = ['BB_Width', 'Vol_Ratio', 'Dist_to_MA20', 'Returns', 'CMF', 'UD_Vol_Ratio', 'CMF_Slope', 'Vol_Velocity', 'BB_Width_Delta', 'Box_Position']
df_train_global.dropna(subset=features + ['Target_Days', 'Target_Upsize'], inplace=True)

df_train_global = apply_historical_feedback_loop(df_train_global, FOLDER_OUTPUT, dict_df_full)
df_latest_global = pd.concat(latest_data, axis=0, ignore_index=True)

print(f"\n🧠 Melatih Otak AI Kesatu & Kedua...")
model_days = RandomForestRegressor(n_estimators=250, max_depth=12, min_samples_leaf=3, random_state=42)
model_days.fit(df_train_global[features], df_train_global['Target_Days'])

model_upsize = RandomForestRegressor(n_estimators=250, max_depth=12, min_samples_leaf=3, random_state=42)
model_upsize.fit(df_train_global[features], df_train_global['Target_Upsize'])

df_latest_global['Expected_Days'] = model_days.predict(df_latest_global[features])
df_latest_global['Expected_Upsize'] = model_upsize.predict(df_latest_global[features])

dragon_candidates = df_latest_global[
    (df_latest_global['BB_Width'] <= BB_WIDTH_MAX) &
    (df_latest_global['CMF'] >= MIN_CMF) &
    (df_latest_global['UD_Vol_Ratio'] >= MIN_UD_RATIO)
].copy()

dragon_candidates['CVI'] = (dragon_candidates['Expected_Upsize'] / (dragon_candidates['Expected_Days'].replace(0, 1e-5) * dragon_candidates['BB_Width'].replace(0, 1e-5))).round(3)
cols_final = ['Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str', 'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio', 'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI', 'Analisis_Kesimpulan', 'Rekomendasi_Action']

if not dragon_candidates.empty:
    dragon_candidates['Analisis_Kesimpulan'] = dragon_candidates.apply(generate_kesimpulan, axis=1)
    dragon_candidates['Rekomendasi_Action'] = dragon_candidates.apply(rekomendasi_action_mendalam, axis=1)
    
    dragon_candidates['Support'] = dragon_candidates['Support'].round(0).astype(int)
    dragon_candidates['Resistance'] = dragon_candidates['Resistance'].round(0).astype(int)
    dragon_candidates['Hari_Ke_Breakout'] = dragon_candidates['Expected_Days'].round(1).astype(str) + ' Hari'
    dragon_candidates['Potensial_Upsize'] = '+' + (dragon_candidates['Expected_Upsize'] * 100).round(2).astype(str) + '%'
    dragon_candidates['BB_Width_Str'] = (dragon_candidates['BB_Width'] * 100).round(2).astype(str) + '%'
    dragon_candidates['CMF'] = dragon_candidates['CMF'].round(3)
    dragon_candidates['UD_Vol_Ratio'] = dragon_candidates['UD_Vol_Ratio'].round(2)
    dragon_candidates['Vol_Velocity'] = dragon_candidates['Vol_Velocity'].round(2)
    
    df_excel_simple = dragon_candidates.sort_values(by='CVI', ascending=False)[cols_final].copy()
    
    print("\n" + "="*210)
    print("🐉 THE TIME-EFFICIENT SLEEPING DRAGON (PRODUCTION RUN)")
    print("="*210)
    print(df_excel_simple.to_string(index=False))
    
    # 🌟 PERBAIKAN: INJEKSI DATA LIVE & HISTORI HARIAN KE DATABASE AWAN
    if IS_CLOUD:
        try:
            # 1. Update data live untuk metrik hari ini
            df_excel_simple.to_sql('screener_live', db_engine, if_exists='replace', index=False)
            
            # 2. Tambah rekam jejak ke tabel histori (Akan bertambah terus ke bawah setiap hari)
            df_histori = df_excel_simple.copy()
            df_histori['Tanggal_Scan'] = datetime.now().strftime('%Y-%m-%d')
            df_histori.to_sql('screener_history', db_engine, if_exists='append', index=False)
            
            print("🚀 DATABASE SUCCESS: Data 'screener_live' & 'screener_history' berhasil diamankan di Cloud.")
        except Exception as e: 
            print(f"❌ DATABASE ERROR: {e}")
        
    # BACKUP LOKAL EXCEL TETAP TERJAGA
    sheet_name_hari_ini = datetime.now().strftime('%Y-%B-%d')
    try:
        with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_excel_simple.to_excel(writer, sheet_name=sheet_name_hari_ini, index=False)
    except: pass
    
    for idx, row in dragon_candidates.iterrows():
        if "BUY" in str(row['Rekomendasi_Action']): simpan_grafik(dict_df_full[row['Ticker']], row['Ticker'], "Screener_Lolos")

# ==========================================
# 4. MONITOR COMMAND CENTER INTERAKTIF / AUTOMATION BYPASS
# ==========================================
# 🌟 NEW: DETEKTOR OTOMATIS GITHUB ACTIONS (BYPASS INPUT MENU UNTUK SERVER CLOUD)
RUN_AUTOMATED_WATCHLIST = os.getenv("GITHUB_ACTIONS") == "true" or IS_CLOUD

if RUN_AUTOMATED_WATCHLIST:
    print("\n🤖 Mode Otomatis Aktif: Memproses file Watchlist langsung ke Cloud Database...")
    path_w = os.path.join(FOLDER_WATCHLIST, 'Watchlist_Stock_26-05-2026.xlsx')
    if not os.path.exists(path_w):
        path_w = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))[0] if glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx")) else path_w
        
    if os.path.exists(path_w):
        df_watch = pd.read_excel(path_w)
        df_watch.columns = df_watch.columns.str.strip().str.upper()
        w_col = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']][0]
        watchlist_results = []
        
        for t in df_watch[w_col].dropna():
            clean_t = str(t).split('.')[0].strip().upper()
            if clean_t in dict_df_full:
                last_row = dict_df_full[clean_t].iloc[[-1]].copy()
                last_row['Expected_Days'] = model_days.predict(last_row[features])
                last_row['Expected_Upsize'] = model_upsize.predict(last_row[features])
                
                est_days_val = last_row['Expected_Days'].values[0]
                bb_w_val = last_row['BB_Width'].values[0]
                cvi_val = round(last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3) if est_days_val > 0 and bb_w_val > 0 else 0.0
                
                watchlist_results.append({
                    'Ticker': clean_t, 'Close': last_row['Close'].values[0],
                    'Support': int(round(last_row['Support'].values[0], 0)), 'Resistance': int(round(last_row['Resistance'].values[0], 0)),
                    'BB_Width_Str': f"{last_row['BB_Width'].values[0]*100:.2f}%", 'Vol_Ratio': round(last_row['Vol_Ratio'].values[0], 2),
                    'Vol_Velocity': round(last_row['Vol_Velocity'].values[0], 2), 'CMF': round(last_row['CMF'].values[0], 3),
                    'UD_Vol_Ratio': round(last_row['UD_Vol_Ratio'].values[0], 2), 'Hari_Ke_Breakout': f"{est_days_val:.1f} Hari",
                    'Potensial_Upsize': f"+{last_row['Expected_Upsize'].values[0]*100:.2f}%", 'CVI': cvi_val,
                    'Analisis_Kesimpulan': generate_kesimpulan(last_row.iloc[0]).strip(), 'Rekomendasi_Action': rekomendasi_action_mendalam(last_row.iloc[0])
                })
        if watchlist_results:
            df_watch_export = pd.DataFrame(watchlist_results).sort_values(by='CVI', ascending=False)
            df_watch_export.to_sql('watchlist_live', db_engine, if_exists='replace', index=False)
            print("🚀 WATCHLIST SUCCESS: Tabel 'watchlist_live' berhasil diupdate di Awan Cloud.")
    print("💤 Seluruh proses cloud selesai. Sistem dimatikan secara bersih.")
    sys.exit()

# BENTENG INTERAKTIF LOKAL (Hanya berjalan jika Anda running manual di Laptop)
print("\n" + "="*90)
print("💻 COMMAND CENTER INTERAKTIF LOCAL MODE")
print("• Ketik 'WATCH'  : Evaluasi massal & ekspor otomatis")
print("• Ketik 'TICKER' : Evaluasi manual satu per satu")
print("• Ketik 'EXIT'   : Keluar dari program")
print("="*90)

while True:
    try:
        pilihan = input("\n👉 Masukkan Perintah (WATCH/TICKER/EXIT): ").strip().upper()
        if pilihan == 'EXIT': print("Terminal ditutup."); break
        if pilihan == 'WATCH':
            path_w = os.path.join(FOLDER_WATCHLIST, 'Watchlist_Stock_26-05-2026.xlsx')
            if not os.path.exists(path_w):
                path_w = glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx"))[0] if glob.glob(os.path.join(FOLDER_WATCHLIST, "*.xlsx")) else path_w
            if not os.path.exists(path_w): print("❌ File watchlist tidak ditemukan."); continue
            
            df_watch = pd.read_excel(path_w)
            df_watch.columns = df_watch.columns.str.strip().str.upper()
            w_col = [c for c in df_watch.columns if c in ['TICKER', 'KODE', 'KODE SAHAM']][0]
            watchlist_results = []
            
            for t in df_watch[w_col].dropna():
                clean_t = str(t).split('.')[0].strip().upper()
                if clean_t in dict_df_full:
                    last_row = dict_df_full[clean_t].iloc[[-1]].copy()
                    last_row['Expected_Days'] = model_days.predict(last_row[features])
                    last_row['Expected_Upsize'] = model_upsize.predict(last_row[features])
                    est_days_val = last_row['Expected_Days'].values[0]
                    bb_w_val = last_row['BB_Width'].values[0]
                    cvi_val = round(last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3) if est_days_val > 0 and bb_w_val > 0 else 0.0
                    
                    print(f"  [{clean_t}] Close: {last_row['Close'].values[0]:<5} | Estimasi: {est_days_val:.1f} Hari | CVI: {cvi_val} | -> Action: {rekomendasi_action_mendalam(last_row.iloc[0])}")
                    watchlist_results.append({
                        'Ticker': clean_t, 'Close': last_row['Close'].values[0],
                        'Support': int(round(last_row['Support'].values[0], 0)), 'Resistance': int(round(last_row['Resistance'].values[0], 0)),
                        'BB_Width_Str': f"{last_row['BB_Width'].values[0]*100:.2f}%", 'Vol_Ratio': round(last_row['Vol_Ratio'].values[0], 2),
                        'Vol_Velocity': round(last_row['Vol_Velocity'].values[0], 2), 'CMF': round(last_row['CMF'].values[0], 3),
                        'UD_Vol_Ratio': round(last_row['UD_Vol_Ratio'].values[0], 2), 'Hari_Ke_Breakout': f"{est_days_val:.1f} Hari",
                        'Potensial_Upsize': f"+{last_row['Expected_Upsize'].values[0]*100:.2f}%", 'CVI': cvi_val,
                        'Analisis_Kesimpulan': generate_kesimpulan(last_row.iloc[0]).strip(), 'Rekomendasi_Action': rekomendasi_action_mendalam(last_row.iloc[0])
                    })
            if watchlist_results:
                df_watch_export = pd.DataFrame(watchlist_results).sort_values(by='CVI', ascending=False)
                with pd.ExcelWriter(FILE_MASTER_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    df_watch_export[cols_final].to_excel(writer, sheet_name='Watchlist_Analisis', index=False)
                print("🚀 Sukses mengekstrak analisa ke sheet 'Watchlist_Analisis'.")
                
        elif pilihan == 'TICKER':
            target_t = input("   Masukkan kode saham (misal: BBCA): ").strip().upper()
            if target_t in dict_df_full:
                last_row = dict_df_full[target_t].iloc[[-1]].copy()
                last_row['Expected_Days'] = model_days.predict(last_row[features])
                last_row['Expected_Upsize'] = model_upsize.predict(last_row[features])
                est_days_val = last_row['Expected_Days'].values[0]
                bb_w_val = last_row['BB_Width'].values[0]
                cvi_val = round(last_row['Expected_Upsize'].values[0] / (est_days_val * bb_w_val), 3) if est_days_val > 0 and bb_w_val > 0 else 0.0
                
                print(f"\n📊 --- DIAGNOSTIK KILAT EMITEN: {target_t} ---")
                print(f"   Harga Penutupan : Rp {last_row['Close'].values[0]:,.0f}")
                print(f"   Estimasi Hari   : {est_days_val:.1f} Hari Bursa")
                print(f"   Proyeksi Upsize : +{last_row['Expected_Upsize'].values[0]*100:.2f}%")
                print(f"   🎯 SKOR CVI     : {cvi_val}")
                print(f"   🎯 Tindakan     : {rekomendasi_action_mendalam(last_row.iloc[0])}")
            else: print("❌ Kode emiten tidak ditemukan.")
    except Exception as e: print(f"⚠️ Hambatan: {e}")
