
import streamlit as st
import pandas as pd
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

def gerar_grafico_taxa_indicativa(df, tipo_remuneracao, taxa_base):
    """Gera gráfico do histórico da taxa indicativa."""
    if df.empty or '% PU da Curva' not in df.columns or taxa_base is None:
        return go.Figure().update_layout(title_text="Sem dados para taxa indicativa.")
    
    df = df.dropna(subset=['% PU da Curva']).copy()
    
    if df.empty:
        return go.Figure().update_layout(title_text="Sem dados válidos.")
    
    # Calcular taxa indicativa para cada ponto: taxa_base * (100 / % PU)
    df['Taxa Indicativa'] = df['% PU da Curva'].apply(
        lambda pu: taxa_base * (100 / pu) if pu > 0 else None
    )
    
    df = df.dropna(subset=['Taxa Indicativa']).sort_values('Data')
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['Data'],
        y=df['Taxa Indicativa'],
        mode='lines+markers',
        name='Taxa Indicativa',
        marker=dict(size=6, color='#636EFA'),
        line=dict(width=2, color='#636EFA'),
        fill='tozeroy',
        fillcolor='rgba(99, 110, 250, 0.1)',
        hovertemplate='%{x|%d/%m/%Y}<br>%{y:.4f}%<extra></extra>'
    ))
    
    # Linha de referência na taxa base
    fig.add_hline(
        y=taxa_base,
        line_dash="dash",
        line_color="green",
        annotation_text=f"Taxa Base ({taxa_base:.4f}%)",
        annotation_position="top right"
    )
    
    titulo = f"Histórico da Taxa Indicativa ({tipo_remuneracao} + Spread)" if tipo_remuneracao else "Histórico da Taxa Indicativa"
    
    fig.update_layout(
        title=titulo,
        title_x=0,
        xaxis_title='Data',
        yaxis_title='Taxa Indicativa (%)',
        template='brokeberg',
        hovermode='x unified',
        showlegend=False
    )
    
    return fig

def render():
    st.header("Crédito Privado")
    
    # --- Seção de Histórico de Debêntures (PRIMEIRO) ---
    st.subheader("📈 Histórico de Preços de Debêntures")
    st.info(
        "Consulte o histórico do **% PU da Curva** de debêntures específicas. "
        "Valores abaixo de 100% indicam negociação com desconto; acima de 100%, com prêmio."
    )
    
    scraper = DebenturesScraper()
    
    # Carregar lista de emissores/ativos recentes (cache para sessão)
    if 'debentures_recentes' not in st.session_state:
        with st.spinner("Carregando lista de debêntures recentes..."):
            df_recentes = scraper.get_precos_ultimos_dias(dias=60)
            if not df_recentes.empty:
                emissores = sorted(df_recentes['Emissor'].unique().tolist())
                ativos_por_emissor = df_recentes.groupby('Emissor')['Código do Ativo'].apply(lambda x: sorted(x.unique().tolist())).to_dict()
                st.session_state['debentures_recentes'] = {
                    'emissores': emissores,
                    'ativos_por_emissor': ativos_por_emissor,
                    'todos_ativos': sorted(df_recentes['Código do Ativo'].unique().tolist())
                }
            else:
                st.session_state['debentures_recentes'] = {'emissores': [], 'ativos_por_emissor': {}, 'todos_ativos': []}
    
    dados_recentes = st.session_state['debentures_recentes']
    
    # Linha 1: Período e Filtro Emissor
    col_periodo, col_emissor = st.columns([1, 2])
    
    with col_periodo:
        periodo_dias = st.selectbox(
            "Período",
            options=[30, 90, 180, 365, 730, 1825, 3650],
            format_func=lambda x: {
                30: "30 dias",
                90: "3 meses",
                180: "6 meses",
                365: "1 ano",
                730: "2 anos",
                1825: "5 anos",
                3650: "Máximo (10 anos)"
            }.get(x, f"{x} dias"),
            index=6
        )
    
    with col_emissor:
        emissor_selecionado = st.selectbox(
            "Filtrar por Emissor (opcional)",
            options=["Todos"] + dados_recentes.get('emissores', []),
            index=0,
            help="Filtre para ver apenas debêntures de um emissor específico"
        )
    
    # Determinar lista de ativos disponíveis
    if emissor_selecionado == "Todos":
        ativos_disponiveis = dados_recentes.get('todos_ativos', [])
    else:
        ativos_disponiveis = dados_recentes.get('ativos_por_emissor', {}).get(emissor_selecionado, [])
    
    # Linha 2: Seleção de Debêntures (multiselect)
    col_select, col_manual = st.columns([3, 1])
    
    with col_select:
        tickers_selecionados = st.multiselect(
            "Selecione Debêntures",
            options=ativos_disponiveis,
            default=[],
            help="Selecione uma ou mais debêntures para comparar"
        )
    
    with col_manual:
        ticker_manual = st.text_input(
            "Ou digite manualmente",
            placeholder="Ex: BRKM21",
            help="Digite um ticker não listado"
        ).strip().upper()
    
    # Combinar seleções
    todos_tickers = list(set(tickers_selecionados + ([ticker_manual] if ticker_manual else [])))
    
    if todos_tickers:
        # Buscar dados de todas as debêntures selecionadas
        with st.spinner(f"Buscando dados de {len(todos_tickers)} debênture(s)..."):
            dfs = []
            for ticker in todos_tickers:
                df_ticker = scraper.get_precos_por_ativo(ticker, dias=periodo_dias)
                if not df_ticker.empty:
                    dfs.append(df_ticker)
            
            if dfs:
                df_combined = pd.concat(dfs, ignore_index=True)
            else:
                df_combined = pd.DataFrame()
        
        if not df_combined.empty:
            # Gráfico do % PU da Curva (múltiplas séries)
            st.plotly_chart(
                gerar_grafico_pu_curva(df_combined),
                use_container_width=True,
                key="chart_pu_curva"
            )
            
            # Métricas e características apenas para seleção única
            if len(todos_tickers) == 1:
                ticker_unico = todos_tickers[0]
                df_valid = df_combined.dropna(subset=['% PU da Curva'])
                
                if not df_valid.empty:
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    ultimo_pu = df_valid.iloc[-1]['% PU da Curva']
                    media_pu = df_valid['% PU da Curva'].mean()
                    min_pu = df_valid['% PU da Curva'].min()
                    max_pu = df_valid['% PU da Curva'].max()
                    
                    with col_m1:
                        st.metric("Último % PU", f"{ultimo_pu:.2f}%", delta=f"{ultimo_pu - 100:.2f}%")
                    with col_m2:
                        st.metric("Média", f"{media_pu:.2f}%")
                    with col_m3:
                        st.metric("Mínimo", f"{min_pu:.2f}%")
                    with col_m4:
                        st.metric("Máximo", f"{max_pu:.2f}%")
                    
                    # Características e Taxa Indicativa
                    st.markdown("#### 📋 Características e Taxa Indicativa")
                    with st.spinner("Buscando características..."):
                        taxa_info = scraper.calcular_taxa_indicativa(ticker_unico, ultimo_pu)
                    
                    if taxa_info.get('erro'):
                        st.warning(f"Não foi possível obter características: {taxa_info['erro']}")
                    else:
                        col_c1, col_c2, col_c3 = st.columns(3)
                        with col_c1:
                            st.metric("Tipo de Remuneração", taxa_info.get('tipo_remuneracao', 'N/D'))
                        with col_c2:
                            taxa_base = taxa_info.get('taxa_base')
                            st.metric("Taxa/Spread Base", f"{taxa_base:.4f}%" if taxa_base else "N/D")
                        with col_c3:
                            taxa_ind = taxa_info.get('taxa_indicativa')
                            st.metric(
                                "Taxa Indicativa", 
                                f"{taxa_ind:.4f}%" if taxa_ind else "N/D",
                                help="Taxa ajustada pelo % PU da Curva atual"
                            )
                        
                        if taxa_info.get('descricao'):
                            st.success(f"**Taxa Indicativa Atual:** {taxa_info['descricao']}")
                        
                        # Gráfico histórico de taxa indicativa
                        st.plotly_chart(
                            gerar_grafico_taxa_indicativa(
                                df_valid, 
                                taxa_info.get('tipo_remuneracao'),
                                taxa_info.get('taxa_base')
                            ),
                            use_container_width=True,
                            key="chart_taxa_indicativa"
                        )
            else:
                # Múltiplas debêntures - mostrar resumo em tabela
                st.markdown("#### 📊 Resumo das Debêntures Selecionadas")
                resumo_data = []
                for ticker in todos_tickers:
                    df_ticker = df_combined[df_combined['Código do Ativo'] == ticker].dropna(subset=['% PU da Curva'])
                    if not df_ticker.empty:
                        ultimo = df_ticker.iloc[-1]['% PU da Curva']
                        emissor = df_ticker.iloc[-1].get('Emissor', 'N/D')
                        resumo_data.append({
                            'Ticker': ticker,
                            'Emissor': emissor,
                            'Último % PU': f"{ultimo:.2f}%",
                            'Vs. Par': f"{ultimo - 100:+.2f}%"
                        })
                
                if resumo_data:
                    st.dataframe(pd.DataFrame(resumo_data), use_container_width=True, hide_index=True)
            
            # Tabela de dados
            with st.expander("📋 Ver dados brutos"):
                st.dataframe(
                    df_combined[['Data', 'Emissor', 'Código do Ativo', 'PU Médio', '% PU da Curva', 'Quantidade', 'Número de Negócios']]
                    .sort_values('Data', ascending=False),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning(f"Nenhum dado encontrado para os tickers selecionados no período.")
    else:
        st.caption("💡 Selecione uma ou mais debêntures para visualizar o histórico.")
    
    st.markdown("---")
    
    # --- IDEX JGP (em expander, carrega sob demanda) ---
    with st.expander("📊 IDEX JGP - Indicador de Crédito Privado (Spread/CDI)", expanded=False):
        st.info(
            "O IDEX-CDI mostra o spread médio (prêmio acima do CDI) exigido pelo mercado para comprar debêntures. "
            "Filtramos emissores que passaram por eventos de crédito relevantes."
        )
        if st.button("Carregar IDEX-CDI", key="btn_idex_cdi"):
            with st.spinner("Carregando dados do IDEX-CDI..."):
                df_idex = carregar_dados_idex()
            if not df_idex.empty:
                st.plotly_chart(gerar_grafico_idex(df_idex), use_container_width=True, key="chart_idex")
            else:
                st.warning("Não foi possível carregar os dados do IDEX-CDI.")

    # --- IDEX INFRA (em expander, carrega sob demanda) ---
    with st.expander("📊 IDEX INFRA - Debêntures de Infraestrutura (Spread/NTN-B)", expanded=False):
        st.info(
            "O IDEX-INFRA mede o spread médio de debêntures incentivadas em relação aos títulos públicos de referência (NTN-Bs)."
        )
        if st.button("Carregar IDEX INFRA", key="btn_idex_infra"):
            with st.spinner("Carregando dados do IDEX INFRA..."):
                df_idex_infra = carregar_dados_idex_infra()
            if not df_idex_infra.empty:
                st.plotly_chart(gerar_grafico_idex_infra(df_idex_infra), use_container_width=True, key="chart_idex_infra")
            else:
                st.warning("Não foi possível carregar os dados do IDEX INFRA.")

