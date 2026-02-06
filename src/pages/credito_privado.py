
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.data_loaders.idex import carregar_dados_idex, carregar_dados_idex_infra
from src.data_loaders.debentures import DebenturesScraper
from src.data_loaders.anbima import AnbimaScraper

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


def gerar_grafico_taxa_vs_duration(df):
    """Gera gráfico de dispersão Taxa Indicativa vs Duration."""
    if df.empty:
        return go.Figure().update_layout(title_text="Sem dados.")
    
    df_chart = df.dropna(subset=['Taxa_Indicativa', 'Duration'])
    
    if df_chart.empty:
        return go.Figure().update_layout(title_text="Sem dados válidos.")
    
    fig = px.scatter(
        df_chart,
        x='Duration',
        y='Taxa_Indicativa',
        color='Tipo',
        hover_data=['Código', 'Nome', 'Índice_Correção', 'PU'],
        title='Taxa Indicativa vs Duration por Tipo de Indexador',
        labels={
            'Duration': 'Duration (dias)',
            'Taxa_Indicativa': 'Taxa Indicativa (%)',
            'Tipo': 'Tipo'
        },
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig.update_layout(
        height=500,
        template='brokeberg',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    fig.update_traces(marker=dict(size=8, opacity=0.7))
    return fig


def gerar_grafico_distribuicao_tipo(df):
    """Gera gráfico de pizza da distribuição por tipo."""
    if df.empty or 'Tipo' not in df.columns:
        return go.Figure().update_layout(title_text="Sem dados.")
    
    tipo_counts = df['Tipo'].value_counts()
    fig = px.pie(
        values=tipo_counts.values,
        names=tipo_counts.index,
        title='Quantidade por Tipo de Indexador',
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig.update_layout(height=400, template='brokeberg')
    return fig


def gerar_grafico_histograma_taxas(df):
    """Gera histograma de taxas indicativas."""
    if df.empty or 'Taxa_Indicativa' not in df.columns:
        return go.Figure().update_layout(title_text="Sem dados.")
    
    df_valid = df.dropna(subset=['Taxa_Indicativa'])
    
    if df_valid.empty:
        return go.Figure().update_layout(title_text="Sem dados válidos.")
    
    fig = px.histogram(
        df_valid,
        x='Taxa_Indicativa',
        color='Tipo',
        nbins=30,
        title='Distribuição de Taxas Indicativas',
        labels={'Taxa_Indicativa': 'Taxa Indicativa (%)'},
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig.update_layout(height=400, template='brokeberg', barmode='stack')
    return fig


def render():
    st.header("Crédito Privado")
    
    # --- Seção do Screener ANBIMA ---
    st.subheader("📊 Screener de Debêntures ANBIMA")
    st.info(
        "Visualize dados de debêntures do mercado secundário com taxas indicativas, "
        "duration e spreads. Dados atualizados diariamente pela ANBIMA."
    )
    
    # Inicializar session state para dados do screener
    if 'anbima_data' not in st.session_state:
        st.session_state['anbima_data'] = None
    
    # Botão para carregar/atualizar dados
    if st.button("🔄 Gerar/Atualizar Screener", key="btn_screener_anbima"):
        with st.spinner("Carregando dados da ANBIMA..."):
            anbima_scraper = AnbimaScraper()
            df_anbima = anbima_scraper.get_latest()
            if not df_anbima.empty:
                st.session_state['anbima_data'] = df_anbima
                st.success(f"✅ Dados carregados | **Data:** {df_anbima['Data_Referência'].iloc[0]} | **Total:** {len(df_anbima)} debêntures")
            else:
                st.error("❌ Não foi possível carregar os dados da ANBIMA.")
    
    # Exibir dados se disponíveis
    if st.session_state['anbima_data'] is not None:
        df_anbima = st.session_state['anbima_data'].copy()
        
        # Filtros em colunas
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            tipos_disponiveis = ['Todos'] + sorted(df_anbima['Tipo'].unique().tolist())
            tipo_selecionado = st.selectbox("📌 Tipo de Indexador", tipos_disponiveis, key="filtro_tipo_anbima")
        
        with col_f2:
            codigo_busca = st.text_input("🔎 Buscar por Código", placeholder="Ex: VALE, PETR...", key="filtro_codigo_anbima")
        
        with col_f3:
            emissor_busca = st.text_input("🏢 Buscar por Emissor", placeholder="Ex: PETROBRAS...", key="filtro_emissor_anbima")
        
        # Aplicar filtros
        df_filtrado = df_anbima.copy()
        
        if tipo_selecionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Tipo'] == tipo_selecionado]
        
        if codigo_busca:
            df_filtrado = df_filtrado[df_filtrado['Código'].str.contains(codigo_busca.upper(), na=False)]
        
        if emissor_busca:
            df_filtrado = df_filtrado[df_filtrado['Nome'].str.contains(emissor_busca.upper(), na=False)]
        
        # Filtros de Duration e Taxa (em expander)
        with st.expander("⚙️ Filtros Avançados", expanded=False):
            col_adv1, col_adv2 = st.columns(2)
            
            with col_adv1:
                if 'Duration' in df_filtrado.columns and df_filtrado['Duration'].notna().any():
                    duration_min = float(df_filtrado['Duration'].min())
                    duration_max = float(df_filtrado['Duration'].max())
                    
                    if duration_min < duration_max:
                        duration_range = st.slider(
                            "⏱️ Duration (dias)",
                            min_value=int(duration_min),
                            max_value=int(duration_max),
                            value=(int(duration_min), int(duration_max)),
                            key="filtro_duration_anbima"
                        )
                        df_filtrado = df_filtrado[
                            (df_filtrado['Duration'] >= duration_range[0]) & 
                            (df_filtrado['Duration'] <= duration_range[1])
                        ]
            
            with col_adv2:
                if 'Taxa_Indicativa' in df_filtrado.columns and df_filtrado['Taxa_Indicativa'].notna().any():
                    taxa_min = float(df_filtrado['Taxa_Indicativa'].min())
                    taxa_max = float(df_filtrado['Taxa_Indicativa'].max())
                    
                    if taxa_min < taxa_max:
                        taxa_range = st.slider(
                            "📈 Taxa Indicativa (%)",
                            min_value=taxa_min,
                            max_value=taxa_max,
                            value=(taxa_min, taxa_max),
                            step=0.1,
                            key="filtro_taxa_anbima"
                        )
                        df_filtrado = df_filtrado[
                            (df_filtrado['Taxa_Indicativa'] >= taxa_range[0]) & 
                            (df_filtrado['Taxa_Indicativa'] <= taxa_range[1])
                        ]
        
        # Métricas principais
        st.markdown("#### 📊 Resumo")
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        
        with col_m1:
            st.metric("Total Filtrado", len(df_filtrado))
        
        with col_m2:
            if 'Taxa_Indicativa' in df_filtrado.columns:
                taxa_media = df_filtrado['Taxa_Indicativa'].mean()
                st.metric("Taxa Média", f"{taxa_media:.2f}%")
        
        with col_m3:
            if 'Duration' in df_filtrado.columns:
                duration_media = df_filtrado['Duration'].mean()
                st.metric("Duration Média", f"{duration_media:.0f} dias")
        
        with col_m4:
            if 'PU' in df_filtrado.columns:
                pu_medio = df_filtrado['PU'].mean()
                st.metric("PU Médio", f"R$ {pu_medio:,.2f}")
        
        with col_m5:
            if 'Perc_PU_Par' in df_filtrado.columns:
                pu_par_medio = df_filtrado['Perc_PU_Par'].mean()
                st.metric("% PU Par Médio", f"{pu_par_medio:.2f}%")
        
        # Tabs para visualização
        tab_tabela, tab_graficos, tab_dist = st.tabs(["📋 Tabela", "📈 Gráficos", "📊 Distribuição"])
        
        with tab_tabela:
            # Colunas para exibição
            display_cols = ['Código', 'Nome', 'Tipo', 'Vencimento', 'Índice_Correção', 
                           'Taxa_Indicativa', 'Taxa_Compra', 'Taxa_Venda', 'PU', 
                           'Perc_PU_Par', 'Duration', 'Desvio_Padrão']
            display_cols = [c for c in display_cols if c in df_filtrado.columns]
            
            # Ordenação
            col_order, order_asc = st.columns([3, 1])
            with col_order:
                ordem_por = st.selectbox("Ordenar por:", display_cols, index=display_cols.index('Taxa_Indicativa') if 'Taxa_Indicativa' in display_cols else 0, key="ordem_anbima")
            with order_asc:
                ordem_crescente = st.checkbox("Crescente", value=False, key="ordem_asc_anbima")
            
            df_display = df_filtrado[display_cols].sort_values(by=ordem_por, ascending=ordem_crescente)
            
            # Configuração de colunas
            column_config = {
                'Taxa_Indicativa': st.column_config.NumberColumn('Taxa Ind.', format="%.4f%%"),
                'Taxa_Compra': st.column_config.NumberColumn('Tx Compra', format="%.4f%%"),
                'Taxa_Venda': st.column_config.NumberColumn('Tx Venda', format="%.4f%%"),
                'PU': st.column_config.NumberColumn('PU', format="R$ %.2f"),
                'Perc_PU_Par': st.column_config.NumberColumn('% PU Par', format="%.2f%%"),
                'Duration': st.column_config.NumberColumn('Duration', format="%.0f"),
                'Desvio_Padrão': st.column_config.NumberColumn('Desvio Pad.', format="%.4f"),
            }
            
            st.dataframe(
                df_display,
                use_container_width=True,
                height=400,
                column_config=column_config,
                hide_index=True
            )
            
            # Download CSV
            csv = df_filtrado.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv,
                file_name=f"debentures_anbima_{df_anbima['Data_Referência'].iloc[0]}.csv",
                mime="text/csv",
                key="download_anbima"
            )
        
        with tab_graficos:
            st.plotly_chart(gerar_grafico_taxa_vs_duration(df_filtrado), use_container_width=True, key="chart_taxa_duration")
        
        with tab_dist:
            col_dist1, col_dist2 = st.columns(2)
            with col_dist1:
                st.plotly_chart(gerar_grafico_distribuicao_tipo(df_filtrado), use_container_width=True, key="chart_dist_tipo")
            with col_dist2:
                st.plotly_chart(gerar_grafico_histograma_taxas(df_filtrado), use_container_width=True, key="chart_hist_taxa")
    
    st.markdown("---")
    
    # --- Seção de Histórico de Debêntures ---
    st.subheader("📈 Histórico de Preços de Debêntures")
    st.info(
        "Consulte o histórico do **% PU da Curva** de debêntures específicas. "
        "Valores abaixo de 100% indicam negociação com desconto; acima de 100%, com prêmio."
    )
    
    scraper = DebenturesScraper()
    anbima_scraper = AnbimaScraper()
    
    # Linha 1: Período e Input Manual
    col_periodo, col_ticker = st.columns([1, 2])
    
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
    
    with col_ticker:
        ticker_input = st.text_input(
            "Digite os tickers (separados por vírgula)",
            placeholder="Ex: BRKM21, VALE25, RECV11",
            help="Digite um ou mais tickers separados por vírgula"
        )
    
    # Processar tickers
    if ticker_input:
        tickers_list = [t.strip().upper() for t in ticker_input.split(',') if t.strip()]
    else:
        tickers_list = []
    
    # Expander opcional para buscar lista de emissores recentes
    with st.expander("🔍 Buscar debêntures recentes (lista auxiliar)", expanded=False):
        if st.button("Carregar lista de emissores", key="btn_carregar_emissores"):
            with st.spinner("Carregando lista (pode demorar)..."):
                df_recentes = scraper.get_precos_ultimos_dias(dias=30)
                if not df_recentes.empty and 'Emissor' in df_recentes.columns:
                    df_recentes = df_recentes.dropna(subset=['Emissor', 'Código do Ativo'])
                    st.session_state['debentures_recentes'] = {
                        'emissores': sorted([e for e in df_recentes['Emissor'].unique() if isinstance(e, str)]),
                        'ativos_por_emissor': df_recentes.groupby('Emissor')['Código do Ativo'].apply(lambda x: sorted([a for a in x.unique() if isinstance(a, str)])).to_dict(),
                        'todos_ativos': sorted([a for a in df_recentes['Código do Ativo'].unique() if isinstance(a, str)])
                    }
                else:
                    st.warning("Não foi possível carregar a lista.")
        
        if 'debentures_recentes' in st.session_state and st.session_state['debentures_recentes'].get('emissores'):
            dados = st.session_state['debentures_recentes']
            emissor_sel = st.selectbox("Filtrar por Emissor", ["Todos"] + dados['emissores'], key="sel_emissor")
            
            if emissor_sel == "Todos":
                ativos = dados['todos_ativos']
            else:
                ativos = dados['ativos_por_emissor'].get(emissor_sel, [])
            
            tickers_aux = st.multiselect("Selecione debêntures", ativos, key="sel_tickers_aux")
            
            # Combinar com tickers manuais
            if tickers_aux:
                tickers_list = list(set(tickers_list + tickers_aux))
    
    if tickers_list:
        # Buscar dados de todas as debêntures selecionadas
        with st.spinner(f"Buscando dados de {len(tickers_list)} debênture(s)..."):
            dfs = []
            for ticker in tickers_list:
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
            if len(tickers_list) == 1:
                ticker_unico = tickers_list[0]
                # Filtrar apenas pelo ticker específico e ordenar por data
                df_valid = df_combined[df_combined['Código do Ativo'] == ticker_unico].dropna(subset=['% PU da Curva']).sort_values('Data')
                
                if not df_valid.empty:
                    ultimo_pu = df_valid.iloc[-1]['% PU da Curva']
                    ultima_data = df_valid.iloc[-1]['Data']
                    media_pu = df_valid['% PU da Curva'].mean()
                    min_pu = df_valid['% PU da Curva'].min()
                    max_pu = df_valid['% PU da Curva'].max()
                    
                    # Mostrar data de referência
                    st.caption(f"📅 Última negociação: **{ultima_data.strftime('%d/%m/%Y') if hasattr(ultima_data, 'strftime') else ultima_data}**")
                    
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    with col_m1:
                        st.metric("Último % PU", f"{ultimo_pu:.2f}%", delta=f"{ultimo_pu - 100:.2f}%")
                    with col_m2:
                        st.metric("Média", f"{media_pu:.2f}%")
                    with col_m3:
                        st.metric("Mínimo", f"{min_pu:.2f}%")
                    with col_m4:
                        st.metric("Máximo", f"{max_pu:.2f}%")
                    
                    # Buscar informações ANBIMA
                    st.markdown("#### 📋 Informações ANBIMA (Mercado Secundário)")
                    with st.spinner("Buscando dados da ANBIMA..."):
                        anbima_info = anbima_scraper.get_debenture_info(ticker_unico)
                    
                    if anbima_info:
                        # Primeira linha de métricas
                        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                        with col_a1:
                            taxa_ind = anbima_info.get('taxa_indicativa')
                            st.metric("Taxa Indicativa", f"{taxa_ind:.4f}%" if taxa_ind else "N/D")
                        with col_a2:
                            duration = anbima_info.get('duration')
                            st.metric("Duration", f"{duration:.0f} dias" if duration else "N/D")
                        with col_a3:
                            pu = anbima_info.get('pu')
                            st.metric("PU", f"R$ {pu:,.2f}" if pu else "N/D")
                        with col_a4:
                            pu_par = anbima_info.get('perc_pu_par')
                            st.metric("% PU Par", f"{pu_par:.2f}%" if pu_par else "N/D")
                        
                        # Segunda linha de métricas
                        col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                        with col_b1:
                            tipo = anbima_info.get('tipo')
                            st.metric("Tipo Indexador", tipo if tipo else "N/D")
                        with col_b2:
                            desvio = anbima_info.get('desvio_padrao')
                            st.metric("Desvio Padrão", f"{desvio:.4f}" if desvio else "N/D")
                        with col_b3:
                            int_min = anbima_info.get('intervalo_min')
                            int_max = anbima_info.get('intervalo_max')
                            if int_min and int_max:
                                st.metric("Intervalo", f"{int_min:.4f}% - {int_max:.4f}%")
                            else:
                                st.metric("Intervalo", "N/D")
                        with col_b4:
                            data_ref = anbima_info.get('data_referencia')
                            st.metric("Data Ref. ANBIMA", data_ref if data_ref else "N/D")
                        
                        # Informações adicionais em expander
                        with st.expander("ℹ️ Detalhes adicionais"):
                            st.write(f"**Código:** {anbima_info.get('codigo')}")
                            st.write(f"**Nome:** {anbima_info.get('nome')}")
                            st.write(f"**Vencimento:** {anbima_info.get('vencimento')}")
                            st.write(f"**Índice de Correção:** {anbima_info.get('indice_correcao')}")
                            if anbima_info.get('taxa_compra'):
                                st.write(f"**Taxa de Compra:** {anbima_info.get('taxa_compra'):.4f}%")
                            if anbima_info.get('taxa_venda'):
                                st.write(f"**Taxa de Venda:** {anbima_info.get('taxa_venda'):.4f}%")
                            if anbima_info.get('ref_ntn_b'):
                                st.write(f"**Ref. NTN-B:** {anbima_info.get('ref_ntn_b')}")
                    else:
                        st.warning(f"Debênture {ticker_unico} não encontrada nos dados ANBIMA mais recentes.")
                        
                        # Fallback: mostrar características do debentures.com.br
                        st.markdown("#### 📋 Características (debentures.com.br)")
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
            else:
                # Múltiplas debêntures - mostrar resumo em tabela
                st.markdown("#### 📊 Resumo das Debêntures Selecionadas")
                resumo_data = []
                for ticker in tickers_list:
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

