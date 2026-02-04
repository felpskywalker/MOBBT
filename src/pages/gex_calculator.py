"""
Página de Análise de GEX (Gamma Exposure) - BOVA11
Calcula e visualiza a exposição gamma dos dealers de opções.
"""

import streamlit as st
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

from src.data_loaders.opcoes_net import fetch_opcoes_net_data, parse_opcoes_net_data
from src.models.gex_calculator import calculate_gex_dataframe, aggregate_gex_by_strike, get_selic_rate
from src.components.charts_gex import create_market_gamma_chart, create_metrics_panel, calculate_metrics, create_open_interest_chart, create_cumulative_gex_chart, create_oi_by_expiry_chart
from src.models.put_utils import get_asset_price_yesterday


def get_spot_price(ticker: str, use_cache: bool = True) -> float:
    """Obtém o preço de fechamento do último pregão (D-1) do ativo.
    
    Usa get_asset_price_yesterday que é mais confiável e tem cache do Streamlit,
    evitando problemas de rate limit do yfinance.
    """
    return get_asset_price_yesterday(ticker)


def get_last_trading_date() -> str:
    """Obtém a última data de pregão."""
    today = datetime.now()
    trading_date = today - timedelta(days=1)
    
    while trading_date.weekday() >= 5:  # Saturday=5, Sunday=6
        trading_date = trading_date - timedelta(days=1)
    
    return trading_date.strftime('%d/%m/%Y')


def render_gex_charts(options_df: pd.DataFrame, spot_price: float, ticker: str, 
                      bucket_size: float, selected_expiry=None):
    """Renderiza os gráficos e métricas de GEX.
    
    Args:
        options_df: DataFrame com todas as opções
        spot_price: Preço spot do ativo  
        ticker: Ticker do ativo
        bucket_size: Tamanho do bucket para agregação
        selected_expiry: Data de vencimento selecionada (None = todos)
    """
    # Filtrar por vencimento se selecionado
    if selected_expiry is not None:
        filtered_df = options_df[options_df['expiry'] == selected_expiry].copy()
        expiry_label = selected_expiry.strftime('%d/%m/%Y')
    else:
        filtered_df = options_df.copy()
        expiry_label = "Todos"
    
    if filtered_df.empty:
        st.warning("⚠️ Nenhuma opção encontrada para este vencimento.")
        return
    
    # Estatísticas das opções filtradas
    col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
    with col_stats1:
        st.metric("Total Opções", len(filtered_df))
    with col_stats2:
        st.metric("CALLs", len(filtered_df[filtered_df['type'] == 'CALL']))
    with col_stats3:
        st.metric("PUTs", len(filtered_df[filtered_df['type'] == 'PUT']))
    with col_stats4:
        st.metric("Strikes Únicos", filtered_df['strike'].nunique())
    
    # Calcular GEX
    try:
        gex_df = calculate_gex_dataframe(filtered_df, spot_price, fetch_prices=False)
        gex_by_strike = aggregate_gex_by_strike(gex_df, bucket_size=bucket_size)
    except Exception as e:
        st.error(f"❌ Erro ao calcular GEX: {e}")
        return
    
    if gex_by_strike.empty:
        st.warning("⚠️ Não foi possível calcular GEX.")
        return
    
    # Debug: Show IV statistics
    with st.expander("🔍 Debug: Estatísticas de IV e Gamma"):
        if 'gamma_source' in gex_df.columns:
            st.subheader("📐 Fonte do Gamma")
            gamma_col1, gamma_col2 = st.columns(2)
            with gamma_col1:
                from_site = (gex_df['gamma_source'] == 'SITE').sum()
                st.metric("Gamma do Opcoes.net", f"{from_site}")
            with gamma_col2:
                from_calc = (gex_df['gamma_source'] == 'CALCULATED').sum()
                st.metric("Gamma Calculado (BS)", f"{from_calc}")
            st.markdown("---")
        
        st.subheader("📊 Fonte da IV")
        if 'iv' in gex_df.columns and 'iv_source' in gex_df.columns:
            iv_stats_col1, iv_stats_col2, iv_stats_col3 = st.columns(3)
            with iv_stats_col1:
                source_count = (gex_df['iv_source'] == 'SOURCE').sum()
                st.metric("IV da Fonte", f"{source_count}")
            with iv_stats_col2:
                nearest_count = (gex_df['iv_source'] == 'NEAREST').sum()
                st.metric("IV Nearest Strike", f"{nearest_count}")
            with iv_stats_col3:
                default_count = (gex_df['iv_source'] == 'DEFAULT').sum()
                st.metric("IV Default (22%)", f"{default_count}")
            
            zero_iv = gex_df[(gex_df['iv'].isna()) | (gex_df['iv'] <= 0.001)]
            if len(zero_iv) > 0:
                st.warning(f"⚠️ {len(zero_iv)} opções ainda sem IV válido")
                st.dataframe(zero_iv[['ticker', 'type', 'strike', 'iv', 'open_interest']].head(10))
            else:
                st.success("✅ Todas as opções têm IV válido!")
            
            valid_ivs = gex_df[gex_df['iv'] > 0.001]['iv']
            if len(valid_ivs) > 0:
                st.info(f"📊 IV Range: {valid_ivs.min()*100:.1f}% - {valid_ivs.max()*100:.1f}% | Média: {valid_ivs.mean()*100:.1f}%")
    
    reference_date = get_last_trading_date()
    
    # Visualização
    st.markdown("---")
    st.subheader("📈 Market Gamma Dashboard")
    
    # Calcular métricas
    metrics = calculate_metrics(gex_by_strike, spot_price)
    
    # Painel de métricas
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    
    gamma_score = metrics.get('gamma_score', 0)
    gamma_atual = metrics.get('gamma_atual', 0)
    flip_point = metrics.get('flip_point', spot_price)
    gamma_min = metrics.get('gamma_min_negativo', 0)
    gamma_max = metrics.get('gamma_max_positivo', 0)
    
    with col_m1:
        score_color = "🟢" if gamma_score > 0.3 else ("🔴" if gamma_score < -0.3 else "🟡")
        st.metric("Gamma Score", f"{score_color} {gamma_score:.2f}")
    
    with col_m2:
        if abs(gamma_atual) >= 1e6:
            gamma_str = f"{gamma_atual/1e6:.1f}M"
        elif abs(gamma_atual) >= 1e3:
            gamma_str = f"{gamma_atual/1e3:.1f}k"
        else:
            gamma_str = f"{gamma_atual:.0f}"
        st.metric("Gamma Atual", gamma_str)
    
    with col_m3:
        diff_flip = flip_point - spot_price
        st.metric("Flip Point", f"R$ {flip_point:.2f}", delta=f"{diff_flip:+.2f}")
    
    with col_m4:
        st.metric("Gamma Mín (Neg)", f"R$ {gamma_min:.2f}")
    
    with col_m5:
        st.metric("Gamma Máx (Pos)", f"R$ {gamma_max:.2f}")
    
    # Interpretação
    if spot_price > flip_point:
        st.success("📈 **Regime Positivo**: Spot acima do Flip Point. Mercado tende a ser mais estável.")
    else:
        st.warning("📉 **Regime Negativo**: Spot abaixo do Flip Point. Mercado tende a ser mais volátil.")
    
    # Gráficos
    try:
        title = f"Total GEX - {ticker} ({expiry_label})"
        fig_gex = create_market_gamma_chart(gex_by_strike, spot_price, title)
        st.plotly_chart(fig_gex, use_container_width=True, key=f"gex_main_chart_{expiry_label}")
        
        title = f"GEX Cumulativo - {ticker} ({expiry_label})"
        fig_cum_gex = create_cumulative_gex_chart(gex_by_strike, spot_price, title)
        st.plotly_chart(fig_cum_gex, use_container_width=True, key=f"gex_cumulative_chart_{expiry_label}")
        
        title = f"Open Interest - {ticker} ({expiry_label})"
        fig_oi = create_open_interest_chart(filtered_df, spot_price, title, bucket_size)
        st.plotly_chart(fig_oi, use_container_width=True, key=f"oi_main_chart_{expiry_label}")
    except Exception as e:
        st.error(f"❌ Erro ao gerar gráfico: {e}")
    
    # Estatísticas resumidas
    st.markdown("---")
    col_sum1, col_sum2, col_sum3 = st.columns(3)
    
    total_gex = gex_by_strike['total_gex'].sum()
    total_call = gex_by_strike['call_gex'].sum()
    total_put = gex_by_strike['put_gex'].sum()
    
    with col_sum1:
        st.metric("GEX Total", f"R$ {total_gex:,.0f}")
    with col_sum2:
        st.metric("GEX CALLs", f"R$ {total_call:,.0f}")
    with col_sum3:
        st.metric("GEX PUTs", f"R$ {total_put:,.0f}")
    
    # IV Média Ponderada
    if 'iv' in gex_df.columns and 'open_interest' in gex_df.columns:
        total_oi = gex_df['open_interest'].sum()
        if total_oi > 0:
            weighted_iv = (gex_df['iv'] * gex_df['open_interest']).sum() / total_oi
            st.info(f"📊 **IV Média Ponderada (por OI):** {weighted_iv*100:.2f}%")
    
    # Tabela detalhada
    with st.expander("📋 Dados Detalhados por Strike"):
        df_display = gex_by_strike.copy()
        df_display['strike'] = df_display['strike'].apply(lambda x: f"R$ {x:.2f}")
        df_display['total_gex'] = df_display['total_gex'].apply(lambda x: f"{x:,.0f}")
        df_display['call_gex'] = df_display['call_gex'].apply(lambda x: f"{x:,.0f}")
        df_display['put_gex'] = df_display['put_gex'].apply(lambda x: f"{x:,.0f}")
        df_display.columns = ['Strike', 'GEX Total', 'GEX CALL', 'GEX PUT']
        st.dataframe(df_display, hide_index=True, use_container_width=True)
    
    # Dados brutos das opções
    with st.expander("📋 Todas as Opções Carregadas"):
        if not filtered_df.empty:
            cols_show = ['ticker', 'type', 'strike', 'expiry', 'iv', 'open_interest', 'market_price']
            cols_available = [c for c in cols_show if c in filtered_df.columns]
            df_opts = filtered_df[cols_available].copy()
            
            if 'strike' in df_opts.columns:
                df_opts['strike'] = df_opts['strike'].apply(lambda x: f"R$ {x:.2f}")
            if 'iv' in df_opts.columns:
                df_opts['iv'] = df_opts['iv'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")
            if 'expiry' in df_opts.columns:
                df_opts['expiry'] = df_opts['expiry'].apply(
                    lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else "-"
                )
            
            st.dataframe(df_opts, hide_index=True, use_container_width=True, height=400)


def render():
    """Renderiza a página de GEX Calculator."""
    st.header("📊 GEX Calculator - Gamma Exposure")
    
    with st.expander("ℹ️ **O que é GEX (Gamma Exposure)?**", expanded=False):
        st.markdown("""
        ### Gamma Exposure (GEX)
        
        O **GEX** mede a exposição gamma agregada dos dealers de opções em cada strike. 
        É uma ferramenta poderosa para entender onde estão os "suportes e resistências" 
        criados pelo posicionamento dos market makers.
        
        #### Interpretação:
        
        📈 **GEX Positivo (acima do Spot)**:
        - Dealers comprados em gamma
        - Mercado tende a ser **mais estável**
        - Dealers hedgeam vendendo nas altas e comprando nas baixas (amortece movimento)
        
        📉 **GEX Negativo (abaixo do Spot)**:
        - Dealers vendidos em gamma
        - Mercado tende a ser **mais volátil**
        - Dealers hedgeam comprando nas altas e vendendo nas baixas (amplifica movimento)
        
        #### Métricas Importantes:
        
        - **Gamma Score**: Pontuação normalizada de -1 a +1
        - **Flip Point**: Preço onde o GEX muda de positivo para negativo
        - **Gamma Atual**: Exposição gamma no preço spot atual
        """)
    
    st.markdown("---")
    
    # Controles
    col1, col2, col3 = st.columns([1.5, 1, 1.5])
    
    with col1:
        ticker = st.text_input(
            "Ativo", 
            value="BOVA11",
            help="Digite o ticker do ativo (ex: BOVA11, PETR4, VALE3)"
        )
    
    with col2:
        bucket_size = st.selectbox(
            "Agregação de Strikes",
            options=[0.5, 1.0, 2.0, 5.0],
            index=1,
            format_func=lambda x: f"R$ {x:.2f}",
            help="Tamanho do bucket para agregar strikes"
        )
    
    with col3:
        st.write("")  # Espaçamento
        st.write("")
        calcular = st.button("🔄 Calcular", type="primary", use_container_width=True)
    
    # Inicializar session_state
    if 'gex_options_df' not in st.session_state:
        st.session_state.gex_options_df = None
    if 'gex_spot_price' not in st.session_state:
        st.session_state.gex_spot_price = None
    if 'gex_ticker' not in st.session_state:
        st.session_state.gex_ticker = None
    if 'gex_bucket_size' not in st.session_state:
        st.session_state.gex_bucket_size = None
    
    if calcular:
        with st.spinner(f"Obtendo preço de {ticker}..."):
            spot_price = get_spot_price(ticker)
        
        if spot_price <= 0:
            st.error(f"❌ Não foi possível obter o preço de {ticker}. Verifique o ticker.")
            return
        
        st.info(f"💰 **Spot Price:** R$ {spot_price:.2f}")
        
        with st.spinner(f"Buscando opções de {ticker} em opcoes.net.br..."):
            try:
                raw_data = fetch_opcoes_net_data(ticker)
                
                if raw_data:
                    st.info(f"📊 Dados brutos: {len(raw_data)} linhas extraídas")
                    with st.expander("🔍 Debug: Amostra dos dados brutos (primeiras 3 linhas)"):
                        import json
                        st.code(json.dumps(raw_data[:3], indent=2, ensure_ascii=False))
                else:
                    st.warning(f"⚠️ Nenhum dado bruto extraído do site")
                
                options_df = parse_opcoes_net_data(raw_data)
                
                if raw_data and options_df.empty:
                    st.warning("⚠️ Dados foram extraídos mas filtrados na validação")
                    
            except Exception as e:
                st.error(f"❌ Erro ao buscar opções: {e}")
                import traceback
                st.code(traceback.format_exc())
                st.info("💡 O scraping pode estar bloqueado ou o site indisponível.")
                return
        
        if options_df.empty:
            st.warning(f"⚠️ Nenhuma opção encontrada para {ticker}.")
            return
        
        st.success(f"✅ Encontradas **{len(options_df)}** opções")
        
        # Armazenar dados no session_state
        st.session_state.gex_options_df = options_df
        st.session_state.gex_spot_price = spot_price
        st.session_state.gex_ticker = ticker
        st.session_state.gex_bucket_size = bucket_size
    
    # Se temos dados carregados, mostrar seletor de vencimento e gráficos
    if st.session_state.gex_options_df is not None:
        options_df = st.session_state.gex_options_df
        spot_price = st.session_state.gex_spot_price
        stored_ticker = st.session_state.gex_ticker
        stored_bucket = st.session_state.gex_bucket_size
        
        # Extrair vencimentos disponíveis
        expiries = sorted(options_df['expiry'].dropna().unique())
        
        if len(expiries) > 0:
            st.markdown("---")
            
            # Gráfico de OI por Vencimento (sempre mostra todos os vencimentos)
            st.subheader("📊 Open Interest por Vencimento")
            try:
                fig_oi_expiry = create_oi_by_expiry_chart(
                    options_df, 
                    title=f"Open Interest por Vencimento - {stored_ticker}"
                )
                st.plotly_chart(fig_oi_expiry, use_container_width=True, key="oi_by_expiry_chart")
            except Exception as e:
                st.error(f"❌ Erro ao gerar gráfico de OI por vencimento: {e}")
            
            st.markdown("---")
            
            # Criar opções para o dropdown
            expiry_options = ["📅 Todos os vencimentos"] + [
                exp.strftime('%d/%m/%Y') for exp in expiries
            ]
            
            # Dropdown para selecionar vencimento
            col_exp1, col_exp2 = st.columns([2, 3])
            with col_exp1:
                selected_expiry_str = st.selectbox(
                    "Vencimento",
                    options=expiry_options,
                    index=1,  # Default: primeiro vencimento (mais próximo)
                    help="Selecione o vencimento para filtrar os gráficos. O mais próximo é selecionado por padrão."
                )
            
            with col_exp2:
                # Mostrar dias úteis até vencimento
                if selected_expiry_str != "📅 Todos os vencimentos":
                    selected_date = datetime.strptime(selected_expiry_str, '%d/%m/%Y')
                    days_to_exp = (selected_date.date() - datetime.now().date()).days
                    st.info(f"⏱️ **{days_to_exp}** dias até o vencimento")
            
            # Converter seleção para objeto datetime ou None
            if selected_expiry_str == "📅 Todos os vencimentos":
                selected_expiry = None
            else:
                selected_expiry = datetime.strptime(selected_expiry_str, '%d/%m/%Y')
                # Encontrar o timestamp correspondente no DataFrame
                for exp in expiries:
                    if exp.strftime('%d/%m/%Y') == selected_expiry_str:
                        selected_expiry = exp
                        break
            
            # Renderizar gráficos com filtro
            render_gex_charts(
                options_df=options_df,
                spot_price=spot_price,
                ticker=stored_ticker,
                bucket_size=stored_bucket,
                selected_expiry=selected_expiry
            )
        else:
            st.warning("⚠️ Nenhum vencimento encontrado nos dados.")
    
    else:
        # Placeholder quando ainda não calculou
        st.info("👆 Clique em **Calcular GEX** para iniciar a análise.")
        
        st.markdown("""
        ### Como Funciona:
        
        1. **Coleta de Dados**: Buscamos opções do ativo em [opcoes.net.br](https://opcoes.net.br)
        2. **Cálculo de Greeks**: Calculamos o Gamma de cada opção via Black-Scholes
        3. **Agregação GEX**: Somamos o GEX (Gamma × OI × Spot²) por strike
        4. **Visualização**: Gráfico estilo Market Gamma com métricas chave
        
        > ⚠️ **Nota**: A primeira execução pode demorar ~30s devido ao web scraping.
        """)
