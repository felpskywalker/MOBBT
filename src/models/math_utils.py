
import pandas as pd
import numpy as np

def parse_pt_br_float(s):
    try:
        if isinstance(s, (int, float)):
            return float(s)
        if isinstance(s, str):
            return float(s.replace('.', '').replace(',', '.'))
        return 0.0
    except:
        return 0.0

def calcular_juro_10a_br(df_tesouro):
    """
    Calcula a série histórica de juros reais de 10 anos (ou próximo disso)
    baseado nos títulos 'Tesouro IPCA+ com Juros Semestrais'.
    """
    df_ntnb = df_tesouro[df_tesouro['Tipo Titulo'] == 'Tesouro IPCA+ com Juros Semestrais'].copy()
    if df_ntnb.empty: return pd.Series(dtype=float)
    
    resultados = {}
    for data_base in df_ntnb['Data Base'].unique():
        df_dia = df_ntnb[df_ntnb['Data Base'] == data_base]
        vencimentos_do_dia = df_dia['Data Vencimento'].unique()
        if len(vencimentos_do_dia) > 0:
            target_10y = pd.to_datetime(data_base) + pd.DateOffset(years=10)
            venc_10y = min(vencimentos_do_dia, key=lambda d: abs(d - target_10y))
            taxa = df_dia[df_dia['Data Vencimento'] == venc_10y]['Taxa Compra Manha'].iloc[0]
            resultados[data_base] = taxa
            
    return pd.Series(resultados).sort_index()

def calcular_inflacao_implicita(df):
    """
    Calcula a curva de inflação implícita (breakeven) usando a fotografia mais recente do Tesouro.
    """
    if df.empty or 'Data Base' not in df.columns:
        return pd.DataFrame()

    df_recente = df[df['Data Base'] == df['Data Base'].max()].copy()
    if df_recente.empty:
        return pd.DataFrame()

    data_referencia = df_recente['Data Base'].max()
    tipos_ipca = ['Tesouro IPCA+ com Juros Semestrais', 'Tesouro IPCA+']
    df_ipca_raw = df_recente[df_recente['Tipo Titulo'].isin(tipos_ipca)]
    df_prefixados = df_recente[df_recente['Tipo Titulo'] == 'Tesouro Prefixado'].set_index('Data Vencimento')
    df_ipca = df_ipca_raw.sort_values('Tipo Titulo', ascending=False).drop_duplicates('Data Vencimento').set_index('Data Vencimento')
    
    if df_prefixados.empty or df_ipca.empty: return pd.DataFrame()
    
    inflacao_implicita = []
    for venc_prefixado, row_prefixado in df_prefixados.iterrows():
        venc_ipca_proximo = min(df_ipca.index, key=lambda d: abs(d - venc_prefixado))
        if abs((venc_ipca_proximo - venc_prefixado).days) < 550:
            taxa_prefixada = row_prefixado['Taxa Compra Manha']
            taxa_ipca = df_ipca.loc[venc_ipca_proximo]['Taxa Compra Manha']

            # Conversão de taxas (% a.a.) para fator e cálculo de breakeven anualizado
            breakeven = (((1 + taxa_prefixada / 100) / (1 + taxa_ipca / 100)) - 1) * 100

            anos_ate_vencimento = (venc_prefixado - data_referencia).days / 365.25
            inflacao_implicita.append({
                'Vencimento do Prefixo': venc_prefixado,
                'Inflação Implícita (% a.a.)': breakeven,
                'Anos até Vencimento': anos_ate_vencimento
            })

    if not inflacao_implicita:
        return pd.DataFrame()

    df_resultado = (
        pd.DataFrame(inflacao_implicita)
        .sort_values('Vencimento do Prefixo')
        .set_index('Vencimento do Prefixo')
    )
    return df_resultado

def calcular_variacao_curva(df_tesouro, dias_atras=5):
    """
    Calcula a variação (diferença) das taxas dos contratos de DI (Prefixados)
    entre a data mais recente e dias anteriores.
    """
    df_prefix = df_tesouro[df_tesouro['Tipo Titulo'] == 'Tesouro Prefixado'].copy()
    if df_prefix.empty: return pd.DataFrame()

    datas_unicas = sorted(df_prefix['Data Base'].unique())
    if len(datas_unicas) < 2: return pd.DataFrame()

    # Pega as últimas N datas disponíveis
    datas_recentes = datas_unicas[-(dias_atras+1):]
    df_recentes = df_prefix[df_prefix['Data Base'].isin(datas_recentes)].copy()

    # Pivota
    df_pivot = df_recentes.pivot(index='Data Base', columns='Data Vencimento', values='Taxa Compra Manha')
    
    # Filtra colunas válidas
    data_max = df_recentes['Data Base'].max()
    valid_cols = df_pivot.loc[data_max].dropna().index
    df_pivot = df_pivot[valid_cols]

    # Calcula a diferença
    df_diff = df_pivot.diff() * 100
    df_diff = df_diff.dropna().round(1)
    
    return df_diff.sort_index(ascending=False)

def calcular_breakeven_historico(df_tesouro):
    """
    Calcula o histórico do Breakeven de Inflação.
    Breakeven = (1 + Taxa Pré) / (1 + Taxa Real) - 1
    
    Retorna duas séries fixas: Curto Prazo (~2-3 anos) e Médio Prazo (~4-5 anos)
    """
    # Prefixados (NTN-F)
    df_pre = df_tesouro[df_tesouro['Tipo Titulo'] == 'Tesouro Prefixado'].copy()
    
    # IPCA+ (NTN-B) - combinar os dois tipos
    tipos_ipca = ['Tesouro IPCA+', 'Tesouro IPCA+ com Juros Semestrais']
    df_ipca = df_tesouro[df_tesouro['Tipo Titulo'].isin(tipos_ipca)].copy()

    if df_pre.empty or df_ipca.empty: 
        return pd.DataFrame()

    # Encontrar datas em comum
    datas_comuns = sorted(list(set(df_pre['Data Base'].unique()) & set(df_ipca['Data Base'].unique())))
    
    if not datas_comuns:
        return pd.DataFrame()
    
    # ALVOS FIXOS: 2 anos (curto) e 5 anos (médio)
    ALVO_CURTO = 2.5
    ALVO_MEDIO = 5.0
    
    resultados_curto = {}
    resultados_medio = {}
    
    for data in datas_comuns:
        data_dt = pd.to_datetime(data)
        df_pre_dia = df_pre[df_pre['Data Base'] == data].copy()
        df_ipca_dia = df_ipca[df_ipca['Data Base'] == data].copy()
        
        if df_pre_dia.empty or df_ipca_dia.empty:
            continue
        
        # Calcular anos até vencimento para cada título
        df_pre_dia['Anos'] = (df_pre_dia['Data Vencimento'] - data_dt).dt.days / 365.25
        df_ipca_dia['Anos'] = (df_ipca_dia['Data Vencimento'] - data_dt).dt.days / 365.25
        
        # Filtrar títulos válidos (> 1 ano e < 10 anos)
        df_pre_dia = df_pre_dia[(df_pre_dia['Anos'] > 1) & (df_pre_dia['Anos'] < 10)]
        df_ipca_dia = df_ipca_dia[(df_ipca_dia['Anos'] > 1) & (df_ipca_dia['Anos'] < 10)]
        
        if df_pre_dia.empty or df_ipca_dia.empty:
            continue
        
        # Calcular breakeven para CURTO PRAZO (~2-3 anos)
        try:
            pre_curto = df_pre_dia.iloc[(df_pre_dia['Anos'] - ALVO_CURTO).abs().argsort()[:1]]
            if not pre_curto.empty:
                anos_pre = pre_curto['Anos'].iloc[0]
                taxa_pre = pre_curto['Taxa Compra Manha'].iloc[0]
                
                ipca_match = df_ipca_dia.iloc[(df_ipca_dia['Anos'] - anos_pre).abs().argsort()[:1]]
                if not ipca_match.empty:
                    anos_ipca = ipca_match['Anos'].iloc[0]
                    taxa_ipca = ipca_match['Taxa Compra Manha'].iloc[0]
                    
                    if abs(anos_pre - anos_ipca) <= 1.5:
                        be = (((1 + taxa_pre/100) / (1 + taxa_ipca/100)) - 1) * 100
                        resultados_curto[data_dt] = be
        except Exception:
            pass
        
        # Calcular breakeven para MÉDIO PRAZO (~4-5 anos)
        try:
            pre_medio = df_pre_dia.iloc[(df_pre_dia['Anos'] - ALVO_MEDIO).abs().argsort()[:1]]
            if not pre_medio.empty:
                anos_pre = pre_medio['Anos'].iloc[0]
                taxa_pre = pre_medio['Taxa Compra Manha'].iloc[0]
                
                # Só calcula se realmente tiver título próximo de 5 anos
                if anos_pre >= 3.5:
                    ipca_match = df_ipca_dia.iloc[(df_ipca_dia['Anos'] - anos_pre).abs().argsort()[:1]]
                    if not ipca_match.empty:
                        anos_ipca = ipca_match['Anos'].iloc[0]
                        taxa_ipca = ipca_match['Taxa Compra Manha'].iloc[0]
                        
                        if abs(anos_pre - anos_ipca) <= 1.5:
                            be = (((1 + taxa_pre/100) / (1 + taxa_ipca/100)) - 1) * 100
                            resultados_medio[data_dt] = be
        except Exception:
            pass
    
    # Construir DataFrame
    if not resultados_curto and not resultados_medio:
        return pd.DataFrame()
    
    df_result = pd.DataFrame({
        'Breakeven Curto (~2-3y)': pd.Series(resultados_curto),
        'Breakeven Médio (~5y)': pd.Series(resultados_medio)
    }).sort_index()
    
    # Remover colunas vazias
    df_result = df_result.dropna(axis=1, how='all')
    
    return df_result

