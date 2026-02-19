# Brokeberg Terminal

Terminal financeiro profissional construído em **Streamlit** para análise do mercado brasileiro. O app é protegido por autenticação (bcrypt) e utiliza um tema visual escuro customizado ("brokeberg").

## Como rodar

```bash
pip install -r requirements.txt
streamlit run App.py
```

> As credenciais de login estão configuradas em `.streamlit/secrets.toml` (não versionado).

## Estrutura do Projeto

```
├── App.py                        # Entry point — routing, autenticação e sidebar
├── requirements.txt              # Dependências Python
├── packages.txt                  # Pacotes de sistema (deploy)
├── scripts/
│   └── collect_pcr.py            # Script agendado (GitHub Actions) para coleta de PCR
├── src/
│   ├── config.py                 # Tema Plotly customizado ("brokeberg") e constantes de cores
│   ├── pages/                    # Cada arquivo = uma aba do menu lateral
│   ├── models/                   # Lógica de negócios e cálculos
│   ├── data_loaders/             # Scraping, APIs externas e leitura de dados
│   └── components/               # Componentes visuais reutilizáveis (gráficos Plotly)
└── .github/workflows/            # CI/CD (coleta automatizada de dados)
```

## Páginas (Abas)

| Aba | Arquivo | Descrição |
|-----|---------|-----------|
| **Juros Brasil** | `dashboard_tesouro.py` | Curvas de juros reais, nominais e spreads (Tesouro Direto) |
| **Crédito Privado** | `credito_privado.py` | Spreads de debêntures (IDEX JGP / ANBIMA) |
| **Amplitude** | `market_breadth.py` | Market breadth — % de ações acima das médias móveis |
| **Volatilidade IV** | `volatilidade_iv.py` | Análise de IV (VXEWZ), IV/HV Spread, superfície de volatilidade |
| **GEX Gamma** | `gex_calculator.py` | Gamma Exposure (GEX) — exposição gamma dos market makers |
| **Sentimento Opções** | `sentimento_opcoes.py` | Put/Call Ratio, sentimento via opções |
| **Calendário** | `event_calendar.py` | Calendário de eventos corporativos e econômicos |
| **Econômicos BR** | `economicos_br.py` | Indicadores macroeconômicos (BCB) |
| **Commodities** | `dashboard_commodities.py` | Painel de preços de commodities |
| **Internacional** | `dashboard_internacional.py` | Indicadores do FRED (EUA) |
| **Ações BR** | `acoes_br.py` | Análise de ações — Ratio (Long & Short), análise setorial |
| **Radar de Insiders** | `radar_insiders.py` | Movimentações de insiders (dados CVM), identificação de tickers via Fundamentus |
| **Calculadora Put** | `calculadora_put.py` | Estruturação de venda de opções (Black-Scholes) |
| **Screener Put** | `screener_put.py` | Screener automatizado de PUTs atrativas |
| **Merger Arbitrage** | `merger_arbitrage.py` | Arbitragem de fusões — spread entre oferta e preço |
| **Exportador DFP** | `exportador_dfp.py` | Exportação de demonstrativos financeiros (DFP) da CVM |
| **Minha Carteira** | `minha_carteira.py` | Gestão e acompanhamento de carteira pessoal |

## Data Loaders (`src/data_loaders/`)

| Arquivo | Fonte | O que busca |
|---------|-------|-------------|
| `amplitude.py` | Fundamentus (`resultado.php`) | Lista de tickers com liquidez > 0 |
| `fundamentus.py` | Fundamentus (`detalhes.php`) | Mapeamento Nome Empresa → Ticker (1053 empresas) |
| `b3_api.py` | B3 API | Dados da bolsa brasileira |
| `bcb_api.py` | BCB (python-bcb) | Indicadores macroeconômicos |
| `fred_api.py` | FRED API | Indicadores EUA |
| `cvm.py` | CVM (dados.cvm.gov.br) | Downloads de ZIPs da CVM |
| `stocks.py` | yfinance | Market Cap e preços históricos |
| `opcoes_net.py` | OpçõesNet | Dados de opções (scraping/Selenium) |
| `di_futuro.py` | B3 | Curva de DI Futuro |
| `tesouro.py` | Tesouro Direto | Preços de títulos públicos |
| `anbima.py` | ANBIMA | Dados de debêntures |
| `debentures.py` | ANBIMA | Screener de debêntures |
| `commodities.py` | yfinance | Preços de commodities |
| `indices.py` | yfinance | Índices de mercado |
| `proventos.py` | Fundamentus | Dados de dividendos/proventos |
| `pcr.py` | B3 | Put/Call Ratio |
| `events.py` | Várias | Calendário de eventos |
| `idex.py` | JGP IDEX | Índice de crédito privado |
| `DFP.py` | CVM | Demonstrativos Financeiros Padronizados |
| `db.py` | Supabase | Conexão com banco de dados |

## Models (`src/models/`)

| Arquivo | Responsabilidade |
|---------|-----------------|
| `amplitude.py` | Cálculos de market breadth (% acima de MMs) |
| `black_scholes.py` | Modelo Black-Scholes para precificação de opções |
| `fractal_analytics.py` | Análise fractal de séries temporais |
| `gex_calculator.py` | Cálculo de Gamma Exposure |
| `indices.py` | Processamento de dados de índices |
| `insiders.py` | Análise de movimentações de insiders (CVM) c/ mapeamento Fundamentus |
| `math_utils.py` | Utilitários matemáticos (volatilidade, etc.) |
| `pair_trading.py` | Pair trading / Long & Short |
| `put_utils.py` | Utilitários para análise de PUTs |

## Components (`src/components/`)

| Arquivo | Responsabilidade |
|---------|-----------------|
| `charts.py` | Gráficos gerais (Plotly) |
| `charts_amplitude.py` | Gráficos de market breadth |
| `charts_gex.py` | Gráficos de GEX/Gamma |
| `charts_insiders.py` | Gráficos de movimentações de insiders |
| `charts_pair_trading.py` | Gráficos de pair trading |
| `ui.py` | Componentes de UI reutilizáveis |

## Fontes de Dados Externas

- **CVM** (dados.cvm.gov.br) — Movimentações de insiders (VLMO), cadastro de empresas (FCA), DFPs
- **Fundamentus** (fundamentus.com.br) — Lista de empresas, tickers, indicadores fundamentalistas
- **B3** — Opções, DI Futuro, PCR
- **BCB** — SELIC, IPCA, câmbio e outros indicadores
- **FRED** — Indicadores macroeconômicos EUA
- **yfinance** — Preços históricos, market cap, commodities
- **ANBIMA** — Debêntures e renda fixa
- **Supabase** — Banco de dados para persistência (carteira, PCR histórico)

## Padrão de Código

- **Cada página** é um arquivo em `src/pages/` que exporta uma função `render()`.
- **Routing** é feito em `App.py` via `option_menu` (streamlit-option-menu).
- **Cache** usa `@st.cache_data` com TTL configurável.
- **Tema visual** é sempre o tema "brokeberg" (dark, cores neon) configurado em `src/config.py`.
- **Gráficos** são em Plotly, usando o template customizado.
- **Dados da CVM** são baixados como ZIPs e parseados com pandas.
- **Scraping** usa `requests` + `BeautifulSoup` ou `pd.read_html`. Selenium é fallback para sites que exigem JS.

## Deploy

O app é deployado no **Streamlit Cloud**. Requer:
- `requirements.txt` (Python deps)
- `packages.txt` (system deps)
- `.streamlit/secrets.toml` (credenciais, configurado no painel do Streamlit Cloud)

## Scripts Agendados

- `scripts/collect_pcr.py` — Coleta diária de Put/Call Ratio via GitHub Actions (10:00 UTC / 07:00 BRT)
