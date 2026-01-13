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
    
    # Exibir tabela com botões de delete
    for item in watchlist:
        symbol = item["symbol"]
        data = stock_data.get(symbol, {})
        preco_atual = data.get("price")
        variacao = data.get("change_pct")
        
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
        with col1:
            st.markdown(f"**{symbol}**")
        
        with col2:
            st.markdown(f"R$ {preco_atual:.2f}" if preco_atual else "N/A")
        
        with col3:
            if variacao is not None:
                color = "green" if variacao >= 0 else "red"
                arrow = "▲" if variacao >= 0 else "▼"
                st.markdown(f":{color}[{arrow} {variacao:+.2f}%]")
            else:
                st.markdown("N/A")
        
        with col4:
            if st.button("🗑️", key=f"delete_{item['id']}", help="Remover ativo"):
                try:
                    delete_stock(item["id"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
    
    st.markdown("---")
    st.caption(f"Total de ativos: {len(watchlist)}")

