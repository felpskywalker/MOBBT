"""
Módulo de cálculos para Correlação e Detecção de Regime.
Inclui: correlação rolling, beta rolling, detecção de regime Risk-On/Risk-Off.
"""

import pandas as pd
import numpy as np
from scipy import stats


def calcular_matriz_correlacao_rolling(df_prices: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    """
    Calcula a matriz de correlação rolling entre múltiplos ativos.
    
    Args:
        df_prices: DataFrame com preços (colunas = ativos)
        window: Janela de cálculo em dias (default 63 = 3 meses)
    
    Returns:
        DataFrame com correlação atual (última observação da rolling)
    """
    returns = df_prices.pct_change().dropna()
    
    # Correlação rolling para cada par
    corr_matrix = returns.iloc[-window:].corr()
    
    return corr_matrix


def calcular_correlacao_rolling_ts(series_a: pd.Series, series_b: pd.Series, window: int = 63) -> pd.Series:
    """
    Calcula correlação rolling ao longo do tempo entre duas séries.
    
    Args:
        series_a: Primeira série de retornos
        series_b: Segunda série de retornos
        window: Janela de cálculo
    
    Returns:
        Series com correlação rolling
    """
    returns_a = series_a.pct_change().dropna()
    returns_b = series_b.pct_change().dropna()
    
    # Alinhar índices
    aligned = pd.DataFrame({'A': returns_a, 'B': returns_b}).dropna()
    
    if len(aligned) < window:
        return pd.Series(dtype=float)
    
    corr_rolling = aligned['A'].rolling(window=window).corr(aligned['B'])
    return corr_rolling


def calcular_beta_rolling(series_ativo: pd.Series, series_indice: pd.Series, window: int = 63) -> pd.Series:
    """
    Calcula beta rolling de um ativo em relação a um índice.
    
    Beta = Cov(ativo, índice) / Var(índice)
    
    Args:
        series_ativo: Série de preços do ativo
        series_indice: Série de preços do índice
        window: Janela de cálculo
    
    Returns:
        Series com beta rolling
    """
    returns_ativo = series_ativo.pct_change().dropna()
    returns_indice = series_indice.pct_change().dropna()
    
    # Alinhar índices
    aligned = pd.DataFrame({'ativo': returns_ativo, 'indice': returns_indice}).dropna()
    
    if len(aligned) < window:
        return pd.Series(dtype=float)
    
    # Covariância rolling
    cov_rolling = aligned['ativo'].rolling(window=window).cov(aligned['indice'])
    # Variância rolling do índice
    var_rolling = aligned['indice'].rolling(window=window).var()
    
    beta_rolling = cov_rolling / var_rolling
    return beta_rolling


def detectar_regime(df_indicators: pd.DataFrame) -> dict:
    """
    Detecta o regime atual do mercado (Risk-On vs Risk-Off).
    
    Indicadores usados:
    - VIX/VXEWZ: Alto = Risk-Off
    - DXY (Dollar): Alto = Risk-Off
    - HY Spread: Alto = Risk-Off (se disponível)
    - Correlação Ibov/Commodities: Alta correlação = Risk-On
    
    Args:
        df_indicators: DataFrame com indicadores
            Colunas esperadas: 'vix', 'dxy', 'ibov', 'commodities'
    
    Returns:
        dict com:
            - regime: 'RISK_ON', 'RISK_OFF', ou 'NEUTRAL'
            - score: -100 a +100 (negativo = Risk-Off, positivo = Risk-On)
            - signals: detalhamento dos sinais
    """
    signals = []
    score = 0
    
    # Verificar cada indicador disponível
    if 'vix' in df_indicators.columns:
        vix_series = df_indicators['vix'].dropna()
        if len(vix_series) > 0:
            vix_atual = vix_series.iloc[-1]
            vix_media = vix_series.mean()
            vix_std = vix_series.std()
            
            z_vix = (vix_atual - vix_media) / vix_std if vix_std > 0 else 0
            
            if z_vix > 1:
                signals.append({'name': 'VIX', 'signal': 'RISK_OFF', 'value': f'{vix_atual:.1f}', 'z': z_vix})
                score -= 25
            elif z_vix < -1:
                signals.append({'name': 'VIX', 'signal': 'RISK_ON', 'value': f'{vix_atual:.1f}', 'z': z_vix})
                score += 25
            else:
                signals.append({'name': 'VIX', 'signal': 'NEUTRAL', 'value': f'{vix_atual:.1f}', 'z': z_vix})
    
    if 'dxy' in df_indicators.columns:
        dxy_series = df_indicators['dxy'].dropna()
        if len(dxy_series) > 0:
            dxy_atual = dxy_series.iloc[-1]
            dxy_media = dxy_series.mean()
            dxy_std = dxy_series.std()
            
            z_dxy = (dxy_atual - dxy_media) / dxy_std if dxy_std > 0 else 0
            
            # DXY alto = Risk-Off (dólar forte)
            if z_dxy > 1:
                signals.append({'name': 'DXY', 'signal': 'RISK_OFF', 'value': f'{dxy_atual:.2f}', 'z': z_dxy})
                score -= 20
            elif z_dxy < -1:
                signals.append({'name': 'DXY', 'signal': 'RISK_ON', 'value': f'{dxy_atual:.2f}', 'z': z_dxy})
                score += 20
            else:
                signals.append({'name': 'DXY', 'signal': 'NEUTRAL', 'value': f'{dxy_atual:.2f}', 'z': z_dxy})
    
    if 'ibov' in df_indicators.columns:
        ibov_series = df_indicators['ibov'].dropna()
        if len(ibov_series) >= 21:
            # Momentum de 21 dias
            momentum = (ibov_series.iloc[-1] / ibov_series.iloc[-21] - 1) * 100
            
            if momentum > 5:
                signals.append({'name': 'IBOV Momentum', 'signal': 'RISK_ON', 'value': f'{momentum:+.1f}%', 'z': 0})
                score += 25
            elif momentum < -5:
                signals.append({'name': 'IBOV Momentum', 'signal': 'RISK_OFF', 'value': f'{momentum:+.1f}%', 'z': 0})
                score -= 25
            else:
                signals.append({'name': 'IBOV Momentum', 'signal': 'NEUTRAL', 'value': f'{momentum:+.1f}%', 'z': 0})
    
    # Determinar regime
    if score >= 30:
        regime = 'RISK_ON'
    elif score <= -30:
        regime = 'RISK_OFF'
    else:
        regime = 'NEUTRAL'
    
    return {
        'regime': regime,
        'score': score,
        'signals': signals
    }


def calcular_metricas_correlacao(df_prices: pd.DataFrame, ativos_principais: list, 
                                 indice: str = '^BVSP') -> dict:
    """
    Calcula métricas de correlação para uma lista de ativos.
    
    Args:
        df_prices: DataFrame com preços
        ativos_principais: Lista de tickers para análise
        indice: Ticker do índice de referência
    
    Returns:
        dict com métricas por ativo
    """
    results = {}
    
    returns = df_prices.pct_change().dropna()
    
    for ativo in ativos_principais:
        if ativo not in returns.columns or indice not in returns.columns:
            continue
        
        ativo_returns = returns[ativo].dropna()
        indice_returns = returns[indice].dropna()
        
        # Alinhar
        aligned = pd.DataFrame({'ativo': ativo_returns, 'indice': indice_returns}).dropna()
        
        if len(aligned) < 63:
            continue
        
        # Correlação atual (63d)
        corr_63d = aligned['ativo'].iloc[-63:].corr(aligned['indice'].iloc[-63:])
        
        # Beta atual (63d)
        cov = aligned['ativo'].iloc[-63:].cov(aligned['indice'].iloc[-63:])
        var = aligned['indice'].iloc[-63:].var()
        beta = cov / var if var > 0 else 0
        
        # Alpha anualizado
        ret_ativo_anual = (1 + aligned['ativo'].mean()) ** 252 - 1
        ret_indice_anual = (1 + aligned['indice'].mean()) ** 252 - 1
        alpha = ret_ativo_anual - beta * ret_indice_anual
        
        results[ativo] = {
            'correlacao_63d': corr_63d,
            'beta': beta,
            'alpha_anual': alpha * 100,  # Em percentual
            'vol_anual': aligned['ativo'].std() * np.sqrt(252) * 100
        }
    
    return results
