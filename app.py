# -*- coding: utf-8 -*-
import asyncio, httpx, pandas as pd, numpy as np
import warnings

warnings.filterwarnings('ignore')

# 🔧 STRATEJİ AYARLARI
SETTINGS = {
    "rsi_period": 14, "ema_period": 20, "mom_period": 9, "vol_ma_period": 20, 
    "tavan_breakout_pct": 0.5, "tavan_min_vol_ratio": 1.2, "atr_mult": 2.0
}

# 📊 TEKNİK GÖSTERGE HESAPLAMALARI
def scan_logic(df):
    if len(df) < 30: return None
    close, high, low = df['Close'], df['High'], df['Low']
    
    # Basit bir RSI ve EMA stratejisi (Buraya kendi karmaşık şartlarını ekleyebilirsin)
    rsi = 100 - (100 / (1 + (close.diff().clip(lower=0).rolling(14).mean() / 
                              close.diff().clip(upper=0).abs().rolling(14).mean())))
    sma20 = close.rolling(20).mean()
    
    if rsi.iloc[-1] < 30 and close.iloc[-1] > sma20.iloc[-1]:
        return "GÜÇLÜ_AL (RSI+SMA)"
    return None

# 🚀 ASENKRON TARAMA MOTORU
async def scan_coin(client, symbol):
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval=1h&limit=50"
        response = await client.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Veriyi DF yapısına çevir
            df = pd.DataFrame(data, columns=['OT', 'Open', 'High', 'Low', 'Close', 'Volume', 'CT', 'QV', 'TN', 'BV', 'BS', 'IG'])
            df[['High', 'Low', 'Close']] = df[['High', 'Low', 'Close']].astype(float)
            
            signal = scan_logic(df)
            if signal: return symbol, signal
    except: pass
    return None, None

async def main():
    async with httpx.AsyncClient() as client:
        # 1. Sembolleri al
        resp = await client.get("https://api.mexc.com/api/v3/ticker/24hr")
        symbols = [t['symbol'] for t in resp.json() if t['symbol'].endswith('USDT')]
        
        print(f"🚀 {len(symbols)} coin taranıyor... Lütfen bekleyin.")
        
        # 2. Hız Sınırlayıcı (Ban yememek için)
        semaphore = asyncio.Semaphore(50)
        
        async def sem_scan(sym):
            async with semaphore:
                return await scan_coin(client, sym)

        # 3. Tüm coinleri aynı anda tara
        tasks = [sem_scan(sym) for sym in symbols]
        results = await asyncio.gather(*tasks)
    
    # 4. Sonuçları yazdır
    found = [r for r in results if r[0] is not None]
    if not found:
        print("🏁 Tarama tamamlandı. Sinyal bulunamadı.")
    else:
        for sym, sig in found:
            print(f"✅ Sinyal: {sym} | Strateji: {sig}")

if __name__ == "__main__":
    asyncio.run(main())
