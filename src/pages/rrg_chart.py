"""
Relative Rotation Graph (RRG) — Índices Setoriais B3
Página do dashboard Streamlit com gráfico interativo Plotly.
Modelo RRG-Lite: RS-Ratio e RS-Momentum via padronização Z-Score (janela 14).
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.colors import hex_to_rgb
from scipy.interpolate import make_interp_spline
import requests
import base64
import json


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _parse_pt_br_float(s):
    try:
        if isinstance(s, (int, float)):
            return float(s)
        if isinstance(s, str):
            return float(s.replace('.', '').replace(',', '.'))
        return 0.0
    except Exception:
        return 0.0


def _fetch_index_composition(index_code: str) -> pd.DataFrame:
    """Busca a composição atual de um índice da B3 via API interna."""
    url_template = (
        "https://sistemaswebb3-listados.b3.com.br"
        "/indexProxy/indexCall/GetPortfolioDay/{}"
    )
    payload_dict = {"index": index_code, "language": "pt-br"}
    payload_b64 = base64.b64encode(
        json.dumps(payload_dict).encode('utf-8')
    ).decode('utf-8')
    url = url_template.format(payload_b64)

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if 'results' not in data:
            return pd.DataFrame()
        df = pd.DataFrame(data['results'])
        if df.empty:
            return pd.DataFrame()
        df = df[['cod', 'theoricalQty']].copy()
        df.columns = ['Ticker', 'Qty']
        df['Ticker'] = df['Ticker'].astype(str).str.strip() + ".SA"
        df['Qty'] = df['Qty'].apply(_parse_pt_br_float)
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
#  Core RRG-Lite Calculations
# ─────────────────────────────────────────────

WINDOW = 14
ROC_LAG = 1


def _compute_rrg_axes(sector_series: pd.Series,
                      benchmark_series: pd.Series) -> pd.DataFrame:
    """Calcula RS-Ratio (eixo X) e RS-Momentum (eixo Y) seguindo RRG-Lite."""
    rs = (sector_series / benchmark_series) * 100

    rs_sma = rs.rolling(WINDOW).mean()
    rs_std = rs.rolling(WINDOW).std()
    rs_ratio = ((rs - rs_sma) / rs_std) + 100

    roc = (rs_ratio / rs_ratio.shift(ROC_LAG) - 1) * 100

    roc_sma = roc.rolling(WINDOW).mean()
    roc_std = roc.rolling(WINDOW).std()
    rs_momentum = ((roc - roc_sma) / roc_std) + 100

    return pd.DataFrame({
        'RS_Ratio': rs_ratio,
        'RS_Momentum': rs_momentum
    })


# ─────────────────────────────────────────────
#  Plotly Visualization
# ─────────────────────────────────────────────

def _plot_rrg_plotly(rrg_data: dict, index_meta: dict, tail_length: int = 10) -> go.Figure:
    """Cria gráfico RRG interativo com Plotly."""

    fig = go.Figure()

    # ── Coletar limites ──
    all_x, all_y = [], []
    for df in rrg_data.values():
        tail = df.dropna().tail(tail_length)
        if not tail.empty:
            all_x.extend(tail['RS_Ratio'].tolist())
            all_y.extend(tail['RS_Momentum'].tolist())

    if not all_x:
        return fig

    margin = 1.5
    x_min = min(min(all_x), 100) - margin
    x_max = max(max(all_x), 100) + margin
    y_min = min(min(all_y), 100) - margin
    y_max = max(max(all_y), 100) + margin

    # ── Quadrantes coloridos ──
    quadrants = [
        # Leading (superior-direito) — verde
        dict(x0=100, x1=x_max, y0=100, y1=y_max,
             fillcolor="rgba(0,204,0,0.08)", line_width=0, layer="below"),
        # Weakening (inferior-direito) — amarelo
        dict(x0=100, x1=x_max, y0=y_min, y1=100,
             fillcolor="rgba(255,204,0,0.08)", line_width=0, layer="below"),
        # Lagging (inferior-esquerdo) — vermelho
        dict(x0=x_min, x1=100, y0=y_min, y1=100,
             fillcolor="rgba(255,0,0,0.08)", line_width=0, layer="below"),
        # Improving (superior-esquerdo) — azul
        dict(x0=x_min, x1=100, y0=100, y1=y_max,
             fillcolor="rgba(0,102,255,0.08)", line_width=0, layer="below"),
    ]

    # ── Labels de quadrante ──
    cx_r = (100 + x_max) / 2
    cx_l = (x_min + 100) / 2
    cy_t = (100 + y_max) / 2
    cy_b = (y_min + 100) / 2

    quad_labels = [
        dict(x=cx_r, y=cy_t, text="LEADING",   font=dict(color="rgba(0,204,0,0.3)", size=16, family="Arial Black")),
        dict(x=cx_r, y=cy_b, text="WEAKENING",  font=dict(color="rgba(204,204,0,0.3)", size=16, family="Arial Black")),
        dict(x=cx_l, y=cy_b, text="LAGGING",    font=dict(color="rgba(204,0,0,0.3)", size=16, family="Arial Black")),
        dict(x=cx_l, y=cy_t, text="IMPROVING",  font=dict(color="rgba(51,153,255,0.3)", size=16, family="Arial Black")),
    ]

    # ── Tails + pontos ──
    for sector_code, df in rrg_data.items():
        tail = df.dropna().tail(tail_length)
        if len(tail) < 3:
            continue

        meta = index_meta.get(sector_code, {})
        color = meta.get('color', '#AAAAAA')
        label = meta.get('name', sector_code)
        r, g, b = hex_to_rgb(color)

        xs = tail['RS_Ratio'].values
        ys = tail['RS_Momentum'].values

        # Spline suavizada
        t = np.arange(len(xs))
        t_smooth = np.linspace(t[0], t[-1], 200)

        try:
            spline_x = make_interp_spline(t, xs, k=3)
            spline_y = make_interp_spline(t, ys, k=3)
            xs_smooth = spline_x(t_smooth)
            ys_smooth = spline_y(t_smooth)
        except Exception:
            xs_smooth = xs
            ys_smooth = ys

        # Trail com fade (dividir em segmentos com opacidade crescente)
        n_segments = 5
        seg_len = len(xs_smooth) // n_segments
        for i in range(n_segments):
            start = i * seg_len
            end = (i + 1) * seg_len + 1 if i < n_segments - 1 else len(xs_smooth)
            alpha = 0.15 + 0.70 * (i / (n_segments - 1))

            fig.add_trace(go.Scatter(
                x=xs_smooth[start:end],
                y=ys_smooth[start:end],
                mode='lines',
                line=dict(color=f'rgba({r},{g},{b},{alpha:.2f})', width=2.5),
                showlegend=False,
                hoverinfo='skip',
            ))

        # Pontos intermediários com fade
        n_pts = len(xs)
        for i in range(n_pts - 1):
            dot_alpha = 0.2 + 0.6 * (i / max(n_pts - 2, 1))
            fig.add_trace(go.Scatter(
                x=[xs[i]], y=[ys[i]],
                mode='markers',
                marker=dict(
                    size=6,
                    color=f'rgba({r},{g},{b},{dot_alpha:.2f})',
                    line=dict(color='white', width=0.5),
                ),
                showlegend=False,
                hovertemplate=f'{label}<br>RS-Ratio: %{{x:.2f}}<br>RS-Momentum: %{{y:.2f}}<extra></extra>',
            ))

        # Ponto mais recente (grande, opaco)
        fig.add_trace(go.Scatter(
            x=[xs[-1]], y=[ys[-1]],
            mode='markers+text',
            marker=dict(
                size=14,
                color=color,
                line=dict(color='white', width=2),
            ),
            text=[label],
            textposition='top right',
            textfont=dict(color=color, size=11, family='Arial Black'),
            name=label,
            showlegend=True,
            hovertemplate=f'<b>{label}</b><br>RS-Ratio: %{{x:.2f}}<br>RS-Momentum: %{{y:.2f}}<extra></extra>',
        ))

    # ── Layout ──
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#0e1117',
        plot_bgcolor='#0e1117',
        title=dict(
            text='Relative Rotation Graph — Índices Setoriais B3<br>'
                 f'<span style="font-size:12px">Tail: {tail_length} semanas  |  Benchmark: IBOVESPA</span>',
            font=dict(size=18, color='white'),
            x=0.5,
        ),
        xaxis=dict(
            title='RS-Ratio',
            range=[x_min, x_max],
            gridcolor='rgba(255,255,255,0.08)',
            zeroline=False,
        ),
        yaxis=dict(
            title='RS-Momentum',
            range=[y_min, y_max],
            gridcolor='rgba(255,255,255,0.08)',
            zeroline=False,
        ),
        shapes=[
            # Linhas centrais em 100
            dict(type='line', x0=100, x1=100, y0=y_min, y1=y_max,
                 line=dict(color='rgba(255,255,255,0.25)', width=1, dash='dash')),
            dict(type='line', x0=x_min, x1=x_max, y0=100, y1=100,
                 line=dict(color='rgba(255,255,255,0.25)', width=1, dash='dash')),
        ] + [dict(type='rect', **q) for q in quadrants],
        annotations=[
            dict(
                x=ql['x'], y=ql['y'], text=ql['text'],
                font=ql['font'], showarrow=False, xanchor='center', yanchor='middle',
            ) for ql in quad_labels
        ],
        legend=dict(
            bgcolor='rgba(14,17,23,0.8)',
            bordercolor='rgba(255,255,255,0.2)',
            borderwidth=1,
            font=dict(color='white', size=11),
        ),
        height=700,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# ─────────────────────────────────────────────
#  Streamlit Page
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_rrg_data(tail_length: int = 10):
    """Carrega e processa todos os dados RRG (cacheado por 1h)."""

    index_meta = {
        'IMOB': {'color': '#00e676', 'name': 'Imobiliário'},
        'IFNC': {'color': '#1e90ff', 'name': 'Financeiro'},
        'ICON': {'color': '#ff4444', 'name': 'Consumo'},
        'UTIL': {'color': '#00e5ff', 'name': 'Utilidade Pública'},
        'IEEX': {'color': '#ff9100', 'name': 'Energia Elétrica'},
        'IMAT': {'color': '#ffd600', 'name': 'Materiais Básicos'},
        'INDX': {'color': '#e040fb', 'name': 'Indústria'},
    }

    # 1. Fetch compositions
    compositions = {}
    all_tickers = set()

    for code in index_meta:
        df = _fetch_index_composition(code)
        if not df.empty:
            compositions[code] = df
            all_tickers.update(df['Ticker'].tolist())

    if not compositions:
        return None, index_meta, "Nenhum índice carregado."

    # 2. Download prices
    all_tickers_list = list(all_tickers) + ['^BVSP']
    start_date = '2023-06-01'

    try:
        raw = yf.download(all_tickers_list, start=start_date, progress=False)
    except Exception as e:
        return None, index_meta, f"Falha ao baixar preços: {e}"

    prices = pd.DataFrame(index=raw.index)
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in all_tickers_list:
            if ('Adj Close', ticker) in raw.columns:
                prices[ticker] = raw[('Adj Close', ticker)]
            elif ('Close', ticker) in raw.columns:
                prices[ticker] = raw[('Close', ticker)]
    else:
        prices = raw.get('Adj Close', raw.get('Close', raw))

    if isinstance(prices, pd.Series):
        prices = prices.to_frame()

    if prices.empty:
        return None, index_meta, "Nenhum dado de preço retornado."

    # 3. Build synthetic sector indices
    sector_indices = pd.DataFrame(index=prices.index)

    for code, comp_df in compositions.items():
        valid_tickers = [t for t in comp_df['Ticker'] if t in prices.columns]
        if not valid_tickers:
            continue

        sector_prices = prices[valid_tickers].copy()
        threshold = 0.80 * len(sector_prices)
        valid_counts = sector_prices.count()
        good_tickers = valid_counts[valid_counts >= threshold].index.tolist()

        if not good_tickers:
            continue

        sector_prices = sector_prices[good_tickers].ffill()
        comp_indexed = comp_df.set_index('Ticker')
        weights = comp_indexed.loc[good_tickers, 'Qty']
        sector_val = sector_prices.dot(weights)
        sector_indices[code] = sector_val

    if sector_indices.empty:
        return None, index_meta, "Não foi possível construir índices setoriais."

    # 4. Resample to weekly
    benchmark_daily = prices['^BVSP'].ffill()
    sector_weekly = sector_indices.resample('W').last().ffill()
    benchmark_weekly = benchmark_daily.resample('W').last().ffill()

    # 5. Compute RRG axes
    rrg_data = {}
    for code in sector_weekly.columns:
        result = _compute_rrg_axes(sector_weekly[code], benchmark_weekly)
        tail = result.dropna().tail(tail_length)
        if len(tail) >= 2:
            rrg_data[code] = result

    if not rrg_data:
        return None, index_meta, "Dados insuficientes para calcular RRG."

    return rrg_data, index_meta, None


def render():
    st.title("📊 Relative Rotation Graph — Setores B3")
    st.markdown("---")

    # Controles
    col1, col2 = st.columns([1, 4])
    with col1:
        tail_length = st.slider("Semanas (tail)", min_value=4, max_value=20, value=10, step=1)

    # Carregar dados
    with st.spinner("Carregando dados RRG… (composição B3, preços yfinance, cálculos)"):
        rrg_data, index_meta, error = _load_rrg_data(tail_length)

    if error:
        st.error(f"❌ {error}")
        return

    # Plotar
    fig = _plot_rrg_plotly(rrg_data, index_meta, tail_length)
    st.plotly_chart(fig, use_container_width=True, key="rrg_chart")

    # Info box
    with st.expander("ℹ️ Como interpretar o RRG"):
        st.markdown("""
        O **Relative Rotation Graph** mostra a força relativa de cada setor em relação ao IBOVESPA:

        | Quadrante | Significado |
        |-----------|-------------|
        | 🟢 **Leading** (superior-direito) | Força relativa alta e crescente |
        | 🟡 **Weakening** (inferior-direito) | Força relativa alta mas perdendo momentum |
        | 🔴 **Lagging** (inferior-esquerdo) | Força relativa baixa e caindo |
        | 🔵 **Improving** (superior-esquerdo) | Força relativa baixa mas ganhando momentum |

        A **rotação típica** segue: Improving → Leading → Weakening → Lagging → Improving.

        - **Eixo X (RS-Ratio):** força relativa normalizada (Z-Score + 100)
        - **Eixo Y (RS-Momentum):** taxa de mudança da força relativa
        - **Tail:** trajetória das últimas semanas (pontos mais opacos = mais recentes)
        """)
