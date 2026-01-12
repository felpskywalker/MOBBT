
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
from src.models.put_utils import get_selic_annual, get_third_friday, generate_put_ticker, get_asset_price_yesterday
from src.data_loaders.b3_api import fetch_option_price_b3
from src.models.black_scholes import implied_volatility

def calcular_term_structure(asset_ticker, asset_price, selic_annual, num_vencimentos=6):
    """
    Calcula a estrutura a termo da volatilidade implícita para opções ATM.
    
    Returns:
        DataFrame com colunas: days_to_exp, iv, expiry_date
    """
    current_date = date.today()
    results = []
    
    # Gera vencimentos futuros (próximos N meses)
    for i in range(1, num_vencimentos + 1):
        try:
            future_date = current_date + relativedelta(months=i)
            expiry = get_third_friday(future_date.year, future_date.month)
            days_to_exp = (expiry - current_date).days
            
            if days_to_exp <= 0:
                continue
            
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
                
                # Calcula IV
                try:
                    iv = implied_volatility(option_price, asset_price, atm_strike, T, r)
                    iv_pct = iv * 100
                    
                    if 5 < iv_pct < 200:  # Filtra valores absurdos
                        results.append({
                            'days_to_exp': days_to_exp,
                            'iv': iv_pct,
                            'expiry_date': expiry,
                            'strike': atm_strike,
                            'option_ticker': option_ticker,
                            'option_price': option_price
                        })
                except:
                    pass
        except Exception as e:
            continue
    
    return pd.DataFrame(results)

def gerar_grafico_term_structure(df_term):
    """Gera gráfico de estrutura a termo da IV"""
    if df_term.empty:
        fig = go.Figure()
        fig.update_layout(
            title_text="Sem dados disponíveis para Term Structure",
            template='brokeberg'
        )
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
    
    # Anotações com os vencimentos
    for _, row in df_term.iterrows():
        fig.add_annotation(
            x=row['days_to_exp'],
            y=row['iv'],
            text=f"{row['expiry_date'].strftime('%d/%m')}",
            showarrow=False,
            yshift=15,
            font=dict(size=10, color='gray')
        )
    
    # Linha de tendência (regressão linear)
    if len(df_term) >= 2:
        z = np.polyfit(df_term['days_to_exp'], df_term['iv'], 1)
        p = np.poly1d(z)
        x_line = np.linspace(df_term['days_to_exp'].min(), df_term['days_to_exp'].max(), 50)
        fig.add_trace(go.Scatter(
            x=x_line,
            y=p(x_line),
            mode='lines',
            name='Tendência',
            line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dash')
        ))
    
    fig.update_layout(
        title_text='Estrutura a Termo da Volatilidade Implícita',
        title_x=0,
        template='brokeberg',
        xaxis_title="Dias até Vencimento",
        yaxis_title="Volatilidade Implícita (%)",
        showlegend=False,
        height=400
    )
    
    return fig


def calcular_iv_rank(series, periodo=252):
    """Calcula o IV Rank rolling baseado em um período."""
    iv_min = series.rolling(window=periodo).min()
    iv_max = series.rolling(window=periodo).max()
    iv_rank = ((series - iv_min) / (iv_max - iv_min)) * 100
    return iv_rank

def interpretar_iv_rank(iv_rank, percentil):
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

def render():
    st.header("📊 Análise de Volatilidade Implícita (VXEWZ)")
    
    # Explicação inicial detalhada
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

    FRED_API_KEY = 'd78668ca6fc142a1248f7cb9132916b0'
    ATIVOS_ANALISE = ['BOVA11.SA', 'SMAL11.SA']
    PERIODOS_RETORNO = {'1 Mês': 21, '3 Meses': 63, '6 Meses': 126, '1 Ano': 252}

    with st.spinner("Carregando dados do VXEWZ..."):
        df_vxewz = carregar_dados_fred(FRED_API_KEY, {'VXEWZCLS': 'CBOE Brazil ETF Volatility Index (VXEWZ)'})

    if df_vxewz.empty:
        st.error("Não foi possível carregar os dados do índice VXEWZ a partir do FRED.")
        return

    vxewz_series = df_vxewz['VXEWZCLS'].dropna()
    if vxewz_series.empty:
        st.error("Série do VXEWZ está vazia.")
        return

    # Série recente (5 anos)
    cutoff_5y = vxewz_series.index.max() - pd.DateOffset(years=5)
    vxewz_recent = vxewz_series[vxewz_series.index >= cutoff_5y]

    # --- Cálculos ---
    valor_atual = vxewz_series.iloc[-1]
    media_hist = vxewz_recent.mean()
    std_hist = vxewz_recent.std()
    z_score = (valor_atual - media_hist) / std_hist
    percentil = stats.percentileofscore(vxewz_recent, valor_atual)
    
    # IV Rank
    iv_rank_series = calcular_iv_rank(vxewz_series, periodo=252)
    iv_rank_atual = iv_rank_series.iloc[-1]
    
    # Médias móveis para regime
    mm21 = vxewz_series.rolling(window=21).mean().iloc[-1]
    mm63 = vxewz_series.rolling(window=63).mean().iloc[-1]

    # ===========================================
    # SEÇÃO 1: MÉTRICAS PRINCIPAIS
    # ===========================================
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

    # Interpretação
    st.markdown("### 📝 Diagnóstico Atual")
    col_int1, col_int2 = st.columns(2)
    with col_int1:
        st.markdown(f"**IV Rank:** {interpretar_iv_rank(iv_rank_atual, percentil)}")
    with col_int2:
        st.markdown(f"**Regime:** {interpretar_regime(mm21, mm63)}")

    st.markdown("---")

    # ===========================================
    # SEÇÃO 2: TERM STRUCTURE (Estrutura a Termo)
    # ===========================================
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
    
    # Input para escolher ativo
    col_term1, col_term2 = st.columns([1, 3])
    with col_term1:
        term_asset = st.text_input("Ativo para Term Structure", value="BOVA11", 
                                   help="Digite o ticker do ativo (ex: VALE3, PETR4, BOVA11)")
    
    if term_asset:
        with st.spinner(f"Buscando opções ATM de {term_asset} na B3..."):
            try:
                import yfinance as yf
                
                # Busca preço do ativo diretamente
                full_ticker = term_asset if term_asset.endswith(".SA") else f"{term_asset}.SA"
                stock = yf.Ticker(full_ticker)
                hist = stock.history(period="5d")
                
                asset_price = 0.0
                if not hist.empty:
                    if isinstance(hist.columns, pd.MultiIndex):
                        hist.columns = hist.columns.get_level_values(0)
                    if 'Close' in hist.columns:
                        hist = hist.dropna(subset=['Close'])
                        if len(hist) >= 1:
                            asset_price = float(hist['Close'].iloc[-1])
                
                selic = get_selic_annual()
                
                if asset_price > 0:
                    # Calcula term structure
                    df_term = calcular_term_structure(term_asset, asset_price, selic, num_vencimentos=6)
                    
                    if not df_term.empty:
                        col_term_chart, col_term_info = st.columns([3, 1])
                        
                        with col_term_chart:
                            st.plotly_chart(gerar_grafico_term_structure(df_term), use_container_width=True)
                        
                        with col_term_info:
                            st.metric("Preço Atual", f"R$ {asset_price:.2f}")
                            st.metric("Selic Anual", f"{selic:.2f}%")
                            
                            # Análise da inclinação
                            if len(df_term) >= 2:
                                slope = (df_term['iv'].iloc[-1] - df_term['iv'].iloc[0]) / (df_term['days_to_exp'].iloc[-1] - df_term['days_to_exp'].iloc[0])
                                if slope > 0.01:
                                    st.success("📈 **CONTANGO** - Curva normal")
                                elif slope < -0.01:
                                    st.error("📉 **BACKWARDATION** - Stress")
                                else:
                                    st.info("➡️ **FLAT** - Curva plana")
                                    
                                st.metric("IV Curto Prazo", f"{df_term['iv'].iloc[0]:.1f}%")
                                st.metric("IV Longo Prazo", f"{df_term['iv'].iloc[-1]:.1f}%")
                        
                        # Tabela com detalhes
                        with st.expander("📋 Detalhes por Vencimento"):
                            df_display = df_term[['expiry_date', 'days_to_exp', 'iv', 'strike', 'option_ticker', 'option_price']].copy()
                            df_display.columns = ['Vencimento', 'Dias', 'IV (%)', 'Strike', 'Ticker Opção', 'Prêmio (R$)']
                            df_display['Vencimento'] = df_display['Vencimento'].apply(lambda x: x.strftime('%d/%m/%Y'))
                            st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.warning(f"Não foram encontradas opções ATM com liquidez para {term_asset}. Tente outro ativo.")
                else:
                    st.error(f"Não foi possível obter o preço de {term_asset}")
            except Exception as e:
                st.error(f"Erro ao calcular Term Structure: {e}")

    st.markdown("---")

    # ===========================================
    # SEÇÃO 3: HISTÓRICO VXEWZ (do market_breadth)
    # ===========================================
    st.subheader("📉 Histórico do VXEWZ")
    
    with st.expander("ℹ️ **Como ler este gráfico**", expanded=False):
        st.markdown("""
        Este é o gráfico histórico do índice VXEWZ mostrando a evolução da volatilidade implícita ao longo do tempo.
        
        - **Linha azul**: Valor do VXEWZ
        - **Linha tracejada cinza**: Média histórica (5 anos)
        - **Linha pontilhada amarela**: Valor atual
        - **Botões de período**: Selecione 6M, 1A, 2A, 5A ou Tudo para ajustar a visualização
        
        **Dica**: Use a roda do mouse para dar zoom no gráfico!
        """)
    
    col_graf, col_hist = st.columns([2, 1])
    with col_graf:
        st.plotly_chart(gerar_grafico_historico_amplitude(vxewz_series, "Histórico VXEWZ", valor_atual, media_hist), use_container_width=True)
    with col_hist:
        st.plotly_chart(gerar_histograma_amplitude(vxewz_recent, "Distribuição", valor_atual, media_hist, nbins=50), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 3: IV RANK HISTÓRICO
    # ===========================================
    st.subheader("🎯 IV Rank Histórico")
    
    with st.expander("ℹ️ **O que é IV Rank e como usar**", expanded=False):
        st.markdown("""
        ### IV Rank (Ranking de Volatilidade Implícita)
        
        O **IV Rank** indica onde a volatilidade atual se encontra em relação ao seu range dos últimos 252 dias (1 ano).
        
        **Fórmula**: `(IV_atual - IV_mín_252d) / (IV_máx_252d - IV_mín_252d) × 100`
        
        #### Interpretação:
        | IV Rank | Significado | Estratégia |
        |---------|-------------|------------|
        | 0-20% | IV muito baixa vs último ano | Comprar opções (prêmios baratos) |
        | 20-40% | IV abaixo da média | Neutro a comprador |
        | 40-60% | IV na média | Neutro |
        | 60-80% | IV acima da média | Neutro a vendedor |
        | 80-100% | IV muito alta vs último ano | Vender opções (prêmios altos) |
        
        #### Diferença entre IV Rank e Percentil:
        - **IV Rank**: Posição relativa ao mínimo/máximo do período
        - **Percentil**: % de dias em que a IV foi menor que a atual
        
        Um IV Rank de 90% significa que estamos **próximos da máxima** do ano.
        Um Percentil de 90% significa que 90% dos dias tiveram IV **menor** que hoje.
        """)
    
    st.plotly_chart(gerar_grafico_iv_rank(iv_rank_series), use_container_width=True)
    
    st.markdown("---")

    # ===========================================
    # SEÇÃO 4: VXEWZ COM BANDAS DE BOLLINGER
    # ===========================================
    st.subheader("📊 VXEWZ com Bandas de Bollinger")
    
    with st.expander("ℹ️ **Como interpretar as Bandas de Bollinger na Volatilidade**", expanded=False):
        st.markdown("""
        ### Bandas de Bollinger aplicadas ao VXEWZ
        
        As bandas consistem em:
        - **Linha central (laranja)**: Média móvel de 20 períodos
        - **Banda superior**: MM20 + 2 desvios padrão
        - **Banda inferior**: MM20 - 2 desvios padrão
        - **Área sombreada**: Região entre as bandas
        
        #### Sinais importantes:
        
        🔴 **Toque na banda superior**: Volatilidade extremamente elevada. Geralmente indica:
        - Pico de stress/medo
        - Possível reversão à média (IV tende a cair)
        - Bom momento para vender opções
        
        🔵 **Toque na banda inferior**: Volatilidade extremamente baixa. Geralmente indica:
        - Complacência excessiva
        - Possível aumento de volatilidade
        - Bom momento para comprar opções/proteção
        
        ⚠️ **Volatilidade é mean-reverting**: Ela tende a voltar para a média. Extremos são oportunidades!
        """)
    
    st.plotly_chart(gerar_grafico_iv_bandas(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 5: REGIME DE VOLATILIDADE
    # ===========================================
    st.subheader("🔄 Regime de Volatilidade (Contango vs Backwardation)")
    
    with st.expander("ℹ️ **Entendendo os regimes de volatilidade**", expanded=False):
        st.markdown("""
        ### Contango vs Backwardation
        
        Este gráfico compara a volatilidade de **curto prazo (MM21)** com a de **médio prazo (MM63)**.
        
        #### Contango (área verde - spread negativo):
        - MM21 < MM63
        - Volatilidade de curto prazo **menor** que a de médio prazo
        - **Estado normal** do mercado
        - Investidores não estão preocupados com o curto prazo
        
        #### Backwardation (área vermelha - spread positivo):
        - MM21 > MM63
        - Volatilidade de curto prazo **maior** que a de médio prazo
        - **Estado de stress** do mercado
        - Investidores estão pagando prêmio por proteção de curto prazo
        - Geralmente coincide com correções ou crises
        
        #### Como usar:
        - **Entrada em backwardation**: Sinal de alerta - considere proteção
        - **Saída de backwardation**: Possível fim do stress - oportunidade de compra
        - **Contango prolongado**: Complacência - cuidado com surpresas
        """)
    
    st.plotly_chart(gerar_grafico_regime_volatilidade(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 6: TAXA DE VARIAÇÃO (ROC)
    # ===========================================
    st.subheader("🚀 Taxa de Variação da Volatilidade (ROC)")
    
    with st.expander("ℹ️ **Interpretando o momentum da volatilidade**", expanded=False):
        st.markdown("""
        ### Rate of Change (ROC) da Volatilidade
        
        O ROC mede a **velocidade de mudança** da volatilidade em dois horizontes:
        - **ROC 5d (azul)**: Variação percentual nos últimos 5 dias úteis
        - **ROC 21d (laranja)**: Variação percentual nos últimos 21 dias úteis (1 mês)
        
        #### Interpretação:
        
        📈 **Spike positivo (> +50%)**:
        - Evento de stress agudo
        - Volatilidade explodiu rapidamente
        - Geralmente coincide com quedas bruscas do mercado
        - Após o spike, IV tende a normalizar (mean reversion)
        
        📉 **Queda acentuada (< -30%)**:
        - Volatilidade colapsando
        - Mercado entrando em modo de complacência
        - Pode indicar fim de crise ou início de rally
        
        #### Uso prático:
        - Spikes extremos no ROC 5d são oportunidades para vender volatilidade
        - Divergências entre ROC 5d e ROC 21d podem indicar mudanças de regime
        """)
    
    st.plotly_chart(gerar_grafico_roc_volatilidade(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 7: HEATMAPS DE RETORNO POR FAIXA DE IV RANK
    # ===========================================
    st.subheader("🗺️ Análise de Retornos por Faixa de IV Rank")
    
    with st.expander("ℹ️ **Como ler os heatmaps**", expanded=False):
        st.markdown("""
        ### Heatmaps de Retorno vs IV Rank
        
        Estes heatmaps mostram o **retorno médio** e **taxa de acerto** do mercado brasileiro 
        (BOVA11/SMAL11) em diferentes horizontes de tempo, agrupados por faixa de IV Rank.
        
        #### Retorno Médio:
        - Mostra o retorno percentual médio para cada combinação de IV Rank e horizonte
        - Cores verdes = retornos positivos
        - Cores vermelhas = retornos negativos
        
        #### Taxa de Acerto:
        - % de vezes que o retorno foi positivo para cada combinação
        - Valores acima de 50% = mais vezes positivo que negativo
        
        #### Como usar:
        - Identifique quais faixas de IV Rank têm melhor retorno histórico
        - A borda branca indica a faixa atual do IV Rank
        - Use como guia probabilístico, não como regra absoluta
        
        **Exemplo**: Se IV Rank 80-100% tem retorno médio de +8% em 3 meses com taxa de acerto de 70%, 
        significa que historicamente foi bom comprar o mercado quando a IV estava muito alta.
        """)

    # Preparar dados para heatmap
    import yfinance as yf
    
    df_analise_base = pd.DataFrame(index=vxewz_series.index).sort_index()
    
    for ativo in ATIVOS_ANALISE:
        try:
            dados_ativo = yf.download(ativo, start=vxewz_series.index.min(), end=vxewz_series.index.max(), auto_adjust=False, progress=False)
            if not dados_ativo.empty:
                if 'Adj Close' in dados_ativo.columns:
                    price_series = dados_ativo[['Adj Close']]
                else:
                    price_series = dados_ativo[['Close']]
                price_series.columns = ['price']
                ativo_label = ativo.replace('.SA', '')
                for nome_periodo, dias in PERIODOS_RETORNO.items():
                    df_analise_base[f'retorno_{nome_periodo} ({ativo_label})'] = price_series['price'].pct_change(periods=dias).shift(-dias) * 100
        except Exception:
            pass

    # Análise por faixa de IV Rank
    iv_rank_for_analysis = iv_rank_series.rename('IV_Rank')
    df_analise_ivr = df_analise_base.join(iv_rank_for_analysis, how='inner').dropna()

    passo = 10
    resultados_ivr = analisar_retornos_por_faixa(df_analise_ivr, 'IV_Rank', passo, 0, 100, '%')

    faixa_atual_val = int(iv_rank_atual // passo) * passo
    faixa_atual = f'{faixa_atual_val} a {faixa_atual_val + passo}%'

    col_hist, col_heat = st.columns([1, 2])
    
    with col_hist:
        st.plotly_chart(gerar_histograma_amplitude(iv_rank_series.dropna(), "Distribuição do IV Rank", iv_rank_atual, iv_rank_series.mean(), nbins=50), use_container_width=True)
    
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
                c1.plotly_chart(gerar_heatmap_amplitude(df_ret, faixa_atual, "Retorno Médio"), use_container_width=True)
                c2.plotly_chart(gerar_heatmap_amplitude(df_hit, faixa_atual, "Taxa de Acerto"), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 8: HEATMAPS POR NÍVEL ABSOLUTO DE VXEWZ
    # ===========================================
    st.subheader("🗺️ Análise de Retornos por Nível de VXEWZ")
    
    with st.expander("ℹ️ **Diferença entre IV Rank e Nível Absoluto**", expanded=False):
        st.markdown("""
        ### Por que analisar pelo nível absoluto também?
        
        O **IV Rank** normaliza a volatilidade pelo range do último ano, mas o **nível absoluto** 
        do VXEWZ também carrega informação importante.
        
        Por exemplo:
        - VXEWZ = 25 com IV Rank = 80% significa que 25 é alto *para o último ano*
        - VXEWZ = 25 historicamente pode ser um nível "normal" ou até baixo
        
        Analisar por faixas absolutas (20-25, 25-30, etc.) ajuda a entender o comportamento 
        do mercado em diferentes *níveis* de volatilidade, independente do contexto recente.
        """)
    
    # Análise por faixa de VXEWZ absoluto
    vxewz_for_analysis = vxewz_series.rename('VXEWZ')
    df_analise_vx = df_analise_base.join(vxewz_for_analysis, how='inner').dropna()
    
    passo_vx = 5
    min_vx = int(np.floor(vxewz_recent.min() / passo_vx)) * passo_vx
    max_vx = int(np.ceil(vxewz_recent.max() / passo_vx)) * passo_vx
    if max_vx == min_vx: max_vx += passo_vx
    
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
            c1.plotly_chart(gerar_heatmap_amplitude(df_ret, faixa_atual_vx, "Retorno Médio"), use_container_width=True)
            c2.plotly_chart(gerar_heatmap_amplitude(df_hit, faixa_atual_vx, "Taxa de Acerto"), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 9: ESTATÍSTICAS DESCRITIVAS
    # ===========================================
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
            st.dataframe(stats_df, hide_index=True, use_container_width=True)
        
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
            st.dataframe(stats_ivr, hide_index=True, use_container_width=True)
