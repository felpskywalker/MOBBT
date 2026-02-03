"""
Screener de PUT - Ações Líquidas (opcoes.net)
=============================================
Monitora opções PUT das ações mais líquidas com yields, gregas e indicadores fractais.
Fonte de dados: opcoes.net.br
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

from src.models.put_utils import (
    get_selic_annual, get_third_friday,
    get_asset_price_yesterday
)
from src.data_loaders.opcoes_net import get_put_options_for_screener
from src.models.black_scholes import implied_volatility, calculate_greeks
from src.models.fractal_analytics import (
    calculate_hurst_exponent, get_hurst_interpretation,
    prob_exercise_bs, prob_exercise_fractal, calculate_historical_volatility,
    check_trend_filters, get_recommendation, calculate_iv_rank
)


# Lista de ações mais líquidas
LIQUID_TICKERS = [
    "VALE3", "PETR4", "MGLU3", "BBAS3", "BRAV3", "ITUB4", "B3SA3", 
    "BBDC4", "PRIO3", "RECV3", "ABEV3", "BPAC11", "ITSA4", "WEGE3", 
    "SUZB3", "BBSE3", "RAIZ4", "HAPV3", "CSAN3", "USIM5", "CSNA3",
    "GGBR4", "RENT3", "RAIL3", "BEEF3"
]

# Range de strikes em % do spot (ITM/OTM)
STRIKE_RANGE_PCT = 5.0


def scan_single_ticker(ticker: str, expiry: date, selic_annual: float) -> list:
    """
    Escaneia um ticker individual e retorna lista de opções PUT com métricas.
    
    Returns:
        list de dicts com métricas de cada opção, ou lista vazia se erro
    """
    try:
        print(f"[SCREENER] Scanning {ticker}...")
        
        # 1. Busca preço do ativo
        spot = get_asset_price_yesterday(ticker)
        if spot <= 0:
            print(f"[SCREENER] {ticker}: No spot price found")
            return []
        print(f"[SCREENER] {ticker}: Spot = R$ {spot:.2f}")
        
        # 2. Busca opções PUT do opcoes.net com range de 5% ITM/OTM
        try:
            options_df = get_put_options_for_screener(
                ticker=ticker,
                spot_price=spot,
                expiry_date=expiry,
                strike_range_pct=STRIKE_RANGE_PCT
            )
        except Exception as e:
            print(f"[SCREENER] {ticker}: Error fetching options: {e}")
            return []
        
        if options_df.empty:
            print(f"[SCREENER] {ticker}: No PUT options found")
            return []
        print(f"[SCREENER] {ticker}: Found {len(options_df)} PUT options")
        
        # 3. Busca histórico para análise fractal (apenas uma vez por ticker)
        full_ticker = f"{ticker}.SA"
        start_date = date.today() - timedelta(days=int(252 * 1.5))
        hist = yf.download(full_ticker, start=start_date.strftime('%Y-%m-%d'), 
                          end=date.today().strftime('%Y-%m-%d'), progress=False)
        
        if hist.empty or len(hist) < 50:
            print(f"[SCREENER] {ticker}: Insufficient historical data")
            return []
        
        # Extrai série de preços
        if 'Adj Close' in hist.columns:
            close_prices = hist['Adj Close'].tail(252)
        elif 'Close' in hist.columns:
            close_prices = hist['Close'].tail(252)
        else:
            close_prices = hist.iloc[:, 0].tail(252)
        
        if isinstance(close_prices, pd.DataFrame):
            close_prices = close_prices.squeeze()
        
        # 4. Calcula métricas fractais (uma vez por ticker)
        hurst = calculate_hurst_exponent(close_prices)
        hist_vol = calculate_historical_volatility(close_prices)
        filters = check_trend_filters(close_prices)
        
        # Interpretação Hurst
        recent_return = (close_prices.iloc[-1] / close_prices.iloc[-20] - 1) * 100 if len(close_prices) >= 20 else 0
        interpretation, trend_dir, _ = get_hurst_interpretation(hurst, recent_return)
        
        # Recomendação
        classification, rec_text, risk_level, rec_color = get_recommendation(hurst, filters, spot)
        
        # 5. Processa cada opção PUT encontrada
        results = []
        days_to_exp = (expiry - date.today()).days
        T = max(days_to_exp / 365.0, 0.001)
        r = selic_annual / 100
        selic_period = ((1 + selic_annual/100) ** (days_to_exp/365) - 1) * 100
        
        for _, opt in options_df.iterrows():
            premium = opt.get('premium', 0)
            strike = opt.get('strike', 0)
            option_ticker = opt.get('option_ticker', '')
            
            if premium is None or premium <= 0 or strike <= 0:
                continue
            
            # Yields
            yield_period = (premium / spot) * 100
            yield_annual = ((1 + yield_period/100) ** (365/max(days_to_exp, 1)) - 1) * 100
            pct_cdi = (yield_period / selic_period * 100) if selic_period > 0 else 0
            
            # Moneyness
            moneyness = ((strike - spot) / spot) * 100
            
            # IV - usar do site ou calcular
            iv = opt.get('iv', None)
            if iv is None or iv <= 0:
                try:
                    iv = implied_volatility(premium, spot, strike, T, r)
                    if iv <= 0:
                        iv = hist_vol
                except:
                    iv = hist_vol
            
            # Probabilidades
            prob_bs = prob_exercise_bs(spot, strike, T, r, iv if iv else hist_vol)
            prob_frac = prob_exercise_fractal(spot, strike, T, r, iv if iv else hist_vol, hurst)
            
            # IV Rank
            iv_rank_data = calculate_iv_rank(iv if iv else hist_vol, close_prices)
            iv_rank = iv_rank_data['iv_rank']
            iv_signal = iv_rank_data.get('sell_signal', 'Neutro')  # Fallback se não tiver
            
            # Gregas do site - converter para scalar se for Series
            delta = opt.get('delta', None)
            gamma = opt.get('gamma', None)
            
            # Converter Series para scalar
            if isinstance(delta, pd.Series):
                delta = delta.iloc[0] if len(delta) > 0 else None
            if isinstance(gamma, pd.Series):
                gamma = gamma.iloc[0] if len(gamma) > 0 else None
            
            results.append({
                'Ticker': ticker,
                'Opção': option_ticker,
                'Spot': round(spot, 2),
                'Strike': round(strike, 2),
                'Prêmio': round(premium, 2),
                'Moneyness': round(moneyness, 1),
                'Delta': round(float(delta), 4) if delta is not None and not pd.isna(delta) else None,
                'Gamma': round(float(gamma), 4) if gamma is not None and not pd.isna(gamma) else None,
                'IV': round(float(iv) * 100, 1) if iv and iv > 0 else None,
                'Yield %': round(yield_period, 2),
                'Yield A.': round(yield_annual, 1),
                '% CDI': round(pct_cdi, 0),
                'Hurst': round(hurst, 3),
                'Tipo': interpretation,
                'Direção': trend_dir,
                'SMA21': '✅' if filters['filter_a'] else '❌',
                'Mom 30d': '✅' if filters['filter_b'] else '❌',
                'Slope': '✅' if filters['filter_c'] else '❌',
                'Prob BS': round(prob_bs * 100, 1),
                'Prob Frac': round(prob_frac * 100, 1),
                'Recomendação': classification,
                'Risco': risk_level,
                '_rec_color': rec_color,
                'OI': int(opt.get('open_interest', 0)),
                'IV Rank': round(iv_rank, 0),
                'IV Sinal': iv_signal,
            })
        
        return results
        
    except Exception as e:
        print(f"[SCREENER] Error scanning {ticker}: {e}")
        traceback.print_exc()
        return []


def run_full_scan(tickers: list, expiry: date, progress_callback=None) -> pd.DataFrame:
    """
    Escaneia todos os tickers em paralelo.
    
    Returns:
        DataFrame com resultados
    """
    selic_annual = get_selic_annual()
    all_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:  # Reduzido para evitar rate limit
        futures = {
            executor.submit(scan_single_ticker, ticker, expiry, selic_annual): ticker 
            for ticker in tickers
        }
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed / len(tickers))
            
            results = future.result()
            if results:
                all_results.extend(results)
    
    if not all_results:
        return pd.DataFrame()
    
    df = pd.DataFrame(all_results)
    
    # Ordena por Yield decrescente
    df = df.sort_values('Yield %', ascending=False)
    
    return df


def apply_recommendation_style(val):
    """Aplica cor de fundo baseada na recomendação."""
    colors = {
        'VENDA FORTE': 'background-color: rgba(57, 229, 140, 0.3)',
        'OPORTUNIDADE': 'background-color: rgba(0, 212, 255, 0.3)',
        'NEUTRO': 'background-color: rgba(99, 110, 250, 0.3)',
        'CAUTELA': 'background-color: rgba(255, 179, 2, 0.3)',
        'RISCO ALTO': 'background-color: rgba(255, 75, 75, 0.3)',
    }
    return colors.get(val, '')


def apply_hurst_style(val):
    """Aplica cor baseada no Hurst."""
    try:
        h = float(val)
        if h > 0.55:
            return 'color: #39E58C'  # Verde - persistente
        elif h < 0.45:
            return 'color: #FFB302'  # Amarelo - reversão
        else:
            return 'color: #636EFA'  # Azul - random
    except:
        return ''


def render():
    st.header("📊 Screener de PUT - Ações Líquidas")
    st.info(
        "Monitora opções PUT das ações mais líquidas da B3 com análise de yields, "
        "gregas, indicadores fractais e recomendações de venda. "
        "**Fonte: opcoes.net.br** | Range: ±5% ITM/OTM"
    )
    
    # Controles
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        # Seleção de vencimento
        current_date = date.today()
        available_expirations = []
        for i in range(1, 4):
            future_date = current_date + relativedelta(months=i)
            available_expirations.append(get_third_friday(future_date.year, future_date.month))
        
        expiry_options = {
            f"{exp.strftime('%d/%m/%Y')} ({(exp - current_date).days} dias)": exp 
            for exp in available_expirations
        }
        selected_expiry_label = st.selectbox(
            "Vencimento",
            options=list(expiry_options.keys()),
            key="screener_expiry"
        )
        expiry = expiry_options[selected_expiry_label]
    
    with col2:
        # Filtro de recomendação
        rec_filter = st.multiselect(
            "Filtrar por Recomendação",
            options=["VENDA FORTE", "OPORTUNIDADE", "NEUTRO", "CAUTELA", "RISCO ALTO"],
            default=["VENDA FORTE", "OPORTUNIDADE", "NEUTRO"],
            key="screener_rec_filter"
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        scan_button = st.button("🔍 Escanear", type="primary", use_container_width=True)
    
    # Métricas gerais
    selic = get_selic_annual()
    days_to_exp = (expiry - current_date).days
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Selic Anual", f"{selic:.2f}%")
    m2.metric("Dias até Vencimento", f"{days_to_exp}")
    m3.metric("Ativos Monitorados", f"{len(LIQUID_TICKERS)}")
    m4.metric("Vencimento", expiry.strftime("%d/%m/%Y"))
    
    st.markdown("---")
    
    # Execução do scan
    if scan_button or 'screener_df' in st.session_state:
        if scan_button:
            st.warning("⏳ Buscando dados do opcoes.net.br... Isso pode levar alguns minutos na primeira execução.")
            progress_bar = st.progress(0, text="Escaneando ativos...")
            
            def update_progress(pct):
                progress_bar.progress(pct, text=f"Escaneando ativos... {int(pct*100)}%")
            
            df = run_full_scan(LIQUID_TICKERS, expiry, update_progress)
            progress_bar.empty()
            
            if df.empty:
                st.warning("Nenhuma opção encontrada com dados válidos.")
                return
            
            st.session_state['screener_df'] = df
            st.session_state['screener_expiry_used'] = expiry
        
        df = st.session_state.get('screener_df', pd.DataFrame())
        
        if df.empty:
            st.warning("Nenhum dado disponível. Clique em 'Escanear' para buscar.")
            return
        
        # Aplica filtro de recomendação
        if rec_filter:
            df_filtered = df[df['Recomendação'].isin(rec_filter)]
        else:
            df_filtered = df
        
        # Estatísticas resumidas
        st.markdown("### 📈 Resumo do Scan")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Opções Encontradas", f"{len(df)}")
        s2.metric("Yield Médio", f"{df['Yield %'].mean():.2f}%")
        s3.metric("Yield Máximo", f"{df['Yield %'].max():.2f}%")
        
        venda_forte_count = len(df[df['Recomendação'] == 'VENDA FORTE'])
        s4.metric("VENDA FORTE", f"{venda_forte_count}")
        
        risco_alto_count = len(df[df['Recomendação'] == 'RISCO ALTO'])
        s5.metric("RISCO ALTO", f"{risco_alto_count}")
        
        st.markdown("---")
        
        # Tabela principal
        st.markdown("### 📋 Resultados do Screener")
        
        # Colunas para exibição (com novas colunas de Gregas)
        display_cols = [
            'Ticker', 'Opção', 'Spot', 'Strike', 'Prêmio', 'Moneyness',
            'Delta', 'Gamma', 'IV',
            'Yield %', '% CDI', 'IV Rank', 'IV Sinal', 'Hurst', 'Tipo', 'Direção',
            'SMA21', 'Mom 30d', 'Slope', 'Prob BS', 'Prob Frac', 'Recomendação'
        ]
        
        # Filtrar apenas colunas que existem
        display_cols = [c for c in display_cols if c in df_filtered.columns]
        df_display = df_filtered[display_cols].copy()
        
        # Estilização
        styled_df = df_display.style.applymap(
            apply_recommendation_style, subset=['Recomendação']
        ).applymap(
            apply_hurst_style, subset=['Hurst']
        ).format({
            'Spot': 'R$ {:.2f}',
            'Strike': 'R$ {:.2f}',
            'Prêmio': 'R$ {:.2f}',
            'Moneyness': '{:.1f}%',
            'Delta': '{:.4f}',
            'Gamma': '{:.4f}',
            'IV': '{:.1f}%',
            'Yield %': '{:.2f}%',
            '% CDI': '{:.0f}%',
            'IV Rank': '{:.0f}%',
            'Hurst': '{:.3f}',
            'Prob BS': '{:.1f}%',
            'Prob Frac': '{:.1f}%',
        }, na_rep='-')
        
        st.dataframe(styled_df, use_container_width=True, height=600)
        
        # Legenda
        with st.expander("📖 Legenda"):
            leg1, leg2 = st.columns(2)
            
            with leg1:
                st.markdown("""
                **Gregas (do opcoes.net):**
                - **Delta**: Sensibilidade ao preço do ativo
                - **Gamma**: Taxa de variação do Delta
                - **IV**: Volatilidade Implícita (%)
                
                **Indicadores de Direção:**
                - **SMA21**: ✅ se Preço > SMA 21 dias
                - **Mom 30d**: ✅ se Momentum 30 dias > 0
                - **Slope**: ✅ se Inclinação da regressão linear > 0
                
                **Interpretação do Hurst:**
                - 🟢 **> 0.55**: Persistente (tendência continua)
                - 🔵 **0.45-0.55**: Random Walk
                - 🟡 **< 0.45**: Reversão à média
                """)
            
            with leg2:
                st.markdown("""
                **Recomendações:**
                - 🟢 **VENDA FORTE**: Alta persistente + todos filtros bullish
                - 🔵 **OPORTUNIDADE**: Ativo esticado para baixo com reversão
                - 🟣 **NEUTRO**: Siga as probabilidades Black-Scholes
                - 🟡 **CAUTELA**: Exaustão de topo
                - 🔴 **RISCO ALTO**: Queda persistente sem suporte
                
                **Range de Strikes:**
                - Opções com strikes entre -5% e +5% do spot
                - Moneyness negativo = ITM (In The Money)
                - Moneyness positivo = OTM (Out of The Money)
                """)
        
        # Download CSV
        csv = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"screener_put_{date.today().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
