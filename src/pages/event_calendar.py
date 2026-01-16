"""
Página de Calendário de Eventos
Inclui: COPOM, FOMC, Ex-Dividendos, Indicadores Econômicos
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar

from src.data_loaders.events import (
    get_copom_dates,
    get_fomc_dates,
    get_upcoming_dividends,
    get_estimated_economic_dates,
    get_all_upcoming_events
)


# ============================================================
# CONSTANTES
# ============================================================
EVENT_COLORS = {
    'COPOM': '#FF6D00',      # Laranja
    'FOMC': '#636EFA',       # Azul
    'Ex-Dividendo': '#00E676',  # Verde
    'IPCA': '#FF4B4B',       # Vermelho
    'IGP-M': '#FFB302',      # Amarelo
    'default': '#888888'     # Cinza
}

EVENT_ICONS = {
    'COPOM': '🏦',
    'FOMC': '🇺🇸',
    'Ex-Dividendo': '💰',
    'IPCA': '📊',
    'IGP-M': '📈',
    'default': '📅'
}


# ============================================================
# WATCHLIST DEFAULT PARA DIVIDENDOS
# ============================================================
DEFAULT_DIVIDEND_TICKERS = [
    'BBAS3.SA', 'ITUB4.SA', 'BBDC4.SA', 'PETR4.SA', 'VALE3.SA',
    'TAEE11.SA', 'KLBN11.SA', 'CPLE6.SA', 'EGIE3.SA', 'VIVT3.SA'
]


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def get_event_color(event_type: str) -> str:
    """Retorna cor para tipo de evento."""
    return EVENT_COLORS.get(event_type, EVENT_COLORS['default'])


def get_event_icon(event_type: str) -> str:
    """Retorna ícone para tipo de evento."""
    return EVENT_ICONS.get(event_type, EVENT_ICONS['default'])


def days_until(event_date: date) -> int:
    """Calcula dias até um evento."""
    return (event_date - date.today()).days


def format_countdown(days: int) -> str:
    """Formata contagem regressiva."""
    if days == 0:
        return "🔴 HOJE"
    elif days == 1:
        return "🟠 Amanhã"
    elif days <= 7:
        return f"🟡 Em {days} dias"
    else:
        return f"⚪ Em {days} dias"


# ============================================================
# FUNÇÕES DE RENDERIZAÇÃO
# ============================================================
def render_header():
    """Renderiza header e explicação."""
    st.header("📅 Calendário de Eventos")
    
    with st.expander("ℹ️ **O que é o Calendário de Eventos?**", expanded=False):
        st.markdown("""
        ### Eventos que Movem o Mercado
        
        Este calendário consolida os principais eventos que podem impactar seus investimentos:
        
        🏦 **COPOM** - Reuniões do Comitê de Política Monetária do Banco Central
        - Decisões sobre taxa SELIC
        - Afeta: Renda fixa, ações, câmbio
        
        🇺🇸 **FOMC** - Federal Open Market Committee (Fed)
        - Decisões sobre Fed Funds Rate
        - Afeta: Mercados globais, dólar
        
        💰 **Ex-Dividendos** - Datas de corte para receber dividendos
        - Ações negociadas após esta data não dão direito ao dividendo
        
        📊 **Indicadores Econômicos** - Divulgações de dados
        - IPCA, IGP-M, PIB, Emprego
        - Afetam expectativas de juros e mercado
        """)


def render_proximos_eventos(df_events: pd.DataFrame, n: int = 5):
    """Renderiza próximos N eventos em destaque."""
    st.subheader("⚡ Próximos Eventos")
    
    if df_events.empty:
        st.info("Nenhum evento encontrado.")
        return
    
    proximos = df_events.head(n)
    
    for _, row in proximos.iterrows():
        event_date = row['date'].date() if hasattr(row['date'], 'date') else row['date']
        days = days_until(event_date)
        icon = get_event_icon(row['event'])
        color = get_event_color(row['event'])
        countdown = format_countdown(days)
        
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col1:
            st.markdown(f"### {icon}")
        
        with col2:
            st.markdown(f"**{row['event']}** - {event_date.strftime('%d/%m/%Y')}")
            st.caption(row.get('description', ''))
        
        with col3:
            if days == 0:
                st.error(countdown)
            elif days <= 7:
                st.warning(countdown)
            else:
                st.info(countdown)
    
    st.markdown("---")


def render_calendario_mensal(df_events: pd.DataFrame, ano: int, mes: int):
    """Renderiza visão de calendário mensal."""
    st.subheader(f"📆 {calendar.month_name[mes]} {ano}")
    
    # Filtrar eventos do mês
    events_mes = df_events[
        (df_events['date'].dt.month == mes) & 
        (df_events['date'].dt.year == ano)
    ]
    
    # Calendário
    cal = calendar.Calendar()
    semanas = cal.monthdayscalendar(ano, mes)
    
    # Header dias da semana
    cols = st.columns(7)
    for i, dia_nome in enumerate(['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']):
        cols[i].markdown(f"**{dia_nome}**")
    
    # Dias do mês
    for semana in semanas:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            if dia == 0:
                cols[i].markdown("&nbsp;")
            else:
                data_atual = date(ano, mes, dia)
                
                # Verificar eventos
                eventos_dia = events_mes[events_mes['date'].dt.day == dia]
                
                if not eventos_dia.empty:
                    icons = " ".join([get_event_icon(e) for e in eventos_dia['event']])
                    cols[i].markdown(f"**{dia}** {icons}")
                else:
                    if data_atual == date.today():
                        cols[i].markdown(f"🔵 **{dia}**")
                    else:
                        cols[i].markdown(f"{dia}")


def render_lista_eventos(df_events: pd.DataFrame, filtro_tipo: str = None):
    """Renderiza lista de eventos em formato de tabela."""
    st.subheader("📋 Lista de Eventos")
    
    if df_events.empty:
        st.info("Nenhum evento para exibir.")
        return
    
    df_display = df_events.copy()
    
    # Filtrar por tipo se especificado
    if filtro_tipo and filtro_tipo != "Todos":
        df_display = df_display[df_display['event'] == filtro_tipo]
    
    if df_display.empty:
        st.info(f"Nenhum evento do tipo '{filtro_tipo}' encontrado.")
        return
    
    # Formatar para exibição
    df_display['Data'] = df_display['date'].dt.strftime('%d/%m/%Y')
    df_display['Dias'] = df_display['date'].apply(
        lambda x: days_until(x.date() if hasattr(x, 'date') else x)
    )
    df_display['Countdown'] = df_display['Dias'].apply(format_countdown)
    
    # Renomear colunas
    df_display = df_display.rename(columns={
        'event': 'Tipo',
        'description': 'Descrição'
    })
    
    # Selecionar colunas
    cols_to_show = ['Data', 'Tipo', 'Descrição', 'Countdown']
    if 'ticker' in df_display.columns:
        cols_to_show.insert(2, 'ticker')
    
    df_display = df_display[[c for c in cols_to_show if c in df_display.columns]]
    
    st.dataframe(df_display, hide_index=True, use_container_width=True, key="events_table")


def render_resumo_semanal(df_events: pd.DataFrame):
    """Renderiza resumo de eventos da semana atual."""
    st.subheader("📊 Esta Semana")
    
    today = date.today()
    end_week = today + timedelta(days=7)
    
    # Filtrar eventos da semana
    events_semana = df_events[
        (df_events['date'].dt.date >= today) & 
        (df_events['date'].dt.date <= end_week)
    ]
    
    if events_semana.empty:
        st.success("✅ Nenhum evento importante nesta semana.")
        return
    
    # Contagem por tipo
    contagem = events_semana['event'].value_counts()
    
    cols = st.columns(len(contagem))
    for i, (tipo, qtd) in enumerate(contagem.items()):
        icon = get_event_icon(tipo)
        cols[i].metric(f"{icon} {tipo}", f"{qtd} evento(s)")


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def render():
    """Função principal de renderização."""
    render_header()
    st.markdown("---")
    
    # Sidebar de configuração
    with st.sidebar:
        st.subheader("⚙️ Configurações")
        
        dias_frente = st.slider(
            "Dias à frente",
            min_value=30,
            max_value=180,
            value=90,
            step=30,
            key="dias_frente_slider"
        )
        
        tipos_evento = st.multiselect(
            "Filtrar por tipo",
            options=['COPOM', 'FOMC', 'Ex-Dividendo', 'IPCA', 'IGP-M'],
            default=['COPOM', 'FOMC', 'Ex-Dividendo', 'IPCA'],
            key="tipos_evento_select"
        )
        
        incluir_dividendos = st.checkbox(
            "Buscar dividendos",
            value=True,
            help="Busca próximos ex-dividendos via yfinance (pode demorar)",
            key="incluir_div_check"
        )
        
        if incluir_dividendos:
            tickers_div = st.text_area(
                "Tickers para dividendos",
                value="\n".join(DEFAULT_DIVIDEND_TICKERS),
                help="Um ticker por linha",
                key="tickers_div_input"
            )
            tickers_list = [t.strip() for t in tickers_div.split('\n') if t.strip()]
        else:
            tickers_list = []
    
    # Carregar eventos
    with st.spinner("Carregando eventos..."):
        df_events = get_all_upcoming_events(
            tickers=tickers_list if incluir_dividendos else None,
            days_ahead=dias_frente
        )
    
    # Filtrar por tipos selecionados
    if tipos_evento:
        df_events = df_events[df_events['event'].isin(tipos_evento)]
    
    # Layout principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Próximos eventos
        render_proximos_eventos(df_events, n=5)
        
        # Lista completa
        filtro = st.selectbox(
            "Filtrar tipo",
            options=['Todos'] + tipos_evento,
            key="filtro_lista"
        )
        render_lista_eventos(df_events, filtro)
    
    with col2:
        # Resumo semanal
        render_resumo_semanal(df_events)
        st.markdown("---")
        
        # Calendário mensal
        hoje = date.today()
        col_m1, col_m2 = st.columns(2)
        mes_sel = col_m1.selectbox(
            "Mês",
            options=list(range(1, 13)),
            index=hoje.month - 1,
            format_func=lambda x: calendar.month_name[x],
            key="mes_select"
        )
        ano_sel = col_m2.selectbox(
            "Ano",
            options=[hoje.year, hoje.year + 1],
            key="ano_select"
        )
        
        render_calendario_mensal(df_events, ano_sel, mes_sel)
    
    # Legenda
    st.markdown("---")
    st.markdown("#### Legenda")
    cols_leg = st.columns(5)
    for i, (tipo, icon) in enumerate(EVENT_ICONS.items()):
        if tipo != 'default':
            cols_leg[i % 5].markdown(f"{icon} {tipo}")
