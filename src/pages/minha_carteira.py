"""
Página Minha Carteira - Watchlist de Ações com Supabase.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from src.data_loaders.db import get_watchlist, add_stock, delete_stock


def get_stock_data(symbols: list) -> dict:
    """
    Busca preços atuais e variação dos ativos via yfinance.
    
    Args:
        symbols: Lista de tickers (ex: ['WEGE3', 'PETR4'])
    
    Returns:
        Dict com ticker -> {'price': float, 'change_pct': float}
    """
    if not symbols:
        return {}
    
    data = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(f"{symbol}.SA")
            info = ticker.fast_info
            current_price = info.get("lastPrice") or info.get("regularMarketPrice")
            previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            
            if current_price and previous_close:
                change_pct = ((current_price - previous_close) / previous_close) * 100
            else:
                change_pct = None
            
            data[symbol] = {
                "price": current_price,
                "change_pct": change_pct
            }
        except Exception:
            data[symbol] = {"price": None, "change_pct": None}
    
    return data


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
    
    # Buscar preços atuais e variação
    symbols = [item["symbol"] for item in watchlist]
    
    with st.spinner("Buscando cotações..."):
        stock_data = get_stock_data(symbols)
    
    # Montar DataFrame
    df_data = []
    for item in watchlist:
        symbol = item["symbol"]
        data = stock_data.get(symbol, {})
        preco_atual = data.get("price")
        variacao = data.get("change_pct")
        
        df_data.append({
            "id": item["id"],
            "Ticker": symbol,
            "Preço Atual (R$)": preco_atual if preco_atual else None,
            "Variação (%)": variacao if variacao else None,
        })
    
    df = pd.DataFrame(df_data)
    
    # Exibir tabela ordenável (st.dataframe tem ordenação nativa)
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
        use_container_width=True
    )
    
    st.markdown("---")
    
    # Seção de remoção de ativos
    st.subheader("🗑️ Remover Ativo")
    
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
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
    
    st.caption(f"Total de ativos: {len(watchlist)}")
