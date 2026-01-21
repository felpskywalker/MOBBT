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
from src.components.charts_gex import create_market_gamma_chart, create_metrics_panel, calculate_metrics


def get_spot_price(ticker: str) -> float:
    """Obtém o preço atual do ativo via yfinance."""
    try:
        yahoo_ticker = f"{ticker}.SA" if not ticker.endswith(".SA") else ticker
        stock = yf.Ticker(yahoo_ticker)
        hist = stock.history(period="1d")
        
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        
        # Fallback
        info = stock.info
        return float(info.get('regularMarketPrice', info.get('previousClose', 0)))
    except Exception as e:
        st.warning(f"Erro ao buscar preço: {e}")
        return 0.0


def get_last_trading_date() -> str:
    """Obtém a última data de pregão."""
    today = datetime.now()
    trading_date = today - timedelta(days=1)
    
    while trading_date.weekday() >= 5:  # Saturday=5, Sunday=6
        trading_date = trading_date - timedelta(days=1)
    
    return trading_date.strftime('%d/%m/%Y')


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
    col1, col2, col3 = st.columns([1, 1, 2])
    
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
        calcular = st.button("🔄 Calcular GEX", type="primary", use_container_width=True)
    
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
                options_df = parse_opcoes_net_data(raw_data)
            except Exception as e:
                st.error(f"❌ Erro ao buscar opções: {e}")
                st.info("💡 O scraping pode estar bloqueado ou o site indisponível.")
                return
        
        if options_df.empty:
            st.warning(f"⚠️ Nenhuma opção encontrada para {ticker}.")
            return
        
        # Estatísticas das opções
        st.success(f"✅ Encontradas **{len(options_df)}** opções")
        
        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
        with col_stats1:
            st.metric("Total Opções", len(options_df))
        with col_stats2:
            st.metric("CALLs", len(options_df[options_df['type'] == 'CALL']))
        with col_stats3:
            st.metric("PUTs", len(options_df[options_df['type'] == 'PUT']))
        with col_stats4:
            st.metric("Strikes Únicos", options_df['strike'].nunique())
        
        with st.spinner("Calculando GEX..."):
            try:
                gex_df = calculate_gex_dataframe(options_df, spot_price, fetch_prices=False)
                gex_by_strike = aggregate_gex_by_strike(gex_df, bucket_size=bucket_size)
            except Exception as e:
                st.error(f"❌ Erro ao calcular GEX: {e}")
                return
        
        if gex_by_strike.empty:
            st.warning("⚠️ Não foi possível calcular GEX.")
            return
        
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
            # Gamma Score gauge
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
        
        # Gráfico principal
        try:
            title = f"Market Gamma - {ticker} ({reference_date})"
            fig = create_market_gamma_chart(gex_by_strike, spot_price, title)
            st.plotly_chart(fig, use_container_width=True, key="gex_main_chart")
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
            if not options_df.empty:
                cols_show = ['ticker', 'type', 'strike', 'expiry', 'iv', 'open_interest', 'market_price']
                cols_available = [c for c in cols_show if c in options_df.columns]
                df_opts = options_df[cols_available].copy()
                
                # Formatar
                if 'strike' in df_opts.columns:
                    df_opts['strike'] = df_opts['strike'].apply(lambda x: f"R$ {x:.2f}")
                if 'iv' in df_opts.columns:
                    df_opts['iv'] = df_opts['iv'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")
                if 'expiry' in df_opts.columns:
                    df_opts['expiry'] = df_opts['expiry'].apply(
                        lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else "-"
                    )
                
                st.dataframe(df_opts, hide_index=True, use_container_width=True, height=400)
    
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
