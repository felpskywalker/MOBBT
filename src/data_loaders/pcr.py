"""
Módulo para cálculo de Put-Call Ratio (PCR) e Max Pain.

Funções para análise de sentimento do mercado de opções.
"""

import pandas as pd
import numpy as np
from datetime import date, datetime
from typing import Optional, Dict, Tuple
import os

# Supabase imports (condicionais para permitir uso standalone)
try:
    import streamlit as st
    from supabase import create_client
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def calcular_pcr(options_df: pd.DataFrame) -> Dict:
    """
    Calcula o Put-Call Ratio a partir de um DataFrame de opções.
    
    Args:
        options_df: DataFrame com colunas 'type', 'open_interest', 'volume' (opcional)
        
    Returns:
        Dict com pcr_oi, pcr_volume, totais e interpretação
    """
    if options_df.empty:
        return {
            'pcr_oi': None,
            'pcr_volume': None,
            'total_call_oi': 0,
            'total_put_oi': 0,
            'total_call_volume': 0,
            'total_put_volume': 0,
            'interpretacao': 'Sem dados'
        }
    
    # Separar calls e puts
    calls = options_df[options_df['type'].str.upper() == 'CALL']
    puts = options_df[options_df['type'].str.upper() == 'PUT']
    
    # Calcular totais de Open Interest
    total_call_oi = calls['open_interest'].sum() if 'open_interest' in calls.columns else 0
    total_put_oi = puts['open_interest'].sum() if 'open_interest' in puts.columns else 0
    
    # Calcular totais de Volume (se disponível)
    total_call_volume = calls['volume'].sum() if 'volume' in calls.columns else 0
    total_put_volume = puts['volume'].sum() if 'volume' in puts.columns else 0
    
    # Calcular PCR
    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
    pcr_volume = total_put_volume / total_call_volume if total_call_volume > 0 else None
    
    # Interpretação
    interpretacao = interpretar_pcr(pcr_oi)
    
    return {
        'pcr_oi': round(pcr_oi, 4) if pcr_oi else None,
        'pcr_volume': round(pcr_volume, 4) if pcr_volume else None,
        'total_call_oi': int(total_call_oi),
        'total_put_oi': int(total_put_oi),
        'total_call_volume': int(total_call_volume),
        'total_put_volume': int(total_put_volume),
        'interpretacao': interpretacao
    }


def interpretar_pcr(pcr_valor: Optional[float]) -> str:
    """
    Retorna interpretação textual do Put-Call Ratio.
    
    Args:
        pcr_valor: Valor do PCR
        
    Returns:
        String com interpretação e emoji
    """
    if pcr_valor is None:
        return "⚪ Sem dados"
    
    if pcr_valor > 1.5:
        return "🔴 Medo Extremo (possível fundo)"
    elif pcr_valor > 1.2:
        return "🟠 Medo Elevado"
    elif pcr_valor > 1.0:
        return "🟡 Cautela / Hedge"
    elif pcr_valor > 0.7:
        return "🟢 Neutro"
    elif pcr_valor > 0.5:
        return "🟡 Otimismo Elevado"
    else:
        return "🔴 Euforia Extrema (possível topo)"


def calcular_max_pain(options_df: pd.DataFrame, spot_price: float = None) -> Tuple[Optional[float], Dict[float, float]]:
    """
    Calcula o Max Pain - strike onde compradores de opções perdem mais dinheiro.
    
    O Max Pain é o strike no qual o valor total de opções que expiram ITM é minimizado.
    
    Args:
        options_df: DataFrame com opções (colunas: type, strike, open_interest)
        spot_price: Preço spot para referência (opcional)
        
    Returns:
        Tuple: (max_pain_strike, dicionário de dor por strike)
    """
    if options_df.empty or 'strike' not in options_df.columns:
        return None, {}
    
    # Garantir que temos as colunas necessárias
    required_cols = ['type', 'strike', 'open_interest']
    if not all(col in options_df.columns for col in required_cols):
        return None, {}
    
    # Separar calls e puts
    calls = options_df[options_df['type'].str.upper() == 'CALL'].copy()
    puts = options_df[options_df['type'].str.upper() == 'PUT'].copy()
    
    if calls.empty and puts.empty:
        return None, {}
    
    # Obter todos os strikes únicos
    all_strikes = sorted(options_df['strike'].unique())
    
    if not all_strikes:
        return None, {}
    
    pain_por_strike = {}
    
    for price_at_expiry in all_strikes:
        dor_total = 0
        
        # Dor das CALLs (perdem dinheiro quando preço < strike)
        for _, call in calls.iterrows():
            if price_at_expiry > call['strike']:
                # Call ITM - comprador ganha (preço - strike) * OI * 100
                # Invertemos porque queremos a "dor" do comprador se preço NÃO chegar lá
                pass  # Não conta como dor neste strike
            else:
                # Call OTM - comprador perde tudo (dor = valor intrínseco que TERIA se fosse ITM)
                # Para max pain, calculamos quanto os compradores perdem
                pass
        
        # Cálculo simplificado: para cada strike de teste, 
        # somamos quanto os compradores de opções perderiam
        
        # CALLs: comprador perde se preço < strike da call
        for _, call in calls.iterrows():
            if price_at_expiry > call['strike']:
                # Call ITM - comprador ganha, vendedor (dealer) perde
                dor_total += (price_at_expiry - call['strike']) * call['open_interest'] * 100
        
        # PUTs: comprador perde se preço > strike da put  
        for _, put in puts.iterrows():
            if price_at_expiry < put['strike']:
                # Put ITM - comprador ganha, vendedor (dealer) perde
                dor_total += (put['strike'] - price_at_expiry) * put['open_interest'] * 100
        
        pain_por_strike[price_at_expiry] = dor_total
    
    # Max Pain = strike com MENOR dor total (onde dealers perdem menos)
    if pain_por_strike:
        max_pain_strike = min(pain_por_strike, key=pain_por_strike.get)
        return max_pain_strike, pain_por_strike
    
    return None, {}


def get_supabase_client_standalone():
    """
    Retorna cliente Supabase para uso em scripts standalone (sem Streamlit).
    Usa variáveis de ambiente.
    """
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    
    if not url or not key:
        raise ValueError("SUPABASE_URL e SUPABASE_KEY devem estar definidos como variáveis de ambiente")
    
    from supabase import create_client
    return create_client(url, key)


def get_supabase_client():
    """
    Retorna cliente Supabase (tenta Streamlit primeiro, depois env vars).
    """
    if STREAMLIT_AVAILABLE:
        try:
            url = st.secrets["general"]["SUPABASE_URL"]
            key = st.secrets["general"]["SUPABASE_KEY"]
            return create_client(url, key)
        except Exception:
            pass
    
    return get_supabase_client_standalone()


def salvar_pcr_supabase(
    data: date,
    ticker: str,
    pcr_data: Dict,
    max_pain_strike: Optional[float],
    spot_price: Optional[float]
) -> bool:
    """
    Salva dados de PCR no Supabase.
    
    Args:
        data: Data de referência
        ticker: Ticker do ativo
        pcr_data: Dict retornado por calcular_pcr()
        max_pain_strike: Strike do Max Pain
        spot_price: Preço spot
        
    Returns:
        True se salvou com sucesso
    """
    try:
        client = get_supabase_client()
        
        record = {
            'data': data.isoformat(),
            'ticker': ticker.upper(),
            'pcr_oi': pcr_data.get('pcr_oi'),
            'pcr_volume': pcr_data.get('pcr_volume'),
            'total_call_oi': pcr_data.get('total_call_oi'),
            'total_put_oi': pcr_data.get('total_put_oi'),
            'max_pain_strike': max_pain_strike,
            'spot_price': spot_price
        }
        
        # Upsert para evitar duplicatas
        client.table('pcr_historico').upsert(record, on_conflict='data,ticker').execute()
        
        return True
        
    except Exception as e:
        print(f"Erro ao salvar PCR no Supabase: {e}")
        return False


def carregar_pcr_historico(ticker: str, dias: int = 252) -> pd.DataFrame:
    """
    Carrega histórico de PCR do Supabase.
    
    Args:
        ticker: Ticker do ativo
        dias: Número de dias de histórico
        
    Returns:
        DataFrame com histórico
    """
    try:
        client = get_supabase_client()
        
        response = client.table('pcr_historico') \
            .select('*') \
            .eq('ticker', ticker.upper()) \
            .order('data', desc=True) \
            .limit(dias) \
            .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            df['data'] = pd.to_datetime(df['data'])
            df = df.sort_values('data')
            return df
        
        return pd.DataFrame()
        
    except Exception as e:
        print(f"Erro ao carregar histórico de PCR: {e}")
        return pd.DataFrame()


def calcular_pcr_percentil(pcr_atual: float, df_historico: pd.DataFrame) -> Optional[float]:
    """
    Calcula o percentil do PCR atual em relação ao histórico.
    
    Args:
        pcr_atual: Valor atual do PCR
        df_historico: DataFrame com histórico de PCR
        
    Returns:
        Percentil (0-100) ou None se não houver histórico
    """
    if df_historico.empty or 'pcr_oi' not in df_historico.columns:
        return None
    
    historico = df_historico['pcr_oi'].dropna()
    
    if len(historico) < 5:
        return None
    
    percentil = (historico < pcr_atual).sum() / len(historico) * 100
    
    return round(percentil, 1)
