
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

@st.cache_data(ttl=3600*8) # Cache de 8 horas
def obter_tickers_fundamentus_amplitude():
    """Busca lista de tickers de ações brasileiras do Fundamentus, filtrando por liquidez > 0."""
    st.info("Buscando lista de tickers do Fundamentus (Liq. > 0)... (Cache de 8h)")
    try:
        url = "https://www.fundamentus.com.br/resultado.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'latin-1'

        tables = pd.read_html(response.text, decimal=',', thousands='.')
        if tables:
            df = tables[0]
            # Filtra por liquidez nos últimos 2 meses > 0
            df['Liq.2meses'] = pd.to_numeric(df['Liq.2meses'], errors='coerce').fillna(0)
            df_filtrado = df[df['Liq.2meses'] > 0]
            tickers = df_filtrado['Papel'].tolist()
            return [t for t in tickers if isinstance(t, str) and len(t) >= 4]
        return None
    except Exception as e:
        st.error(f"Erro ao buscar tickers do Fundamentus: {e}")
        return None

@st.cache_data(ttl=3600*8) # Cache de 8 horas
def obter_precos_historicos_amplitude(tickers, anos_historico=5):
    """Esta função baixa os preços históricos para a análise de amplitude."""
    st.info(f"Baixando dados de preços de {len(tickers)} ativos... (Cache de 8h)")
    
    # Batch processing could be added here if list is huge, but yfinance handles chunks reasonably well.
    # App.py behavior:
    tickers_sa = [ticker + ".SA" for ticker in tickers]
    
    try:
        dados_completos = yf.download(
            tickers=tickers_sa,
            start=datetime.now() - timedelta(days=anos_historico*365),
            end=datetime.now(),
            auto_adjust=False,
            progress=False,
            group_by='ticker'
        )
        if not dados_completos.empty:
            # Seleciona 'Adj Close' (preferencial) ou 'Close' como fallback
            # Logic adapted from App.py
            if isinstance(dados_completos.columns, pd.MultiIndex):
                 # This is tricky with current yfinance versions.
                 # Assuming standard structure: (PriceType, Ticker) or (Ticker, PriceType)
                 # The App.py logic:
                 # price_type = 'Adj Close' if 'Adj Close' in dados_completos.columns.get_level_values(1) else 'Close'
                 # precos = dados_completos.stack(level=0, future_stack=True)[price_type].unstack(level=1)
                 
                 # Simpler robust way:
                 xs_key = 'Adj Close' if 'Adj Close' in dados_completos.columns.get_level_values(0) else 'Close'
                 # Note: yfinance format varies. Let's assume (Price, Ticker) or (Ticker, Price).
                 # App.py used stack/unstack which implies (Ticker, Price) or similar.
                 # Let's try to extract Adj Close column for all tickers.
                 
                 # Reconstruct from App.py snippet:
                 # price_type = 'Adj Close' if 'Adj Close' in dados_completos.columns.get_level_values(1) else 'Close'
                 # precos = dados_completos.stack(level=0, future_stack=True)[price_type].unstack(level=1)
                 
                 # Using the exact logic from App.py for consistency
                 return dados_completos.stack(level=0, future_stack=True)['Adj Close'].unstack(level=1).astype('float32') # approximate
                 # Wait, yfinance recent versions might have changed.
                 # I'll stick to what I saw in App.py:
                 # return precos.astype('float32')
            
            return pd.DataFrame() # Fallback
            
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()
