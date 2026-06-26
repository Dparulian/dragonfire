import yfinance as yf
import pandas as pd
import numpy as np
import os
import sys
import glob
import warnings
import logging
from datetime import datetime, timedelta, timezone
from sklearn.ensemble import (
    RandomForestClassifier, VotingClassifier, GradientBoostingClassifier
)
from sqlalchemy import create_engine, text
import urllib.parse

warnings.filterwarnings("ignore")
logging.getLogger("lightgbm").setLevel(logging.ERROR)
logging.getLogger("xgboost").setLevel(logging.ERROR)

# ── Waktu Jakarta (GMT+7) ─────────────────────────────────────────
_WIB = timezone(timedelta(hours=7))
def now_wib():      return datetime.now(tz=_WIB)
def today_wib_str():return now_wib().strftime("%Y-%m-%d")

# ── Library opsional ──────────────────────────────────────────────
try:    from lightgbm import LGBMClassifier;  HAS_LGBM = True
except: HAS_LGBM = False
try:    from xgboost import XGBClassifier;    HAS_XGB  = True
except: HAS_XGB  = False

# ══════════════════════════════════════════════════════════════════
# 1. KONFIGURASI
# ══════════════════════════════════════════════════════════════════
FOLDER_OUTPUT    = "LAPORAN HARIAN"
FOLDER_WATCHLIST = "WATCHLIST"
os.makedirs(FOLDER_OUTPUT,    exist_ok=True)
os.makedirs(FOLDER_WATCHLIST, exist_ok=True)

# Tiger Hunter parameters
MIN_CONF_STRONG_BUY  = 0.15
MIN_SCORE_SCREENING  = 70
MIN_HARGA            = 100
BIG_CAP_LIMIT        = 50_000_000_000_000
MID_CAP_LIMIT        =  5_000_000_000_000
SMALL_CAP_LIMIT      =  1_000_000_000_000
MIN_DATA_DAYS        = 60       # yfinance: pakai 60 (lebih longgar dari Excel 100)

# Shared Dragon parameters
BB_WIDTH_MAX  = 0.15
MIN_CMF       = -0.05
MIN_UD_RATIO  = 1.20

STATUS_RANK = {
    "⚡ BREAKOUT":      5,
    "🚀 STRONG BUY":   4,
    "📦 ACCUMULATION": 3,
    "📈 SUPER BULLISH": 2,
    "🔍 WATCHING":      1,
}

# Sektor IDX → yfinance ticker
SECTOR_INDICES = [
    "IDXENERGY","IDXBASIC","IDXINDUST","IDXNONCYC","IDXCYCLIC",
    "IDXHEALTH","IDXFINANCE","IDXPROPERT","IDXTECHNO","IDXINFRA","IDXTRANS"
]
SECTOR_YF = {s: f"{s}.JK" for s in SECTOR_INDICES}
SECTOR_YF["IHSG"] = "^JKSE"

# ── Database connector ────────────────────────────────────────────
def sanitize_db_url(url):
    if not url: return url
    if "=" in url and not url.strip().startswith("postgres"):
        try: url = url.split("=",1)[1]
        except: pass
    url = url.strip().strip('"').strip("'")
    prefix = "postgresql://"
    if url.startswith("postgres://"): url = url.replace("postgres://",prefix,1)
    if url.startswith(prefix):
        rem = url[len(prefix):]
        auth_part, path_part = rem.rsplit("/",1) if "/" in rem else (rem,"")
        if "@" in auth_part:
            creds, host_port = auth_part.rsplit("@",1)
            if ":" in creds:
                user, pw = creds.split(":",1)
                return f"{prefix}{user}:{urllib.parse.quote_plus(pw)}@{host_port}/{path_part}"
    return url

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.strip():
    path_secrets = os.path.join(".streamlit","secrets.toml")
    if os.path.exists(path_secrets):
        try:
            with open(path_secrets) as f:
                for line in f:
                    if "DATABASE_URL" in line and "=" in line:
                        DATABASE_URL = line.split("=",1)[1].strip().strip('"').strip("'")
                        break
        except: pass

DATABASE_URL = sanitize_db_url(DATABASE_URL)
IS_CLOUD = bool(DATABASE_URL and DATABASE_URL.strip())

if IS_CLOUD:
    try:
        db_engine = create_engine(DATABASE_URL)
        print("🌐 Tiger Cloud Mode: Koneksi ke Supabase siap.")
    except Exception as e:
        print(f"❌ Gagal init DB engine: {e}"); IS_CLOUD = False
else:
    print("💻 Tiger Local Mode.")

# ══════════════════════════════════════════════════════════════════
# 2. DATA DOWNLOAD (yfinance — pengganti folder DATA HARIAN)
# ══════════════════════════════════════════════════════════════════
def load_daftar_saham():
    FILE_TICKER = "daftar_saham.csv"
    if not os.path.exists(FILE_TICKER):
        for alt in ["Ticker Saham.csv","TIcker Saham.csv"]:
            if os.path.exists(alt): FILE_TICKER = alt; break
    if not os.path.exists(FILE_TICKER):
        print(f"❌ {FILE_TICKER} tidak ditemukan."); sys.exit()

    tickers = []
    with open(FILE_TICKER, encoding="utf-8-sig") as f:
        for line in f:
            kode = line.strip().upper().split(".")[0].strip()
            if 2 <= len(kode) <= 4 and kode.isalpha():
                tickers.append(kode)
    tickers = sorted(list(set(tickers)))
    print(f"📂 Tiger: {len(tickers)} emiten dari {FILE_TICKER}")
    return tickers

def download_market_data(tickers_jk, period="1y"):
    """Download OHLCV untuk semua saham sekaligus via yfinance batch."""
    batch_size = 100
    all_dfs    = []
    for i in range(0, len(tickers_jk), batch_size):
        batch = tickers_jk[i:i+batch_size]
        print(f"   ⏳ Tiger Batch {i//batch_size+1} ({len(batch)} emiten)...")
        try:
            raw = yf.download(batch, period=period, group_by="ticker",
                              auto_adjust=True, progress=False)
            all_dfs.append(raw)
        except Exception as e:
            print(f"   ⚠️  Batch gagal: {e}")
    if not all_dfs: return None
    return pd.concat(all_dfs, axis=1)

def download_sector_ihsg():
    """Download data IHSG dan sektor idx dari yfinance."""
    symbols = list(SECTOR_YF.values())
    try:
        raw = yf.download(symbols, period="1y", group_by="ticker",
                          auto_adjust=True, progress=False)
        return raw
    except Exception as e:
        print(f"⚠️  Download sektor/IHSG gagal: {e}")
        return None

def extract_ticker_df(raw_data, ticker_jk):
    """Ekstrak DataFrame OHLCV untuk satu ticker dari batch download."""
    try:
        if ticker_jk not in raw_data.columns.get_level_values(0):
            return pd.DataFrame()
        df = raw_data[ticker_jk].dropna(subset=["Close"])
        df = df.reset_index()
        if "Date" not in df.columns and "index" in df.columns:
            df.rename(columns={"index":"Date"}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        return df.sort_values("Date").reset_index(drop=True)
    except: return pd.DataFrame()

def build_sector_features(sector_raw):
    """Bangun fitur IHSG dan sektor dari data yfinance."""
    if sector_raw is None: return {}
    rows = {}
    for name, yf_sym in SECTOR_YF.items():
        try:
            if yf_sym not in sector_raw.columns.get_level_values(0): continue
            s = sector_raw[yf_sym]["Close"].dropna()
            if s.empty: continue
            s.index = pd.to_datetime(s.index).tz_localize(None)
            rows[name] = s
        except: continue
    if not rows: return {}

    df_sec = pd.DataFrame(rows)
    result = {}
    for col in df_sec.columns:
        s = df_sec[col].dropna()
        if s.empty: continue
        ma20 = s.rolling(20).mean()
        mom5 = s.pct_change(5)
        trend = (s > ma20).astype(int)
        if len(s) >= 1:
            result[f"{col}_Close"]  = float(s.iloc[-1])
            result[f"{col}_Trend"]  = int(trend.iloc[-1]) if not pd.isna(trend.iloc[-1]) else 0
            result[f"{col}_Mom5"]   = float(mom5.iloc[-1]) if not pd.isna(mom5.iloc[-1]) else 0.0

    trend_cols = [v for k,v in result.items() if k.endswith("_Trend") and k != "IHSG_Trend"]
    result["Sector_Breadth_Ratio"] = sum(trend_cols) / len(trend_cols) if trend_cols else 0.5
    mom5_cols  = [v for k,v in result.items() if k.endswith("_Mom5") and k != "IHSG_Mom5"]
    result["Sector_AvgMom5"] = np.mean(mom5_cols) if mom5_cols else 0.0
    return result

# ══════════════════════════════════════════════════════════════════
# 3. FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════
def calculate_atr(df, period=14):
    hl  = df["High"] - df["Low"]
    hcp = np.abs(df["High"] - df["Close"].shift())
    lcp = np.abs(df["Low"]  - df["Close"].shift())
    tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def compute_features(df, sector_features=None):
    """Hitung semua fitur teknikal + inject fitur sektor/IHSG."""
    d = df.copy().sort_values("Date").reset_index(drop=True)
    close, high, low, vol = d["Close"], d["High"], d["Low"], d["Volume"]

    # MA
    d["MA5"]  = close.rolling(5).mean()
    d["MA10"] = close.rolling(10).mean()
    d["MA20"] = close.rolling(20).mean()
    d["MA50"] = close.rolling(50).mean()

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["MACD"]        = ema12 - ema26
    d["MACD_Signal"] = d["MACD"].ewm(span=9, adjust=False).mean()
    d["MACD_Hist"]   = d["MACD"] - d["MACD_Signal"]

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    d["BB_Upper"]   = bb_mid + 2*bb_std
    d["BB_Lower"]   = bb_mid - 2*bb_std
    d["BB_Width"]   = (d["BB_Upper"] - d["BB_Lower"]) / (bb_mid + 1e-9)
    d["BB_Pct"]     = (close - d["BB_Lower"]) / (d["BB_Upper"] - d["BB_Lower"] + 1e-9)
    d["BB_Squeeze"] = (d["BB_Width"] < d["BB_Width"].rolling(50).mean()*0.85).astype(int)

    # RSI
    delta = close.diff()
    g14   = delta.where(delta>0,0).rolling(14).mean()
    l14   = (-delta.where(delta<0,0)).rolling(14).mean()
    d["RSI"] = 100 - (100/(1 + g14/(l14+1e-9)))

    # CCI
    tp      = (high+low+close)/3
    tp_ma   = tp.rolling(20).mean()
    tp_mad  = tp.rolling(20).apply(lambda x: np.abs(x-x.mean()).mean(), raw=True)
    d["CCI"] = (tp - tp_ma)/(0.015*tp_mad + 1e-9)

    # ATR / Std
    d["ATR"]      = calculate_atr(d, 14)
    d["ATR_Pct"]  = d["ATR"]/(close+1e-9)
    d["Std20_Pct"]= close.rolling(20).std()/(close+1e-9)

    # Volume
    d["VMA5"]  = vol.rolling(5).mean()
    d["VMA20"] = vol.rolling(20).mean()
    d["Vol_Ratio5"]  = vol/(d["VMA5"] +1e-9)
    d["Vol_Ratio20"] = vol/(d["VMA20"]+1e-9)
    d["Vol_Buildup"] = vol.rolling(5).mean()/(d["VMA20"]+1e-9)

    # OBV
    d["OBV"]       = (np.sign(close.diff())*vol).fillna(0).cumsum()
    d["OBV_MA20"]  = d["OBV"].rolling(20).mean()
    d["OBV_Slope10"] = (d["OBV"] - d["OBV"].shift(10))/(vol.rolling(10).mean()*10+1e-9)

    # Momentum
    d["Mom_1"]  = close.pct_change(1)
    d["Mom_3"]  = close.pct_change(3)
    d["Mom_5"]  = close.pct_change(5)
    d["Mom_10"] = close.pct_change(10)
    d["Mom_20"] = close.pct_change(20)
    d["Price_MA20_Ratio"] = close/(d["MA20"]+1e-9)
    d["Price_MA50_Ratio"] = close/(d["MA50"]+1e-9)

    # ADX
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm.where(plus_dm>minus_dm,0), 0)
    atr_adx  = d["ATR"]
    plus_di  = 100*plus_dm.rolling(14).mean()/(atr_adx+1e-9)
    minus_di = 100*minus_dm.rolling(14).mean()/(atr_adx+1e-9)
    dx       = 100*(plus_di-minus_di).abs()/(plus_di+minus_di+1e-9)
    d["ADX"] = dx.rolling(14).mean()

    # UD Vol Ratio (Dragon method)
    d["Up_Vol"]           = np.where(d["Mom_1"]>0, vol, 0)
    d["Down_Vol"]         = np.where(d["Mom_1"]<0, vol, 0)
    d["UD_Vol_Ratio_Dragon"] = d["Up_Vol"].rolling(20).sum()/d["Down_Vol"].rolling(20).sum().replace(0,1)

    # CMF
    clv      = ((close-low)-(high-close))/(high-low+1e-9)
    d["CMF"] = (clv*vol).rolling(20).sum()/(vol.rolling(20).sum()+1e-9)

    # Percentile ranks
    d["RSI_Pct"]    = d["RSI"].rank(pct=True)
    d["Vol_Pct"]    = vol.rank(pct=True)
    d["MACD_H_Pct"] = d["MACD_Hist"].rank(pct=True)
    d["Mom5_Pct"]   = d["Mom_5"].rank(pct=True)

    # Foreign flow: tidak tersedia di yfinance → set ke 0
    d["Foreign_Net_5d"]   = 0.0
    d["Foreign_Net_20d"]  = 0.0
    d["Foreign_Net_Accum"]= 0.0
    d["Nilai_Ratio"]      = 1.0
    d["Freq_Ratio"]       = 1.0

    # Inject sektor/IHSG features
    sf = sector_features or {}
    d["IHSG_Ret"]              = sf.get("IHSG_Mom5", 0.0)
    d["IHSG_Trend"]            = sf.get("IHSG_Trend", 0)
    d["IHSG_Mom5"]             = sf.get("IHSG_Mom5", 0.0)
    d["Sector_Breadth_Ratio"]  = sf.get("Sector_Breadth_Ratio", 0.5)
    d["Sector_AvgMom5"]        = sf.get("Sector_AvgMom5", 0.0)
    for s in SECTOR_INDICES:
        d[f"{s}_Trend"] = sf.get(f"{s}_Trend", 0)
        d[f"{s}_Mom5"]  = sf.get(f"{s}_Mom5",  0.0)

    # Home sector (fallback: IHSG)
    d["Home_Trend"] = sf.get("IHSG_Trend", 0)
    d["Home_Mom5"]  = sf.get("IHSG_Mom5",  0.0)
    d["Home_RS"]    = d["Mom_5"] - sf.get("IHSG_Mom5", 0.0)
    d["Home_Rank"]  = 6.0
    for s in SECTOR_INDICES:
        d[f"Sec_{s}"] = 0.0

    d["Alpha_vs_IHSG"] = d["Mom_5"] - sf.get("IHSG_Mom5", 0.0)
    return d

# ══════════════════════════════════════════════════════════════════
# 4. MODEL & SCORING
# ══════════════════════════════════════════════════════════════════
FEATURE_COLS = [
    "Price_MA20_Ratio","Price_MA50_Ratio","MACD_Signal","MACD_Hist",
    "RSI","RSI_Pct","Vol_Ratio5","Vol_Ratio20","Vol_Buildup","Vol_Pct",
    "Mom_5","Mom_20","Alpha_vs_IHSG","MACD_H_Pct","Mom5_Pct","ATR_Pct",
    "CMF","OBV_Slope10",
    "Foreign_Net_5d","Foreign_Net_20d","Foreign_Net_Accum",
    "Nilai_Ratio","Freq_Ratio",
    "Home_Trend","Home_Mom5","Home_RS","Home_Rank"
] + [f"Sec_{s}" for s in SECTOR_INDICES]

IHSG_COLS = [
    "IHSG_Ret","IHSG_Trend","IHSG_Mom5","Sector_Breadth_Ratio","Sector_AvgMom5"
] + [f"{s}_Trend" for s in SECTOR_INDICES] + [f"{s}_Mom5" for s in SECTOR_INDICES]

def build_ensemble_model():
    rf = RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                 max_features="sqrt", random_state=42, n_jobs=-1)
    estimators = [("rf", rf)]
    if HAS_LGBM:
        estimators.append(("lgbm", LGBMClassifier(n_estimators=300, learning_rate=0.05,
            max_depth=6, num_leaves=31, min_child_samples=10, subsample=0.8,
            colsample_bytree=0.8, random_state=42, verbose=-1)))
    if HAS_XGB:
        estimators.append(("xgb", XGBClassifier(n_estimators=300, learning_rate=0.05,
            max_depth=6, subsample=0.8, colsample_bytree=0.8, random_state=42,
            eval_metric="logloss", verbosity=0)))
    if len(estimators) == 1:
        estimators.append(("gbm", GradientBoostingClassifier(n_estimators=200,
            learning_rate=0.05, max_depth=5, random_state=42)))
    return VotingClassifier(estimators, voting="soft")

def compute_ichimoku(df):
    h, l = df["High"], df["Low"]
    d = df.copy()
    d["Ichi_Tenkan"]    = (h.rolling(9).max() + l.rolling(9).min())/2
    d["Ichi_Kijun"]     = (h.rolling(26).max() + l.rolling(26).min())/2
    d["Ichi_SpanA"]     = ((d["Ichi_Tenkan"]+d["Ichi_Kijun"])/2).shift(26)
    d["Ichi_SpanB"]     = ((h.rolling(52).max()+l.rolling(52).min())/2).shift(26)
    d["Ichi_KumoTop"]   = d[["Ichi_SpanA","Ichi_SpanB"]].max(axis=1)
    d["Ichi_KumoBottom"]= d[["Ichi_SpanA","Ichi_SpanB"]].min(axis=1)
    return d

def compute_vrvp(df, lookback=252, bins=50):
    d = df.tail(lookback).copy()
    if len(d) < 30: return None
    lo_min, hi_max, current = d["Low"].min(), d["High"].max(), d["Close"].iloc[-1]
    if hi_max <= lo_min: return None
    edges  = np.linspace(lo_min, hi_max, bins+1)
    centers= (edges[:-1]+edges[1:])/2
    bsize  = edges[1]-edges[0]
    vp     = np.zeros(bins)
    for _, row in d.iterrows():
        b_lo = max(0, int((row["Low"]-lo_min)/bsize))
        b_hi = min(bins-1, int((row["High"]-lo_min)/bsize))
        vp[b_lo:b_hi+1] += row["Volume"]/max(1, b_hi-b_lo+1)
    above = vp.copy(); above[centers<=current] = 0
    return {"next_res": centers[int(above.argmax())] if above.max()>0 else current*1.10}

def analyze_ticker(ticker, df_raw, sector_features, force_return=False):
    """Analisis satu ticker — return dict hasil atau None jika tidak lolos."""
    df = compute_features(df_raw, sector_features)
    if len(df) < MIN_DATA_DAYS: return None

    last, prev = df.iloc[-1], df.iloc[-2]
    if last["Close"] < MIN_HARGA:
        return None  # filter penny

    shares = df.get("Shares", pd.Series([0]*len(df))).iloc[-1] if "Shares" in df.columns else 0
    market_cap = last["Close"] * shares if shares > 0 else 0

    # Target: naik 4% dalam 5 atau 10 hari
    up5d  = df["Close"].shift(-5)  > df["Close"]*1.04
    up10d = df["Close"].shift(-10) > df["Close"]*1.04
    df["Target"] = (up5d | up10d).astype(int)

    use_cols = FEATURE_COLS.copy()
    for c in IHSG_COLS:
        if c in df.columns: use_cols.append(c)
    use_cols = list(dict.fromkeys([c for c in use_cols if c in df.columns]))

    df_ml       = df[use_cols+["Target"]].dropna()
    ai_conf_val = 0.5
    if len(df_ml) >= 40 and df_ml["Target"].nunique() >= 2:
        try:
            model = build_ensemble_model()
            model.fit(df_ml[use_cols], df_ml["Target"])
            X_latest = df[use_cols].dropna().tail(1)
            if not X_latest.empty:
                prob = model.predict_proba(X_latest)[0]
                ai_conf_val = float(prob[1]) if len(prob)>1 else 0.5
        except: pass

    df_ichi  = compute_ichimoku(df)
    last_ich = df_ichi.iloc[-1]

    is_volume_explosion = last["Vol_Ratio20"] > 2.5
    is_breakout   = (last["Vol_Ratio20"]>1.75 and last["Close"]>last["MA20"]
                     and last["Close"]>prev["Close"])
    is_strong_buy = (ai_conf_val>=MIN_CONF_STRONG_BUY and last["MACD_Hist"]>0
                     and last["RSI"]<75)

    score = 0
    if last["Close"]>last["MA20"]:                        score += 15
    if last["MA20"]>last["MA50"]:                         score += 15
    if last["MACD_Hist"]>0:                               score += 10
    if last.get("MACD_Signal",0)>0:                       score += 10
    if 40<last["RSI"]<70:                                 score += 10
    if last["Vol_Ratio20"]>1.1:                           score += 10
    if last.get("Vol_Buildup",1)>1.15:                    score += 10
    if last.get("CMF",0)>0.05:                            score += 10
    if last.get("OBV_Slope10",0)>0:                       score += 10
    if last.get("Foreign_Net_Accum",0)>=2:                score += 10
    if ai_conf_val>=0.25:                                 score += 10
    elif ai_conf_val>=0.15:                               score += 5
    tk_bull = (not pd.isna(last_ich["Ichi_Tenkan"])
               and not pd.isna(last_ich["Ichi_Kijun"])
               and last_ich["Ichi_Tenkan"]>last_ich["Ichi_Kijun"])
    if tk_bull: score += 3
    if is_volume_explosion: score += 20; is_breakout = True

    # Status
    if is_breakout:             status = "⚡ BREAKOUT"
    elif is_strong_buy:         status = "🚀 STRONG BUY"
    elif last["BB_Squeeze"]==1 and last["Vol_Ratio20"]<1.5: status = "📦 ACCUMULATION"
    elif score>=80 and last["Mom_5"]>0: status = "📈 SUPER BULLISH"
    else:                       status = "🔍 WATCHING"

    if not force_return and status not in ["⚡ BREAKOUT","🚀 STRONG BUY","📦 ACCUMULATION"]:
        return None

    # Ichimoku cloud position
    kt = last_ich.get("Ichi_KumoTop",np.nan)
    kb = last_ich.get("Ichi_KumoBottom",np.nan)
    if pd.isna(kt):                   ichi_pos = "–"
    elif last["Close"]>kt:             ichi_pos = "Di Atas Awan ☁✅"
    elif last["Close"]<kb:             ichi_pos = "Di Bawah Awan ☁❌"
    else:                              ichi_pos = "Dalam Awan ☁⚠️"

    atr = float(last["ATR"]) if not pd.isna(last["ATR"]) else last["Close"]*0.05
    kijun_val = float(last_ich.get("Ichi_Kijun",0)) if not pd.isna(last_ich.get("Ichi_Kijun")) else 0
    stop_loss = int(max(last["Close"]-1.5*atr, kijun_val, last["Close"]*0.85))

    vrvp        = compute_vrvp(df)
    target_price= int(max(last["Close"]+2.5*atr,
                          vrvp["next_res"] if (vrvp and vrvp["next_res"]>last["Close"]*1.01) else 0))
    target_src  = "VRVP" if (vrvp and vrvp["next_res"]>last["Close"]*1.01
                             and vrvp["next_res"]>=last["Close"]+2.5*atr) else "ATR"

    if market_cap > BIG_CAP_LIMIT:     kasta = "1. Big Cap"
    elif market_cap > MID_CAP_LIMIT:   kasta = "2. Medium Cap"
    elif market_cap > SMALL_CAP_LIMIT: kasta = "3. Small Cap"
    else:                               kasta = "4. Micro Cap"

    cmf_raw     = float(last.get("CMF",0.0))
    bb_raw      = float(last["BB_Width"])
    ud_raw      = float(last.get("UD_Vol_Ratio_Dragon",1.0))
    vr_raw      = float(last["Vol_Ratio20"])

    # Dragon Action (tetap ada sebagai referensi silang)
    if bb_raw<=0.15 and cmf_raw>0.05 and ud_raw>=1.5:
        dragon_action = "ACCUMULATION BUY (NAGA TERBAIK)"
    elif bb_raw<=0.15 and -0.05<=cmf_raw<=0.05 and ud_raw>=2.0:
        dragon_action = "STEALTH BUY (NYICIL SILUMAN)"
    elif bb_raw>0.20 and cmf_raw<-0.10:
        dragon_action = "HINDARI (BANDAR DISTRIBUSI / DUMP)"
    else:
        dragon_action = "WAIT & SEE (NANTI DULU)"

    vol_keterangan  = "Volum Kering. " if vr_raw<0.5 else ("Volum Tinggi. " if vr_raw>1.5 else "Volum Normal. ")
    cmf_keterangan  = "Akumulasi Kuat. " if cmf_raw>0.05 else ("Akumulasi Siluman. " if cmf_raw>-0.05 else "Distribusi Terdeteksi. ")
    dragon_concl    = (vol_keterangan+cmf_keterangan).strip()

    return {
        "Ticker":             ticker,
        "Harga":              int(last["Close"]),
        "Kasta":              kasta,
        "Status":             status,
        "Status_Rank":        STATUS_RANK.get(status,0),
        "Score":              score,
        "AI_Conf":            f"{ai_conf_val:.2%}",
        "AI_Conf_Val":        ai_conf_val,
        "RSI":                f"{last['RSI']:.1f}",
        "MACD_Hist":          f"{last['MACD_Hist']:.2f}",
        "CMF":                f"{cmf_raw:.3f}",
        "OBV_Slope":          f"{last.get('OBV_Slope10',0):.3f}",
        "Vol_Buildup":        f"{last.get('Vol_Buildup',1):.2f}",
        "Ichimoku":           ichi_pos,
        "Kijun":              int(kijun_val) if kijun_val else "N/A",
        "Buy_Area":           f"{int(last['Close'])} - {int(last['Close']*1.02)}",
        "Target_Price":       target_price,
        "Target_Src":         target_src,
        "Stop_Loss":          stop_loss,
        "BB_Width_Str":       f"{bb_raw*100:.2f}%",
        "CMF_Raw":            round(cmf_raw,3),
        "UD_Vol_Ratio":       round(ud_raw,2),
        "Vol_Ratio":          round(vr_raw,2),
        "Prob_AI":            f"{ai_conf_val*100:.2f}%",
        "Dragon_Kesimpulan":  dragon_concl,
        "Dragon_Action":      dragon_action,
        "IHSG_Trend":         sector_features.get("IHSG_Trend",0) if sector_features else 0,
        "Sector_Breadth":     f"{sector_features.get('Sector_Breadth_Ratio',0.5)*100:.0f}%" if sector_features else "N/A",
    }

# ══════════════════════════════════════════════════════════════════
# 5. SCHEMA-SAFE DB SAVE (sama dengan Dragon Fire)
# ══════════════════════════════════════════════════════════════════
def safe_append_history(df_histori, table_name, engine):
    """Append ke tabel histori dengan cek skema — cegah silent fail."""
    try:
        with engine.connect() as conn:
            tbl_exists = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                f"WHERE table_name = \'{table_name}\')"
            )).scalar()
            if tbl_exists:
                existing_cols = set(r[0] for r in conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = \'{table_name}\'"
                )).fetchall())
                needed_cols = set(c.lower() for c in df_histori.columns)
                if needed_cols - existing_cols:
                    print(f"⚠️  {table_name}: skema berubah — tabel direkonstruksi.")
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
                    conn.commit()
                else:
                    tgl = today_wib_str()
                    deleted = conn.execute(text(
                        f'DELETE FROM "{table_name}" WHERE "Tanggal_Scan" = :tgl'
                    ), {"tgl": tgl}).rowcount
                    conn.commit()
                    if deleted > 0:
                        print(f"🔄 {table_name}: {deleted} baris lama {tgl} dihapus.")
        df_histori.to_sql(table_name, engine, if_exists="append", index=False)
        return True
    except Exception as e:
        print(f"❌ {table_name} ERROR: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# 6. MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════
print("🐯 Dragon Hunt Tiger — Cloud Engine dimulai...")
DAFTAR_SAHAM  = load_daftar_saham()
tickers_jk    = [t+".JK" for t in DAFTAR_SAHAM]

print("📡 Download data sektor & IHSG...")
sector_raw      = download_sector_ihsg()
sector_features = build_sector_features(sector_raw)
ihsg_trend_str  = "Bullish" if sector_features.get("IHSG_Trend",0)==1 else "Bearish/Netral"
breadth_pct     = sector_features.get("Sector_Breadth_Ratio",0.5)
print(f"   IHSG: {ihsg_trend_str} | Sektor Bullish: {breadth_pct*100:.0f}%")

print("🌐 Download data saham (1 tahun terakhir)...")
raw_data = download_market_data(tickers_jk, period="1y")
if raw_data is None:
    print("❌ Download data gagal total."); sys.exit()

print("🔬 Analisis & scoring semua emiten...")
all_results = []
failed      = []
for idx, ticker in enumerate(DAFTAR_SAHAM, 1):
    t_jk = ticker+".JK"
    try:
        df_raw = extract_ticker_df(raw_data, t_jk)
        if df_raw.empty or len(df_raw) < MIN_DATA_DAYS:
            failed.append(ticker); continue
        result = analyze_ticker(ticker, df_raw, sector_features, force_return=False)
        if result: all_results.append(result)
    except Exception as e:
        failed.append(ticker)
    if idx % 100 == 0 or idx == len(DAFTAR_SAHAM):
        print(f"   ⏳ {idx}/{len(DAFTAR_SAHAM)} diproses | Lolos: {len(all_results)}")

print(f"\n✅ Selesai: {len(all_results)} emiten lolos | {len(failed)} gagal/tidak cukup data")

if not all_results:
    print("⚠️  Tidak ada saham lolos kriteria hari ini.")
    if IS_CLOUD:
        sys.exit()
    else:
        sys.exit()

# ── Susun DataFrame hasil ─────────────────────────────────────────
df_results = pd.DataFrame(all_results)
df_results["_rank_score"] = df_results["Score"]*0.4 + df_results["AI_Conf_Val"]*100*0.6
df_results = df_results.sort_values(
    ["Status_Rank","_rank_score"], ascending=[False,False]
).reset_index(drop=True)

COLS_EXPORT = [
    "Ticker","Harga","Kasta","Status","Score","AI_Conf",
    "RSI","MACD_Hist","CMF","OBV_Slope","Vol_Buildup",
    "Ichimoku","Kijun","Buy_Area","Target_Price","Target_Src","Stop_Loss",
    "BB_Width_Str","CMF_Raw","UD_Vol_Ratio","Vol_Ratio","Prob_AI",
    "Dragon_Kesimpulan","Dragon_Action","IHSG_Trend","Sector_Breadth"
]
COLS_EXPORT = [c for c in COLS_EXPORT if c in df_results.columns]
df_export = df_results[COLS_EXPORT].copy()

print("\n" + "="*120)
print("🐯 DRAGON HUNT TIGER — HASIL SCREENING HARI INI")
print("="*120)
print(df_export[["Ticker","Harga","Kasta","Status","Score","AI_Conf",
                  "BB_Width_Str","CMF","Dragon_Action"]].to_string(index=False))

# ── Simpan ke Cloud DB ─────────────────────────────────────────────
if IS_CLOUD:
    try:
        # tiger_screener_live: hasil screener hari ini
        df_export.to_sql("tiger_screener_live", db_engine, if_exists="replace", index=False)
        print(f"\n🚀 tiger_screener_live: {len(df_export)} baris")

        # tiger_all_stocks_live: SEMUA emiten yang berhasil diproses
        # (untuk Diagnostik Ticker di app.py)
        df_all_results = []
        print("📦 Membangun master DB semua emiten (untuk Diagnostik)...")
        for idx, ticker in enumerate(DAFTAR_SAHAM, 1):
            t_jk = ticker+".JK"
            try:
                df_raw = extract_ticker_df(raw_data, t_jk)
                if df_raw.empty or len(df_raw) < MIN_DATA_DAYS: continue
                result = analyze_ticker(ticker, df_raw, sector_features, force_return=True)
                if result: df_all_results.append(result)
            except: continue
            if idx % 200 == 0:
                print(f"   ⏳ Master DB: {idx}/{len(DAFTAR_SAHAM)}")
        if df_all_results:
            df_all_exp = pd.DataFrame(df_all_results)[COLS_EXPORT]
            df_all_exp.to_sql("tiger_all_stocks_live", db_engine, if_exists="replace", index=False)
            print(f"🚀 tiger_all_stocks_live: {len(df_all_exp)} baris")

            # tiger_history: arsip harian
            df_hist = df_all_exp.copy()
            df_hist["Tanggal_Scan"] = today_wib_str()
            ok = safe_append_history(df_hist, "tiger_history", db_engine)
            if ok: print(f"🚀 tiger_history: +{len(df_hist)} baris ({today_wib_str()})")

    except Exception as e:
        print(f"❌ DATABASE ERROR: {e}")

# ── Simpan Excel lokal ─────────────────────────────────────────────
sheet_name = now_wib().strftime("%Y-%B-%d")
file_local = os.path.join(FOLDER_OUTPUT, "Tiger_Hunter_Master_Report.xlsx")
try:
    if os.path.exists(file_local):
        with pd.ExcelWriter(file_local, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
            df_export.to_excel(w, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(file_local, engine="openpyxl") as w:
            df_export.to_excel(w, sheet_name=sheet_name, index=False)
    print(f"✅ Excel: {file_local} — sheet {sheet_name}")
except Exception as e:
    print(f"⚠️  Excel error: {e}")

print("\n💤 Tiger Cloud Engine selesai.")
