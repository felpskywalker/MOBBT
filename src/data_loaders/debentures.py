"""
Módulo para scraping de preços de debêntures do site debentures.com.br
"""

import pandas as pd
import requests
from datetime import datetime, timedelta
from io import StringIO


class DebenturesScraper:
    """Classe para fazer scraping de preços de debêntures."""
    
    BASE_URL = "https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario"
    DOWNLOAD_ENDPOINT = "/precosdenegociacao_e.asp"
    
    def __init__(self):
        """Inicializa o scraper com headers padrão."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'{self.BASE_URL}/precosdenegociacao_f.asp'
        })
    
    def _format_date(self, date: datetime) -> str:
        """Formata data no padrão YYYYMMDD para a API."""
        return date.strftime('%Y%m%d')
    
    def get_precos(
        self,
        dt_inicio: datetime = None,
        dt_fim: datetime = None,
        emissor: str = "",
        ativo: str = "",
        isin: str = "",
        incluir_excluidos: bool = False
    ) -> pd.DataFrame:
        """
        Busca preços de negociação de debêntures.
        
        Args:
            dt_inicio: Data inicial (default: 30 dias atrás)
            dt_fim: Data final (default: hoje)
            emissor: Filtro por emissor
            ativo: Filtro por ticker
            isin: Filtro por código ISIN
            incluir_excluidos: Incluir debêntures vencidas
            
        Returns:
            DataFrame com os preços
        """
        # Define datas padrão
        if dt_fim is None:
            dt_fim = datetime.now()
        if dt_inicio is None:
            dt_inicio = dt_fim - timedelta(days=30)
        
        # Define status dos ativos
        op_exc = "Nada" if incluir_excluidos else "False"
        
        # Monta parâmetros
        params = {
            'op_exc': op_exc,
            'emissor': emissor,
            'isin': isin,
            'ativo': ativo,
            'dt_ini': self._format_date(dt_inicio),
            'dt_fim': self._format_date(dt_fim)
        }
        
        url = f"{self.BASE_URL}{self.DOWNLOAD_ENDPOINT}"
        
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            # Decodifica com encoding correto
            content = response.content.decode('latin-1')
            
            if not content.strip() or 'Nenhum registro' in content:
                return pd.DataFrame()
            
            # Lê TSV pulando 2 primeiras linhas (título + vazia)
            df = pd.read_csv(
                StringIO(content),
                sep='\t',
                decimal=',',
                thousands='.',
                encoding='latin-1',
                skiprows=2,
                on_bad_lines='skip'
            )
            
            # Limpa nomes das colunas
            df.columns = df.columns.str.strip()
            
            # Converte coluna de data
            if 'Data' in df.columns:
                df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
            
            # Processa % PU da Curva
            df = self._processar_pu_curva(df)
            
            return df
            
        except Exception as e:
            print(f"Erro ao buscar debêntures: {e}")
            return pd.DataFrame()
    
    def _processar_pu_curva(self, df: pd.DataFrame) -> pd.DataFrame:
        """Processa a coluna % PU da Curva para numérico."""
        if df.empty or '% PU da Curva' not in df.columns:
            return df
        
        df = df.copy()
        
        # Substituir ND por NaN
        df['% PU da Curva'] = df['% PU da Curva'].replace('ND', pd.NA)
        
        # Converter vírgula para ponto se for string
        if df['% PU da Curva'].dtype == 'object':
            df['% PU da Curva'] = (
                df['% PU da Curva']
                .astype(str)
                .str.replace(',', '.', regex=False)
            )
            df['% PU da Curva'] = pd.to_numeric(df['% PU da Curva'], errors='coerce')
        
        return df
    
    def get_precos_ultimos_dias(self, dias: int = 7) -> pd.DataFrame:
        """Busca preços dos últimos N dias."""
        dt_fim = datetime.now()
        dt_inicio = dt_fim - timedelta(days=dias)
        return self.get_precos(dt_inicio=dt_inicio, dt_fim=dt_fim)
    
    def get_precos_por_ativo(self, ticker: str, dias: int = 365) -> pd.DataFrame:
        """Busca histórico de um ativo específico."""
        dt_fim = datetime.now()
        dt_inicio = dt_fim - timedelta(days=dias)
        return self.get_precos(dt_inicio=dt_inicio, dt_fim=dt_fim, ativo=ticker)
    
    def listar_ativos_disponiveis(self, dias: int = 30) -> list:
        """Lista ativos com negociação nos últimos N dias."""
        df = self.get_precos_ultimos_dias(dias=dias)
        if df.empty or 'Código do Ativo' not in df.columns:
            return []
        return sorted(df['Código do Ativo'].unique().tolist())
