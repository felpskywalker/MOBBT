"""
Scraper de Debêntures do Mercado Secundário - ANBIMA

Este módulo baixa e processa os arquivos XLS diários da ANBIMA
com dados de spreads e taxas indicativas de debêntures.
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


class AnbimaScraper:
    """Classe para fazer scraping de dados de debêntures da ANBIMA."""
    
    BASE_URL = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs"
    
    # Mapeamento de mês para abreviação em português
    MESES_PT = {
        1: 'jan', 2: 'fev', 3: 'mar', 4: 'abr', 5: 'mai', 6: 'jun',
        7: 'jul', 8: 'ago', 9: 'set', 10: 'out', 11: 'nov', 12: 'dez'
    }
    
    # Tipos de debêntures disponíveis (abas do Excel)
    SHEET_TYPES = [
        'DI_PERCENTUAL',
        'DI_SPREAD', 
        'IGP-M',
        'IPCA_SPREAD',
        'PREFIXADO',
        'VENCIDOS_ANTECIPADAMENTE'
    ]
    
    # Colunas do arquivo
    COLUMNS = [
        'Código', 'Nome', 'Vencimento', 'Índice_Correção',
        'Taxa_Compra', 'Taxa_Venda', 'Taxa_Indicativa', 'Desvio_Padrão',
        'Intervalo_Min', 'Intervalo_Max', 'PU', 'Perc_PU_Par',
        'Duration', 'Perc_Reune', 'Ref_NTN_B'
    ]
    
    def __init__(self):
        """Inicializa o scraper com headers padrão."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.ms-excel,*/*',
            'Accept-Language': 'pt-BR,pt;q=0.9',
        })
    
    def _build_url(self, date: datetime) -> str:
        """
        Constrói a URL do arquivo XLS para uma data específica.
        
        Formato: d{YY}{MMM}{DD}.xls (ex: d26fev04.xls para 04/fev/2026)
        """
        year = f"{date.year % 100:02d}"
        month = self.MESES_PT[date.month]
        day = f"{date.day:02d}"
        filename = f"d{year}{month}{day}.xls"
        return f"{self.BASE_URL}/{filename}"
    
    def _parse_sheet(self, df_raw: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
        """
        Processa uma aba do Excel e retorna DataFrame limpo.
        
        O arquivo tem cabeçalho nas linhas 7-8 (índice 6-7) e dados a partir da linha 9.
        """
        # Encontrar linha do cabeçalho (linha que contém "Código")
        header_row = None
        for i, row in df_raw.iterrows():
            if 'Código' in str(row.values):
                header_row = i
                break
        
        if header_row is None:
            return pd.DataFrame()
        
        # Pegar dados a partir de header_row + 2 (pula cabeçalho e linha vazia)
        data_start = header_row + 2
        df_data = df_raw.iloc[data_start:].copy()
        
        # Remover linhas que são observações/notas de rodapé
        df_data = df_data[df_data.iloc[:, 0].notna()]
        df_data = df_data[~df_data.iloc[:, 0].astype(str).str.contains(r'^\(\*|^Obs\.|^#|^\s*$|\(\#\)|Condição|condição|Condi', na=True, regex=True)]
        
        if df_data.empty:
            return pd.DataFrame()
        
        # Resetar índice e renomear colunas
        df_data = df_data.reset_index(drop=True)
        
        # Atribuir nomes das colunas
        num_cols = min(len(self.COLUMNS), len(df_data.columns))
        df_data.columns = self.COLUMNS[:num_cols] + [f'Extra_{i}' for i in range(num_cols, len(df_data.columns))]
        
        # Manter apenas colunas principais
        cols_to_keep = [c for c in self.COLUMNS if c in df_data.columns]
        df_data = df_data[cols_to_keep]
        
        # Adicionar coluna de tipo de indexador
        df_data['Tipo'] = sheet_name
        
        # Converter colunas numéricas
        numeric_cols = ['Taxa_Compra', 'Taxa_Venda', 'Taxa_Indicativa', 'Desvio_Padrão',
                       'Intervalo_Min', 'Intervalo_Max', 'PU', 'Perc_PU_Par', 'Duration', 'Perc_Reune']
        for col in numeric_cols:
            if col in df_data.columns:
                df_data[col] = pd.to_numeric(df_data[col], errors='coerce')
        
        return df_data
    
    def get_data(self, date: datetime, sheet_type: str = None) -> pd.DataFrame:
        """
        Baixa e processa dados de debêntures para uma data específica.
        
        Args:
            date: Data de referência
            sheet_type: Tipo específico de debênture (None = todos os tipos)
            
        Returns:
            DataFrame com os dados de debêntures
        """
        url = self._build_url(date)
        
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            
            # Ler arquivo Excel
            excel_file = BytesIO(response.content)
            
            if sheet_type:
                # Carregar apenas aba específica
                df_raw = pd.read_excel(excel_file, sheet_name=sheet_type, header=None)
                df = self._parse_sheet(df_raw, sheet_type)
            else:
                # Carregar todas as abas
                all_sheets = pd.read_excel(excel_file, sheet_name=None, header=None)
                dfs = []
                for name, df_raw in all_sheets.items():
                    if name in self.SHEET_TYPES and name != 'VENCIDOS_ANTECIPADAMENTE':
                        df_parsed = self._parse_sheet(df_raw, name)
                        if not df_parsed.empty:
                            dfs.append(df_parsed)
                
                df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
            
            # Adicionar data de referência
            if not df.empty:
                df['Data_Referência'] = date.strftime('%Y-%m-%d')
            
            return df
            
        except requests.exceptions.RequestException as e:
            print(f"Erro ao baixar dados de {date.strftime('%d/%m/%Y')}: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Erro ao processar dados: {e}")
            return pd.DataFrame()
    
    def get_latest(self, max_days_back: int = 7) -> pd.DataFrame:
        """
        Busca dados do dia útil mais recente disponível.
        
        Args:
            max_days_back: Máximo de dias para tentar retroativamente
            
        Returns:
            DataFrame com os dados mais recentes
        """
        date = datetime.now()
        
        for _ in range(max_days_back):
            df = self.get_data(date)
            if not df.empty:
                return df
            date -= timedelta(days=1)
        
        return pd.DataFrame()
    
    def get_debenture_info(self, codigo: str) -> Optional[dict]:
        """
        Busca informações de uma debênture específica nos dados mais recentes.
        
        Args:
            codigo: Código da debênture (ex: RECV11, BRKM21)
            
        Returns:
            Dict com informações da debênture ou None se não encontrada
        """
        df = self.get_latest()
        
        if df.empty:
            return None
        
        # Buscar debênture pelo código
        df_deb = df[df['Código'].str.upper() == codigo.upper()]
        
        if df_deb.empty:
            return None
        
        # Retornar primeira ocorrência
        row = df_deb.iloc[0]
        
        return {
            'codigo': row.get('Código'),
            'nome': row.get('Nome'),
            'tipo': row.get('Tipo'),
            'vencimento': row.get('Vencimento'),
            'indice_correcao': row.get('Índice_Correção'),
            'taxa_indicativa': row.get('Taxa_Indicativa'),
            'taxa_compra': row.get('Taxa_Compra'),
            'taxa_venda': row.get('Taxa_Venda'),
            'desvio_padrao': row.get('Desvio_Padrão'),
            'intervalo_min': row.get('Intervalo_Min'),
            'intervalo_max': row.get('Intervalo_Max'),
            'pu': row.get('PU'),
            'perc_pu_par': row.get('Perc_PU_Par'),
            'duration': row.get('Duration'),
            'perc_reune': row.get('Perc_Reune'),
            'ref_ntn_b': row.get('Ref_NTN_B'),
            'data_referencia': row.get('Data_Referência')
        }
