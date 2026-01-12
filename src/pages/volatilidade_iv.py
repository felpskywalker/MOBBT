
import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
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
    st.header("Análise de Volatilidade Implícita (VXEWZ)")
    st.info(
        "O índice **VXEWZ** mede a volatilidade implícita das opções do ETF EWZ (iShares MSCI Brazil). "
        "Valores altos indicam stress e medo no mercado brasileiro, enquanto valores baixos indicam complacência."
    )
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
    st.subheader("📊 Métricas Principais")
    
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
    st.markdown("### 📝 Interpretação")
    col_int1, col_int2 = st.columns(2)
    with col_int1:
        st.markdown(f"**IV Rank:** {interpretar_iv_rank(iv_rank_atual, percentil)}")
    with col_int2:
        st.markdown(f"**Regime:** {interpretar_regime(mm21, mm63)}")

    st.markdown("---")

    # ===========================================
    # SEÇÃO 2: IV RANK HISTÓRICO
    # ===========================================
    st.subheader("📈 IV Rank Histórico")
    st.plotly_chart(gerar_grafico_iv_rank(iv_rank_series), use_container_width=True)
    
    st.markdown("---")

    # ===========================================
    # SEÇÃO 3: VXEWZ COM BANDAS DE BOLLINGER
    # ===========================================
    st.subheader("📉 VXEWZ com Bandas de Bollinger")
    st.caption("Bandas de 2 desvios padrão (20 períodos). Toques na banda superior indicam volatilidade extrema.")
    st.plotly_chart(gerar_grafico_iv_bandas(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 4: REGIME DE VOLATILIDADE
    # ===========================================
    st.subheader("🔄 Regime de Volatilidade (Contango vs Backwardation)")
    st.caption("Compara MM21 vs MM63. Backwardation (vermelho) indica stress; Contango (verde) indica normalidade.")
    st.plotly_chart(gerar_grafico_regime_volatilidade(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 5: TAXA DE VARIAÇÃO (ROC)
    # ===========================================
    st.subheader("🚀 Taxa de Variação da Volatilidade (ROC)")
    st.caption("Mede o momentum da volatilidade. Spikes acima de +50% indicam eventos de stress agudo.")
    st.plotly_chart(gerar_grafico_roc_volatilidade(vxewz_series), use_container_width=True)

    st.markdown("---")

    # ===========================================
    # SEÇÃO 6: DISTRIBUIÇÃO E HEATMAPS
    # ===========================================
    st.subheader("📊 Distribuição e Análise de Retornos por Faixa de IV Rank")

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
    # SEÇÃO 7: ESTATÍSTICAS DESCRITIVAS
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
