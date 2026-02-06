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


def gerar_grafico_oi_agregado(options_df: pd.DataFrame):
    """Gera gráfico de barras do Open Interest agregado por tipo."""
    if options_df.empty:
        return go.Figure().update_layout(title="Sem dados")
    
    # Agregar por strike e tipo
    df_agg = options_df.groupby(['strike', 'type'])['open_interest'].sum().reset_index()
    
    # Pivotar para ter colunas separadas
    df_pivot = df_agg.pivot(index='strike', columns='type', values='open_interest').fillna(0)
    
    fig = go.Figure()
    
    if 'CALL' in df_pivot.columns:
        fig.add_trace(go.Bar(
            x=df_pivot.index,
            y=df_pivot['CALL'],
            name='CALL OI',
            marker_color='#00CC96',
            opacity=0.7
        ))
    
    if 'PUT' in df_pivot.columns:
        fig.add_trace(go.Bar(
            x=df_pivot.index,
            y=-df_pivot['PUT'],  # Negativo para ficar embaixo
            name='PUT OI',
            marker_color='#EF553B',
            opacity=0.7
        ))
    
    fig.update_layout(
        title='Open Interest por Strike',
        xaxis_title='Strike (R$)',
        yaxis_title='Open Interest',
        template='brokeberg',
        barmode='overlay',
        height=350,
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
    
    # Botão para carregar dados
    if st.button("🔄 Carregar/Atualizar Dados", key="btn_carregar_sentimento"):
        with st.spinner(f"Buscando dados de opções de {ticker}..."):
            # Buscar dados de opções
            options_df = get_cached_options_data(ticker, force_refresh=True)
            
            if not options_df.empty:
                st.session_state['options_sentimento'] = options_df
                st.session_state['ticker_sentimento_atual'] = ticker
                st.success(f"✅ {len(options_df)} opções carregadas!")
            else:
                st.error("❌ Não foi possível carregar dados de opções.")
    
    # Exibir análise se tiver dados
    if 'options_sentimento' in st.session_state and st.session_state.get('ticker_sentimento_atual') == ticker:
        options_df = st.session_state['options_sentimento']
        
        # Obter preço spot
        spot_price = get_asset_price_yesterday(f"{ticker}.SA")
        
        if spot_price is None:
            st.warning("Não foi possível obter preço spot. Usando estimativa.")
            spot_price = options_df['strike'].median()
        
        # Calcular PCR
        pcr_data = calcular_pcr(options_df)
        
        # Calcular Max Pain
        max_pain_strike, pain_por_strike = calcular_max_pain(options_df, spot_price)
        
        st.markdown("---")
        
        # ================== MÉTRICAS PRINCIPAIS ==================
        st.markdown("### 📈 Indicadores Atuais")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            pcr_oi = pcr_data.get('pcr_oi')
            st.metric(
                "Put-Call Ratio (OI)",
                f"{pcr_oi:.3f}" if pcr_oi else "N/D",
                help="Relação entre Open Interest de PUTs e CALLs. >1 = mais PUTs (medo), <1 = mais CALLs (otimismo)"
            )
        
        with col2:
            st.metric(
                "Sentimento",
                pcr_data.get('interpretacao', 'N/D'),
                help="Interpretação do PCR atual"
            )
        
        with col3:
            st.metric(
                "Max Pain",
                f"R$ {max_pain_strike:.2f}" if max_pain_strike else "N/D",
                help="Strike onde vendedores de opções perdem menos dinheiro"
            )
        
        with col4:
            if max_pain_strike and spot_price:
                dist_pct = ((max_pain_strike - spot_price) / spot_price) * 100
                st.metric(
                    "Distância ao Max Pain",
                    f"{dist_pct:+.1f}%",
                    help="Distância percentual do spot ao Max Pain"
                )
            else:
                st.metric("Distância ao Max Pain", "N/D")
        
        # Segunda linha de métricas
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            st.metric("Total PUT OI", f"{pcr_data.get('total_put_oi', 0):,}")
        
        with col6:
            st.metric("Total CALL OI", f"{pcr_data.get('total_call_oi', 0):,}")
        
        with col7:
            st.metric("Spot Price", f"R$ {spot_price:.2f}" if spot_price else "N/D")
        
        with col8:
            total_oi = pcr_data.get('total_put_oi', 0) + pcr_data.get('total_call_oi', 0)
            st.metric("Total OI", f"{total_oi:,}")
        
        st.markdown("---")
        
        # ================== GRÁFICOS ==================
        tab1, tab2, tab3 = st.tabs(["🎯 Max Pain", "📊 Open Interest", "📈 Histórico PCR"])
        
        with tab1:
            st.markdown("#### Max Pain Analysis")
            st.caption(
                "O **Max Pain** é o strike onde o valor total de opções ITM é minimizado. "
                "Teoria: o preço tende a convergir para o Max Pain próximo ao vencimento."
            )
            
            if max_pain_strike and pain_por_strike:
                st.plotly_chart(
                    gerar_grafico_max_pain(pain_por_strike, max_pain_strike, spot_price),
                    use_container_width=True,
                    key="chart_max_pain"
                )
                
                # Resumo
                col_resumo1, col_resumo2 = st.columns(2)
                with col_resumo1:
                    if max_pain_strike > spot_price:
                        st.success(f"📈 Max Pain ({max_pain_strike:.2f}) está **acima** do spot ({spot_price:.2f})")
                    else:
                        st.warning(f"📉 Max Pain ({max_pain_strike:.2f}) está **abaixo** do spot ({spot_price:.2f})")
                
                with col_resumo2:
                    menor_dor = pain_por_strike.get(max_pain_strike, 0) / 1_000_000
                    st.info(f"💰 Menor exposição no Max Pain: **R$ {menor_dor:.1f}M**")
            else:
                st.warning("Não foi possível calcular o Max Pain.")
        
        with tab2:
            st.markdown("#### Distribuição de Open Interest")
            st.plotly_chart(
                gerar_grafico_oi_agregado(options_df),
                use_container_width=True,
                key="chart_oi_agregado"
            )
        
        with tab3:
            st.markdown("#### Histórico do Put-Call Ratio")
            st.caption("O histórico é construído automaticamente ao longo do tempo via coleta diária.")
            
            # Carregar histórico do Supabase
            df_historico = carregar_pcr_historico(ticker)
            
            if not df_historico.empty:
                # Calcular percentil
                percentil = calcular_pcr_percentil(pcr_data.get('pcr_oi'), df_historico)
                
                if percentil is not None:
                    st.metric("PCR Percentil (Histórico)", f"{percentil:.0f}%",
                             help="Posição do PCR atual em relação ao histórico. >80% = medo extremo, <20% = euforia")
                
                st.plotly_chart(
                    gerar_grafico_pcr_historico(df_historico),
                    use_container_width=True,
                    key="chart_pcr_historico"
                )
                
                # Estatísticas
                with st.expander("📊 Estatísticas do Histórico"):
                    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                    with col_stat1:
                        st.metric("Média", f"{df_historico['pcr_oi'].mean():.3f}")
                    with col_stat2:
                        st.metric("Mínimo", f"{df_historico['pcr_oi'].min():.3f}")
                    with col_stat3:
                        st.metric("Máximo", f"{df_historico['pcr_oi'].max():.3f}")
                    with col_stat4:
                        st.metric("Dias de Dados", len(df_historico))
            else:
                st.warning(
                    "📭 Ainda não há histórico de PCR para este ativo. "
                    "O histórico será construído automaticamente pela coleta diária."
                )
    else:
        st.caption("👆 Clique em 'Carregar/Atualizar Dados' para começar a análise.")
    
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
