"""
Página de Sentimento de Opções

Inclui: Put-Call Ratio (PCR), Max Pain, histórico de PCR.
Indicadores de sentimento baseados no mercado de opções.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date

from src.data_loaders.opcoes_net import get_cached_options_data
from src.data_loaders.pcr import (
    calcular_pcr,
    calcular_max_pain,
    interpretar_pcr,
    carregar_pcr_historico,
    calcular_pcr_percentil
)
from src.models.put_utils import get_asset_price_yesterday


# ============================================================
# GRÁFICOS
# ============================================================

def gerar_grafico_max_pain(pain_por_strike: dict, max_pain_strike: float, spot_price: float):
    """Gera gráfico de barras do Max Pain."""
    if not pain_por_strike:
        return go.Figure().update_layout(title="Sem dados de Max Pain")
    
    strikes = list(pain_por_strike.keys())
    valores = [v / 1_000_000 for v in pain_por_strike.values()]  # Converter para milhões
    
    # Criar cores (destacar max pain)
    colors = ['#636EFA' if s != max_pain_strike else '#00CC96' for s in strikes]
    
    fig = go.Figure(data=[
        go.Bar(
            x=strikes,
            y=valores,
            marker_color=colors,
            hovertemplate='Strike: R$ %{x:.2f}<br>Dor: R$ %{y:.1f}M<extra></extra>'
        )
    ])
    
    # Linha do spot price
    fig.add_vline(
        x=spot_price,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Spot: R$ {spot_price:.2f}",
        annotation_position="top"
    )
    
    # Linha do max pain
    fig.add_vline(
        x=max_pain_strike,
        line_dash="solid",
        line_color="#00CC96",
        line_width=2,
        annotation_text=f"Max Pain: R$ {max_pain_strike:.2f}",
        annotation_position="bottom"
    )
    
    fig.update_layout(
        title='Max Pain por Strike (Dor Total dos Compradores)',
        xaxis_title='Strike (R$)',
        yaxis_title='Valor em Risco (R$ Milhões)',
        template='brokeberg',
        showlegend=False,
        height=400
    )
    
    return fig


def gerar_grafico_pcr_historico(df_historico: pd.DataFrame):
    """Gera gráfico de linha do PCR histórico."""
    if df_historico.empty:
        return go.Figure().update_layout(title="Sem histórico de PCR disponível")
    
    fig = go.Figure()
    
    # Linha do PCR
    fig.add_trace(go.Scatter(
        x=df_historico['data'],
        y=df_historico['pcr_oi'],
        mode='lines+markers',
        name='PCR (OI)',
        line=dict(color='#636EFA', width=2),
        marker=dict(size=6),
        hovertemplate='%{x|%d/%m/%Y}<br>PCR: %{y:.3f}<extra></extra>'
    ))
    
    # Bandas de referência
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", 
                  annotation_text="Neutro (1.0)", annotation_position="right")
    fig.add_hline(y=1.2, line_dash="dot", line_color="orange",
                  annotation_text="Medo (1.2)", annotation_position="right")
    fig.add_hline(y=0.7, line_dash="dot", line_color="green",
                  annotation_text="Otimismo (0.7)", annotation_position="right")
    
    # Áreas de extremo
    fig.add_hrect(y0=1.5, y1=df_historico['pcr_oi'].max() * 1.1 if not df_historico['pcr_oi'].isna().all() else 2,
                  fillcolor="red", opacity=0.1, line_width=0,
                  annotation_text="Zona de Medo Extremo", annotation_position="top left")
    
    fig.add_hrect(y0=0, y1=0.5,
                  fillcolor="red", opacity=0.1, line_width=0,
                  annotation_text="Zona de Euforia", annotation_position="bottom left")
    
    fig.update_layout(
        title='Histórico do Put-Call Ratio (OI)',
        xaxis_title='Data',
        yaxis_title='Put-Call Ratio',
        template='brokeberg',
        height=400,
        hovermode='x unified'
    )
    
    return fig


def gerar_grafico_oi_agregado(options_df: pd.DataFrame, spot_price: float = None):
    """Gera gráfico de barras do Open Interest agregado por tipo e bins de strike."""
    if options_df.empty:
        return go.Figure().update_layout(title="Sem dados")
    
    # Criar cópia e agregar strikes em bins de R$5
    df = options_df.copy()
    bin_size = 5
    df['strike_bin'] = (df['strike'] // bin_size) * bin_size
    
    # Agregar por bin e tipo
    df_agg = df.groupby(['strike_bin', 'type'])['open_interest'].sum().reset_index()
    
    # Pivotar para ter colunas separadas
    df_pivot = df_agg.pivot(index='strike_bin', columns='type', values='open_interest').fillna(0)
    
    fig = go.Figure()
    
    if 'CALL' in df_pivot.columns:
        fig.add_trace(go.Bar(
            x=df_pivot.index,
            y=df_pivot['CALL'],
            name='CALL OI',
            marker_color='#00CC96',
            hovertemplate='Strike: R$ %{x:.0f}-%{customdata:.0f}<br>CALL OI: %{y:,.0f}<extra></extra>',
            customdata=[x + bin_size for x in df_pivot.index]
        ))
    
    if 'PUT' in df_pivot.columns:
        fig.add_trace(go.Bar(
            x=df_pivot.index,
            y=df_pivot['PUT'],
            name='PUT OI',
            marker_color='#EF553B',
            hovertemplate='Strike: R$ %{x:.0f}-%{customdata:.0f}<br>PUT OI: %{y:,.0f}<extra></extra>',
            customdata=[x + bin_size for x in df_pivot.index]
        ))
    
    # Adicionar linha do spot price
    if spot_price:
        fig.add_vline(
            x=spot_price,
            line_dash="dash",
            line_color="white",
            line_width=2,
            annotation_text=f"Spot: R$ {spot_price:.2f}",
            annotation_position="top"
        )
    
    fig.update_layout(
        title='Open Interest por Strike (Agregado em bins de R$5)',
        xaxis_title='Strike (R$)',
        yaxis_title='Open Interest',
        template='brokeberg',
        barmode='group',
        height=400,
        legend=dict(orientation='h', yanchor='bottom', y=1.02)
    )
    
    return fig


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def render():
    st.header("📊 Sentimento de Opções")
    
    st.info(
        "Análise de sentimento do mercado baseada em **Put-Call Ratio** e **Max Pain**. "
        "O PCR mede a proporção entre opções de venda e compra; o Max Pain indica onde os vendedores de opções (dealers) perdem menos dinheiro."
    )
    
    # Seleção do ativo
    ticker = st.selectbox(
        "Ativo",
        options=["BOVA11", "PETR4", "VALE3", "ITUB4", "BBDC4"],
        index=0,
        key="ticker_sentimento"
    )
    
    # Dois botões separados
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        btn_max_pain = st.button("🎯 Calcular Max Pain", key="btn_max_pain", use_container_width=True)
    
    with col_btn2:
        btn_pcr = st.button("📊 Calcular PCR", key="btn_pcr", use_container_width=True)
    
    # Carregar dados para Max Pain
    if btn_max_pain:
        with st.spinner(f"Buscando dados de opções de {ticker} para Max Pain..."):
            options_df = get_cached_options_data(ticker, force_refresh=True)
            
            if not options_df.empty:
                st.session_state['options_max_pain'] = options_df
                st.session_state['ticker_max_pain'] = ticker
                st.success(f"✅ {len(options_df)} opções carregadas para Max Pain!")
            else:
                st.error("❌ Não foi possível carregar dados de opções.")
    
    # Carregar dados para PCR
    if btn_pcr:
        with st.spinner(f"Buscando dados de opções de {ticker} para PCR..."):
            options_df = get_cached_options_data(ticker, force_refresh=True)
            
            if not options_df.empty:
                st.session_state['options_pcr'] = options_df
                st.session_state['ticker_pcr'] = ticker
                st.success(f"✅ {len(options_df)} opções carregadas para PCR!")
            else:
                st.error("❌ Não foi possível carregar dados de opções.")
    
    st.markdown("---")
    
    # ================== SEÇÃO MAX PAIN ==================
    st.markdown("### 🎯 Max Pain")
    
    if 'options_max_pain' in st.session_state and st.session_state.get('ticker_max_pain') == ticker:
        options_df = st.session_state['options_max_pain']
        
        # Obter preço spot
        spot_price = get_asset_price_yesterday(f"{ticker}.SA")
        if spot_price is None:
            spot_price = options_df['strike'].median()
        
        # Calcular Max Pain
        max_pain_strike, pain_por_strike = calcular_max_pain(options_df, spot_price)
        
        if max_pain_strike and pain_por_strike:
            # Métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Max Pain Strike", f"R$ {max_pain_strike:.2f}")
            with col2:
                st.metric("Spot Price", f"R$ {spot_price:.2f}")
            with col3:
                dist_pct = ((max_pain_strike - spot_price) / spot_price) * 100
                st.metric("Distância", f"{dist_pct:+.1f}%")
            
            # Gráfico
            st.plotly_chart(
                gerar_grafico_max_pain(pain_por_strike, max_pain_strike, spot_price),
                use_container_width=True,
                key="chart_max_pain"
            )
            
            # Resumo
            if max_pain_strike > spot_price:
                st.success(f"📈 Max Pain está **acima** do spot → Pressão de alta esperada")
            else:
                st.warning(f"📉 Max Pain está **abaixo** do spot → Pressão de baixa esperada")
        else:
            st.warning("Não foi possível calcular o Max Pain.")
    else:
        st.caption("👆 Clique em 'Calcular Max Pain' para ver a análise.")
    
    st.markdown("---")
    
    # ================== SEÇÃO PCR ==================
    st.markdown("### 📊 Put-Call Ratio")
    
    if 'options_pcr' in st.session_state and st.session_state.get('ticker_pcr') == ticker:
        options_df = st.session_state['options_pcr']
        
        # Obter spot price
        spot_price = get_asset_price_yesterday(f"{ticker}.SA")
        if spot_price is None:
            spot_price = options_df['strike'].median()
        
        # Calcular PCR
        pcr_data = calcular_pcr(options_df)
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            pcr_oi = pcr_data.get('pcr_oi')
            st.metric("PCR (OI)", f"{pcr_oi:.3f}" if pcr_oi else "N/D")
        
        with col2:
            st.metric("Sentimento", pcr_data.get('interpretacao', 'N/D'))
        
        with col3:
            st.metric("Total PUT OI", f"{pcr_data.get('total_put_oi', 0):,}")
        
        with col4:
            st.metric("Total CALL OI", f"{pcr_data.get('total_call_oi', 0):,}")
        
        # Tabs para gráficos - Histórico primeiro
        tab1, tab2 = st.tabs(["📈 Histórico PCR", "📊 Open Interest"])
        
        with tab1:
            st.caption("O histórico é construído automaticamente via coleta diária.")
            
            df_historico = carregar_pcr_historico(ticker)
            
            if not df_historico.empty:
                percentil = calcular_pcr_percentil(pcr_data.get('pcr_oi'), df_historico)
                if percentil is not None:
                    st.metric("PCR Percentil", f"{percentil:.0f}%")
                
                st.plotly_chart(
                    gerar_grafico_pcr_historico(df_historico),
                    use_container_width=True,
                    key="chart_pcr_historico"
                )
            else:
                st.warning("📭 Ainda não há histórico de PCR. Será construído automaticamente.")
        
        with tab2:
            st.plotly_chart(
                gerar_grafico_oi_agregado(options_df, spot_price),
                use_container_width=True,
                key="chart_oi_agregado"
            )
    else:
        st.caption("👆 Clique em 'Calcular PCR' para ver a análise.")
    
    st.markdown("---")
    
    # ================== EXPLICAÇÃO ==================
    with st.expander("ℹ️ Como interpretar estes indicadores"):
        st.markdown("""
        ### Put-Call Ratio (PCR)
        
        | PCR | Interpretação |
        |-----|---------------|
        | > 1.5 | 🔴 Medo Extremo - Possível fundo (indicador contrário) |
        | 1.2 - 1.5 | 🟠 Medo Elevado - Mercado cauteloso |
        | 1.0 - 1.2 | 🟡 Cautela - Hedge ativo |
        | 0.7 - 1.0 | 🟢 Neutro - Equilíbrio |
        | 0.5 - 0.7 | 🟡 Otimismo - Mais calls que puts |
        | < 0.5 | 🔴 Euforia Extrema - Possível topo (indicador contrário) |
        
        ### Max Pain
        
        - **Strike onde dealers (vendedores) perdem menos dinheiro** no vencimento
        - O preço tende a convergir para o Max Pain próximo ao vencimento
        - É mais relevante nas últimas semanas antes do vencimento
        - **Acima do spot**: pressão de alta esperada
        - **Abaixo do spot**: pressão de baixa esperada
        """)
