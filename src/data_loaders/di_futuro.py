"""
Módulo para buscar dados de DI Futuro da B3.
Similar ao b3_api.py para opções.
"""

import requests
import pandas as pd
import zipfile
import io
import streamlit as st
from datetime import date, timedelta


def get_ultimo_dia_util() -> str:
    """Retorna o último dia útil no formato YYYY-MM-DD."""
    today = date.today()
    if today.weekday() == 0:  # Segunda
        return (today - timedelta(days=3)).strftime("%Y-%m-%d")
    elif today.weekday() == 6:  # Domingo
        return (today - timedelta(days=2)).strftime("%Y-%m-%d")
    elif today.weekday() == 5:  # Sábado
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")


@st.cache_data(ttl=3600)  # Cache de 1 hora
def fetch_di_futuro_b3(di_ticker: str, trade_date: str = None) -> dict:
    """
    Busca dados de DI Futuro da B3.
    
    Args:
        di_ticker: código do DI futuro (ex: DI1F29, DI1F30)
        trade_date: data no formato YYYY-MM-DD (default: último dia útil)
    
    Returns:
        dict com last_price (taxa), volume, trades ou None se erro
    """
    
    if trade_date is None:
        trade_date = get_ultimo_dia_util()
    
    url = f"https://arquivos.b3.com.br/rapinegocios/tickercsv/{di_ticker}/{trade_date}"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None
        
        # Extrai ZIP
        z = zipfile.ZipFile(io.BytesIO(response.content))
        if not z.namelist():
            return None
        
        # Lê o arquivo CSV
        with z.open(z.namelist()[0]) as f:
            content = f.read().decode('latin-1')
            df = pd.read_csv(io.StringIO(content), sep=';', decimal=',')
        
        if df.empty or 'PrecoNegocio' not in df.columns:
            return None
        
        # Para DI, o PrecoNegocio é a taxa
        return {
            'taxa': df['PrecoNegocio'].iloc[-1],  # Última taxa negociada
            'taxa_media': df['PrecoNegocio'].mean(),
            'taxa_min': df['PrecoNegocio'].min(),
            'taxa_max': df['PrecoNegocio'].max(),
            'volume': df['QuantidadeNegociada'].sum() if 'QuantidadeNegociada' in df.columns else 0,
            'trades': len(df),
            'date': trade_date,
            'ticker': di_ticker
        }
    except Exception as e:
        return None


def gerar_ticker_di(ano: int, mes: int = 1) -> str:
    """
    Gera o ticker do DI Futuro para um determinado ano e mês.
    
    O código de vencimento segue o padrão:
    - F = Janeiro
    - G = Fevereiro
    - H = Março
    - J = Abril
    - K = Maio
    - M = Junho
    - N = Julho
    - Q = Agosto
    - U = Setembro
    - V = Outubro
    - X = Novembro
    - Z = Dezembro
    
    Args:
        ano: ano do vencimento (ex: 2029)
        mes: mês do vencimento (1-12, default janeiro)
    
    Returns:
        Ticker no formato DI1X29
    """
    meses = {
        1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
        7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
    }
    
    letra_mes = meses.get(mes, 'F')
    ano_curto = str(ano)[-2:]  # Últimos 2 dígitos
    
    return f"DI1{letra_mes}{ano_curto}"


@st.cache_data(ttl=3600)
def fetch_curva_di_b3(anos_frente: int = 10, trade_date: str = None) -> pd.DataFrame:
    """
    Busca a curva de DI Futuro para múltiplos vencimentos.
    
    Args:
        anos_frente: quantos anos à frente buscar
        trade_date: data de referência
    
    Returns:
        DataFrame com colunas: ticker, ano, taxa, volume
    """
    if trade_date is None:
        trade_date = get_ultimo_dia_util()
    
    hoje = date.today()
    ano_atual = hoje.year
    
    resultados = []
    
    # Buscar vencimentos de janeiro para os próximos N anos
    for ano in range(ano_atual + 1, ano_atual + anos_frente + 1):
        ticker = gerar_ticker_di(ano, mes=1)  # Janeiro de cada ano
        dados = fetch_di_futuro_b3(ticker, trade_date)
        
        if dados and dados['taxa']:
            resultados.append({
                'ticker': ticker,
                'ano': ano,
                'vencimento': f"Jan/{ano}",
                'taxa': dados['taxa'],
                'volume': dados['volume'],
                'trades': dados['trades']
            })
    
    if not resultados:
        return pd.DataFrame()
    
    return pd.DataFrame(resultados).sort_values('ano')


def calcular_juro_10a_di(trade_date: str = None) -> float:
    """
    Calcula a taxa de juros de 10 anos usando DI Futuro.
    
    Returns:
        Taxa de 10 anos (ou None se não disponível)
    """
    hoje = date.today()
    ano_10y = hoje.year + 10
    
    # Tenta buscar o vencimento de janeiro do ano 10 anos à frente
    ticker_10y = gerar_ticker_di(ano_10y, mes=1)
    dados = fetch_di_futuro_b3(ticker_10y, trade_date)
    
    if dados and dados['taxa']:
        return dados['taxa']
    
    # Fallback: buscar vencimento mais próximo de 10 anos
    for delta in [-1, 1, -2, 2]:
        ticker_alt = gerar_ticker_di(ano_10y + delta, mes=1)
        dados_alt = fetch_di_futuro_b3(ticker_alt, trade_date)
        if dados_alt and dados_alt['taxa']:
            return dados_alt['taxa']
    
    return None
