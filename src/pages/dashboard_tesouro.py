
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from src.data_loaders.tesouro import obter_dados_tesouro
from src.data_loaders.di_futuro import fetch_curva_di_b3, calcular_juro_10a_di
from src.models.math_utils import (
    calcular_juro_10a_br, 
    calcular_inflacao_implicita, 
    calcular_breakeven_historico
)
from src.components.charts import (
    gerar_grafico_ntnb_multiplos_vencimentos,
    gerar_grafico_breakeven_historico,
    gerar_grafico_curva_juros_real_ntnb,
    gerar_grafico_spread_juros,
    gerar_grafico_ettj_generico
)


def render():
    st.title("Análise de Juros e Inflação")
    st.markdown("---")

    df_tesouro = obter_dados_tesouro()

    if df_tesouro.empty:
        st.error("Não foi possível carregar os dados do Tesouro Direto.")
        return

    # =======================================================
    # 1. ETTJ - Dinâmica da Curva Prefixada (TOPO, lado a lado)
    # =======================================================
    st.subheader("1. Dinâmica da Curva Prefixada (ETTJ)")
    st.caption("Evolução temporal das taxas prefixadas em diferentes prazos.")
    
    col_ettj1, col_ettj2 = st.columns(2)
    
    with col_ettj1:
        st.markdown("**Curto Prazo**")
        fig_curto = gerar_grafico_ettj_generico(df_tesouro, 'Tesouro Prefixado', 'Curva Prefixada - Curto Prazo')
        st.plotly_chart(fig_curto, use_container_width=True, key="ettj_curto")
        
    with col_ettj2:
        st.markdown("**Longo Prazo**")
        fig_longo = gerar_grafico_ettj_generico(df_tesouro, 'Tesouro Prefixado', 'Curva Prefixada - Histórico')
        st.plotly_chart(fig_longo, use_container_width=True, key="ettj_longo")

    st.markdown("---")

    # =======================================================
    # 2. Juros de Longo Prazo (Real e Pré)
    # =======================================================
    st.subheader("2. Juros de Longo Prazo (Proxy 10 anos)")
    
    col_juros1, col_juros2 = st.columns(2)
    
    # --- Juro Real (NTN-B) ---
    with col_juros1:
        st.markdown("**Juro Real (IPCA+)**")
        st.caption("Baseado na taxa de compra da NTN-B mais próxima de 10 anos.")
        
        serie_10y_real = calcular_juro_10a_br(df_tesouro)
        if not serie_10y_real.empty:
            ultimo_real = serie_10y_real.iloc[-1]
            delta_real = ultimo_real - serie_10y_real.iloc[-2] if len(serie_10y_real) > 1 else 0
            
            st.metric("Juro Real 10y (IPCA+)", f"{ultimo_real:.2f}%", f"{delta_real:+.2f}%")
            
            fig_real = px.line(
                x=serie_10y_real.index, 
                y=serie_10y_real.values, 
                title="Histórico Juro Real 10y (Proxy NTN-B)", 
                template='brokeberg'
            )
            fig_real.update_layout(yaxis_title="Taxa (% a.a.)", xaxis_title="Data", title_x=0)
            fig_real.update_traces(line=dict(color='#00E676'))
            st.plotly_chart(fig_real, use_container_width=True, key="juro_real_10y")
        else:
            st.warning("Dados insuficientes para Juro Real 10y.")
    
    # --- Juro Prefixado (DI Futuro ou NTN-F) ---
    with col_juros2:
        st.markdown("**Juro Prefixado (Taxa Pré)**")
        st.caption("Baseado no DI Futuro de 10 anos (B3) ou NTN-F.")
        
        # Tentar buscar do DI Futuro primeiro
        taxa_pre_10y = calcular_juro_10a_di()
        
        if taxa_pre_10y:
            # Se conseguiu do DI
            st.metric("Juro Pré 10y (DI)", f"{taxa_pre_10y:.2f}%")
            
            # Buscar curva completa para gráfico
            df_curva_di = fetch_curva_di_b3(anos_frente=10)
            if not df_curva_di.empty:
                fig_pre = px.line(
                    df_curva_di,
                    x='ano',
                    y='taxa',
                    title="Curva DI Futuro (B3)",
                    template='brokeberg',
                    markers=True
                )
                fig_pre.update_layout(yaxis_title="Taxa (% a.a.)", xaxis_title="Ano", title_x=0)
                fig_pre.update_traces(line=dict(color='#FF6D00'))
                st.plotly_chart(fig_pre, use_container_width=True, key="curva_di")
            else:
                st.info("Curva DI não disponível.")
        else:
            # Fallback: usar NTN-F do Tesouro
            df_ntnf = df_tesouro[df_tesouro['Tipo Titulo'] == 'Tesouro Prefixado'].copy()
            if not df_ntnf.empty:
                # Calcular série histórica similar ao juro real
                resultados_pre = {}
                for data_base in df_ntnf['Data Base'].unique():
                    df_dia = df_ntnf[df_ntnf['Data Base'] == data_base]
                    vencimentos_do_dia = df_dia['Data Vencimento'].unique()
                    if len(vencimentos_do_dia) > 0:
                        target_10y = pd.to_datetime(data_base) + pd.DateOffset(years=10)
                        venc_10y = min(vencimentos_do_dia, key=lambda d: abs(d - target_10y))
                        taxa = df_dia[df_dia['Data Vencimento'] == venc_10y]['Taxa Compra Manha'].iloc[0]
                        resultados_pre[data_base] = taxa
                
                serie_pre = pd.Series(resultados_pre).sort_index()
                if not serie_pre.empty:
                    ultimo_pre = serie_pre.iloc[-1]
                    delta_pre = ultimo_pre - serie_pre.iloc[-2] if len(serie_pre) > 1 else 0
                    
                    st.metric("Juro Pré 10y (NTN-F)", f"{ultimo_pre:.2f}%", f"{delta_pre:+.2f}%")
                    
                    fig_pre = px.line(
                        x=serie_pre.index, 
                        y=serie_pre.values, 
                        title="Histórico Juro Pré 10y (NTN-F)", 
                        template='brokeberg'
                    )
                    fig_pre.update_layout(yaxis_title="Taxa (% a.a.)", xaxis_title="Data", title_x=0)
                    fig_pre.update_traces(line=dict(color='#FF6D00'))
                    st.plotly_chart(fig_pre, use_container_width=True, key="juro_pre_tesouro")
                else:
                    st.warning("Dados insuficientes para Juro Pré 10y.")
            else:
                st.warning("DI Futuro indisponível e não há dados de NTN-F.")

    st.markdown("---")

    # =======================================================
    # 3. Curva de Juros Real e Inflação Implícita Atual
    # =======================================================
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("3. Curva de Juros Real (NTN-B)")
        fig_curva_real = gerar_grafico_curva_juros_real_ntnb(df_tesouro)
        st.plotly_chart(fig_curva_real, use_container_width=True, key="curva_real")
        
    with col_b:
        st.subheader("4. Inflação Implícita (Breakeven)")
        df_breakeven = calcular_inflacao_implicita(df_tesouro)
        if not df_breakeven.empty:
            fig_be = go.Figure()
            fig_be.add_trace(go.Scatter(
                x=df_breakeven['Anos até Vencimento'], 
                y=df_breakeven['Inflação Implícita (% a.a.)'],
                mode='lines+markers',
                name='Implícita',
                line=dict(color='#FFB302')
            ))
            fig_be.update_layout(
                title="Estrutura a Termo da Inflação Implícita", 
                template='brokeberg', 
                xaxis_title="Anos", 
                yaxis_title="Inflação (%)",
                title_x=0
            )
            st.plotly_chart(fig_be, use_container_width=True, key="breakeven_atual")
        else:
            st.info("Não foi possível calcular a curva de inflação implícita.")

    st.markdown("---")

    # =======================================================
    # 5. Histórico de Breakeven - Inflação Implícita
    # =======================================================
    st.subheader("5. Histórico da Inflação Implícita (Breakeven)")
    st.caption("Breakeven = Taxa Prefixada - Taxa Real (IPCA+). Calcula a inflação esperada pelo mercado.")
    
    with st.spinner("Calculando histórico de breakeven..."):
        df_be_hist = calcular_breakeven_historico(df_tesouro)
        
        if not df_be_hist.empty and len(df_be_hist.columns) > 0:
            # Verificar se temos dados suficientes - tratar cada coluna
            cols_disponiveis = []
            for c in df_be_hist.columns:
                try:
                    count = df_be_hist[c].notna().sum()
                    if isinstance(count, pd.Series):
                        count = count.iloc[0]
                    if count > 10:
                        cols_disponiveis.append(c)
                except Exception:
                    continue
            
            # Remover duplicatas
            cols_disponiveis = list(dict.fromkeys(cols_disponiveis))
            
            if cols_disponiveis:
                fig_be_hist = gerar_grafico_breakeven_historico(df_be_hist[cols_disponiveis])
                st.plotly_chart(fig_be_hist, use_container_width=True, key="breakeven_hist")
                
                # Mostrar estatísticas
                with st.expander("📊 Estatísticas do Breakeven"):
                    for col in cols_disponiveis:
                        try:
                            serie = df_be_hist[col].dropna()
                            if isinstance(serie, pd.DataFrame):
                                serie = serie.iloc[:, 0]
                            if len(serie) > 0:
                                st.markdown(f"**{col}:** Atual: {serie.iloc[-1]:.2f}% | Média: {serie.mean():.2f}% | Mín: {serie.min():.2f}% | Máx: {serie.max():.2f}%")
                        except Exception:
                            continue
            else:
                st.warning("Dados insuficientes para calcular breakeven histórico.")
        else:
            st.warning("Não foi possível calcular o histórico de breakeven.")

    st.markdown("---")

    # =======================================================
    # 6. Spread NTN-F 10y vs 2y
    # =======================================================
    st.subheader("6. Spread NTN-F 10y vs 2y")
    st.caption("Diferença entre taxas prefixadas longas e curtas - indica inclinação da curva.")
    fig_spread = gerar_grafico_spread_juros(df_tesouro)
    st.plotly_chart(fig_spread, use_container_width=True, key="spread_juros")

    st.markdown("---")

    # =======================================================
    # 7. Análise de Títulos Específicos
    # =======================================================
    st.subheader("7. Histórico de Taxas por Vencimento")
    
    tipos_disponiveis = df_tesouro['Tipo Titulo'].dropna().unique().tolist()
    tipo_selecionado = st.selectbox(
        "Selecione o Tipo de Título", 
        tipos_disponiveis, 
        index=tipos_disponiveis.index('Tesouro IPCA+') if 'Tesouro IPCA+' in tipos_disponiveis else 0,
        key="tipo_titulo_select"
    )
    
    df_tipo = df_tesouro[df_tesouro['Tipo Titulo'] == tipo_selecionado]
    vencimentos_disponiveis = sorted(df_tipo['Data Vencimento'].unique())
    
    vencimentos_selecionados = st.multiselect(
        "Selecione os Vencimentos", 
        vencimentos_disponiveis,
        default=[vencimentos_disponiveis[-1]] if vencimentos_disponiveis else [],
        format_func=lambda x: x.strftime('%d/%m/%Y'),
        key="vencimentos_select"
    )
    
    metrica = st.radio("Métrica", ['Taxa Compra Manha', 'PU Compra Manha'], horizontal=True, key="metrica_radio")
    
    fig_multiplo = gerar_grafico_ntnb_multiplos_vencimentos(df_tipo, vencimentos_selecionados, metrica)
    st.plotly_chart(fig_multiplo, use_container_width=True, key="titulos_especificos")
