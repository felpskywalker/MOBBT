"""
Página de Correlações e Detecção de Regime
Inclui: matriz de correlação, beta rolling, regime Risk-On/Risk-Off
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

from src.models.correlations import (
    calcular_matriz_correlacao_rolling,
    calcular_correlacao_rolling_ts,
    calcular_beta_rolling,
    detectar_regime,
    calcular_metricas_correlacao
)
from src.components.charts_correlations import (
    gerar_heatmap_correlacao,
    gerar_grafico_beta_rolling,
    gerar_gauge_regime,
    gerar_grafico_correlacao_ts
)

# ============================================================
# CONSTANTES
# ============================================================
ATIVOS_BR = {
    'BOVA11.SA': 'BOVA11 (IBOV ETF)',
    'PETR4.SA': 'PETR4 (Petrobras)',
    'VALE3.SA': 'VALE3 (Vale)',
    'ITUB4.SA': 'ITUB4 (Itaú)',
    'BBDC4.SA': 'BBDC4 (Bradesco)',
    'WEGE3.SA': 'WEGE3 (WEG)',
    'RENT3.SA': 'RENT3 (Localiza)',
    'PRIO3.SA': 'PRIO3 (PetroRio)',
    '^BVSP': 'IBOV (Índice)',
}

FATORES_GLOBAIS = {
    'EWZ': 'EWZ (ETF Brasil)',
    '^VIX': 'VIX (Volatilidade)',
    'DX-Y.NYB': 'DXY (Dollar Index)',
    'CL=F': 'Petróleo WTI',
    'GC=F': 'Ouro',
    '^GSPC': 'S&P 500',
}

PERIODOS_CORRELACAO = {
    '21 dias (1M)': 21,
    '63 dias (3M)': 63,
    '126 dias (6M)': 126,
    '252 dias (1A)': 252,
}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
@st.cache_data(ttl=3600*2)
def carregar_precos(tickers: list, periodo_anos: int = 3):
    """Carrega preços históricos via yfinance."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=periodo_anos * 365)
    
    try:
        df = yf.download(
            tickers, 
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            auto_adjust=True,
            progress=False
        )
        
        if df.empty:
            return pd.DataFrame()
        
        # Lidar com MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            # Pegar só Close
            if 'Close' in df.columns.get_level_values(0):
                df = df['Close']
            elif 'Adj Close' in df.columns.get_level_values(0):
                df = df['Adj Close']
            else:
                df = df.iloc[:, :len(tickers)]
        
        return df.ffill().dropna()
    
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()


# ============================================================
# FUNÇÕES DE RENDERIZAÇÃO
# ============================================================
def render_header():
    """Renderiza header e explicação."""
    st.header("📊 Correlações & Regime de Mercado")
    
    with st.expander("ℹ️ **O que é Correlação e Regime?**", expanded=False):
        st.markdown("""
        ### Correlação
        
        A **correlação** mede a relação entre dois ativos:
        - **+1**: Movem juntos na mesma direção
        - **0**: Sem relação
        - **-1**: Movem em direções opostas
        
        #### Por que importa:
        - Correlações **mudam ao longo do tempo**
        - Em crises, correlações tendem a **aumentar** (todos ativos caem juntos)
        - Diversificar com ativos de baixa correlação reduz risco
        
        ---
        
        ### Regime de Mercado
        
        O mercado alterna entre dois regimes principais:
        
        🟢 **Risk-On**:
        - Apetite por risco alto
        - Ações e commodities sobem
        - Dólar cai
        - Volatilidade baixa
        
        🔴 **Risk-Off**:
        - Aversão ao risco
        - Ativos seguros sobem (dólar, ouro)
        - Ações caem
        - Volatilidade alta
        
        **Entender o regime atual ajuda a posicionar a carteira corretamente.**
        """)


def render_matriz_correlacao(df_prices: pd.DataFrame, window: int):
    """Renderiza matriz de correlação."""
    st.subheader("🔗 Matriz de Correlação")
    
    if df_prices.empty:
        st.warning("Dados não disponíveis para matriz de correlação.")
        return
    
    # Calcular matriz
    corr_matrix = calcular_matriz_correlacao_rolling(df_prices, window=window)
    
    # Limpar nomes das colunas
    corr_matrix.columns = [c.replace('.SA', '') for c in corr_matrix.columns]
    corr_matrix.index = [c.replace('.SA', '') for c in corr_matrix.index]
    
    # Gráfico
    st.plotly_chart(
        gerar_heatmap_correlacao(corr_matrix, f"Correlação ({window} dias)"),
        use_container_width=True,
        key="corr_matrix_chart"
    )
    
    # Tabela com valores
    with st.expander("📋 Tabela de Correlações"):
        st.dataframe(
            corr_matrix.style.format("{:.2f}"),
            use_container_width=True
        )


def render_regime_detection(df_indicators: pd.DataFrame):
    """Renderiza indicador de regime."""
    st.subheader("⚡ Regime de Mercado Atual")
    
    if df_indicators.empty:
        st.warning("Dados não disponíveis para detecção de regime.")
        return
    
    # Detectar regime
    resultado = detectar_regime(df_indicators)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # Gauge
        st.plotly_chart(
            gerar_gauge_regime(resultado['score'], resultado['regime']),
            use_container_width=True,
            key="regime_gauge"
        )
    
    with col2:
        # Detalhamento dos sinais
        st.markdown("#### 📡 Sinais")
        for signal in resultado['signals']:
            if signal['signal'] == 'RISK_ON':
                st.success(f"✅ **{signal['name']}**: {signal['value']} → Risk-On")
            elif signal['signal'] == 'RISK_OFF':
                st.error(f"⚠️ **{signal['name']}**: {signal['value']} → Risk-Off")
            else:
                st.info(f"⚖️ **{signal['name']}**: {signal['value']} → Neutro")
        
        # Interpretação
        st.markdown("---")
        if resultado['regime'] == 'RISK_ON':
            st.success("""
            **Ambiente Risk-On detectado**
            
            Considere:
            - Aumentar exposição a ações
            - Reduzir posições defensivas
            - Commodities cíclicas
            """)
        elif resultado['regime'] == 'RISK_OFF':
            st.error("""
            **Ambiente Risk-Off detectado**
            
            Considere:
            - Reduzir exposição a ações
            - Aumentar caixa ou renda fixa
            - Ativos defensivos
            """)
        else:
            st.info("""
            **Ambiente Neutro/Transição**
            
            Considere:
            - Manter portfólio balanceado
            - Aguardar sinais mais claros
            - Evitar posições direcionais fortes
            """)


def render_beta_rolling(df_prices: pd.DataFrame, ativo_selecionado: str, indice: str = '^BVSP'):
    """Renderiza beta rolling de um ativo."""
    st.subheader("📈 Beta Rolling")
    
    if df_prices.empty:
        st.warning("Dados não disponíveis.")
        return
    
    if ativo_selecionado not in df_prices.columns:
        st.warning(f"Ativo {ativo_selecionado} não encontrado.")
        return
    
    if indice not in df_prices.columns:
        st.warning(f"Índice {indice} não encontrado nos dados.")
        return
    
    # Calcular beta rolling
    beta_series = calcular_beta_rolling(
        df_prices[ativo_selecionado],
        df_prices[indice],
        window=63
    )
    
    if beta_series.empty:
        st.warning("Dados insuficientes para calcular beta.")
        return
    
    # Métricas atuais
    beta_atual = beta_series.iloc[-1]
    beta_medio = beta_series.mean()
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Beta Atual", f"{beta_atual:.2f}")
    m2.metric("Beta Médio (2A)", f"{beta_medio:.2f}")
    m3.metric("Diferença", f"{beta_atual - beta_medio:+.2f}")
    
    # Interpretação
    if beta_atual > 1.2:
        st.warning("⚠️ Beta **alto** - Ativo mais volátil que o mercado. Maior risco.")
    elif beta_atual < 0.8:
        st.success("✅ Beta **baixo** - Ativo mais defensivo que o mercado.")
    else:
        st.info("⚖️ Beta **neutro** - Volatilidade similar ao mercado.")
    
    # Gráfico
    ativo_clean = ativo_selecionado.replace('.SA', '')
    st.plotly_chart(
        gerar_grafico_beta_rolling(beta_series, ativo_clean, "IBOV"),
        use_container_width=True,
        key="beta_rolling_chart"
    )


def render_correlacao_fatores(df_prices: pd.DataFrame, ativo: str):
    """Renderiza correlação de um ativo com fatores globais."""
    st.subheader("🌍 Correlação com Fatores Globais")
    
    fatores = ['EWZ', '^VIX', 'DX-Y.NYB', 'CL=F', 'GC=F', '^GSPC']
    fatores_disponiveis = [f for f in fatores if f in df_prices.columns]
    
    if not fatores_disponiveis or ativo not in df_prices.columns:
        st.warning("Dados insuficientes para análise de fatores.")
        return
    
    # Calcular correlações
    correlacoes = {}
    for fator in fatores_disponiveis:
        corr_series = calcular_correlacao_rolling_ts(
            df_prices[ativo],
            df_prices[fator],
            window=63
        )
        if not corr_series.empty:
            correlacoes[fator] = corr_series.iloc[-1]
    
    # Tabela de correlações
    if correlacoes:
        corr_df = pd.DataFrame({
            'Fator': [FATORES_GLOBAIS.get(k, k) for k in correlacoes.keys()],
            'Correlação': list(correlacoes.values())
        })
        corr_df['Interpretação'] = corr_df['Correlação'].apply(
            lambda x: '🟢 Alta (+)' if x > 0.5 else ('🔴 Alta (-)' if x < -0.5 else '⚪ Baixa')
        )
        corr_df['Correlação'] = corr_df['Correlação'].apply(lambda x: f"{x:.2f}")
        
        st.dataframe(corr_df, hide_index=True, use_container_width=True, key="corr_fatores_df")
    
    # Gráfico de um fator selecionado
    if fatores_disponiveis:
        fator_selecionado = st.selectbox(
            "Selecione fator para gráfico",
            options=fatores_disponiveis,
            format_func=lambda x: FATORES_GLOBAIS.get(x, x),
            key="fator_select"
        )
        
        corr_ts = calcular_correlacao_rolling_ts(
            df_prices[ativo],
            df_prices[fator_selecionado],
            window=63
        )
        
        if not corr_ts.empty:
            ativo_clean = ativo.replace('.SA', '')
            fator_name = FATORES_GLOBAIS.get(fator_selecionado, fator_selecionado)
            st.plotly_chart(
                gerar_grafico_correlacao_ts(corr_ts, f"{ativo_clean} vs {fator_name}"),
                use_container_width=True,
                key="corr_ts_chart"
            )


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def render():
    """Função principal de renderização."""
    render_header()
    st.markdown("---")
    
    # Sidebar de configuração
    with st.sidebar:
        st.subheader("⚙️ Configurações")
        
        periodo_corr = st.selectbox(
            "Período para Correlação",
            options=list(PERIODOS_CORRELACAO.keys()),
            index=1,  # Default 63 dias
            key="periodo_corr_select"
        )
        window = PERIODOS_CORRELACAO[periodo_corr]
        
        ativos_selecionados = st.multiselect(
            "Ativos para Matriz",
            options=list(ATIVOS_BR.keys()),
            default=['^BVSP', 'BOVA11.SA', 'PETR4.SA', 'VALE3.SA', 'ITUB4.SA'],
            format_func=lambda x: ATIVOS_BR.get(x, x),
            key="ativos_select"
        )
        
        ativo_beta = st.selectbox(
            "Ativo para Beta",
            options=[a for a in ATIVOS_BR.keys() if a != '^BVSP'],
            format_func=lambda x: ATIVOS_BR.get(x, x),
            key="ativo_beta_select"
        )
    
    # Carregar dados
    all_tickers = list(set(ativos_selecionados) | set(FATORES_GLOBAIS.keys()) | {'^BVSP', ativo_beta})
    
    with st.spinner("Carregando dados de mercado..."):
        df_prices = carregar_precos(all_tickers, periodo_anos=3)
    
    if df_prices.empty:
        st.error("❌ Não foi possível carregar dados. Verifique sua conexão.")
        return
    
    # 1. Regime de Mercado
    df_indicators = pd.DataFrame()
    if '^VIX' in df_prices.columns:
        df_indicators['vix'] = df_prices['^VIX']
    if 'DX-Y.NYB' in df_prices.columns:
        df_indicators['dxy'] = df_prices['DX-Y.NYB']
    if '^BVSP' in df_prices.columns:
        df_indicators['ibov'] = df_prices['^BVSP']
    
    render_regime_detection(df_indicators)
    st.markdown("---")
    
    # 2. Matriz de Correlação
    df_matriz = df_prices[[c for c in ativos_selecionados if c in df_prices.columns]]
    render_matriz_correlacao(df_matriz, window)
    st.markdown("---")
    
    # 3. Beta Rolling
    render_beta_rolling(df_prices, ativo_beta, '^BVSP')
    st.markdown("---")
    
    # 4. Correlação com Fatores Globais
    render_correlacao_fatores(df_prices, ativo_beta)
