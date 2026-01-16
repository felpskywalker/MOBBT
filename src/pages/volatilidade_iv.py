"""
Página de Análise de Volatilidade Implícita (VXEWZ)
Inclui: Term Structure, Volatility Skew, IV Rank, Bandas de Bollinger, Regime, ROC e Heatmaps
"""

import streamlit as st
import pandas as pd
import numpy as np
import traceback
from scipy import stats
from datetime import date
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go

from src.data_loaders.fred_api import carregar_dados_fred
from src.data_loaders.b3_api import fetch_option_price_b3
from src.models.amplitude import analisar_retornos_por_faixa
from src.models.put_utils import (
    get_selic_annual, 
    get_third_friday, 
    generate_put_ticker, 
    get_asset_price_yesterday
)
from src.models.black_scholes import implied_volatility
from src.components.charts_amplitude import (
    gerar_grafico_historico_amplitude,
    gerar_histograma_amplitude,
    gerar_heatmap_amplitude,
    gerar_grafico_iv_bandas,
    gerar_grafico_regime_volatilidade,
    gerar_grafico_roc_volatilidade,
    gerar_grafico_iv_rank
)

# ============================================================
# CONSTANTES
# ============================================================
ATIVOS_ANALISE = ['BOVA11.SA', 'SMAL11.SA']
PERIODOS_RETORNO = {'1 Mês': 21, '3 Meses': 63, '6 Meses': 126, '1 Ano': 252}



# ============================================================
# FUNÇÕES DE CÁLCULO - TERM STRUCTURE
# ============================================================
def calcular_term_structure(asset_ticker, asset_price, selic_annual, num_vencimentos=6):
    """
    Calcula a estrutura a termo da volatilidade implícita para opções ATM.
    Retorna DataFrame com: days_to_exp, iv, expiry_date, strike, option_ticker, option_price
    """
    current_date = date.today()
    results = []
    
    for i in range(1, num_vencimentos + 1):
        try:
            future_date = current_date + relativedelta(months=i)
            expiry = get_third_friday(future_date.year, future_date.month)
            days_to_exp = (expiry - current_date).days
            
            if days_to_exp <= 0:
                continue
            
            atm_strike = round(asset_price, 0)
            option_ticker = generate_put_ticker(asset_ticker[:4], expiry, atm_strike)
            b3_data = fetch_option_price_b3(option_ticker)
            
            if b3_data and b3_data['last_price'] > 0:
                option_price = b3_data['last_price']
                T = max(days_to_exp / 365.0, 0.001)
                r = selic_annual / 100
                
                try:
                    iv = implied_volatility(option_price, asset_price, atm_strike, T, r)
                    
                    if iv is None or np.isnan(iv) or np.isinf(iv):
                        continue
                    
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
                except Exception:
                    pass
        except Exception:
            continue
    
    return pd.DataFrame(results)


def gerar_grafico_term_structure(df_term):
    """Gera gráfico de estrutura a termo da IV"""
    if df_term.empty:
        fig = go.Figure()
        fig.update_layout(title_text="Sem dados disponíveis para Term Structure", template='brokeberg')
        return fig
    
    fig = go.Figure()
    
    # Linha principal
    fig.add_trace(go.Scatter(
        x=df_term['days_to_exp'],
        y=df_term['iv'],
        mode='lines+markers',
        name='IV ATM',
        line=dict(color='#00E676', width=2),
        marker=dict(size=10, color='#00E676')
    ))
    
    # Anotações com vencimentos
    for _, row in df_term.iterrows():
        fig.add_annotation(
            x=row['days_to_exp'],
            y=row['iv'],
            text=row['expiry_date'].strftime('%d/%m'),
            showarrow=False,
            yshift=15,
            font=dict(size=10, color='gray')
        )
    
    # Linha de tendência
    if len(df_term) >= 2:
        z = np.polyfit(df_term['days_to_exp'], df_term['iv'], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df_term['days_to_exp'].min(), df_term['days_to_exp'].max(), 50)
        fig.add_trace(go.Scatter(
            x=x_line, y=p(x_line),
            mode='lines', name='Tendência',
            line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dash')
        ))
    
    fig.update_layout(
        title_text='Estrutura a Termo da Volatilidade Implícita',
        title_x=0, template='brokeberg',
        xaxis_title="Dias até Vencimento",
        yaxis_title="Volatilidade Implícita (%)",
        showlegend=False, height=400
    )
    return fig


# ============================================================
# FUNÇÕES DE CÁLCULO - VOLATILITY SKEW
# ============================================================
def calcular_volatility_skew(asset_ticker, asset_price, selic_annual, expiry_date):
    """
    Calcula a volatilidade implícita para diferentes strikes (Volatility Skew).
    Retorna DataFrame com: strike, moneyness, iv, option_ticker, option_price
    """
    current_date = date.today()
    days_to_exp = (expiry_date - current_date).days
    
    if days_to_exp <= 0:
        return pd.DataFrame()
    
    results = []
    moneyness_levels = [0.85, 0.90, 0.95, 1.00, 1.05, 1.10]
    
    for moneyness in moneyness_levels:
        try:
            strike = round(asset_price * moneyness, 0)
            option_ticker = generate_put_ticker(asset_ticker[:4], expiry_date, strike)
            b3_data = fetch_option_price_b3(option_ticker)
            
            if b3_data and b3_data['last_price'] > 0:
                option_price = b3_data['last_price']
                T = max(days_to_exp / 365.0, 0.001)
                r = selic_annual / 100
                
                try:
                    iv = implied_volatility(option_price, asset_price, strike, T, r)
                    
                    if iv is None or np.isnan(iv) or np.isinf(iv):
                        continue
                    
                    iv_pct = iv * 100
                    if 5 < iv_pct < 200:
                        results.append({
                            'strike': strike,
                            'moneyness': (moneyness - 1) * 100,
                            'moneyness_pct': moneyness * 100,
                            'iv': iv_pct,
                            'option_ticker': option_ticker,
                            'option_price': option_price
                        })
                except Exception:
                    pass
        except Exception:
            continue
    
    return pd.DataFrame(results)


def gerar_grafico_skew(df_skew, asset_ticker):
    """Gera gráfico de Volatility Skew (IV vs Moneyness)"""
    if df_skew.empty:
        fig = go.Figure()
        fig.update_layout(title_text="Sem dados disponíveis para Volatility Skew", template='brokeberg')
        return fig
    
    fig = go.Figure()
    
    # Linha do Skew
    fig.add_trace(go.Scatter(
        x=df_skew['moneyness'], y=df_skew['iv'],
        mode='lines+markers', name='IV',
        line=dict(color='#FF6D00', width=3),
        marker=dict(size=12, color='#FF6D00', symbol='circle')
    ))
    
    # Marca ponto ATM
    atm_row = df_skew[df_skew['moneyness'].abs() < 1]
    if not atm_row.empty:
        fig.add_trace(go.Scatter(
            x=atm_row['moneyness'], y=atm_row['iv'],
            mode='markers', name='ATM',
            marker=dict(size=18, color='#00E676', symbol='star')
        ))
    
    # Linha vertical no ATM
    fig.add_vline(x=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
    
    # Anotações dos strikes
    for _, row in df_skew.iterrows():
        label = "ATM" if abs(row['moneyness']) < 1 else f"K={int(row['strike'])}"
        fig.add_annotation(
            x=row['moneyness'], y=row['iv'],
            text=label, showarrow=False, yshift=20,
            font=dict(size=9, color='gray')
        )
    
    fig.update_layout(
        title_text=f'Volatility Skew - {asset_ticker} (PUT)',
        title_x=0, template='brokeberg',
        xaxis_title="Moneyness (% vs ATM)",
        yaxis_title="Volatilidade Implícita (%)",
        showlegend=False, height=400
    )
    return fig


# ============================================================
# FUNÇÕES DE CÁLCULO - IV RANK E INTERPRETAÇÕES
# ============================================================
def calcular_iv_rank(series, periodo=252):
    """Calcula o IV Rank rolling baseado em um período."""
    iv_min = series.rolling(window=periodo).min()
    iv_max = series.rolling(window=periodo).max()
    return ((series - iv_min) / (iv_max - iv_min)) * 100


def interpretar_iv_rank(iv_rank):
    """Retorna interpretação textual do IV Rank atual."""
    if iv_rank >= 80:
        return "🔴 **ALTO** - Volatilidade elevada. Bom momento para **vender opções** (prêmios altos)."
    elif iv_rank >= 60:
        return "🟠 **MODERADAMENTE ALTO** - Volatilidade acima da média. Venda de opções pode ser interessante."
    elif iv_rank >= 40:
        return "🟡 **NEUTRO** - Volatilidade em torno da média histórica."
    elif iv_rank >= 20:
        return "🟢 **MODERADAMENTE BAIXO** - Volatilidade abaixo da média. Compra de opções pode ser interessante."
    else:
        return "🔵 **BAIXO** - Volatilidade muito baixa. Bom momento para **comprar opções** (prêmios baratos)."


def interpretar_regime(mm21, mm63):
    """Retorna interpretação do regime de volatilidade."""
    spread = mm21 - mm63
    if spread > 2:
        return "⚠️ **BACKWARDATION FORTE** - Mercado em stress. Volatilidade de curto prazo muito elevada."
    elif spread > 0:
        return "🟠 **BACKWARDATION** - Mercado em alerta. Volatilidade de curto prazo acima da média."
    elif spread > -2:
        return "🟢 **CONTANGO LEVE** - Mercado em normalidade."
    else:
        return "🔵 **CONTANGO FORTE** - Mercado muito calmo. Volatilidade de curto prazo bem abaixo da média."


# ============================================================
# FUNÇÕES DE RENDERIZAÇÃO - SEÇÕES
# ============================================================
def render_header_explicacao():
    """Renderiza header e explicação inicial"""
    st.header("📊 Análise de Volatilidade Implícita (VXEWZ)")
    
    with st.expander("ℹ️ **O que é o VXEWZ e por que ele importa?**", expanded=False):
        st.markdown("""
        ### O Índice VXEWZ
        
        O **VXEWZ** (CBOE Brazil ETF Volatility Index) é o "índice do medo" do mercado brasileiro. 
        Ele mede a **volatilidade implícita** das opções do ETF EWZ (iShares MSCI Brazil), que é 
        negociado nos Estados Unidos e replica o desempenho das ações brasileiras.
        
        #### Como interpretar:
        - **Valores baixos (< 20)**: Mercado complacente, investidores confiantes. Opções estão "baratas".
        - **Valores médios (20-30)**: Normalidade do mercado brasileiro.
        - **Valores altos (> 35)**: Stress, medo e incerteza. Opções estão "caras".
        - **Picos extremos (> 50)**: Pânico. Geralmente coincide com crises ou eventos extremos.
        
        #### Por que acompanhar:
        1. **Timing de operações**: IV alto = momento de vender opções; IV baixo = momento de comprar opções
        2. **Sentimento do mercado**: Antecipa movimentos de stress antes que eles se materializem nos preços
        3. **Proteção de carteira**: Ajuda a decidir quando comprar proteção (puts) está barato ou caro
        """)
    st.markdown("---")


def render_metricas_principais(valor_atual, media_hist, iv_rank_atual, percentil, z_score, mm21, vxewz_series):
    """Renderiza seção de métricas principais"""
    st.subheader("📈 Métricas Principais")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("VXEWZ Atual", f"{valor_atual:.2f}")
        st.metric("Média (5A)", f"{media_hist:.2f}")
    with col2:
        delta_pct = ((valor_atual - media_hist) / media_hist) * 100
        st.metric("IV Rank (252d)", f"{iv_rank_atual:.1f}%", delta=f"{delta_pct:+.1f}% vs média")
        st.metric("Percentil", f"{percentil:.1f}%")
    with col3:
        st.metric("Z-Score", f"{z_score:.2f}")
        st.metric("MM21", f"{mm21:.2f}")
    with col4:
        st.metric("Mín 252d", f"{vxewz_series.rolling(252).min().iloc[-1]:.2f}")
        st.metric("Máx 252d", f"{vxewz_series.rolling(252).max().iloc[-1]:.2f}")


def render_diagnostico(iv_rank_atual, mm21, mm63):
    """Renderiza diagnóstico atual"""
    st.markdown("### 📝 Diagnóstico Atual")
    col_int1, col_int2 = st.columns(2)
    with col_int1:
        st.markdown(f"**IV Rank:** {interpretar_iv_rank(iv_rank_atual)}")
    with col_int2:
        st.markdown(f"**Regime:** {interpretar_regime(mm21, mm63)}")
    st.markdown("---")


def render_term_structure():
    """Renderiza seção Term Structure"""
    st.subheader("📈 Estrutura a Termo da IV (Term Structure)")
    
    with st.expander("ℹ️ **O que é a Estrutura a Termo da Volatilidade?**", expanded=False):
        st.markdown("""
        ### Term Structure da Volatilidade Implícita
        
        A **Estrutura a Termo** mostra como a volatilidade implícita varia entre diferentes vencimentos 
        de opções. É a "curva de juros" da volatilidade.
        
        #### Formatos da curva:
        
        📈 **Contango (curva ascendente)** - IV aumenta com o tempo:
        - Estado **normal** do mercado
        - Incerteza de longo prazo maior que curto prazo
        - Mercado "calmo" no curto prazo
        
        📉 **Backwardation (curva descendente)** - IV diminui com o tempo:
        - Estado de **stress** do mercado
        - Medo concentrado no curto prazo
        - Geralmente ocorre durante crises ou eventos
        
        ➡️ **Flat (curva plana)** - IV similar em todos os vencimentos:
        - Transição entre regimes
        - Incerteza generalizada
        
        #### Como usar:
        - **Entrada em backwardation**: Sinal de alerta
        - **Saída de backwardation para contango**: Possível fim do stress
        - **Steepness da curva**: Inclinação indica intensidade do regime
        """)
    
    # Inputs
    col_term1, col_term2, col_term3 = st.columns([1, 1, 2])
    with col_term1:
        term_asset = st.text_input("Ativo para Term Structure", value="BOVA11", key="term_struct_asset_input",
                                   help="Digite o ticker do ativo (ex: VALE3, PETR4, BOVA11)")
    with col_term2:
        manual_price = st.number_input("Preço Manual (opcional)", value=0.0, min_value=0.0, step=0.01,
                                       key="term_struct_price_input",
                                       help="Digite o preço manualmente se o Yahoo estiver bloqueando")
    
    if term_asset:
        with st.spinner(f"Buscando opções ATM de {term_asset} na B3..."):
            try:
                if manual_price > 0:
                    asset_price = manual_price
                else:
                    asset_price = get_asset_price_yesterday(term_asset)
                    if asset_price == 0.0:
                        st.warning(f"⚠️ Não foi possível obter o preço. Digite o preço de {term_asset} manualmente.")
                
                selic = get_selic_annual()
                
                if asset_price > 0:
                    df_term = calcular_term_structure(term_asset, asset_price, selic, num_vencimentos=6)
                    
                    if not df_term.empty:
                        with st.container():
                            col_chart, col_info = st.columns([3, 1])
                            
                            with col_chart:
                                st.plotly_chart(gerar_grafico_term_structure(df_term), use_container_width=True, key="term_struct_chart")
                        
                        with col_info:
                            st.metric("Preço Atual", f"R$ {asset_price:.2f}")
                            st.metric("Selic Anual", f"{selic:.2f}%")
                            
                            if len(df_term) >= 2:
                                slope = (df_term['iv'].iloc[-1] - df_term['iv'].iloc[0]) / \
                                       (df_term['days_to_exp'].iloc[-1] - df_term['days_to_exp'].iloc[0])
                                if slope > 0.01:
                                    st.success("📈 **CONTANGO** - Curva normal")
                                elif slope < -0.01:
                                    st.error("📉 **BACKWARDATION** - Stress")
                                else:
                                    st.info("➡️ **FLAT** - Curva plana")
                                
                                st.metric("IV Curto Prazo", f"{df_term['iv'].iloc[0]:.1f}%")
                                st.metric("IV Longo Prazo", f"{df_term['iv'].iloc[-1]:.1f}%")
                        
                            with st.expander("📋 Detalhes por Vencimento"):
                                df_display = df_term[['expiry_date', 'days_to_exp', 'iv', 'strike', 'option_ticker', 'option_price']].copy()
                                df_display.columns = ['Vencimento', 'Dias', 'IV (%)', 'Strike', 'Ticker Opção', 'Prêmio (R$)']
                                df_display['Vencimento'] = df_display['Vencimento'].apply(lambda x: x.strftime('%d/%m/%Y'))
                                st.dataframe(df_display, hide_index=True, use_container_width=True, key="term_struct_df")
                    else:
                        st.warning(f"Não foram encontradas opções ATM com liquidez para {term_asset}.")
                else:
                    st.error(f"Não foi possível obter o preço de {term_asset}")
            except Exception as e:
                with st.container():
                     st.error(f"Erro ao calcular Term Structure: {e}")
                     st.code(traceback.format_exc(), language="python")
    
    st.markdown("---")


def render_volatility_skew():
    """Renderiza seção Volatility Skew"""
    st.subheader("📐 Volatility Skew")
    
    with st.expander("ℹ️ **O que é Volatility Skew e como interpretar?**", expanded=False):
        st.markdown("""
        ### Volatility Skew (Inclinação da Volatilidade)
        
        O **Volatility Skew** mostra como a volatilidade implícita varia entre diferentes **strikes** 
        para um **mesmo vencimento**. É também conhecido como "smile" ou "smirk" de volatilidade.
        
        #### Formatos típicos:
        
        😊 **Smile (U invertido)** - IV maior nos extremos:
        - Comum em índices e commodities
        - Investidores precificam eventos de cauda
        
        😏 **Smirk (inclinação negativa)** - IV maior em OTM:
        - **Formato mais comum em ações e índices de ações**
        - PUTs OTM (strike < spot) têm IV maior que CALLs OTM
        - Reflete demanda por proteção contra quedas
        
        📏 **Flat (plano)** - IV similar em todos strikes:
        - Raro na prática
        - Pode indicar evento binário
        
        #### Como usar:
        - Skew alto = proteção cara → vender PUTs OTM pode ser interessante
        - Skew baixo = proteção barata → comprar proteção pode valer a pena
        """)
    
    # Inputs
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        skew_asset = st.text_input("Ativo para Skew Analysis", value="BOVA11", key="skew_asset",
                                   help="Digite o ticker do ativo")
    with col2:
        skew_months = st.selectbox("Vencimento", options=[1, 2, 3], index=0, key="skew_month_select",
                                   format_func=lambda x: f"{x} mês" if x == 1 else f"{x} meses",
                                   help="Selecione o vencimento")
    with col3:
        skew_manual_price = st.number_input("Preço Manual (opcional)", value=0.0, min_value=0.0, step=0.01,
                                            key="skew_manual_price", help="Digite o preço se Yahoo bloqueando")
    
    if skew_asset:
        with st.spinner(f"Buscando opções de {skew_asset} para análise de Skew..."):
            try:
                if skew_manual_price > 0:
                    asset_price = skew_manual_price
                else:
                    asset_price = get_asset_price_yesterday(skew_asset)
                    if asset_price == 0.0:
                        st.warning(f"⚠️ Não foi possível obter o preço. Digite o preço manualmente.")
                
                selic = get_selic_annual()
                
                if asset_price > 0:
                    current_date = date.today()
                    future_date = current_date + relativedelta(months=skew_months)
                    expiry = get_third_friday(future_date.year, future_date.month)
                    days_to_exp = (expiry - current_date).days
                    
                    if days_to_exp > 0:
                        df_skew = calcular_volatility_skew(skew_asset, asset_price, selic, expiry)
                        
                        if not df_skew.empty and len(df_skew) >= 3:
                            with st.container():
                                col_chart, col_info = st.columns([3, 1])
                                
                                with col_chart:
                                    st.plotly_chart(gerar_grafico_skew(df_skew, skew_asset), use_container_width=True, key="skew_chart")
                            
                            with col_info:
                                st.metric("Preço Atual", f"R$ {asset_price:.2f}")
                                st.metric("Vencimento", expiry.strftime('%d/%m/%Y'))
                                st.metric("Dias até Venc.", f"{days_to_exp} dias")
                                
                                # Skew Ratio
                                atm_iv = df_skew[df_skew['moneyness'].abs() < 1]['iv'].values
                                otm_5_iv = df_skew[df_skew['moneyness'].between(-6, -4)]['iv'].values
                                
                                if len(atm_iv) > 0 and len(otm_5_iv) > 0:
                                    skew_ratio = otm_5_iv[0] / atm_iv[0]
                                    if skew_ratio >= 1.20:
                                        st.error(f"**Skew Ratio**: {skew_ratio:.2f}")
                                        st.caption("⚠️ Proteção muito cara")
                                    elif skew_ratio >= 1.10:
                                        st.warning(f"**Skew Ratio**: {skew_ratio:.2f}")
                                        st.caption("📊 Demanda moderada")
                                    elif skew_ratio >= 1.00:
                                        st.success(f"**Skew Ratio**: {skew_ratio:.2f}")
                                        st.caption("✅ Skew normal")
                                    else:
                                        st.info(f"**Skew Ratio**: {skew_ratio:.2f}")
                                        st.caption("🔵 Proteção barata")
                            
                                with st.expander("📋 Detalhes por Strike"):
                                    df_display = df_skew[['strike', 'moneyness', 'iv', 'option_ticker', 'option_price']].copy()
                                    df_display.columns = ['Strike', 'Moneyness (%)', 'IV (%)', 'Ticker Opção', 'Prêmio (R$)']
                                    df_display['Strike'] = df_display['Strike'].apply(lambda x: f"R$ {x:.2f}")
                                    df_display['Moneyness (%)'] = df_display['Moneyness (%)'].apply(lambda x: f"{x:+.1f}%")
                                    df_display['IV (%)'] = df_display['IV (%)'].apply(lambda x: f"{x:.1f}%")
                                    df_display['Prêmio (R$)'] = df_display['Prêmio (R$)'].apply(lambda x: f"R$ {x:.2f}")
                                    st.dataframe(df_display, hide_index=True, use_container_width=True, key="skew_df")
                        else:
                            st.warning(f"Poucos dados disponíveis para {skew_asset}.")
                    else:
                        st.error("Vencimento inválido (já passou)")
                else:
                    st.error(f"Não foi possível obter o preço de {skew_asset}")
            except Exception as e:
                with st.container():
                    st.error(f"Erro ao calcular Volatility Skew: {e}")
                    st.code(traceback.format_exc(), language="python")
    
    st.markdown("---")


def render_historico_vxewz(vxewz_series, valor_atual, media_hist, vxewz_recent):
    """Renderiza seção de histórico VXEWZ"""
    st.subheader("📉 Histórico do VXEWZ")
    
    with st.expander("ℹ️ **Como ler este gráfico**", expanded=False):
        st.markdown("""
        Este é o gráfico histórico do índice VXEWZ.
        
        - **Linha azul**: Valor do VXEWZ
        - **Linha tracejada cinza**: Média histórica (5 anos)
        - **Linha pontilhada amarela**: Valor atual
        
        **Dica**: Use a roda do mouse para dar zoom!
        """)
    
    col_graf, col_hist = st.columns([2, 1])
    with col_graf:
        st.plotly_chart(gerar_grafico_historico_amplitude(vxewz_series, "Histórico VXEWZ", valor_atual, media_hist), use_container_width=True, key="vxewz_history_chart")
    with col_hist:
        st.plotly_chart(gerar_histograma_amplitude(vxewz_recent, "Distribuição", valor_atual, media_hist, nbins=50), use_container_width=True, key="vxewz_dist_chart")
    
    st.markdown("---")


def render_iv_rank_historico(iv_rank_series):
    """Renderiza seção IV Rank histórico"""
    st.subheader("🎯 IV Rank Histórico")
    
    with st.expander("ℹ️ **O que é IV Rank e como usar**", expanded=False):
        st.markdown("""
        ### IV Rank (Ranking de Volatilidade Implícita)
        
        O **IV Rank** indica onde a volatilidade atual se encontra em relação ao range dos últimos 252 dias.
        
        **Fórmula**: `(IV_atual - IV_mín_252d) / (IV_máx_252d - IV_mín_252d) × 100`
        
        #### Interpretação:
        | IV Rank | Significado | Estratégia |
        |---------|-------------|------------|
        | 0-20% | IV muito baixa | Comprar opções |
        | 20-40% | IV abaixo da média | Neutro a comprador |
        | 40-60% | IV na média | Neutro |
        | 60-80% | IV acima da média | Neutro a vendedor |
        | 80-100% | IV muito alta | Vender opções |
        """)
    
    st.plotly_chart(gerar_grafico_iv_rank(iv_rank_series), use_container_width=True, key="iv_rank_chart")
    st.markdown("---")


def render_bandas_bollinger(vxewz_series):
    """Renderiza seção Bandas de Bollinger"""
    st.subheader("📊 VXEWZ com Bandas de Bollinger")
    
    with st.expander("ℹ️ **Como interpretar as Bandas de Bollinger**", expanded=False):
        st.markdown("""
        ### Bandas de Bollinger aplicadas ao VXEWZ
        
        - **Linha central**: Média móvel de 20 períodos
        - **Banda superior**: MM20 + 2 desvios padrão
        - **Banda inferior**: MM20 - 2 desvios padrão
        
        #### Sinais:
        🔴 **Toque na banda superior**: IV extremamente elevada → vender opções
        🔵 **Toque na banda inferior**: IV extremamente baixa → comprar opções
        
        ⚠️ **Volatilidade é mean-reverting**: Extremos são oportunidades!
        """)
    
    st.plotly_chart(gerar_grafico_iv_bandas(vxewz_series), use_container_width=True, key="bb_chart")
    st.markdown("---")


def render_regime_volatilidade(vxewz_series):
    """Renderiza seção Regime de Volatilidade"""
    st.subheader("🔄 Regime de Volatilidade (Contango vs Backwardation)")
    
    with st.expander("ℹ️ **Entendendo os regimes de volatilidade**", expanded=False):
        st.markdown("""
        ### Contango vs Backwardation
        
        Compara volatilidade de **curto prazo (MM21)** com **médio prazo (MM63)**.
        
        #### Contango (área verde):
        - MM21 < MM63 → Volatilidade de curto prazo menor
        - **Estado normal** do mercado
        
        #### Backwardation (área vermelha):
        - MM21 > MM63 → Volatilidade de curto prazo maior
        - **Estado de stress** do mercado
        """)
    
    st.plotly_chart(gerar_grafico_regime_volatilidade(vxewz_series), use_container_width=True, key="regime_chart")
    st.markdown("---")


def render_roc_volatilidade(vxewz_series):
    """Renderiza seção ROC"""
    st.subheader("🚀 Taxa de Variação da Volatilidade (ROC)")
    
    with st.expander("ℹ️ **Interpretando o momentum da volatilidade**", expanded=False):
        st.markdown("""
        ### Rate of Change (ROC) da Volatilidade
        
        - **ROC 5d**: Variação nos últimos 5 dias úteis
        - **ROC 21d**: Variação nos últimos 21 dias úteis
        
        #### Interpretação:
        📈 **Spike > +50%**: Evento de stress → vender volatilidade após spike
        📉 **Queda < -30%**: Volatilidade colapsando → fim de crise
        """)
    
    st.plotly_chart(gerar_grafico_roc_volatilidade(vxewz_series), use_container_width=True, key="roc_chart")
    st.markdown("---")


def render_heatmaps_iv_rank(vxewz_series, iv_rank_series, iv_rank_atual, df_analise_base, cutoff_5y):
    """Renderiza seção Heatmaps por IV Rank"""
    st.subheader("🗺️ Análise de Retornos por Faixa de IV Rank")
    
    with st.expander("ℹ️ **Como ler os heatmaps**", expanded=False):
        st.markdown("""
        Heatmaps mostram **retorno médio** e **taxa de acerto** por faixa de IV Rank.
        
        - Cores verdes = retornos positivos
        - Cores vermelhas = retornos negativos
        - Borda branca = faixa atual
        """)
    
    iv_rank_for_analysis = iv_rank_series.rename('IV_Rank')
    df_analise_ivr = df_analise_base.join(iv_rank_for_analysis, how='inner').dropna()
    
    passo = 10
    resultados_ivr = analisar_retornos_por_faixa(df_analise_ivr, 'IV_Rank', passo, 0, 100, '%')
    
    faixa_atual_val = int(iv_rank_atual // passo) * passo
    faixa_atual = f'{faixa_atual_val} a {faixa_atual_val + passo}%'
    
    col_hist, col_heat = st.columns([1, 2])
    
    with col_hist:
        st.plotly_chart(gerar_histograma_amplitude(iv_rank_series.dropna(), "Distribuição do IV Rank", iv_rank_atual, iv_rank_series.mean(), nbins=50), use_container_width=True, key="iv_rank_dist_chart")
    
    with col_heat:
        for ativo in ATIVOS_ANALISE:
            ativo_clean = ativo.replace('.SA', '')
            sufixo = f" ({ativo_clean})"
            st.markdown(f"**{ativo}**")
            cols_ativo = [c for c in resultados_ivr['Retorno Médio'].columns if ativo_clean in c]
            
            if cols_ativo:
                df_ret = resultados_ivr['Retorno Médio'][cols_ativo].rename(columns=lambda x: x.replace(sufixo, ''))
                df_hit = resultados_ivr['Taxa de Acerto'][cols_ativo].rename(columns=lambda x: x.replace(sufixo, ''))
                
                c1, c2 = st.columns(2)
                c1.plotly_chart(gerar_heatmap_amplitude(df_ret, faixa_atual, "Retorno Médio"), use_container_width=True, key=f"heatmap_ret_{ativo_clean}")
                c2.plotly_chart(gerar_heatmap_amplitude(df_hit, faixa_atual, "Taxa de Acerto"), use_container_width=True, key=f"heatmap_hit_{ativo_clean}")
    
    st.markdown("---")


def render_heatmaps_nivel_absoluto(vxewz_series, vxewz_recent, valor_atual, df_analise_base):
    """Renderiza seção Heatmaps por nível absoluto"""
    st.subheader("🗺️ Análise de Retornos por Nível de VXEWZ")
    
    with st.expander("ℹ️ **Diferença entre IV Rank e Nível Absoluto**", expanded=False):
        st.markdown("""
        O **IV Rank** normaliza pelo range do último ano, mas o **nível absoluto** também é importante.
        
        Analisar por faixas absolutas (20-25, 25-30, etc.) ajuda a entender comportamento 
        em diferentes *níveis* de volatilidade.
        """)
    
    vxewz_for_analysis = vxewz_series.rename('VXEWZ')
    df_analise_vx = df_analise_base.join(vxewz_for_analysis, how='inner').dropna()
    
    passo_vx = 5
    min_vx = int(np.floor(vxewz_recent.min() / passo_vx)) * passo_vx
    max_vx = int(np.ceil(vxewz_recent.max() / passo_vx)) * passo_vx
    if max_vx == min_vx:
        max_vx += passo_vx
    
    resultados_vx = analisar_retornos_por_faixa(df_analise_vx, 'VXEWZ', passo_vx, min_vx, max_vx, '')
    
    faixa_atual_vx_val = int(valor_atual // passo_vx) * passo_vx
    faixa_atual_vx = f'{faixa_atual_vx_val} a {faixa_atual_vx_val + passo_vx}'
    
    for ativo in ATIVOS_ANALISE:
        ativo_clean = ativo.replace('.SA', '')
        sufixo = f" ({ativo_clean})"
        st.markdown(f"**{ativo}**")
        cols_ativo = [c for c in resultados_vx['Retorno Médio'].columns if ativo_clean in c]
        
        if cols_ativo:
            df_ret = resultados_vx['Retorno Médio'][cols_ativo].rename(columns=lambda x: x.replace(sufixo, ''))
            df_hit = resultados_vx['Taxa de Acerto'][cols_ativo].rename(columns=lambda x: x.replace(sufixo, ''))
            
            c1, c2 = st.columns(2)
            c1.plotly_chart(gerar_heatmap_amplitude(df_ret, faixa_atual_vx, "Retorno Médio"), use_container_width=True, key=f"heatmap_vx_ret_{ativo_clean}")
            c2.plotly_chart(gerar_heatmap_amplitude(df_hit, faixa_atual_vx, "Taxa de Acerto"), use_container_width=True, key=f"heatmap_vx_hit_{ativo_clean}")
    
    st.markdown("---")


def render_estatisticas_descritivas(vxewz_recent, iv_rank_series, cutoff_5y):
    """Renderiza seção estatísticas descritivas"""
    with st.expander("📋 Estatísticas Descritivas Completas"):
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            st.markdown("**VXEWZ (5 Anos)**")
            stats_df = pd.DataFrame({
                'Estatística': ['Média', 'Mediana', 'Desvio Padrão', 'Mínimo', 'Máximo', 'Assimetria', 'Curtose'],
                'Valor': [
                    f"{vxewz_recent.mean():.2f}",
                    f"{vxewz_recent.median():.2f}",
                    f"{vxewz_recent.std():.2f}",
                    f"{vxewz_recent.min():.2f}",
                    f"{vxewz_recent.max():.2f}",
                    f"{vxewz_recent.skew():.2f}",
                    f"{vxewz_recent.kurtosis():.2f}"
                ]
            })
            st.dataframe(stats_df, hide_index=True, use_container_width=True, key="stats_desc_df")
        
        with col_stat2:
            st.markdown("**IV Rank (5 Anos)**")
            iv_rank_recent = iv_rank_series[iv_rank_series.index >= cutoff_5y].dropna()
            stats_ivr = pd.DataFrame({
                'Estatística': ['Média', 'Mediana', 'Desvio Padrão', 'Mínimo', 'Máximo', '% Tempo acima 80', '% Tempo abaixo 20'],
                'Valor': [
                    f"{iv_rank_recent.mean():.1f}%",
                    f"{iv_rank_recent.median():.1f}%",
                    f"{iv_rank_recent.std():.1f}%",
                    f"{iv_rank_recent.min():.1f}%",
                    f"{iv_rank_recent.max():.1f}%",
                    f"{(iv_rank_recent >= 80).mean() * 100:.1f}%",
                    f"{(iv_rank_recent <= 20).mean() * 100:.1f}%"
                ]
            })
            st.dataframe(stats_ivr, hide_index=True, use_container_width=True, key="stats_ivr_df")



# ============================================================
# FUNÇÃO PRINCIPAL - RENDER
# ============================================================
def render():
    """Função principal de renderização da página"""
    
    # Debug inicial - deve aparecer sempre
    st.write("### 🔍 Debug: Iniciando renderização da página...")
    
    # 1. Header e explicação
    render_header_explicacao()
    st.markdown("---")
    
    try:
        # 2. Carregar segredos
        st.write("DEBUG: Carregando secrets...")
        try:
            FRED_API_KEY = st.secrets["general"]["FRED_API_KEY"]
        except Exception as e:
            st.error(f"❌ Erro ao acessar secrets: {e}. Certifique-se que FRED_API_KEY existe em [general].")
            return
        
        # 3. Carregar dados FRED
        st.write("DEBUG: Chamando API do FRED...")
        with st.spinner("Carregando dados do VXEWZ..."):
            df_vxewz = carregar_dados_fred(FRED_API_KEY, {'VXEWZCLS': 'CBOE Brazil ETF Volatility Index (VXEWZ)'})
        
        if df_vxewz.empty:
            st.error("Não foi possível carregar os dados do índice VXEWZ.")
            return
        
        st.write("DEBUG: Dados FRED carregados com sucesso.")
        vxewz_series = df_vxewz['VXEWZCLS'].dropna()
        if vxewz_series.empty:
            st.error("Série do VXEWZ está vazia.")
            return
        
        # 4. Cálculos Iniciais
        st.write("DEBUG: Iniciando cálculos estatísticos...")
        cutoff_5y = vxewz_series.index.max() - pd.DateOffset(years=5)
        vxewz_recent = vxewz_series[vxewz_series.index >= cutoff_5y]
        
        # Cálculos principais
        valor_atual = vxewz_series.iloc[-1]
        media_hist = vxewz_recent.mean()
        std_hist = vxewz_recent.std()
        z_score = (valor_atual - media_hist) / std_hist
        percentil = stats.percentileofscore(vxewz_recent, valor_atual)
        iv_rank_series = calcular_iv_rank(vxewz_series, periodo=252)
        iv_rank_atual = iv_rank_series.iloc[-1]
        mm21 = vxewz_series.rolling(window=21).mean().iloc[-1]
        mm63 = vxewz_series.rolling(window=63).mean().iloc[-1]
        
        # Renderizar seções
        render_metricas_principais(valor_atual, media_hist, iv_rank_atual, percentil, z_score, mm21, vxewz_series)
        render_diagnostico(iv_rank_atual, mm21, mm63)
        render_term_structure()
        render_volatility_skew()
        render_historico_vxewz(vxewz_series, valor_atual, media_hist, vxewz_recent)
        render_iv_rank_historico(iv_rank_series)
        render_bandas_bollinger(vxewz_series)
        render_regime_volatilidade(vxewz_series)
        render_roc_volatilidade(vxewz_series)
        
        # Preparar dados para heatmaps (historico longo via yfinance)
        import yfinance as yf
        df_analise_base = pd.DataFrame(index=vxewz_series.index).sort_index()
        
        for ativo in ATIVOS_ANALISE:
            try:
                # yf já importado no topo
                dados_ativo = yf.download(ativo, start=vxewz_series.index.min(), end=vxewz_series.index.max(), auto_adjust=False, progress=False)
                if not dados_ativo.empty:
                    if isinstance(dados_ativo.columns, pd.MultiIndex):
                        dados_ativo.columns = dados_ativo.columns.get_level_values(0)
                    
                    if 'Adj Close' in dados_ativo.columns:
                        price_col = dados_ativo['Adj Close']
                    elif 'Close' in dados_ativo.columns:
                        price_col = dados_ativo['Close']
                    else:
                        continue
                    
                    ativo_label = ativo.replace('.SA', '')
                    for nome_periodo, dias in PERIODOS_RETORNO.items():
                        df_analise_base[f'retorno_{nome_periodo} ({ativo_label})'] = price_col.pct_change(periods=dias).shift(-dias) * 100
            except Exception:
                pass
        
        render_heatmaps_iv_rank(vxewz_series, iv_rank_series, iv_rank_atual, df_analise_base, cutoff_5y)
        render_heatmaps_nivel_absoluto(vxewz_series, vxewz_recent, valor_atual, df_analise_base)
        render_estatisticas_descritivas(vxewz_recent, iv_rank_series, cutoff_5y)
    
    except Exception as e:
        st.error(f"❌ Erro inesperado na página Volatilidade IV: {e}")
        st.code(traceback.format_exc(), language="python")


