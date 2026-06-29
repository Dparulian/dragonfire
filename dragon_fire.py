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


def save_screener_history(df_all_export, db_engine, today_str):
    """
    Simpan snapshot harian ke screener_history — bulletproof v4.
    - Lowercase semua kolom (Postgres always lowercase)
    - ALTER TABLE untuk kolom baru
    - DELETE pakai tanggal_scan lowercase (cocok Postgres)
    - INSERT bersih
    """
    try:
        df_h = df_all_export.copy()
        df_h.columns         = [c.lower() for c in df_h.columns]
        df_h['tanggal_scan'] = today_str

        with db_engine.connect() as conn:
            tbl_ok = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='screener_history')"
            )).scalar()

            if tbl_ok:
                exist_cols = set(
                    r[0].lower() for r in conn.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='screener_history'"
                    )).fetchall()
                )
                for col in sorted(set(df_h.columns) - exist_cols):
                    try:
                        conn.execute(text(
                            f"ALTER TABLE screener_history "
                            f"ADD COLUMN IF NOT EXISTS {col} TEXT"
                        ))
                    except Exception:
                        pass
                conn.commit()

                res = conn.execute(text(
                    "DELETE FROM screener_history WHERE tanggal_scan = :tgl"
                ), {"tgl": today_str})
                conn.commit()
                if res.rowcount:
                    print(f"   Hapus {res.rowcount} baris lama {today_str}.")

        df_h.to_sql('screener_history', db_engine, if_exists='append', index=False)
        print(f"   screener_history: +{len(df_h)} baris ({today_str}) OK")
        return True
    except Exception as e:
        import traceback
        print(f"screener_history ERROR: {e}")
        traceback.print_exc()
        return False


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
    # Signal line & histogram (untuk reversal detector)
    df['MACD_Sig']  = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Sig']

    # RSI 14 (untuk reversal detector — oversold < 35)
    delta  = df['Close'].diff()
    gain   = delta.where(delta > 0, 0).rolling(14).mean()
    loss   = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss.replace(0, 1e-9)))

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


# ── DETECTOR: REVERSAL WATCH ──────────────────────────────────────
def detect_reversal(row, df_hist):
    """
    Deteksi pola pembalikan (reversal) v3 — 9 improvements:
    1. StochRSI < 0.20 (extreme oversold presisi)
    2. ADX melemah (downtrend habis)
    3. Formal bullish divergence
    4. Volume konfirmasi dalam 10 hari
    5. Filter likuiditas: Close>=50, Vol_Ratio>=0.10, VMA20>=10.000 lot
    6. Priority Score 0-100+
    7. Penalti RSI > 50 (sinyal tidak reliable)
    8. Handle RSI = 0/NaN sebagai anomali Low Liquidity
    9. Tier lebih ketat: STRONG butuh RSI<30, WATCH butuh RSI<35 strict
    """
    try:
        close     = float(row.get('Close', 0))
        cmf_sl    = float(row.get('CMF_Slope', 0)) if row.get('CMF_Slope') is not None else 0.0
        ud_vol    = float(row.get('UD_Vol_Ratio', 0))
        macd_h    = float(row.get('MACD_Hist', 0)) if row.get('MACD_Hist') is not None else 0.0
        macd_sl   = float(row.get('MACD_Slope', 0))
        vol_ratio = float(row.get('Vol_Ratio', 0))

        if close <= 0: return False, {}

        # Improvement 5a: filter likuiditas dasar
        if vol_ratio < 0.10 or close < 50:
            return False, {}

        # Improvement 5b: VMA20 >= 10.000 lot/hari
        if df_hist is not None and len(df_hist) >= 20:
            try:
                vma20_lot = float(df_hist['Volume'].rolling(20).mean().iloc[-1])
                if vma20_lot < 10_000:
                    return False, {}
            except: pass

        # Kriteria 1: Drawdown dari High 52 minggu
        if df_hist is not None and len(df_hist) >= 60:
            high_52w = (df_hist['High'].tail(252).max()
                        if len(df_hist) >= 252 else df_hist['High'].max())
            drawdown = (close - high_52w) / high_52w
        else:
            drawdown = 0.0

        # Kriteria 2: RSI oversold — Improvement 8: handle RSI=0 sebagai anomali
        rsi_raw = row.get('RSI', None)
        low_liquidity_flag = False
        if rsi_raw is None or (isinstance(rsi_raw, float) and np.isnan(rsi_raw)):
            rsi_val = 50.0
            low_liquidity_flag = True
        else:
            rsi_val = float(rsi_raw)
            if rsi_val == 0.0:
                rsi_val = 50.0
                low_liquidity_flag = True

        # Improvement 1: StochRSI
        stoch_rsi = 0.5
        if df_hist is not None and len(df_hist) >= 28 and 'Close' in df_hist.columns:
            try:
                cs    = df_hist['Close'].tail(50)
                delta = cs.diff()
                g14   = delta.where(delta > 0, 0).rolling(14).mean()
                l14   = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi_s = 100 - (100 / (1 + g14 / l14.replace(0, 1e-9)))
                rsi_s = rsi_s.dropna()
                if len(rsi_s) >= 14:
                    rmin  = rsi_s.rolling(14).min().iloc[-1]
                    rmax  = rsi_s.rolling(14).max().iloc[-1]
                    stoch_rsi = float((rsi_s.iloc[-1] - rmin) / max(rmax - rmin, 1e-9))
            except: pass
        crit_stoch_rsi = stoch_rsi < 0.20

        # Improvement 2: ADX melemah
        adx_weakening = False
        if df_hist is not None and len(df_hist) >= 30:
            try:
                hs = df_hist['High'].tail(30); ls = df_hist['Low'].tail(30); cs2 = df_hist['Close'].tail(30)
                pdm = hs.diff().clip(lower=0); mdm = (-ls.diff()).clip(lower=0)
                pdm = pdm.where(pdm > mdm, 0); mdm = mdm.where(mdm > pdm, 0)
                tr  = pd.concat([hs-ls,(hs-cs2.shift()).abs(),(ls-cs2.shift()).abs()],axis=1).max(axis=1)
                atr = tr.rolling(14).mean().replace(0, 1e-9)
                pdi = 100*pdm.rolling(14).mean()/atr; mdi = 100*mdm.rolling(14).mean()/atr
                dx  = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,1e-9)
                adx_ser = dx.rolling(14).mean().dropna()
                if len(adx_ser) >= 5:
                    adx_weakening = bool(adx_ser.iloc[-1] < adx_ser.iloc[-5])
            except: pass

        # Improvement 3: Formal bullish divergence
        bullish_divergence = False
        if df_hist is not None and len(df_hist) >= 25:
            try:
                c20 = df_hist['Close'].tail(20)
                if float(c20.iloc[-1]) <= float(c20.min()):
                    if 'MACD' in df_hist.columns and 'MACD_Sig' in df_hist.columns:
                        h20 = (df_hist['MACD'] - df_hist['MACD_Sig']).tail(20)
                        bullish_divergence = bool(float(h20.iloc[-1]) > float(h20.min()))
                    else:
                        bullish_divergence = bool(macd_sl > 0)
            except: pass

        # Improvement 4: Volume konfirmasi
        vol_confirmed = False
        if df_hist is not None and len(df_hist) >= 15:
            try:
                v10  = df_hist['Volume'].tail(10)
                vm20 = df_hist['Volume'].rolling(20).mean().tail(10)
                vol_confirmed = bool(np.any(v10.values / (vm20.values + 1e-9) >= 1.5))
            except: pass

        # 5 kriteria original
        crit_drawdown = drawdown <= -0.30
        crit_rsi      = rsi_val < 35
        crit_cmf_turn = cmf_sl > 0
        crit_macd_div = macd_sl > 0 and macd_h > -0.001
        crit_ud_vol   = ud_vol >= 1.0

        score_rev   = sum([crit_drawdown, crit_rsi, crit_cmf_turn, crit_macd_div, crit_ud_vol])
        is_reversal = score_rev >= 4

        # Improvement 6: Priority Score
        cmf_val = float(row.get('CMF', 0) or 0)
        p_score = score_rev * 6
        p_score += max(0.0, (35.0 - rsi_val) * 1.25)
        p_score += min(20.0, abs(drawdown) * 100 * 0.25)
        p_score += 15.0 if cmf_val > 0.3 else (10.0 if cmf_val > 0 else 5.0)
        p_score += min(10.0, ud_vol * 2.0)

        # Improvement 7: Penalti RSI > 50
        if rsi_val > 50:
            p_score -= (rsi_val - 50) * 0.5

        if crit_stoch_rsi:     p_score += 5.0
        if adx_weakening:      p_score += 3.0
        if bullish_divergence: p_score += 5.0
        if vol_confirmed:      p_score += 3.0

        # Improvement 8: Penalti Low Liquidity
        if low_liquidity_flag:
            p_score -= 20.0

        # Improvement 9: Tier lebih ketat
        if (score_rev == 5 and rsi_val < 30
                and ud_vol >= 1.5 and not low_liquidity_flag):
            rev_tier = 'STRONG REVERSAL'
        elif (score_rev >= 4 and crit_rsi and cmf_sl > 0 and not low_liquidity_flag):
            rev_tier = 'REVERSAL WATCH'
        else:
            rev_tier = 'PANTAU REVERSAL'

        detail = {
            'Rev_Drawdown_pct':  round(drawdown * 100, 1),
            'Rev_RSI':           round(rsi_val, 1),
            'Rev_CMF_Slope':     round(cmf_sl, 4),
            'Rev_MACD_Div':      crit_macd_div,
            'Rev_UD_Vol':        round(ud_vol, 2),
            'Rev_Score':         score_rev,
            'Rev_Priority':      round(p_score, 1),
            'Rev_Tier':          rev_tier,
            'Rev_StochRSI':      round(stoch_rsi, 3),
            'Rev_ADX_Weak':      adx_weakening,
            'Rev_Divergence':    bullish_divergence,
            'Rev_Vol_Confirm':   vol_confirmed,
            'Rev_Low_Liquidity': low_liquidity_flag,
        }
        return is_reversal, detail
    except:
        return False, {}

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
        data = yf.download(batch, period="2y", group_by='ticker',
                            auto_adjust=False, progress=False)
                            # auto_adjust=False: pakai harga RAW agar Close = harga pasar
                            # (auto_adjust=True menghasilkan Adjusted Close yang sudah
                            # dikurangi dividen — menyebabkan beda harga vs broker/Yahoo)
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
        df_raw = raw_data[t_jk].copy()
        if 'Adj Close' in df_raw.columns:
            df_raw = df_raw.drop(columns=['Adj Close'])   # kolom ekstra dari auto_adjust=False
        df_raw = df_raw.dropna(subset=['Close'])
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

# ── Hitung Reversal Watch flag ────────────────────────────────────
print("🔄 Mendeteksi pola reversal (koreksi dalam + sinyal teknikal berbalik)...")
reversal_flags  = {}
reversal_details= {}
for _, row_rev in df_latest_global.iterrows():
    t = row_rev.get('Ticker', '')
    df_h = dict_df_full.get(t, None)
    is_rev, det = detect_reversal(row_rev, df_h)
    reversal_flags[t]   = is_rev
    reversal_details[t] = det

df_latest_global['Is_Reversal']   = df_latest_global['Ticker'].map(reversal_flags).fillna(False)
df_latest_global['Rev_Score']     = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Score', 0)
)
df_latest_global['Rev_Drawdown']  = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Drawdown_pct', 0)
)
df_latest_global['Rev_RSI']       = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_RSI', 0)
)
df_latest_global['Rev_Priority']  = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Priority', 0.0)
)
df_latest_global['Rev_Tier']      = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Tier', 'PANTAU REVERSAL')
)
df_latest_global['Rev_StochRSI']  = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_StochRSI', 0.5)
)
df_latest_global['Rev_Divergence']= df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Divergence', False)
)
df_latest_global['Rev_VolConfirm']= df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Vol_Confirm', False)
)
df_latest_global['Rev_Low_Liquidity'] = df_latest_global['Ticker'].map(
    lambda t: reversal_details.get(t, {}).get('Rev_Low_Liquidity', False)
)
n_reversal = int(df_latest_global['Is_Reversal'].sum())
print(f"   🔄 Pola reversal terdeteksi: {n_reversal} emiten")

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
df_latest_global['RSI_raw']                = df_latest_global['RSI'].round(1) if 'RSI' in df_latest_global.columns else 0.0

# ── B1: Profit Target Dinamis ──────────────────────────────────────
def _get_profit_target(row):
    try:
        upsize_str = str(row.get('Potensial_Upsize_raw', '+10%')).replace('+','').replace('%','')
        pred_upsize = float(upsize_str)
        return max(10.0, pred_upsize * 0.75)
    except:
        return 10.0
df_latest_global['Profit_Target'] = df_latest_global.apply(_get_profit_target, axis=1).round(1)

# ── B2: CVI Tier ────────────────────────────────────────────────────
def _cvi_tier(v):
    try:
        f = float(v)
        if f > 0.15:  return 'Tinggi'
        if f >= 0.07: return 'Sedang'
        return 'Rendah'
    except: return 'Rendah'
df_latest_global['CVI_Tier'] = df_latest_global['CVI_raw'].apply(_cvi_tier)

# ── B3: Conf Score (0-5) ────────────────────────────────────────────
def _conf_score(row):
    s = 0
    try:
        if float(row.get('CMF', 0) or 0) >= 0.10: s += 1
        if float(row.get('UD_Vol_Ratio', 0) or 0) >= 2.00: s += 1
        bb = float(str(row.get('BB_Width_Str_raw','100%')).replace('%',''))
        if bb <= 8.0: s += 1
        if float(row.get('Vol_Velocity', 0) or 0) >= 0.90: s += 1
        adx_ok = float(row.get('ADX', 0) or 0) >= 25
        macd_ok = bool(row.get('MACD_PreCross', False))
        if adx_ok or macd_ok: s += 1
    except: pass
    return s
df_latest_global['Conf_Score'] = df_latest_global.apply(_conf_score, axis=1)

# ── ADX ─────────────────────────────────────────────────────────────
if 'ADX' not in df_latest_global.columns:
    df_latest_global['ADX'] = 0.0

cols_final = [
    'Ticker', 'Close', 'Support', 'Resistance', 'BB_Width_Str',
    'Vol_Ratio', 'Vol_Velocity', 'CMF', 'UD_Vol_Ratio',
    'Hari_Ke_Breakout', 'Potensial_Upsize', 'CVI',
    'MACD', 'MACD_Slope', 'MACD_PreCross',
    'Alert_Flag', 'Analisis_Kesimpulan', 'Rekomendasi_Action',
    'Is_Reversal', 'Rev_Score', 'Rev_Drawdown', 'Rev_RSI',
    'Profit_Target', 'CVI_Tier', 'Conf_Score', 'ADX',
]

# Master semua emiten
_export_cols_src = [
    'Ticker', 'Close',
    'Support_raw', 'Resistance_raw',
    'BB_Width_Str_raw', 'Vol_Ratio', 'Vol_Velocity',
    'CMF', 'UD_Vol_Ratio',
    'Hari_Ke_Breakout_raw', 'Potensial_Upsize_raw',
    'CVI_raw', 'MACD_raw', 'MACD_Slope_raw', 'MACD_PreCross',
    'Alert_Flag', 'Analisis_Kesimpulan_raw', 'Rekomendasi_Action_raw',
    'Is_Reversal', 'Rev_Score', 'Rev_Drawdown', 'Rev_RSI',
    'Profit_Target', 'CVI_Tier', 'Conf_Score', 'ADX',
]
# Pastikan semua kolom sumber ada
_export_cols_src = [c for c in _export_cols_src if c in df_latest_global.columns]
df_all_export = df_latest_global[_export_cols_src].copy()
df_all_export.columns = [c for c in cols_final if c in
    ['Ticker','Close','Support','Resistance','BB_Width_Str',
     'Vol_Ratio','Vol_Velocity','CMF','UD_Vol_Ratio',
     'Hari_Ke_Breakout','Potensial_Upsize','CVI',
     'MACD','MACD_Slope','MACD_PreCross',
     'Alert_Flag','Analisis_Kesimpulan','Rekomendasi_Action',
     'Is_Reversal','Rev_Score','Rev_Drawdown','Rev_RSI',
     'Profit_Target','CVI_Tier','Conf_Score','ADX'
    ]][:len(_export_cols_src)]

# ── Reversal candidates: TERPISAH dari screener utama ────────────
# Tidak lolos BB filter, tapi menunjukkan sinyal pembalikan
reversal_candidates = df_latest_global[
    (df_latest_global['Is_Reversal'] == True) &
    (df_latest_global['Vol_Ratio'] >= MIN_VOL_RATIO)
].copy()
reversal_candidates['RSI_str'] = df_latest_global.loc[
    reversal_candidates.index, 'Rev_RSI'
].round(1).astype(str)
reversal_candidates['BB_Width_Str'] = (
    reversal_candidates['BB_Width'] * 100
).round(2).astype(str) + '%'
n_rev_cand = len(reversal_candidates)
print(f"🔄 Reversal candidates: {n_rev_cand} emiten masuk daftar pantau reversal")

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
            # Simpan reversal candidates ke tabel tersendiri
            if not reversal_candidates.empty:
                rev_cols = [c for c in [
                    'Ticker', 'Close', 'BB_Width_Str', 'Vol_Ratio', 'Vol_Velocity',
                    'CMF', 'UD_Vol_Ratio', 'MACD', 'MACD_Slope', 'MACD_PreCross',
                    'ADX', 'CVI', 'CVI_Tier', 'Conf_Score', 'Profit_Target',
                    'Rekomendasi_Action', 'Analisis_Kesimpulan', 'Alert_Flag',
                    'Rev_Score', 'Rev_Priority', 'Rev_Tier',
                    'Rev_Drawdown', 'Rev_RSI', 'Rev_StochRSI',
                    'Rev_Divergence', 'Rev_VolConfirm', 'Rev_Low_Liquidity',
                    'Support', 'Resistance',
                ] if c in reversal_candidates.columns]
                rev_export = reversal_candidates[rev_cols].copy()
                rev_export.to_sql('reversal_live', db_engine, if_exists='replace', index=False)

            # ── screener_history: schema-safe append ──────────────
            # FIX: if_exists='append' gagal diam-diam ketika skema tabel di Supabase
            # tidak cocok dengan DataFrame (misal: kolom MACD/Alert_Flag belum ada
            # di tabel lama yang dibuat sebelum kolom ini ditambahkan).
            # Solusi: cek skema tabel dulu, jika berbeda hapus & buat ulang,
            # lalu delete baris hari ini (idempotent) sebelum insert baru.
            save_screener_history(df_all_export, db_engine, today_wib_str())

            print(f"\n🚀 DATABASE SUCCESS:")
            print(f"   → screener_live   : {len(df_excel_simple)} baris")
            print(f"   → all_stocks_live : {len(df_all_export)} baris")
            print(f"   → screener_history: {today_wib_str()} (lihat log di atas)")
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
            save_screener_history(df_all_export, db_engine, today_wib_str())
            print(f"🚀 Master DB diupdate. screener_history: {today_wib_str()} (lihat log)")
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
