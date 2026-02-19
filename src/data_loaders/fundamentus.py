
import streamlit as st
import pandas as pd
import requests
import re
import unicodedata


@st.cache_data(ttl=3600*24)  # Cache de 24 horas
def obter_mapeamento_empresas_fundamentus():
    """
    Busca a tabela de detalhes do Fundamentus com Papel, Nome Comercial e Razão Social.
    Retorna um DataFrame com essas 3 colunas.
    """
    try:
        url = "https://www.fundamentus.com.br/detalhes.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'latin-1'

        tables = pd.read_html(response.text, decimal=',', thousands='.')
        if tables:
            df = tables[0]
            # Colunas esperadas: Papel, Nome Comercial, Razão Social
            df.columns = ['Papel', 'Nome_Comercial', 'Razao_Social']
            df = df.dropna(subset=['Papel'])
            df['Papel'] = df['Papel'].astype(str).str.strip()
            df['Nome_Comercial'] = df['Nome_Comercial'].astype(str).str.strip()
            df['Razao_Social'] = df['Razao_Social'].astype(str).str.strip()
            return df
        return pd.DataFrame(columns=['Papel', 'Nome_Comercial', 'Razao_Social'])
    except Exception as e:
        st.warning(f"Erro ao buscar mapeamento do Fundamentus: {e}")
        return pd.DataFrame(columns=['Papel', 'Nome_Comercial', 'Razao_Social'])


def _normalizar_nome(nome):
    """Remove acentos, pontuação e normaliza para comparação."""
    if not isinstance(nome, str):
        return ""
    nome = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('ASCII')
    nome = nome.upper()
    # Substitui hífens por espaço antes de remover pontuação (ex: IOCHPE-MAXION -> IOCHPE MAXION)
    nome = nome.replace('-', ' ')
    nome = re.sub(r'[^A-Z0-9\s]', '', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome


_TOKENS_GENERICOS = {'SA', 'S', 'A', 'DE', 'DO', 'DA', 'DOS', 'DAS', 'E', 'EM', 'COM', 'LTDA', 'CIA', 'COMPANHIA'}


def _calcular_similaridade(nome_cvm, nome_fund):
    """
    Calcula similaridade entre nome CVM e nome Fundamentus.
    Usa combinação de Jaccard Index + cobertura para não penalizar nomes mais longos.
    """
    tokens_cvm = set(_normalizar_nome(nome_cvm).split())
    tokens_fund = set(_normalizar_nome(nome_fund).split())

    if not tokens_cvm or not tokens_fund:
        return 0.0

    tokens_cvm_limpos = tokens_cvm - _TOKENS_GENERICOS
    tokens_fund_limpos = tokens_fund - _TOKENS_GENERICOS

    if not tokens_cvm_limpos or not tokens_fund_limpos:
        tokens_cvm_limpos = tokens_cvm
        tokens_fund_limpos = tokens_fund

    intersecao = tokens_cvm_limpos & tokens_fund_limpos
    uniao = tokens_cvm_limpos | tokens_fund_limpos

    if not uniao or not intersecao:
        return 0.0

    jaccard = len(intersecao) / len(uniao)
    # Cobertura: quanto do menor conjunto está coberto pela interseção
    # Isso evita penalizar nomes mais longos (ex: COSAN SA INDUSTRIA E COMERCIO vs COSAN SA)
    menor = min(len(tokens_cvm_limpos), len(tokens_fund_limpos))
    cobertura = len(intersecao) / menor if menor > 0 else 0.0

    # Score combinado: 40% Jaccard + 60% cobertura
    return 0.4 * jaccard + 0.6 * cobertura


def mapear_nomes_para_tickers(nomes_companhias, df_fundamentus=None):
    """
    Recebe uma lista/Series de nomes de companhias (da CVM) e retorna
    um dicionário {nome_companhia: ticker} com os melhores matches do Fundamentus.
    
    Regras de matching:
    - Usa Jaccard similarity sobre tokens das Razão Social e Nome Comercial
    - Threshold mínimo: 0.3
    - Quando múltiplos tickers têm o mesmo score, prefere o que termina em '3' (ações ON)
    """
    if df_fundamentus is None or df_fundamentus.empty:
        df_fundamentus = obter_mapeamento_empresas_fundamentus()

    if df_fundamentus.empty:
        return {}

    # Correções manuais para nomes ambíguos (holdings com subsidiárias de nome similar)
    _correcoes_nome = {
        'COSAN S.A.': 'CSAN3',
        'CENTRAIS ELET BRAS S.A. - ELETROBRAS': 'ELET3',
    }

    # Pré-computa nomes normalizados do Fundamentus
    df_fund = df_fundamentus.copy()
    df_fund['Razao_Social_Norm'] = df_fund['Razao_Social'].apply(_normalizar_nome)
    df_fund['Nome_Comercial_Norm'] = df_fund['Nome_Comercial'].apply(_normalizar_nome)

    resultado = {}
    nomes_unicos = set(nomes_companhias) if not isinstance(nomes_companhias, set) else nomes_companhias

    for nome in nomes_unicos:
        # Verifica correções manuais primeiro
        if nome in _correcoes_nome:
            resultado[nome] = _correcoes_nome[nome]
            continue

        nome_norm = _normalizar_nome(nome)
        if not nome_norm:
            continue

        # Coleta todos os candidatos com score
        candidatos = []

        for _, row in df_fund.iterrows():
            # Score com Razão Social (match principal)
            score_razao = _calcular_similaridade(nome, row['Razao_Social'])
            # Score com Nome Comercial
            score_comercial = _calcular_similaridade(nome, row['Nome_Comercial'])

            score = max(score_razao, score_comercial)

            if score >= 0.3:
                candidatos.append((row['Papel'], score))

        if not candidatos:
            continue

        def _ticker_priority(ticker):
            """Prioridade do ticker: ações ON (3) > PN (4) > Units (11) > BDRs (33/34/35)."""
            if ticker.endswith('33') or ticker.endswith('34') or ticker.endswith('35'):
                return 0  # BDR — menor prioridade
            if ticker.endswith('11'):
                return 1  # Unit
            if ticker.endswith('3'):
                return 3  # ON — maior prioridade
            if ticker.endswith('4'):
                return 2  # PN
            return 1  # Outros

        # Ordena: maior score primeiro, desempate por prioridade do ticker
        candidatos.sort(key=lambda x: (x[1], _ticker_priority(x[0])), reverse=True)
        resultado[nome] = candidatos[0][0]

    return resultado
