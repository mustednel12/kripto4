# -*- coding: utf-8 -*-
import asyncio, httpx, pandas as pd, numpy as np
import warnings

warnings.filterwarnings('ignore')

# 🔧 SENİN STRATEJİNİN PARAMETRELERİ (Özetlenmiş)
SETTINGS = {
    "rsi_period": 14, "ema_period": 20, "vol_ma_period": 20,
    "tavan_breakout_pct": 0.5, "atr_mult": 2.0
}

# 📊 TEKNİK GÖSTERGELER (Hızlı hesaplama için)
def check_signals(df):
    if len(df) < 30: return None
    close = df['Close']
    rsi = 100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / 
                              close.diff().clip(upper=0).abs().rolling(14).mean())))
    # Örnek: Tavan veya RSI şartı
    if rsi.iloc[-1] < 30: return "RSI_ASIRI_SATIM"
    return None

# 🚀 ASENKRON TARAMA
async def scan_coin(client, symbol):
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50"
        response = await client.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame([float(k[4]) for k in data], columns=['Close'])
            signal = check_signals(df)
            if signal: return symbol, signal
    except: pass
    return None, None

async def main():
    # 1. Sembolleri çek
    symbols_raw = await httpx.get("https://api.mexc.com/api/v3/ticker/24hr")
    symbols = [t['symbol'] for t in symbols_raw.json() if t['symbol'].endswith('USDT')]
    
    print(f"🔍 {len(symbols)} coin taraması başlıyor...")
    
    # 2. Hız Sınırlayıcı (API Ban yememek için 50'şerli paketler)
    semaphore = asyncio.Semaphore(50)
    
    async def sem_scan(client, sym):
        async with semaphore:
            return await scan_coin(client, sym)

    async with httpx.AsyncClient() as client:
        tasks = [sem_scan(client, sym) for sym in symbols]
        results = await asyncio.gather(*tasks)
    
    # 3. Sonuçları listele
    found = [r for r in results if r[0] is not None]
    for sym, sig in found:
        print(f"✅ Sinyal: {sym} | Strateji: {sig}")

if __name__ == "__main__":
    asyncio.run(main())
