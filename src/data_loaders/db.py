"""
Módulo de conexão com Supabase para gerenciamento da Watchlist.
"""

import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase_client() -> Client:
    """Retorna cliente Supabase cacheado para performance."""
    url = st.secrets["general"]["SUPABASE_URL"]
    key = st.secrets["general"]["SUPABASE_KEY"]
    return create_client(url, key)


def get_watchlist() -> list:
    """Retorna todos os tickers da watchlist."""
    client = get_supabase_client()
    response = client.table("tickers").select("*").execute()
    return response.data


def add_stock(symbol: str) -> dict:
    """
    Adiciona um novo ticker à watchlist.
    
    Args:
        symbol: Código do ativo (ex: WEGE3)
    
    Returns:
        Registro inserido
    """
    client = get_supabase_client()
    data = {"symbol": symbol.upper().strip()}
    response = client.table("tickers").insert(data).execute()
    return response.data


def delete_stock(stock_id: int) -> dict:
    """
    Remove um ticker da watchlist pelo ID.
    
    Args:
        stock_id: ID do registro na tabela
    
    Returns:
        Registro removido
    """
    client = get_supabase_client()
    response = client.table("tickers").delete().eq("id", stock_id).execute()
    return response.data
