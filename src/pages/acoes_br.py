
import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from src.models.pair_trading import calcular_metricas_ratio, calcular_kpis_ratio
from src.components.charts_pair_trading import gerar_grafico_ratio

@st.cache_data(ttl=3600)  # Cache por 1 hora
def buscar_tickers_fundamentus():
    """Busca lista de tickers de ações brasileiras do Fundamentus."""
    try:
        url = "https://www.fundamentus.com.br/resultado.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'latin-1'
        
        # Parse HTML tables
        tables = pd.read_html(response.text, decimal=',', thousands='.')
        if tables:
            df = tables[0]
            # A primeira coluna é "Papel" (ticker)
            tickers = df['Papel'].tolist()
            return [t for t in tickers if isinstance(t, str) and len(t) >= 4]
        return []
    except Exception as e:
        st.warning(f"Erro ao buscar tickers do Fundamentus: {e}")
        return []

@st.cache_data(ttl=300)  # Cache por 5 minutos
def buscar_ranking_acoes(tickers: list, top_n: int = 20):
    """Busca variação e volume do dia via yfinance para criar ranking."""
    if not tickers:
        return pd.DataFrame()
    
    # Adiciona .SA para tickers brasileiros
    tickers_sa = [f"{t}.SA" for t in tickers if not t.endswith('.SA')]
    
    resultados = []
    
    # Busca em lotes para performance
    batch_size = 50
    for i in range(0, len(tickers_sa), batch_size):
        batch = tickers_sa[i:i+batch_size]
        try:
            data = yf.download(
                batch, 
                period="2d", 
                progress=False, 
                group_by='ticker',
                auto_adjust=True
            )
            
            for ticker in batch:
                try:
                    if len(batch) == 1:
                        ticker_data = data
                    else:
                        ticker_data = data[ticker]
                    
                    if ticker_data.empty or len(ticker_data) < 2:
                        continue
                    
                    close_hoje = ticker_data['Close'].iloc[-1]
                    close_ontem = ticker_data['Close'].iloc[-2]
                    volume = ticker_data['Volume'].iloc[-1]
                    
                    if pd.notna(close_hoje) and pd.notna(close_ontem) and close_ontem > 0:
                        variacao = ((close_hoje / close_ontem) - 1) * 100
                        resultados.append({
                            'Ticker': ticker.replace('.SA', ''),
                            'Preço': close_hoje,
                            'Variação (%)': variacao,
                            'Volume': volume
                        })
                except Exception:
                    continue
        except Exception:
            continue
    
    if not resultados:
        return pd.DataFrame()
    
    df = pd.DataFrame(resultados)
    df = df.dropna()
    df = df[df['Volume'] > 0]  # Remove ações sem volume
    
    return df

def formatar_volume(vol):
    """Formata volume para exibição (K, M, B)."""
    if vol >= 1e9:
        return f"{vol/1e9:.2f}B"
    elif vol >= 1e6:
        return f"{vol/1e6:.2f}M"
    elif vol >= 1e3:
        return f"{vol/1e3:.2f}K"
    return f"{vol:.0f}"

def exibir_ranking_section():
    """Exibe a seção de ranking de maiores altas e baixas."""
    st.subheader("📊 Ranking do Dia - Maiores Altas e Baixas")
    st.info("Ranking baseado na variação de preço do dia. Tickers extraídos do Fundamentus, cotações do Yahoo Finance.")
    
    col1, col2 = st.columns([0.7, 0.3])
    with col2:
        top_n = st.selectbox("Exibir Top", [10, 20, 30, 50], index=1, key="ranking_top_n")
    
    if st.button("🔄 Atualizar Ranking", use_container_width=True, key="btn_ranking"):
        st.cache_data.clear()
    
    with st.spinner("Buscando dados de ações brasileiras..."):
        tickers = buscar_tickers_fundamentus()
        
        if not tickers:
            st.error("Não foi possível obter a lista de tickers do Fundamentus.")
            return
        
        st.caption(f"📈 {len(tickers)} ações encontradas no Fundamentus")
        
        df_ranking = buscar_ranking_acoes(tickers, top_n=top_n)
        
        if df_ranking.empty:
            st.warning("Não foi possível obter dados de cotação. Tente novamente.")
            return
    
    # --- Maiores Altas e Baixas ---
    col_alta, col_baixa = st.columns(2)
    
    with col_alta:
        st.markdown("### 🟢 Maiores Altas")
        df_altas = df_ranking.nlargest(top_n, 'Variação (%)')
        
        # Formata para exibição
        df_altas_display = df_altas.copy()
        df_altas_display['Preço'] = df_altas_display['Preço'].apply(lambda x: f"R$ {x:.2f}")
        df_altas_display['Variação (%)'] = df_altas_display['Variação (%)'].apply(lambda x: f"+{x:.2f}%" if x > 0 else f"{x:.2f}%")
        df_altas_display['Volume'] = df_altas_display['Volume'].apply(formatar_volume)
        
        st.dataframe(
            df_altas_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Preço": st.column_config.TextColumn("Preço", width="small"),
                "Variação (%)": st.column_config.TextColumn("Var. (%)", width="small"),
                "Volume": st.column_config.TextColumn("Volume", width="small"),
            }
        )
    
    with col_baixa:
        st.markdown("### 🔴 Maiores Baixas")
        df_baixas = df_ranking.nsmallest(top_n, 'Variação (%)')
        
        # Formata para exibição
        df_baixas_display = df_baixas.copy()
        df_baixas_display['Preço'] = df_baixas_display['Preço'].apply(lambda x: f"R$ {x:.2f}")
        df_baixas_display['Variação (%)'] = df_baixas_display['Variação (%)'].apply(lambda x: f"+{x:.2f}%" if x > 0 else f"{x:.2f}%")
        df_baixas_display['Volume'] = df_baixas_display['Volume'].apply(formatar_volume)
        
        st.dataframe(
            df_baixas_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Preço": st.column_config.TextColumn("Preço", width="small"),
                "Variação (%)": st.column_config.TextColumn("Var. (%)", width="small"),
                "Volume": st.column_config.TextColumn("Volume", width="small"),
            }
        )

@st.cache_data
def carregar_dados_acoes(tickers, period="max"):
    try:
        data = yf.download(tickers, period=period, auto_adjust=True, progress=False)['Close']
        if isinstance(data, pd.Series): 
            data = data.to_frame(tickers[0])
        return data.dropna()
    except Exception:
        return pd.DataFrame()

def render():
    st.header("Ferramentas de Análise de Ações Brasileiras")
    st.markdown("---")
    
    # --- Nova seção: Ranking de Maiores Altas e Baixas ---
    exibir_ranking_section()
    
    st.markdown("---")
    
    # --- Seção existente: Análise de Ratio ---
    st.subheader("Análise de Ratio de Ativos (Long & Short)")
    st.info("Calcula o ratio entre o preço de dois ativos (Ativo A / Ativo B).")

    col1, col2, col3 = st.columns([0.4, 0.4, 0.2])
    with col1: ticker_a = st.text_input("Ticker do Ativo A (Numerador)", "SMAL11.SA", key="ticker_a_key")
    with col2: ticker_b = st.text_input("Ticker do Ativo B (Denominador)", "BOVA11.SA", key="ticker_b_key")
    with col3: window_size = st.number_input("Janela Móvel (dias)", min_value=20, max_value=500, value=252, key="window_size_key")
    
    if st.button("Analisar Ratio", use_container_width=True):
        st.session_state.analisar_ratio_trigger = True

    if st.session_state.get('analisar_ratio_trigger'):
        with st.spinner(f"Buscando dados..."):
            close_prices = carregar_dados_acoes([ticker_a, ticker_b], period="max")
            
            if close_prices.empty or close_prices.shape[1] < 2:
                st.error("Não foi possível obter dados para ambos os tickers.")
            else:
                ratio_analysis = calcular_metricas_ratio(close_prices, ticker_a, ticker_b, window=window_size)
                fig_ratio = gerar_grafico_ratio(ratio_analysis, ticker_a, ticker_b, window=window_size)
                kpis = calcular_kpis_ratio(ratio_analysis)
                
                if kpis:
                    cols = st.columns(5)
                    cols[0].metric("Ratio Atual", f"{kpis['atual']:.2f}")
                    cols[1].metric("Média Histórica", f"{kpis['media']:.2f}")
                    cols[2].metric("Mínimo", f"{kpis['minimo']:.2f}", f"{kpis['data_minimo'].strftime('%d/%m/%Y')}")
                    cols[3].metric("Máximo", f"{kpis['maximo']:.2f}", f"{kpis['data_maximo'].strftime('%d/%m/%Y')}")
                    cols[4].metric("Var. p/ Média", f"{kpis['variacao_para_media']:.2f}%")
                
                st.plotly_chart(fig_ratio, use_container_width=True)
