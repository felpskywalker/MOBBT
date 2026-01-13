"""
Página Minha Carteira - Watchlist de Ações com Supabase.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from src.data_loaders.db import get_watchlist, add_stock, delete_stock


def get_current_prices(symbols: list) -> dict:
    """
    Busca preços atuais dos ativos via yfinance.
    
    Args:
        symbols: Lista de tickers (ex: ['WEGE3', 'PETR4'])
    
    Returns:
        Dict com ticker -> preço atual
    """
    if not symbols:
        return {}
    
    prices = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(f"{symbol}.SA")
            info = ticker.fast_info
            prices[symbol] = info.get("lastPrice") or info.get("regularMarketPrice")
        except Exception:
            prices[symbol] = None
    
    return prices


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
    
    # Buscar preços atuais
    symbols = [item["symbol"] for item in watchlist]
    
    with st.spinner("Buscando cotações..."):
        prices = get_current_prices(symbols)
    
    # Montar DataFrame para exibição
    df_data = []
    for item in watchlist:
        symbol = item["symbol"]
        preco_atual = prices.get(symbol)
        
        df_data.append({
            "id": item["id"],
            "Ticker": symbol,
            "Preço Atual (R$)": f"R$ {preco_atual:.2f}" if preco_atual else "N/A",
        })
    
    df = pd.DataFrame(df_data)
    
    # Exibir tabela com botões de delete
    for idx, row in df.iterrows():
        col1, col2, col3 = st.columns([2, 3, 1])
        
        with col1:
            st.markdown(f"**{row['Ticker']}**")
        
        with col2:
            st.markdown(row["Preço Atual (R$)"])
        
        with col3:
            if st.button("🗑️", key=f"delete_{row['id']}", help="Remover ativo"):
                try:
                    delete_stock(row["id"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
    
    st.markdown("---")
    st.caption(f"Total de ativos: {len(watchlist)}")
