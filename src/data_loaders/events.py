"""
Módulo de dados para Calendário de Eventos.
Inclui: datas COPOM, FOMC, ex-dividendos, e indicadores econômicos.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, date, timedelta
import streamlit as st


# ============================================================
# DATAS COPOM 2025/2026 (Banco Central do Brasil)
# ============================================================
# Fonte: https://www.bcb.gov.br/publicacoes/atascopom
COPOM_DATES_2025 = [
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 11, 5),
    date(2025, 12, 10),
]

COPOM_DATES_2026 = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 5, 6),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 11, 4),
    date(2026, 12, 9),
]


# ============================================================
# DATAS FOMC 2025/2026 (Federal Reserve)
# ============================================================
# Fonte: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_DATES_2025 = [
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 11, 5),
    date(2025, 12, 17),
]

FOMC_DATES_2026 = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 5, 6),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 11, 4),
    date(2026, 12, 16),
]


# ============================================================
# INDICADORES ECONÔMICOS BR (estimativas)
# ============================================================
# Datas típicas de divulgação
INDICADORES_BR = {
    'IPCA': {
        'description': 'Índice de Preços ao Consumidor Amplo',
        'frequency': 'monthly',
        'typical_day': 10,  # Divulgado em torno do dia 10 do mês seguinte
    },
    'IGP-M': {
        'description': 'Índice Geral de Preços - Mercado',
        'frequency': 'monthly',
        'typical_day': 1,  # Divulgado no início do mês
    },
    'PIB': {
        'description': 'Produto Interno Bruto',
        'frequency': 'quarterly',
        'months': [3, 6, 9, 12],  # Trimestral
    },
    'Emprego (PNAD)': {
        'description': 'Taxa de Desemprego',
        'frequency': 'monthly',
        'typical_day': 28,  # Final do mês
    },
}


# ============================================================
# FUNÇÕES DE CONSULTA
# ============================================================
def get_copom_dates(year: int = None) -> list:
    """
    Retorna lista de datas das reuniões do COPOM.
    
    Args:
        year: Ano específico (default: ano atual e próximo)
    
    Returns:
        Lista de dicts com 'date' e 'description'
    """
    if year is None:
        current_year = datetime.now().year
        dates = []
        for y in [current_year, current_year + 1]:
            dates.extend(get_copom_dates(y))
        return dates
    
    if year == 2025:
        base_dates = COPOM_DATES_2025
    elif year == 2026:
        base_dates = COPOM_DATES_2026
    else:
        # Para outros anos, estimar baseado em padrões
        base_dates = _estimate_meeting_dates(year, 8)  # 8 reuniões por ano
    
    return [
        {'date': d, 'event': 'COPOM', 'description': f'Reunião COPOM - {d.strftime("%B %Y")}'}
        for d in base_dates
    ]


def get_fomc_dates(year: int = None) -> list:
    """
    Retorna lista de datas das reuniões do FOMC.
    
    Args:
        year: Ano específico (default: ano atual e próximo)
    
    Returns:
        Lista de dicts com 'date' e 'description'
    """
    if year is None:
        current_year = datetime.now().year
        dates = []
        for y in [current_year, current_year + 1]:
            dates.extend(get_fomc_dates(y))
        return dates
    
    if year == 2025:
        base_dates = FOMC_DATES_2025
    elif year == 2026:
        base_dates = FOMC_DATES_2026
    else:
        base_dates = _estimate_meeting_dates(year, 8)
    
    return [
        {'date': d, 'event': 'FOMC', 'description': f'Reunião FOMC - {d.strftime("%B %Y")}'}
        for d in base_dates
    ]


def _estimate_meeting_dates(year: int, num_meetings: int = 8) -> list:
    """Estima datas de reunião baseado em padrões históricos."""
    # Distribuir uniformemente ao longo do ano
    months = [1, 3, 5, 6, 7, 9, 11, 12][:num_meetings]
    return [date(year, m, 15) for m in months]  # Aproximação


@st.cache_data(ttl=3600*6)
def get_upcoming_dividends(tickers: list, days_ahead: int = 60) -> list:
    """
    Busca próximos dividendos via yfinance.
    
    Args:
        tickers: Lista de tickers para verificar
        days_ahead: Quantos dias à frente verificar
    
    Returns:
        Lista de dicts com 'date', 'ticker', 'description', 'amount'
    """
    dividends = []
    deadline = datetime.now() + timedelta(days=days_ahead)
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            
            # Tentar obter próximo dividendo do calendar
            if hasattr(stock, 'calendar') and stock.calendar is not None:
                cal = stock.calendar
                if cal is not None and not cal.empty:
                    # calendar pode ter 'Ex-Dividend Date'
                    if 'Ex-Dividend Date' in cal.index:
                        ex_date = cal.loc['Ex-Dividend Date']
                        if isinstance(ex_date, pd.Timestamp):
                            ex_date = ex_date.date()
                        elif isinstance(ex_date, datetime):
                            ex_date = ex_date.date()
                        
                        if ex_date and ex_date >= date.today() and ex_date <= deadline.date():
                            div_amount = cal.loc.get('Dividend', 0)
                            dividends.append({
                                'date': ex_date,
                                'event': 'Ex-Dividendo',
                                'ticker': ticker.replace('.SA', ''),
                                'description': f'Ex-Dividendo {ticker.replace(".SA", "")}',
                                'amount': div_amount if div_amount else None
                            })
        except Exception:
            continue
    
    return dividends


def get_estimated_economic_dates(months_ahead: int = 3) -> list:
    """
    Estima datas de divulgação de indicadores econômicos BR.
    
    Args:
        months_ahead: Quantos meses à frente estimar
    
    Returns:
        Lista de dicts com 'date', 'event', 'description'
    """
    events = []
    today = date.today()
    
    for i in range(months_ahead + 1):
        month_date = today + timedelta(days=30 * i)
        month = month_date.month
        year = month_date.year
        
        # IPCA (meio do mês seguinte)
        ipca_date = date(year, month, min(10, 28))
        if ipca_date >= today:
            events.append({
                'date': ipca_date,
                'event': 'IPCA',
                'description': f'Divulgação IPCA - Ref. {(month - 1) or 12}/{year if month > 1 else year - 1}'
            })
        
        # IGP-M (início do mês)
        igpm_date = date(year, month, 1)
        if igpm_date >= today:
            events.append({
                'date': igpm_date,
                'event': 'IGP-M',
                'description': f'Divulgação IGP-M - Ref. {(month - 1) or 12}/{year if month > 1 else year - 1}'
            })
    
    return events


def get_all_upcoming_events(tickers: list = None, days_ahead: int = 90) -> pd.DataFrame:
    """
    Consolida todos os eventos futuros em um DataFrame.
    
    Args:
        tickers: Lista de tickers para verificar dividendos
        days_ahead: Quantos dias à frente
    
    Returns:
        DataFrame com colunas: date, event, description, ticker (opcional)
    """
    all_events = []
    
    today = date.today()
    deadline = today + timedelta(days=days_ahead)
    
    # COPOM
    for event in get_copom_dates():
        if event['date'] >= today and event['date'] <= deadline:
            all_events.append(event)
    
    # FOMC
    for event in get_fomc_dates():
        if event['date'] >= today and event['date'] <= deadline:
            all_events.append(event)
    
    # Dividendos
    if tickers:
        all_events.extend(get_upcoming_dividends(tickers, days_ahead))
    
    # Indicadores econômicos
    all_events.extend(get_estimated_economic_dates(months_ahead=3))
    
    # Criar DataFrame e ordenar por data
    if not all_events:
        return pd.DataFrame(columns=['date', 'event', 'description'])
    
    df = pd.DataFrame(all_events)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df = df.drop_duplicates(subset=['date', 'event'])
    
    return df
