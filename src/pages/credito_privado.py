
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from src.data_loaders.idex import carregar_dados_idex, carregar_dados_idex_infra
from src.data_loaders.debentures import DebenturesScraper

def gerar_grafico_idex(df_idex):
    if df_idex.empty: return go.Figure().update_layout(title_text="Sem dados IDEX.")
    fig = px.line(df_idex, y=['IDEX Geral (Filtrado)', 'IDEX Low Rated (Filtrado)'], title='Histórico do Spread Médio Ponderado: IDEX JGP', template='brokeberg')
    fig.update_yaxes(tickformat=".2%")
    fig.update_traces(hovertemplate='%{y:.2%}')
    fig.update_layout(title_x=0, yaxis_title='Spread Médio Ponderado (%)', xaxis_title='Data', legend_title_text='Índice', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def gerar_grafico_idex_infra(df_idex_infra):
    if df_idex_infra.empty: return go.Figure().update_layout(title_text="Sem dados IDEX INFRA.")
    fig = px.line(df_idex_infra, y='spread_bps_ntnb', title='Histórico do Spread Médio Ponderado: IDEX INFRA', template='brokeberg')
    fig.update_layout(title_x=0, yaxis_title='Spread Médio (Bps sobre NTNB)', xaxis_title='Data', showlegend=False)
    return fig

def gerar_grafico_pu_curva(df):
    """Gera gráfico do % PU da Curva por ativo."""
    if df.empty or '% PU da Curva' not in df.columns:
        return go.Figure().update_layout(title_text="Sem dados de % PU da Curva.")
    
    # Remove linhas sem dados válidos
    df = df.dropna(subset=['% PU da Curva'])
    
    if df.empty:
        return go.Figure().update_layout(title_text="Sem dados válidos de % PU da Curva.")
    
    fig = go.Figure()
    
    # Plotar cada ativo
    for ativo in df['Código do Ativo'].unique():
        df_ativo = df[df['Código do Ativo'] == ativo].sort_values('Data')
        fig.add_trace(go.Scatter(
            x=df_ativo['Data'],
            y=df_ativo['% PU da Curva'],
            mode='lines+markers',
            name=ativo,
            marker=dict(size=6),
            line=dict(width=2),
            hovertemplate='%{x|%d/%m/%Y}<br>%{y:.2f}%<extra></extra>'
        ))
    
    # Linha de referência em 100% (par)
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color="red",
        annotation_text="Par (100%)",
        annotation_position="top right"
    )
    
    fig.update_layout(
        title='Histórico do % PU da Curva',
        title_x=0,
        xaxis_title='Data',
        yaxis_title='% PU da Curva',
        template='brokeberg',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode='x unified'
    )
    
    return fig

def render():
    st.header("IDEX JGP - Indicador de Crédito Privado (Spread/CDI)")
    st.info(
        "O IDEX-CDI mostra o spread médio (prêmio acima do CDI) exigido pelo mercado para comprar debêntures. "
        "Filtramos emissores que passaram por eventos de crédito relevantes."
    )
    df_idex = carregar_dados_idex()
    if not df_idex.empty:
        st.plotly_chart(gerar_grafico_idex(df_idex), use_container_width=True, key="chart_idex")
    else:
        st.warning("Não foi possível carregar os dados do IDEX-CDI.")

    st.markdown("---")

    st.header("IDEX INFRA - Debêntures de Infraestrutura (Spread/NTN-B)")
    st.info(
        "O IDEX-INFRA mede o spread médio de debêntures incentivadas em relação aos títulos públicos de referência (NTN-Bs)."
    )
    df_idex_infra = carregar_dados_idex_infra()
    if not df_idex_infra.empty:
        st.plotly_chart(gerar_grafico_idex_infra(df_idex_infra), use_container_width=True, key="chart_idex_infra")
    else:
        st.warning("Não foi possível carregar os dados do IDEX INFRA.")
    
    st.markdown("---")
    
    # --- Seção de Histórico de Debêntures ---
    st.header("📈 Histórico de Preços de Debêntures")
    st.info(
        "Consulte o histórico do **% PU da Curva** de debêntures específicas. "
        "Valores abaixo de 100% indicam negociação com desconto; acima de 100%, com prêmio."
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        ticker_debenture = st.text_input(
            "Ticker da Debênture",
            placeholder="Ex: BRKM21, VALE25, PETR12",
            help="Digite o código do ativo conforme listado na ANBIMA/B3"
        ).strip().upper()
    
    with col2:
        periodo_dias = st.selectbox(
            "Período",
            options=[30, 90, 180, 365, 730],
            format_func=lambda x: {
                30: "30 dias",
                90: "3 meses",
                180: "6 meses",
                365: "1 ano",
                730: "2 anos"
            }.get(x, f"{x} dias"),
            index=3
        )
    
    if ticker_debenture:
        with st.spinner(f"Buscando dados de {ticker_debenture}..."):
            scraper = DebenturesScraper()
            df_debenture = scraper.get_precos_por_ativo(ticker_debenture, dias=periodo_dias)
        
        if not df_debenture.empty:
            # Gráfico do % PU da Curva
            st.plotly_chart(
                gerar_grafico_pu_curva(df_debenture),
                use_container_width=True,
                key="chart_pu_curva"
            )
            
            # Métricas resumo
            df_valid = df_debenture.dropna(subset=['% PU da Curva'])
            if not df_valid.empty:
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                ultimo_pu = df_valid.iloc[-1]['% PU da Curva']
                media_pu = df_valid['% PU da Curva'].mean()
                min_pu = df_valid['% PU da Curva'].min()
                max_pu = df_valid['% PU da Curva'].max()
                
                with col_m1:
                    delta_color = "normal" if ultimo_pu >= 100 else "inverse"
                    st.metric("Último % PU", f"{ultimo_pu:.2f}%", delta=f"{ultimo_pu - 100:.2f}%")
                with col_m2:
                    st.metric("Média", f"{media_pu:.2f}%")
                with col_m3:
                    st.metric("Mínimo", f"{min_pu:.2f}%")
                with col_m4:
                    st.metric("Máximo", f"{max_pu:.2f}%")
            
            # Tabela de dados
            with st.expander("📋 Ver dados brutos"):
                st.dataframe(
                    df_debenture[['Data', 'Emissor', 'Código do Ativo', 'PU Médio', '% PU da Curva', 'Quantidade', 'Número de Negócios']]
                    .sort_values('Data', ascending=False),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning(f"Nenhum dado encontrado para '{ticker_debenture}' no período selecionado.")
    else:
        st.caption("💡 Digite um ticker de debênture para visualizar o histórico.")
