# -*- coding: utf-8 -*-
import requests, time, sys
import pandas as pd
import warnings
import urllib3

urllib3.disable_warnings()
warnings.filterwarnings('ignore')

# 🔧 AYARLAR
SETTINGS = {
    "rsi_period": 14, "ema_period": 20, "mom_period": 9,
    "vol_ma_period": 20, "atr_period": 14, "base_olasilik": 65.0
}

# 🌐 API İSTEK FONKSİYONU (HATA KORUMALI)
def get_stock_data(symbol, timeframe="1h"):
    try:
        # Timeout eklendi (5 saniye)
        url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit=50"
        r = requests.get(url, timeout=5, verify=False)
        if r.status_code != 200: return None
        data = r.json()
        if not isinstance(data, list): return None
        return pd.DataFrame([float(k[4]) for k in data], columns=['Close'])
    except: return None

def get_symbols():
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10, verify=False)
        return [t['symbol'] for t in r.json() if t['symbol'].endswith('USDT')][:100] # Hız için ilk 100
    except: return []

# 🚀 TARA VE ÇIKIŞ YAP (DÖNGÜSÜZ)
def run_scanner():
    print("🚀 Tarama başlatılıyor...")
    symbols = get_symbols()
    found_signals = 0
    
    for sym in symbols:
        print(f"🔍 Taranıyor: {sym}")
        df = get_stock_data(sym)
        
        if df is not None and len(df) > 20:
            # Basit bir örnek koşul
            last_close = df['Close'].iloc[-1]
            sma = df['Close'].rolling(20).mean().iloc[-1]
            if last_close > sma:
                print(f"✅ Sinyal Bulundu: {sym} (Fiyat: {last_close})")
                found_signals += 1
        
        # API ban yememek için gecikme
        time.sleep(0.3) 
    
    print(f"🏁 Tarama tamamlandı. Toplam {found_signals} sinyal bulundu.")
    # GitHub Action'ın başarıyla bitmesi için çıkış yapıyoruz
    sys.exit(0)

if __name__ == "__main__":
    run_scanner()
