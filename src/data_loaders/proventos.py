"""
Módulo para buscar dados de proventos/dividendos do Fundamentus.
Usado como fallback quando a API B3 não encontra o ticker.
"""

import pandas as pd
import requests
import streamlit as st
from datetime import datetime, date
from io import StringIO
import re


@st.cache_data(ttl=3600*12)  # Cache de 12 horas
def buscar_proventos_detalhados(ticker: str) -> pd.DataFrame:
    """
    Busca histórico de proventos de um ativo no Fundamentus.
    
    Args:
        ticker: Código do ativo (ex: PETR4, VALE3)
    
    Returns:
        DataFrame com colunas: Data, Tipo, Valor, Valor_Liquido
        (JCP tem desconto de 15% de IR, Valor_Liquido = Valor * 0.85)
    """
    ticker = ticker.upper().replace(".SA", "").strip()
    
    url = f"https://www.fundamentus.com.br/proventos.php?papel={ticker}&tipo=2"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.fundamentus.com.br/',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'latin-1'
        
        # Parse HTML tables - NÃO usar decimal/thousands aqui, fazer parsing manual
        tables = pd.read_html(StringIO(response.text))
        
        if not tables:
            return pd.DataFrame(columns=['Data', 'Tipo', 'Valor', 'Valor_Liquido'])
        
        df = tables[0]
        
        # Normaliza nomes das colunas
        df.columns = [str(c).strip() for c in df.columns]
        
        # Identifica colunas de data, tipo e valor
        date_col = None
        type_col = None
        value_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'data' in col_lower and date_col is None:
                date_col = col
            elif 'tipo' in col_lower and type_col is None:
                type_col = col
            elif 'valor' in col_lower and value_col is None:
                value_col = col
        
        # Fallback para colunas posicionais
        if date_col is None and len(df.columns) >= 1:
            date_col = df.columns[0]
        if value_col is None and len(df.columns) >= 2:
            value_col = df.columns[1]
        if type_col is None and len(df.columns) >= 3:
            type_col = df.columns[2]
        
        result_data = []
        
        for _, row in df.iterrows():
            try:
                # Parse data
                data_str = str(row[date_col]) if date_col else None
                if data_str:
                    try:
                        data = pd.to_datetime(data_str, format='%d/%m/%Y')
                    except:
                        data = pd.to_datetime(data_str, dayfirst=True, errors='coerce')
                else:
                    continue
                
                if pd.isna(data):
                    continue
                
                # Parse valor - formato brasileiro: "1,5695" = 1.5695
                valor = 0.0
                if value_col:
                    val_raw = row[value_col]
                    if isinstance(val_raw, (int, float)):
                        # pd.read_html pode ter convertido errado, verificar magnitude
                        if val_raw > 100:  # Provavelmente erro de parsing (ex: 15695 deveria ser 1.5695)
                            valor = val_raw / 10000.0
                        else:
                            valor = float(val_raw)
                    else:
                        # Valor como string
                        val_str = str(val_raw).strip()
                        # Remove pontos de milhar e troca vírgula por ponto
                        val_str = val_str.replace('.', '').replace(',', '.')
                        val_str = re.sub(r'[^\d.\-]', '', val_str)
                        if val_str:
                            valor = float(val_str)
                
                # Parse tipo (JCP ou Dividendo)
                tipo = "Dividendo"
                if type_col and pd.notna(row[type_col]):
                    tipo_str = str(row[type_col]).upper()
                    if 'JCP' in tipo_str or 'JUROS' in tipo_str:
                        tipo = "JCP"
                    elif 'DIV' in tipo_str:
                        tipo = "Dividendo"
                
                # Calcula valor líquido (JCP tem 15% de IR)
                if tipo == "JCP":
                    valor_liquido = valor * 0.85
                else:
                    valor_liquido = valor
                
                result_data.append({
                    'Data': data,
                    'Tipo': tipo,
                    'Valor': valor,
                    'Valor_Liquido': valor_liquido
                })
                
            except Exception:
                continue
        
        result_df = pd.DataFrame(result_data)
        
        if not result_df.empty:
            result_df = result_df.sort_values('Data', ascending=False)
            result_df = result_df.reset_index(drop=True)
        
        return result_df
        
    except Exception as e:
        return pd.DataFrame(columns=['Data', 'Tipo', 'Valor', 'Valor_Liquido'])


def calcular_soma_proventos(df: pd.DataFrame, data_inicio: date = None) -> float:
    """
    Soma os proventos líquidos desde uma data específica.
    
    Args:
        df: DataFrame retornado por buscar_proventos_detalhados
        data_inicio: Data de início para soma (None = últimos 3 meses)
    
    Returns:
        Soma dos valores líquidos dos proventos
    """
    if df.empty:
        return 0.0
    
    if data_inicio is None:
        # Default: últimos 3 meses (período típico de ajuste de opções)
        data_inicio = datetime.now() - pd.Timedelta(days=90)
    
    if isinstance(data_inicio, date) and not isinstance(data_inicio, datetime):
        data_inicio = datetime.combine(data_inicio, datetime.min.time())
    
    # Filtra proventos desde data_inicio
    df_filtrado = df[df['Data'] >= data_inicio]
    
    return df_filtrado['Valor_Liquido'].sum()
