# Especificação: Scraper de Preços de Debêntures

## Objetivo
Implementar funcionalidade para coletar preços de negociação de debêntures do site [debentures.com.br](https://www.debentures.com.br) e exibir gráficos históricos do **% PU da Curva**.

---

## 1. Fonte de Dados

### Endpoint de Download Direto (TSV)
```
https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_e.asp
```

### Parâmetros da URL
| Parâmetro | Tipo | Descrição | Exemplo |
|-----------|------|-----------|---------|
| `op_exc` | String | Status dos ativos: `False` (ativos), `True` (excluídos), `Nada` (ambos) | `False` |
| `emissor` | String | Filtro por emissor (vazio = todos) | `BRASKEM` |
| `ativo` | String | Filtro por ticker da debênture | `BRKM21` |
| `isin` | String | Filtro por código ISIN | |
| `dt_ini` | String | Data inicial formato `YYYYMMDD` | `20240101` |
| `dt_fim` | String | Data final formato `YYYYMMDD` | `20241231` |

### Exemplo de URL completa
```
https://www.debentures.com.br/exploreosnd/consultaadados/mercadosecundario/precosdenegociacao_e.asp?op_exc=False&emissor=&isin=&ativo=&dt_ini=20240101&dt_fim=20241231
```

---

## 2. Formato de Resposta

O endpoint retorna um arquivo **TSV (Tab-Separated Values)** com encoding **ISO-8859-1 (Latin-1)**.

### Estrutura do arquivo
- **Linha 1**: Título com timestamp → `"Mercado Secundário de Debêntures - Gerado em DD/MM/YYYY HH:MM:SS"`
- **Linha 2**: Vazia
- **Linha 3**: Cabeçalho das colunas
- **Linha 4+**: Dados

### Colunas (10 no total)
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| Data | date | Data do pregão (formato `DD/M/YYYY`) |
| Emissor | string | Nome da empresa emissora |
| Código do Ativo | string | Ticker da debênture (ex: `BRKM21`) |
| ISIN | string | Código internacional de identificação |
| Quantidade | int | Quantidade de debêntures negociadas |
| Número de Negócios | int | Quantidade de operações |
| PU Mínimo | float | Preço unitário mínimo (separador decimal: vírgula) |
| PU Médio | float | Preço unitário médio (separador decimal: vírgula) |
| PU Máximo | float | Preço unitário máximo (separador decimal: vírgula) |
| % PU da Curva | float/string | Percentual em relação à curva teórica. Pode ser `ND` (não disponível) |

---

## 3. Código Python do Scraper

```python
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
            'Referer': f'{BASE_URL}/precosdenegociacao_f.asp'
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
            
            return df
            
        except Exception as e:
            print(f"Erro: {e}")
            return pd.DataFrame()
    
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
```

---

## 4. Processamento da Coluna % PU da Curva

A coluna `% PU da Curva` requer tratamento especial:
- Pode conter `ND` (não disponível) → substituir por `NaN`
- Usa vírgula como separador decimal → converter para ponto
- Valores típicos: entre 80% e 120%

```python
def processar_pu_curva(df: pd.DataFrame) -> pd.DataFrame:
    """Processa a coluna % PU da Curva para numérico."""
    df = df.copy()
    
    # Substituir ND por NaN
    df['% PU da Curva'] = df['% PU da Curva'].replace('ND', pd.NA)
    
    # Converter vírgula para ponto se for string
    if df['% PU da Curva'].dtype == 'object':
        df['% PU da Curva'] = df['% PU da Curva'].str.replace(',', '.').astype(float)
    
    return df
```

---

## 5. Exemplo: Buscar Debêntures da Braskem

```python
from datetime import datetime, timedelta

scraper = DebenturesScraper()

# Buscar últimos 2 anos
dt_fim = datetime.now()
dt_inicio = dt_fim - timedelta(days=730)

df = scraper.get_precos(dt_inicio=dt_inicio, dt_fim=dt_fim)

# Filtrar Braskem
df_braskem = df[df['Emissor'].str.contains('BRASKEM', case=False, na=False)]

# Processar % PU da Curva
df_braskem = processar_pu_curva(df_braskem)

# Ver ativos disponíveis
print(df_braskem['Código do Ativo'].unique())
```

---

## 6. Gráfico do % PU da Curva

```python
import matplotlib.pyplot as plt

def gerar_grafico_pu_curva(df: pd.DataFrame, titulo: str = "% PU da Curva"):
    """Gera gráfico do % PU da Curva por ativo."""
    
    # Remover linhas sem dados válidos
    df = df.dropna(subset=['% PU da Curva'])
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Plotar cada ativo
    for ativo in df['Código do Ativo'].unique():
        df_ativo = df[df['Código do Ativo'] == ativo].sort_values('Data')
        ax.plot(
            df_ativo['Data'], 
            df_ativo['% PU da Curva'],
            marker='o', markersize=4, linewidth=1.5,
            label=ativo, alpha=0.8
        )
    
    # Linha de referência em 100% (par)
    ax.axhline(y=100, color='red', linestyle='--', linewidth=1.5, 
               alpha=0.7, label='Par (100%)')
    
    ax.set_xlabel('Data')
    ax.set_ylabel('% PU da Curva')
    ax.set_title(titulo, fontweight='bold')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    
    return fig
```

---

## 7. Dependências

```
pandas>=2.0.0
requests>=2.28.0
matplotlib>=3.7.0
```

---

## 8. Interpretação do % PU da Curva

| Valor | Interpretação |
|-------|---------------|
| **< 100%** | Debênture negociada **abaixo** do preço teórico (desconto) |
| **= 100%** | Debênture negociada **ao par** (preço justo teórico) |
| **> 100%** | Debênture negociada **acima** do preço teórico (prêmio) |

**Exemplo**: Se % PU da Curva = 95%, significa que a debênture está sendo negociada com 5% de desconto em relação ao seu valor teórico.

---

## 9. Notas Importantes

1. **Encoding**: O site usa ISO-8859-1 (Latin-1), não UTF-8
2. **Formato de data na API**: `YYYYMMDD` (sem separadores)
3. **Separador decimal**: Vírgula (formato brasileiro)
4. **Separador de milhares**: Ponto
5. **Timeout recomendado**: 60 segundos (consultas grandes podem demorar)
6. **Headers**: Incluir User-Agent e Referer para evitar bloqueios
