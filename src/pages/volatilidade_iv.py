
import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
from src.data_loaders.fred_api import carregar_dados_fred
from src.models.amplitude import analisar_retornos_por_faixa
from src.components.charts_amplitude import (
    gerar_grafico_historico_amplitude,
    gerar_histograma_amplitude,
    gerar_heatmap_amplitude,
    gerar_grafico_iv_bandas,
    gerar_grafico_regime_volatilidade,
    gerar_grafico_roc_volatilidade,
    gerar_grafico_iv_rank
)
from src.models.put_utils import (
    get_selic_annual, get_third_friday, generate_put_ticker, 
    generate_call_ticker, get_asset_price_yesterday, get_next_expiration
)
from src.data_loaders.b3_api import fetch_option_price_b3
from src.models.black_scholes import implied_volatility

def calcular_term_structure(asset_ticker, asset_price, selic_annual, num_vencimentos=6):
    """
    Calcula a estrutura a termo da volatilidade implícita para opções ATM.
    Returns: DataFrame com colunas: days_to_exp, iv, expiry_date
    """
    current_date = date.today()
    results = []
    
    # Gera vencimentos futuros (próximos N meses)
    for i in range(1, num_vencimentos + 1):
        try:
            future_date = current_date + relativedelta(months=i)
            expiry = get_third_friday(future_date.year, future_date.month)
            days_to_exp = (expiry - current_date).days
            
            if days_to_exp <= 0: continue
            
            # Encontra strike ATM (arredondado)
            atm_strike = round(asset_price, 0)
            
            # Gera ticker da opção PUT ATM
            option_ticker = generate_put_ticker(asset_ticker[:4], expiry, atm_strike)
            
            # Busca preço na B3
            b3_data = fetch_option_price_b3(option_ticker)
            
            if b3_data and b3_data['last_price'] > 0:
                option_price = b3_data['last_price']
                T = max(days_to_exp / 365.0, 0.001)
                r = selic_annual / 100
                
                try:
                    iv = implied_volatility(option_price, asset_price, atm_strike, T, r)
                    iv_pct = iv * 100
                    if 5 < iv_pct < 200:
                        results.append({
                            'days_to_exp': days_to_exp,
                            'iv': iv_pct,
                            'expiry_date': expiry,
                            'strike': atm_strike,
                            'option_ticker': option_ticker,
                            'option_price': option_price
                        })
                except: pass
        except Exception: continue
    
    return pd.DataFrame(results)

def calcular_skew(asset_ticker, asset_price, selic_annual):
    """
    Calcula o Volatility Skew para o próximo vencimento líquido.
    Analisa opções OTM (Puts para baixo, Calls para cima).
    """
    current_date = date.today()
    # Pega próximo vencimento (M+1)
    expiry = get_next_expiration(current_date)
    days_to_exp = (expiry - current_date).days
    
    if days_to_exp < 5: # Se estiver muito perto, pega o próximo
        expiry = get_third_friday(expiry.year, expiry.month + 1 if expiry.month < 12 else 1)
        days_to_exp = (expiry - current_date).days

    T = max(days_to_exp / 365.0, 0.001)
    r = selic_annual / 100
    
    results = []
    
    # Range de Moneyness (80% a 120%)
    moneyness_range = np.arange(0.80, 1.25, 0.05) # 5% steps
    
    for m in moneyness_range:
        try:
            strike = round(asset_price * m)
            
            # Define se é Put ou Call (para ser OTM)
            if strike < asset_price:
                option_type = 'put'
                ticker = generate_put_ticker(asset_ticker[:4], expiry, strike)
            else:
                option_type = 'call'
                ticker = generate_call_ticker(asset_ticker[:4], expiry, strike)
            
            b3_data = fetch_option_price_b3(ticker)
            
            if b3_data and b3_data['last_price'] > 0:
                price = b3_data['last_price']
                
                # Para IV, Black-Scholes precisa saber se é call ou put
                # Minha func implied_volatility atual é HARDCODED para PUT no black_scholes.py?
                # Vamos verificar... A função implied_volatility chama black_scholes_put.
                # PRECISARIA ter call no implied_volatility ou adaptar.
                # WORKAROUND: Put-Call Parity para Calls?
                # call = put + S - K*exp(-rT) -> put = call - S + K*exp(-rT)
                # Então se for Call, converto preço para "Put equivalente" e calculo IV.
                
                price_for_iv = price
                if option_type == 'call':
                     # C - P = S - K*e^-rT  =>  P = C - S + K*e^-rT
                     price_for_iv = price - asset_price + strike * np.exp(-r * T)
                     # Se P < 0 (arbitragem ou dados ruins), skip
                     if price_for_iv < 0: continue
                
                iv = implied_volatility(price_for_iv, asset_price, strike, T, r)
                iv_pct = iv * 100
                
                if 5 < iv_pct < 200:
                    results.append({
                        'strike': strike,
                        'moneyness': m * 100,
                        'iv': iv_pct,
                        'ticker': ticker,
                        'type': option_type.upper(),
                        'price': price
                    })
        except: pass
        
    return pd.DataFrame(results), expiry

def gerar_grafico_term_structure(df_term):
    if df_term.empty:
        return go.Figure().update_layout(title_text="Sem dados para Term Structure", template='brokeberg')
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_term['days_to_exp'], y=df_term['iv'],
        mode='lines+markers', name='IV ATM',
        line=dict(color='#00E676', width=3), marker=dict(size=8)
    ))
    
    for _, row in df_term.iterrows():
        fig.add_annotation(
            x=row['days_to_exp'], y=row['iv'],
            text=f"{row['expiry_date'].strftime('%d/%m')}",
            showarrow=False, yshift=15, font=dict(color='white')
        )

    fig.update_layout(
        title='Estrutura a Termo (IV ATM)', template='brokeberg',
        xaxis_title="Dias até Vencimento", yaxis_title="IV (%)",
        height=350, margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

def gerar_grafico_skew(df_skew, expiry):
    if df_skew.empty:
        return go.Figure().update_layout(title_text="Sem dados para Skew", template='brokeberg')
        
    fig = go.Figure()
    
    # Separa Puts e Calls para cores diferentes
    puts = df_skew[df_skew['type'] == 'PUT']
    calls = df_skew[df_skew['type'] == 'CALL']
    
    fig.add_trace(go.Scatter(
        x=df_skew['strike'], y=df_skew['iv'],
        mode='lines', name='Curva Skew',
        line=dict(color='gray', width=1, dash='dot')
    ))
    
    fig.add_trace(go.Scatter(
        x=puts['strike'], y=puts['iv'],
        mode='markers', name='Puts OTM (Proteção)',
        marker=dict(color='#FF5252', size=10, symbol='triangle-down')
    ))
    
    fig.add_trace(go.Scatter(
        x=calls['strike'], y=calls['iv'],
        mode='markers', name='Calls OTM (Alta)',
        marker=dict(color='#00E676', size=10, symbol='triangle-up')
    ))

    fig.update_layout(
        title=f'Volatility Skew - Vencimento {expiry.strftime("%d/%m/%Y")}',
        template='brokeberg',
        xaxis_title="Strike", yaxis_title="Implied Volatility (%)",
        hovermode="x unified",
        height=350
    )
    return fig

def gerar_grafico_spread_vix(df_merged):
    fig = go.Figure()
    
    # Área do Spread
    fig.add_trace(go.Scatter(
        x=df_merged.index, y=df_merged['Spread'],
        mode='lines', name='Spread Brasil',
        line=dict(color='#FFB74D', width=2),
        fill='tozeroy', fillcolor='rgba(255, 183, 77, 0.1)'
    ))
    
    # Média
    mean_val = df_merged['Spread'].mean()
    fig.add_hline(y=mean_val, line_dash="dash", line_color="gray", annotation_text="Média")
    
    fig.update_layout(
        title='Spread de Risco: VXEWZ (Brasil) - VIX (EUA)',
        template='brokeberg',
        yaxis_title="Pontos de Volatilidade",
        height=350
    )
    return fig


def calcular_iv_rank(series, periodo=252):
    iv_min = series.rolling(window=periodo).min()
    iv_max = series.rolling(window=periodo).max()
    iv_rank = ((series - iv_min) / (iv_max - iv_min)) * 100
    return iv_rank

def interpretar_iv_rank(iv_rank, percentil):
    if iv_rank >= 80: return "🔴 **ALTO** - Volatilidade elevada."
    elif iv_rank >= 60: return "🟠 **MODERADAMENTE ALTO**."
    elif iv_rank >= 40: return "🟡 **NEUTRO**."
    elif iv_rank >= 20: return "🟢 **MODERADAMENTE BAIXO**."
    else: return "🔵 **BAIXO** - Volatilidade muito baixa."

def interpretar_regime(mm21, mm63):
    spread = mm21 - mm63
    if spread > 2: return "⚠️ **BACKWARDATION FORTE**"
    elif spread > 0: return "🟠 **BACKWARDATION**"
    elif spread > -2: return "🟢 **CONTANGO LEVE**"
    else: return "🔵 **CONTANGO FORTE**"

def render():
    st.header("📊 Análise de Volatilidade Implícita (VXEWZ)")
    
    with st.expander("ℹ️ **Sobre o VXEWZ**", expanded=False):
        st.markdown("O **VXEWZ** mede a volatilidade implícita do ETF EWZ (Brasil). Valores altos indicam medo.")
    
    st.markdown("---")

    FRED_API_KEY = 'd78668ca6fc142a1248f7cb9132916b0'
    ATIVOS_ANALISE = ['BOVA11.SA', 'SMAL11.SA']
    PERIODOS_RETORNO = {'1 Mês': 21, '3 Meses': 63, '6 Meses': 126, '1 Ano': 252}

    with st.spinner("Carregando dados de Volatilidade (VXEWZ e VIX)..."):
        # Carrega VXEWZ e VIX para calcular spread
        df_fred = carregar_dados_fred(FRED_API_KEY, {
            'VXEWZCLS': 'VXEWZ',
            'VIXCLS': 'VIX'
        })

    if df_fred.empty or 'VXEWZ' not in df_fred.columns:
        st.error("Erro ao carregar dados do FRED.")
        return

    # Processamento dos dados
    df_fred = df_fred.dropna()
    vxewz_series = df_fred['VXEWZ']
    
    # Cálculo Spread
    if 'VIX' in df_fred.columns:
        df_fred['Spread'] = df_fred['VXEWZ'] - df_fred['VIX']
    
    # Dados recentes
    cutoff_5y = vxewz_series.index.max() - pd.DateOffset(years=5)
    vxewz_recent = vxewz_series[vxewz_series.index >= cutoff_5y]
    
    if 'Spread' in df_fred.columns:
        spread_recent = df_fred['Spread'][df_fred.index >= cutoff_5y]
    
    # Métricas
    valor_atual = vxewz_series.iloc[-1]
    media_hist = vxewz_recent.mean()
    z_score = (valor_atual - media_hist) / vxewz_recent.std()
    percentil = stats.percentileofscore(vxewz_recent, valor_atual)
    
    iv_rank_series = calcular_iv_rank(vxewz_series)
    iv_rank_atual = iv_rank_series.iloc[-1]
    
    mm21 = vxewz_series.rolling(21).mean().iloc[-1]
    mm63 = vxewz_series.rolling(63).mean().iloc[-1]

    # --- LAYOUT ---
    
    # 1. KPIs
    st.subheader("📈 Métricas Principais")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("VXEWZ", f"{valor_atual:.2f}")
    k2.metric("IV Rank", f"{iv_rank_atual:.1f}%", delta=f"{((valor_atual - media_hist)/media_hist)*100:.1f}% vs média")
    k3.metric("Z-Score", f"{z_score:.2f}")
    k4.metric("Spread Brasil", f"{df_fred['Spread'].iloc[-1]:.2f} pts" if 'Spread' in df_fred.columns else "N/A")

    d1, d2 = st.columns(2)
    d1.info(f"**Diagnóstico IV Rank**: {interpretar_iv_rank(iv_rank_atual, percentil)}")
    d2.info(f"**Diagnóstico Regime**: {interpretar_regime(mm21, mm63)}")

    st.markdown("---")
    
    # 2. ANÁLISE INTERATIVA (SKEW E TERM STRUCTURE)
    st.subheader("🧩 Análise Interativa de Opções")
    
    col_input, col_void = st.columns([1, 2])
    with col_input:
        term_asset = st.text_input("Ativo para Análise (Ex: BOVA11)", value="BOVA11")
    
    if term_asset:
        with st.spinner(f"Analisando cadeia de opções de {term_asset}..."):
            try:
                # Busca Preço com nova lógica robusta
                import yfinance as yf
                full_ticker = term_asset if term_asset.endswith(".SA") else f"{term_asset}.SA"
                hist = yf.Ticker(full_ticker).history(period="5d")
                asset_price = 0.0
                if not hist.empty:
                     if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                     if 'Close' in hist.columns: 
                          h = hist.dropna(subset=['Close'])
                          if len(h) >= 1: asset_price = float(h['Close'].iloc[-1])
                
                selic = get_selic_annual()
                
                if asset_price > 0:
                    t1, t2 = st.tabs(["📉 Volatility Skew (Smile)", "📅 Term Structure"])
                    
                    with t1:
                        st.caption("A curva 'Skew' mostra a volatilidade implícita por Strike. Puts OTM (esquerda) geralmente têm IV maior (medo).")
                        df_skew, expiry_skew = calcular_skew(term_asset, asset_price, selic)
                        if not df_skew.empty:
                            c_skew1, c_skew2 = st.columns([3, 1])
                            c_skew1.plotly_chart(gerar_grafico_skew(df_skew, expiry_skew), use_container_width=True)
                            with c_skew2:
                                st.write("**Dados do Skew**")
                                st.dataframe(df_skew[['strike', 'iv', 'type']].sort_values('strike'), hide_index=True, height=300)
                        else:
                            st.warning("Não foi possível gerar o Skew (dados insuficientes).")
                            
                    with t2:
                        st.caption("A 'Term Structure' mostra a volatilidade implícita por vencimento.")
                        df_term = calcular_term_structure(term_asset, asset_price, selic)
                        if not df_term.empty:
                            c_term1, c_term2 = st.columns([3, 1])
                            c_term1.plotly_chart(gerar_grafico_term_structure(df_term), use_container_width=True)
                            with c_term2:
                                st.write("**Dados por Vencimento**")
                                st.dataframe(df_term[['expiry_date', 'iv']].sort_values('expiry_date'), hide_index=True, height=300)
                        else:
                            st.warning("Não foi possível gerar Term Structure.")
                else:
                    st.error(f"Preço do ativo {term_asset} não encontrado.")
            except Exception as e:
                st.error(f"Erro na análise: {e}")
                
    st.markdown("---")

    # 3. SPREAD BRASIL
    if 'Spread' in df_fred.columns:
        st.subheader("🇺🇸 x 🇧🇷 Spread de Risco (VXEWZ - VIX)")
        st.caption("Diferença entre volatilidade Brasil e EUA. Spread alto indica risco local elevado.")
        st.plotly_chart(gerar_grafico_spread_vix(df_fred), use_container_width=True)
        st.markdown("---")

    # 4. HISTÓRICO E OUTROS
    st.subheader("📉 Histórico VXEWZ")
    c1, c2 = st.columns([2, 1])
    c1.plotly_chart(gerar_grafico_historico_amplitude(vxewz_series, "Histórico", valor_atual, media_hist), use_container_width=True)
    c2.plotly_chart(gerar_histograma_amplitude(vxewz_recent, "Distribuição", valor_atual, media_hist), use_container_width=True)
    
    st.markdown("---")
    st.subheader("Bandas de Bollinger e Regime")
    b1, b2 = st.columns(2)
    b1.plotly_chart(gerar_grafico_iv_bandas(vxewz_series), use_container_width=True)
    b2.plotly_chart(gerar_grafico_regime_volatilidade(vxewz_series), use_container_width=True)
    
    st.markdown("---")
    st.subheader("Análise de Retornos por IV Rank")
    
    # Lógica de Heatmaps simplificada - mantendo a original mas compacta
    df_analise_base = pd.DataFrame(index=vxewz_series.index).sort_index()
    for atv in ATIVOS_ANALISE:
        try:
             d = yf.download(atv, start=vxewz_series.index.min(), progress=False, auto_adjust=False)
             if not d.empty:
                prices = d['Adj Close'] if 'Adj Close' in d.columns else d['Close']
                if isinstance(prices, pd.DataFrame): prices = prices.iloc[:,0]
                lbl = atv.replace('.SA', '')
                for np_name, dias in PERIODOS_RETORNO.items():
                    df_analise_base[f'retorno_{np_name} ({lbl})'] = prices.pct_change(periods=dias).shift(-dias) * 100
        except: pass
        
    res_ivr = analisar_retornos_por_faixa(df_analise_base.join(iv_rank_series.rename('IV'), how='inner'), 'IV', 10, 0, 100, '%')
    f_atual = f"{int(iv_rank_atual//10)*10} a {int(iv_rank_atual//10)*10+10}%"
    
    col_hvs, col_h1, col_h2 = st.columns([1,1,1])
    col_hvs.plotly_chart(gerar_grafico_iv_rank(iv_rank_series), use_container_width=True)
    
    if not res_ivr['Retorno Médio'].empty:
        # Exibe apenas do primeiro ativo para economizar espaço ou faz tabs?
        # Fazendo tabs para ativos
        tabs_atv = st.tabs([a.replace('.SA','') for a in ATIVOS_ANALISE])
        for i, atv in enumerate(ATIVOS_ANALISE):
            clean = atv.replace('.SA','')
            with tabs_atv[i]:
                c_a = [c for c in res_ivr['Retorno Médio'].columns if clean in c]
                if c_a:
                    r = res_ivr['Retorno Médio'][c_a].rename(columns=lambda x: x.replace(f" ({clean})", ''))
                    h = res_ivr['Taxa de Acerto'][c_a].rename(columns=lambda x: x.replace(f" ({clean})", ''))
                    ch1, ch2 = st.columns(2)
                    ch1.plotly_chart(gerar_heatmap_amplitude(r, f_atual, "Retorno Médio"), use_container_width=True)
                    ch2.plotly_chart(gerar_heatmap_amplitude(h, f_atual, "Taxa de Acerto"), use_container_width=True)

