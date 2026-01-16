
import streamlit as st
import yfinance as yf
from datetime import date, datetime
from src.models.put_utils import get_selic_annual


def get_current_price(ticker: str) -> float:
    """Busca o preço atual do ticker via yfinance."""
    try:
        full_ticker = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        stock = yf.Ticker(full_ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return 0.0
    except Exception:
        return 0.0


def render():
    st.header("Calculadora de Merger Arbitrage")
    st.info(
        "Ferramenta para analisar oportunidades de arbitragem em operações de M&A. "
        "Calcula a probabilidade implícita do mercado e compara retornos com o CDI."
    )
    st.markdown("---")
    
    # ===================== INPUTS =====================
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📊 Dados da Operação")
        
        ticker = st.text_input(
            "Ticker da Empresa Alvo", 
            "", 
            help="Ex: PTNT4, LINX3"
        ).upper().strip()
        
        preco_aquisicao = st.number_input(
            "Preço de Aquisição (R$)", 
            value=0.0, 
            step=0.01, 
            format="%.2f",
            help="Valor oferecido por ação na aquisição"
        )
        
        preco_antes = st.number_input(
            "Preço Antes do Anúncio (R$)", 
            value=0.0, 
            step=0.01, 
            format="%.2f",
            help="Preço da ação antes do anúncio da aquisição (Unaffected Price)"
        )
        
        data_conclusao = st.date_input(
            "Data de Conclusão Prevista",
            value=date.today(),
            help="Data estimada para fechamento da operação"
        )
        
        prob_estimada = st.slider(
            "Probabilidade Estimada (%)",
            min_value=0,
            max_value=100,
            value=80,
            help="Sua estimativa pessoal da probabilidade de sucesso do deal"
        )
    
    with col2:
        st.markdown("### 💰 Dados de Mercado (Automático)")
        
        # Busca preço atual
        preco_atual = 0.0
        if ticker:
            with st.spinner(f"Buscando {ticker}..."):
                preco_atual = get_current_price(ticker)
        
        col_preco, col_cdi = st.columns(2)
        
        if preco_atual > 0:
            col_preco.metric("Preço Atual", f"R$ {preco_atual:.2f}")
        else:
            col_preco.metric("Preço Atual", "R$ 0.00")
            if ticker:
                st.warning("Não foi possível obter o preço atual.")
        
        # CDI (Selic)
        cdi_anual = get_selic_annual()
        cdi_mensal = ((1 + cdi_anual / 100) ** (1/12) - 1) * 100
        cdi_diario = ((1 + cdi_anual / 100) ** (1/252) - 1) * 100
        
        col_cdi.metric("CDI Anual", f"{cdi_anual:.2f}%")
        
        # Dias até conclusão
        dias_para_conclusao = (data_conclusao - date.today()).days
        dias_para_conclusao = max(dias_para_conclusao, 1)  # Mínimo 1 dia
        
        st.metric("Dias para Conclusão", f"{dias_para_conclusao} dias")
        
        # Exibe CDI mensal e diário
        cdi_col1, cdi_col2 = st.columns(2)
        cdi_col1.metric("CDI Mensal", f"{cdi_mensal:.2f}%")
        cdi_col2.metric("CDI Diário", f"{cdi_diario:.4f}%")
    
    # ===================== CÁLCULOS =====================
    st.markdown("---")
    
    if preco_aquisicao > 0 and preco_atual > 0 and preco_antes > 0:
        # Fórmulas do print
        upside = preco_aquisicao - preco_atual
        downside = preco_atual - preco_antes
        
        # Probabilidade implícita do mercado
        if (upside + downside) > 0:
            prob_calculada = (downside / (upside + downside)) * 100
        else:
            prob_calculada = 0.0
        
        # Retornos
        retorno_esperado = (upside / preco_atual) * 100 if preco_atual > 0 else 0
        
        # Retorno esperado com margem (ponderado pela probabilidade estimada)
        retorno_com_margem = retorno_esperado * (prob_estimada / 100)
        
        # Retorno diário
        retorno_diario = retorno_esperado / dias_para_conclusao if dias_para_conclusao > 0 else 0
        retorno_diario_margem = retorno_com_margem / dias_para_conclusao if dias_para_conclusao > 0 else 0
        
        # CDI do período
        cdi_periodo = ((1 + cdi_anual / 100) ** (dias_para_conclusao / 365) - 1) * 100
        
        # % do CDI
        pct_cdi = (retorno_esperado / cdi_periodo) * 100 if cdi_periodo > 0 else 0
        pct_cdi_margem = (retorno_com_margem / cdi_periodo) * 100 if cdi_periodo > 0 else 0
        
        # ===================== RESULTADOS =====================
        st.markdown("## 📈 Resultados")
        
        # Linha 1: Dados da operação
        st.markdown("### Dados Resumidos")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Ticker", ticker)
        d2.metric("Preço de Aquisição", f"R$ {preco_aquisicao:.2f}")
        d3.metric("Preço Atual", f"R$ {preco_atual:.2f}")
        d4.metric("Preço Antes", f"R$ {preco_antes:.2f}")
        
        # Linha 2: Probabilidades
        st.markdown("### Probabilidades")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Probabilidade Estimada", f"{prob_estimada:.2f}%", help="Sua estimativa")
        p2.metric(
            "Probabilidade Calculada", 
            f"{prob_calculada:.2f}%", 
            delta=f"{prob_calculada - prob_estimada:+.2f} p.p.",
            delta_color="off",
            help="Implícita pelo mercado: Downside / (Upside + Downside)"
        )
        p3.metric("Upside", f"R$ {upside:.2f}", help="Preço Aquisição - Preço Atual")
        p4.metric("Downside", f"R$ {downside:.2f}", help="Preço Atual - Preço Antes")
        
        # Linha 3: Retornos
        st.markdown("### Retornos")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric(
            "Retorno Esperado", 
            f"{retorno_esperado:.2f}%",
            help="Se o deal fechar: (Upside / Preço Atual)"
        )
        r2.metric(
            "Retorno Esperado c/ Margem", 
            f"{retorno_com_margem:.2f}%",
            help="Retorno ponderado pela probabilidade estimada"
        )
        r3.metric(
            "Retorno Diário Esperado", 
            f"{retorno_diario:.4f}%"
        )
        r4.metric(
            "Retorno Diário c/ Margem", 
            f"{retorno_diario_margem:.4f}%"
        )
        
        # Linha 4: Comparativo CDI
        st.markdown("### Comparativo com CDI")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CDI do Período", f"{cdi_periodo:.2f}%", help=f"CDI acumulado em {dias_para_conclusao} dias")
        c2.metric(
            "% do CDI", 
            f"{pct_cdi:.0f}%",
            delta="Acima do CDI" if pct_cdi > 100 else "Abaixo do CDI",
            delta_color="normal" if pct_cdi > 100 else "inverse"
        )
        c3.metric(
            "% do CDI c/ Margem", 
            f"{pct_cdi_margem:.0f}%",
            delta="Acima do CDI" if pct_cdi_margem > 100 else "Abaixo do CDI",
            delta_color="normal" if pct_cdi_margem > 100 else "inverse"
        )
        c4.metric("Dias para Conclusão", f"{dias_para_conclusao}")
        
        # Análise qualitativa
        st.markdown("---")
        st.markdown("### 💡 Análise")
        
        if prob_calculada < prob_estimada:
            st.success(
                f"**Oportunidade potencial:** A probabilidade implícita do mercado ({prob_calculada:.1f}%) "
                f"é **menor** que sua estimativa ({prob_estimada}%). O mercado pode estar subestimando o deal."
            )
        elif prob_calculada > prob_estimada:
            st.warning(
                f"**Cautela:** A probabilidade implícita do mercado ({prob_calculada:.1f}%) "
                f"é **maior** que sua estimativa ({prob_estimada}%). O mercado pode saber algo que você não sabe."
            )
        else:
            st.info("Probabilidade implícita alinhada com sua estimativa.")
        
        if pct_cdi > 100:
            st.success(f"✅ Retorno esperado equivale a **{pct_cdi:.0f}%** do CDI do período.")
        else:
            st.warning(f"⚠️ Retorno esperado equivale a apenas **{pct_cdi:.0f}%** do CDI do período.")
    
    else:
        st.info("Preencha todos os campos para ver os cálculos.")
