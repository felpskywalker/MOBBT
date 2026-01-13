"""
Página Minha Carteira - Watchlist de Ações com Supabase.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from src.data_loaders.db import get_watchlist, add_stock, delete_stock


@st.cache_data(ttl=300)  # Cache por 5 minutos
def get_stock_data_batch(symbols: list) -> pd.DataFrame:
    """
    Busca preços atuais e variação dos ativos via yfinance (batch).
    Usa yf.download() para buscar todos os tickers de uma vez.
    
    Args:
        symbols: Lista de tickers (ex: ['WEGE3', 'PETR4'])
    
    Returns:
        DataFrame com ticker, preço e variação
    """
    if not symbols:
        return pd.DataFrame()
    
    # Adiciona .SA para todos os tickers
    tickers_sa = [f"{s}.SA" for s in symbols]
    
    try:
        # Download dos últimos 2 dias para calcular variação
        df = yf.download(tickers_sa, period="2d", progress=False, auto_adjust=True)
        
        if df.empty:
            return pd.DataFrame()
        
        results = []
        
        # Se só tem 1 ticker, a estrutura é diferente
        if len(tickers_sa) == 1:
            ticker = symbols[0]
            if len(df) >= 2:
                current_price = df['Close'].iloc[-1]
                prev_close = df['Close'].iloc[-2]
                change_pct = ((current_price - prev_close) / prev_close) * 100
            elif len(df) == 1:
                current_price = df['Close'].iloc[-1]
                change_pct = 0.0
            else:
                current_price = None
                change_pct = None
            
            results.append({
                "Ticker": ticker,
                "Preço Atual (R$)": float(current_price) if current_price else None,
                "Variação (%)": float(change_pct) if change_pct else None
            })
        else:
            # Múltiplos tickers - estrutura MultiIndex
            for i, symbol in enumerate(symbols):
                ticker_sa = f"{symbol}.SA"
                try:
                    if ticker_sa in df['Close'].columns:
                        prices = df['Close'][ticker_sa].dropna()
                        if len(prices) >= 2:
                            current_price = prices.iloc[-1]
                            prev_close = prices.iloc[-2]
                            change_pct = ((current_price - prev_close) / prev_close) * 100
                        elif len(prices) == 1:
                            current_price = prices.iloc[-1]
                            change_pct = 0.0
                        else:
                            current_price = None
                            change_pct = None
                        
                        results.append({
                            "Ticker": symbol,
                            "Preço Atual (R$)": float(current_price) if current_price else None,
                            "Variação (%)": float(change_pct) if change_pct else None
                        })
                    else:
                        results.append({
                            "Ticker": symbol,
                            "Preço Atual (R$)": None,
                            "Variação (%)": None
                        })
                except Exception:
                    results.append({
                        "Ticker": symbol,
                        "Preço Atual (R$)": None,
                        "Variação (%)": None
                    })
        
        return pd.DataFrame(results)
    
    except Exception as e:
        st.warning(f"Erro ao buscar cotações: {e}")
        return pd.DataFrame([{"Ticker": s, "Preço Atual (R$)": None, "Variação (%)": None} for s in symbols])


def render():
    st.header("📋 Minha Carteira")
    st.markdown("Gerencie sua watchlist de ações monitoradas.")
    st.markdown("---")
    
    # --- Formulário de Adição ---
    st.subheader("➕ Adicionar Ativo")
    
    with st.form("add_stock_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            ticker_input = st.text_input(
                "Ticker",
                placeholder="Ex: WEGE3, PETR4, VALE3",
                help="Digite o código do ativo na B3"
            )
        
        with col2:
            st.write("")  # Espaçamento
            submitted = st.form_submit_button("Adicionar", use_container_width=True)
        
        if submitted and ticker_input:
            try:
                add_stock(ticker_input)
                st.success(f"✅ {ticker_input.upper()} adicionado com sucesso!")
                st.cache_data.clear()  # Limpa cache para buscar novo ticker
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao adicionar: {e}")
    
    st.markdown("---")
    
    # --- Lista de Ativos ---
    st.subheader("📊 Meus Ativos")
    
    watchlist = get_watchlist()
    
    if not watchlist:
        st.info("Sua watchlist está vazia. Adicione um ativo acima para começar!")
        return
    
    # Buscar preços atuais e variação (batch)
    symbols = [item["symbol"] for item in watchlist]
    
    with st.spinner("Buscando cotações..."):
        df = get_stock_data_batch(symbols)
    
    if df.empty:
        st.warning("Não foi possível carregar as cotações. Tente novamente em alguns segundos.")
        return
    
    # Adicionar IDs para remoção
    id_map = {item["symbol"]: item["id"] for item in watchlist}
    df["id"] = df["Ticker"].map(id_map)
    
    # Exibir tabela ordenável
    st.dataframe(
        df[["Ticker", "Preço Atual (R$)", "Variação (%)"]],
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", width="medium"),
            "Preço Atual (R$)": st.column_config.NumberColumn(
                "Preço Atual (R$)",
                format="R$ %.2f",
                width="medium"
            ),
            "Variação (%)": st.column_config.NumberColumn(
                "Variação (%)",
                format="%.2f%%",
                width="medium"
            ),
        },
        hide_index=True,
        use_container_width=True,
        height=min(400, 35 * len(df) + 38)  # Altura dinâmica baseada no número de linhas
    )
    
    st.caption(f"📈 Total de ativos: {len(watchlist)} | Dados com ~15 min de atraso")
    
    st.markdown("---")
    
    # Seção de remoção de ativos (APÓS a tabela completa)
    with st.expander("🗑️ Remover Ativo"):
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            ticker_to_delete = st.selectbox(
                "Selecione o ativo para remover",
                options=[(item["id"], item["symbol"]) for item in watchlist],
                format_func=lambda x: x[1],
                label_visibility="collapsed"
            )
        with col_del2:
            if st.button("Remover", type="secondary", use_container_width=True):
                if ticker_to_delete:
                    try:
                        delete_stock(ticker_to_delete[0])
                        st.success(f"✅ {ticker_to_delete[1]} removido!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

