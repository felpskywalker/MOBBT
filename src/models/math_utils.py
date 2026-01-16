
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
    Calcula o histórico do Breakeven de Inflação comparando:
    - Taxa Prefixada (NTN-F / Tesouro Prefixado)
    - Taxa Real (NTN-B / Tesouro IPCA+)
    
    Retorna breakeven para o maior prazo disponível em cada tipo.
    Como NTN-F só vai até ~5 anos e NTN-B vai até 30+, calculamos apenas
    o breakeven para prazos onde AMBOS existem.
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
    
    resultados = []
    
    for data in datas_comuns:
        data_dt = pd.to_datetime(data)
        df_pre_dia = df_pre[df_pre['Data Base'] == data].copy()
        df_ipca_dia = df_ipca[df_ipca['Data Base'] == data].copy()
        
        if df_pre_dia.empty or df_ipca_dia.empty:
            continue
        
        # Calcular anos até vencimento para cada título
        df_pre_dia['Anos'] = (df_pre_dia['Data Vencimento'] - data_dt).dt.days / 365.25
        df_ipca_dia['Anos'] = (df_ipca_dia['Data Vencimento'] - data_dt).dt.days / 365.25
        
        # Filtrar títulos válidos (> 1 ano)
        df_pre_dia = df_pre_dia[df_pre_dia['Anos'] > 1].sort_values('Anos')
        df_ipca_dia = df_ipca_dia[df_ipca_dia['Anos'] > 1].sort_values('Anos')
        
        if df_pre_dia.empty or df_ipca_dia.empty:
            continue
        
        row = {'Data Base': data_dt}
        
        # Pegar o título prefixado de prazo mais longo
        max_pre = df_pre_dia['Anos'].max()
        
        # Definir alvos baseados no que está disponível
        # Se prefixado máximo for ~5 anos, usamos 3y e 5y
        # Se for mais curto, ajustamos
        if max_pre >= 4:
            alvos = [3, min(5, max_pre - 0.5)]
        elif max_pre >= 2.5:
            alvos = [2, max_pre - 0.5]
        else:
            alvos = [max_pre - 0.3] if max_pre > 1 else []
        
        for alvo_anos in alvos:
            try:
                # Encontrar título prefixado mais próximo do alvo
                df_pre_dia['Dist'] = abs(df_pre_dia['Anos'] - alvo_anos)
                idx_pre = df_pre_dia['Dist'].idxmin()
                taxa_pre = df_pre_dia.loc[idx_pre, 'Taxa Compra Manha']
                anos_pre = df_pre_dia.loc[idx_pre, 'Anos']
                
                # Encontrar título IPCA+ mais próximo do mesmo prazo
                df_ipca_dia['Dist'] = abs(df_ipca_dia['Anos'] - anos_pre)
                idx_ipca = df_ipca_dia['Dist'].idxmin()
                taxa_ipca = df_ipca_dia.loc[idx_ipca, 'Taxa Compra Manha']
                anos_ipca = df_ipca_dia.loc[idx_ipca, 'Anos']
                
                # Só calcula se os prazos forem razoavelmente próximos (até 1 ano de diferença)
                if abs(anos_pre - anos_ipca) <= 1.0:
                    # Fórmula do breakeven: (1 + Taxa Pré) / (1 + Taxa Real) - 1
                    breakeven = (((1 + taxa_pre/100) / (1 + taxa_ipca/100)) - 1) * 100
                    
                    # Nomear baseado no prazo real
                    prazo_label = f"{int(round(alvo_anos))}y"
                    row[f'Breakeven {prazo_label}'] = breakeven
                    
            except Exception:
                continue
        
        if len(row) > 1:  # Tem pelo menos um breakeven calculado
            resultados.append(row)
    
    if not resultados:
        return pd.DataFrame()
    
    df_result = pd.DataFrame(resultados).set_index('Data Base').sort_index()
    
    # Consolidar colunas duplicadas (se houver) - manter apenas a primeira
    if df_result.columns.duplicated().any():
        df_result = df_result.loc[:, ~df_result.columns.duplicated()]
    
    return df_result

