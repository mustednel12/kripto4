# -*- coding: utf-8 -*-
import os, time, requests, threading
from datetime import datetime
import numpy as np
import pandas as pd
import gradio as gr
import warnings, urllib3

urllib3.disable_warnings()
warnings.filterwarnings('ignore')

# ══════════════════════════════════════════════════════════════
# 📱 TELEGRAM AYARLARI
# ══════════════════════════════════════════════════════════════
TELEGRAM_TOKEN = os.environ.get("", "BURAYA_BOT_TOKEN_YAZ")
TELEGRAM_CHAT_ID = os.environ.get("", "BURAYA_CHAT_ID_YAZ")

def send_telegram_message(text):
    if TELEGRAM_TOKEN == "BURAYA_BOT_TOKEN_YAZ":
        print("Telegram ayarları yapılmamış!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}")

# ══════════════════════════════════════════════════════════════
# 🔧 BOT AYARLARI & HESAPLAMALAR
# ══════════════════════════════════════════════════════════════
SETTINGS = {
    "enable_tavan_al": True, "enable_sat": True, "enable_quantum_al": True,
    "enable_obv_al": True, "enable_obv_sat": True,
    "rsi_period": 14, "ema_period": 20, "mom_period": 9, "vol_ma_period": 20, "fib_len": 14,
    "obv_ema_len": 3, "tavan_breakout_pct": 0.5, "tavan_min_vol_ratio": 1.2,
    "sat_breakout_pct": 0.5, "sat_min_vol_ratio": 1.2,
    "auto_zone_days": 50, "auto_peak_pct": 3.0, "auto_dip_pct": 3.0,
    "hassasiyet": 0.1, "atr_period": 14, "atr_mult": 2.0, "base_olasilik": 65.0,
    "guc_carpan": 50.0, "olasilik_artis_bolucu": 4.0, "ek_olasilik_bonusu": 12.0,
    "hassasiyet_carpan": 2.5, "max_olasilik": 98.0, "min_guc_seviyesi": 0.0,
}

TARAMA_ZAMAN_DILIMI = "4h" # Tarama yapılacak periyot
DONGU_BEKLEME_SURESI = 7200 # Tarama bittikten sonra bir sonraki taramaya kadar beklenecek saniye (3600 = 1 saat)

# Son durum logunu arayüzde göstermek için global değişken
LATEST_STATUS = "Bot başlatılıyor..."

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def calc_ema(series, period): return series.ewm(span=period, adjust=False).mean()
def calc_sma(series, period): return series.rolling(window=period).mean()
def calc_momentum(series, period=9): return series.diff(period)

def calc_atr(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calc_heikin_ashi(df):
    ha_close = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
    ha_high = pd.concat([df['High'], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df['Low'], ha_open, ha_close], axis=1).min(axis=1)
    return pd.DataFrame({'haOpen': ha_open, 'haHigh': ha_high, 'haLow': ha_low, 'haClose': ha_close}, index=df.index)

def calc_obv(df):
    obv = [0]
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > df['Close'].iloc[i-1]: obv.append(obv[-1] + df['Volume'].iloc[i])
        elif df['Close'].iloc[i] < df['Close'].iloc[i-1]: obv.append(obv[-1] - df['Volume'].iloc[i])
        else: obv.append(obv[-1])
    return pd.Series(obv, index=df.index)

def calc_vol_ratio(df, period=20):
    vol_sma = df['Volume'].rolling(window=period).mean()
    return df['Volume'] / vol_sma.replace(0, np.nan)

MEXC_BASE = "https://api.mexc.com"
SESSION = requests.Session()

def get_mexc_usdt_symbols():
    try:
        r = SESSION.get(f"{MEXC_BASE}/api/v3/ticker/24hr", timeout=30)
        data = r.json()
        exclude = ("3L","3S","5L","5S","UP","DOWN","BULL","BEAR")
        symbols = [{"symbol": t["symbol"], "volume": float(t.get("quoteVolume", 0))} for t in data if t["symbol"].endswith("USDT") and not any(t["symbol"][:-4].endswith(x) for x in exclude)]
        return sorted(symbols, key=lambda x: x["volume"], reverse=True)
    except: return []

def get_stock_data(symbol, interval="1h"):
    try:
        r = SESSION.get(f"{MEXC_BASE}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": 1000}, timeout=20)
        data = r.json()
        if not isinstance(data, list) or len(data) < 50: return None
        df = pd.DataFrame([{"timestamp": pd.to_datetime(int(k[0]), unit="ms"), "Open": float(k[1]), "High": float(k[2]), "Low": float(k[3]), "Close": float(k[4]), "Volume": float(k[5])} for k in data])
        df.set_index("timestamp", inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    except: return None

# ══════════════════════════════════════════════════════════════
# 🎯 TARAMA MOTORU
# ══════════════════════════════════════════════════════════════
def scan_symbol(df, s):
    close, high, low, volume = df['Close'], df['High'], df['Low'], df['Volume']
    rsi_val, rsi_ema = calc_rsi(close, s['rsi_period']), calc_ema(calc_rsi(close, s['rsi_period']), s['ema_period'])
    momentum_val, vol_ma = calc_momentum(close, s['mom_period']), calc_sma(volume, s['vol_ma_period'])
    vol_ratio, atr_val = calc_vol_ratio(df, s['vol_ma_period']), calc_atr(df, s['atr_period'])
    rsi_top, rsi_bot = rsi_val.rolling(s['fib_len']).max(), rsi_val.rolling(s['fib_len']).min()
    fib_500 = rsi_top - (rsi_top - rsi_bot) * 0.500
    ha = calc_heikin_ashi(df)
    obv_val = calc_obv(df)
    obv_ema = calc_ema(obv_val, s['obv_ema_len'])

    pdh, pdl = high.shift(1), low.shift(1)
    i, i_prev = -1, -2

    c_close, p_close = float(close.iloc[i]), float(close.iloc[i_prev])
    c_pdh, c_pdl = float(pdh.iloc[i]) if not pd.isna(pdh.iloc[i]) else c_close, float(pdl.iloc[i]) if not pd.isna(pdl.iloc[i]) else c_close
    c_vol_ratio, c_vol, c_vol_ma = float(vol_ratio.iloc[i]) if not pd.isna(vol_ratio.iloc[i]) else 1.0, float(volume.iloc[i]), float(vol_ma.iloc[i])
    c_atr = float(atr_val.iloc[i]) if not pd.isna(atr_val.iloc[i]) else c_close * 0.02
    
    c_rsi, p_rsi = float(rsi_val.iloc[i]), float(rsi_val.iloc[i_prev])
    c_rsi_ema, p_rsi_ema = float(rsi_ema.iloc[i]), float(rsi_ema.iloc[i_prev])
    p_fib_500, c_mom = float(fib_500.iloc[i_prev]), float(momentum_val.iloc[i])
    c_obv, p_obv = float(obv_val.iloc[i]), float(obv_val.iloc[i_prev])
    c_obv_ema, p_obv_ema = float(obv_ema.iloc[i]), float(obv_ema.iloc[i_prev])
    c_ha_close, c_ha_open = float(ha['haClose'].iloc[i]), float(ha['haOpen'].iloc[i])
    p_ha_close, p_ha_open, p_ha_high = float(ha['haClose'].iloc[i_prev]), float(ha['haOpen'].iloc[i_prev]), float(ha['haHigh'].iloc[i_prev])

    raw_sources, signal_gucu, olasilik = [], 0, s['base_olasilik']
    
    if s['enable_tavan_al'] and (c_close > c_pdh) and (p_close <= c_pdh) and (c_close > c_pdh * (1 + s['tavan_breakout_pct']/100)) and (c_vol_ratio >= s['tavan_min_vol_ratio']):
        auto_high = high.rolling(window=s['auto_zone_days']).max().iloc[i]
        if not (c_pdh >= auto_high * (1 - s['auto_peak_pct']/100) and c_pdh <= auto_high):
            raw_sources.append("TAVAN"); signal_gucu = 85
            
    if s['enable_quantum_al']:
        mutlak_degisim = abs(((c_ha_close - c_ha_open) / c_ha_open) * 100 if c_ha_open > 0 else 0)
        if (c_ha_close > c_ha_open) and ((p_ha_close <= p_ha_open) or (c_ha_close > p_ha_high)) and mutlak_degisim >= s['hassasiyet']:
            raw_sources.append("QUANTUM")
            avg_body = abs((ha['haClose'] - ha['haOpen']) / ha['haOpen'] * 100).rolling(10).mean().iloc[i]
            sg = min(100, (mutlak_degisim / (avg_body if avg_body > 0 and not pd.isna(avg_body) else 1)) * s['guc_carpan'])
            signal_gucu = max(signal_gucu, sg)
            
    if s['enable_obv_al'] and (c_obv > c_obv_ema) and (p_obv <= p_obv_ema): raw_sources.append("OBV_AL"); signal_gucu = max(signal_gucu, 75)
    if s['enable_obv_sat'] and (c_obv < c_obv_ema) and (p_obv >= p_obv_ema): raw_sources.append("OBV_SAT"); signal_gucu = max(signal_gucu, 75)

    if not raw_sources: return None
    
    rsi_up = ((c_rsi > c_rsi_ema) and (p_rsi <= p_rsi_ema)) or ((c_rsi > p_fib_500) and (p_rsi <= p_fib_500))
    rsi_down = ((c_rsi < c_rsi_ema) and (p_rsi >= p_rsi_ema)) or ((c_rsi < p_fib_500) and (p_rsi >= p_fib_500))
    
    ind2_buy = rsi_up and (c_mom > 0) and (c_vol > c_vol_ma)
    ind2_sell = rsi_down and (c_mom < 0) and (c_vol > c_vol_ma)
    
    buy_sources = [src for src in raw_sources if src in ["TAVAN", "QUANTUM", "OBV_AL"]]
    sell_sources = [src for src in raw_sources if src in ["OBV_SAT"]] # Destek iptal edildiği için sadece OBV_SAT
    
    if buy_sources and ind2_buy and signal_gucu >= s['min_guc_seviyesi']:
        hedef = c_close + (c_atr * s['atr_mult'])
        return {"type": "GÜÇLÜ_AL", "symbol": "", "price": c_close, "hedef": hedef, "kar": ((hedef - c_close) / c_close) * 100, "guc": signal_gucu, "rsi": c_rsi, "kaynak": "+".join(buy_sources)}
        
    if sell_sources and ind2_sell and signal_gucu >= s['min_guc_seviyesi']:
        hedef = c_close - (c_atr * s['atr_mult'])
        return {"type": "GÜÇLÜ_SAT", "symbol": "", "price": c_close, "hedef": hedef, "kar": ((c_close - hedef) / c_close) * 100, "guc": signal_gucu, "rsi": c_rsi, "kaynak": "+".join(sell_sources)}
        
    return None

# ══════════════════════════════════════════════════════════════
# 🔄 ARKA PLAN DÖNGÜSÜ
# ══════════════════════════════════════════════════════════════
def background_scanner():
    global LATEST_STATUS
    while True:
        try:
            LATEST_STATUS = f"[{datetime.now().strftime('%H:%M:%S')}] MEXC piyasası çekiliyor..."
            print(LATEST_STATUS)
            symbols = get_mexc_usdt_symbols()
            total = len(symbols)
            
            bulunan_sinyaller = []
            
            for idx, coin in enumerate(symbols):
                sym = coin['symbol']
                if idx % 50 == 0:
                    LATEST_STATUS = f"[{datetime.now().strftime('%H:%M:%S')}] Taranıyor: {idx}/{total} ({sym})"
                    
                df = get_stock_data(sym, TARAMA_ZAMAN_DILIMI)
                if df is not None:
                    sig = scan_money_trader(df, SETTINGS)
                    if sig:
                        sig['symbol'] = sym
                        bulunan_sinyaller.append(sig)
                        
                        # Anında Telegram'a gönder
                        mesaj = (
                            f"🚨 <b>YENİ SİNYAL: {sym}</b>\n\n"
                            f"<b>Yön:</b> {sig['type']}\n"
                            f"<b>Fiyat:</b> {sig['price']:.6f}\n"
                            f"<b>Hedef:</b> {sig['hedef']:.6f} (+%{sig['kar']:.2f})\n"
                            f"<b>Kaynak:</b> {sig['kaynak']}\n"
                            f"<b>Güç:</b> %{sig['guc']:.1f} | <b>RSI:</b> {sig['rsi']:.1f}\n"
                            f"<b>Periyot:</b> {TARAMA_ZAMAN_DILIMI}"
                        )
                        send_telegram_message(mesaj)
                time.sleep(0.15) # API ban yememek için bekleme
                
            LATEST_STATUS = f"[{datetime.now().strftime('%H:%M:%S')}] Tarama bitti. {len(bulunan_sinyaller)} sinyal bulundu. Uykuya geçiliyor ({DONGU_BEKLEME_SURESI} sn)."
            print(LATEST_STATUS)
            time.sleep(DONGU_BEKLEME_SURESI)
            
        except Exception as e:
            LATEST_STATUS = f"Hata oluştu: {str(e)}. 60 saniye sonra tekrar denenecek."
            print(LATEST_STATUS)
            time.sleep(60)

# ══════════════════════════════════════════════════════════════
# 🌐 GRADIO ARAYÜZÜ (Sunucuyu Hayatta Tutmak İçin)
# ══════════════════════════════════════════════════════════════
def get_status():
    return LATEST_STATUS

# Arka plan tarama motorunu başlat
threading.Thread(target=background_scanner, daemon=True).start()

# Basit bir web arayüzü başlat
with gr.Blocks(title="Money Trader Bot") as demo:
    gr.Markdown("# 🤖 Money Trader Bot - Aktif")
    gr.Markdown("Bu sayfa Hugging Face sunucusunu açık tutmak için oluşturulmuştur. Sinyaller doğrudan Telegram'a iletilmektedir.")
    status_text = gr.Textbox(label="Botun Anlık Durumu", value=get_status())
    refresh_btn = gr.Button("Durumu Güncelle")
    refresh_btn.click(fn=get_status, outputs=status_text)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)

