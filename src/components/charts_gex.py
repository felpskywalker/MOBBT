"""
GEX Visualization Module - Market Gamma Style
Creates line charts with smooth curves and key metrics panel.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.interpolate import make_interp_spline
from typing import Tuple, Dict

# Brokeberg color constants (matching dashboard theme)
COLORS = {
    'VERDE_NEON': '#39E58C',
    'AMARELO_OURO': '#FFB302',
    'CIANO_NEON': '#00D4FF',
    'VERMELHO_NEON': '#FF4B4B',
    'FUNDO_ESCURO': '#050505',
    'FUNDO_CARDS': '#161B22',
    'TEXTO_PRINCIPAL': '#F0F6FC',
    'TEXTO_SECUNDARIO': '#C9D1D9',
    'GRADE_SUTIL': '#30363D',
}


def calculate_metrics(gex_data: pd.DataFrame, spot_price: float) -> Dict:
    """
    Calculate key GEX metrics.
    
    Returns dict with:
    - gamma_atual: Current gamma at spot
    - gamma_min_negativo: Strike with minimum (most negative) GEX
    - gamma_max_positivo: Strike with maximum (most positive) GEX
    - flip_point: Strike where GEX crosses from positive to negative
    - gamma_score: Normalized score from -1 to 1
    """
    if gex_data.empty:
        return {}
    
    df = gex_data.sort_values('strike').reset_index(drop=True)
    
    # Current gamma at spot (interpolate)
    gamma_atual = np.interp(spot_price, df['strike'], df['total_gex'])
    
    # Find max positive and min negative
    max_pos_idx = df['total_gex'].idxmax()
    min_neg_idx = df['total_gex'].idxmin()
    
    gamma_max_positivo = df.loc[max_pos_idx, 'strike']
    gamma_min_negativo = df.loc[min_neg_idx, 'strike']
    
    # Find flip point (where GEX crosses zero, closest to spot)
    flip_point = None
    for i in range(len(df) - 1):
        if df.loc[i, 'total_gex'] * df.loc[i+1, 'total_gex'] < 0:
            # Linear interpolation to find zero crossing
            x1, x2 = df.loc[i, 'strike'], df.loc[i+1, 'strike']
            y1, y2 = df.loc[i, 'total_gex'], df.loc[i+1, 'total_gex']
            flip = x1 - y1 * (x2 - x1) / (y2 - y1)
            if flip_point is None or abs(flip - spot_price) < abs(flip_point - spot_price):
                flip_point = flip
    
    # Gamma Score: normalize current gamma position
    # Score ranges from -1 (very negative) to +1 (very positive)
    max_gex = df['total_gex'].max()
    min_gex = df['total_gex'].min()
    
    if max_gex - min_gex != 0:
        gamma_score = 2 * (gamma_atual - min_gex) / (max_gex - min_gex) - 1
    else:
        gamma_score = 0
    
    return {
        'gamma_atual': gamma_atual,
        'gamma_min_negativo': gamma_min_negativo,
        'gamma_max_positivo': gamma_max_positivo,
        'flip_point': flip_point if flip_point else spot_price,
        'gamma_score': gamma_score
    }


def smooth_curve(x: np.ndarray, y: np.ndarray, num_points: int = 300) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create smooth curve using spline interpolation.
    """
    if len(x) < 4:
        return x, y
    
    # Sort by x
    sorted_indices = np.argsort(x)
    x_sorted = x[sorted_indices]
    y_sorted = y[sorted_indices]
    
    # Remove duplicates
    unique_indices = np.unique(x_sorted, return_index=True)[1]
    x_unique = x_sorted[unique_indices]
    y_unique = y_sorted[unique_indices]
    
    if len(x_unique) < 4:
        return x_unique, y_unique
    
    try:
        # Create spline
        spline = make_interp_spline(x_unique, y_unique, k=3)
        x_smooth = np.linspace(x_unique.min(), x_unique.max(), num_points)
        y_smooth = spline(x_smooth)
        return x_smooth, y_smooth
    except Exception:
        return x_unique, y_unique


def create_market_gamma_chart(
    gex_data: pd.DataFrame,
    spot_price: float,
    title: str = "Total GEX"
) -> go.Figure:
    """
    Create Market Gamma style bar chart showing Net GEX.
    Green bars for positive GEX, red bars for negative GEX.
    """
    if gex_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    df = gex_data.sort_values('strike').reset_index(drop=True)
    
    # Separate positive and negative GEX for coloring
    positive_gex = df['total_gex'].apply(lambda x: x if x > 0 else 0)
    negative_gex = df['total_gex'].apply(lambda x: x if x < 0 else 0)
    
    # Create figure
    fig = go.Figure()
    
    # Add positive GEX bars (green)
    fig.add_trace(
        go.Bar(
            x=df['strike'],
            y=positive_gex,
            name='GEX Positivo',
            marker_color=COLORS['VERDE_NEON'],
            opacity=0.85,
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>GEX:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add negative GEX bars (red)
    fig.add_trace(
        go.Bar(
            x=df['strike'],
            y=negative_gex,
            name='GEX Negativo',
            marker_color=COLORS['VERMELHO_NEON'],
            opacity=0.85,
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>GEX:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color=COLORS['GRADE_SUTIL'], line_width=1)
    
    # Add spot price vertical line
    fig.add_vline(
        x=spot_price,
        line_width=2,
        line_dash="dash",
        line_color=COLORS['AMARELO_OURO'],
    )
    
    # Add spot price annotation
    fig.add_annotation(
        x=spot_price,
        y=1.05,
        yref='paper',
        text=f"Spot: R$ {spot_price:.2f}",
        showarrow=False,
        font=dict(color=COLORS['TEXTO_PRINCIPAL'], size=12),
        bgcolor=COLORS['FUNDO_CARDS'],
        borderpad=4
    )
    
    # Update layout - Brokeberg theme
    fig.update_layout(
        title={
            'text': title,
            'x': 0,
            'xanchor': 'left',
            'font': {'size': 20, 'color': COLORS['TEXTO_PRINCIPAL'], 'family': 'Segoe UI, sans-serif'}
        },
        xaxis_title="Strike",
        yaxis_title="GEX",
        template='brokeberg',
        paper_bgcolor=COLORS['FUNDO_ESCURO'],
        plot_bgcolor=COLORS['FUNDO_ESCURO'],
        barmode='relative',
        showlegend=False,
        height=450,
        margin=dict(t=80, b=60, l=80, r=40),
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            tickangle=45,
            range=[spot_price - 50, spot_price + 50],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            zeroline=True,
            zerolinecolor=COLORS['GRADE_SUTIL'],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        )
    )
    
    return fig


def create_cumulative_gex_chart(
    gex_data: pd.DataFrame,
    spot_price: float,
    title: str = "GEX Cumulativo"
) -> go.Figure:
    """
    Create Cumulative GEX chart showing accumulated gamma exposure across strikes.
    Line chart that sums the total GEX progressively.
    """
    if gex_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    df = gex_data.sort_values('strike').reset_index(drop=True)
    
    # Calculate cumulative sum
    df['cumulative_gex'] = df['total_gex'].cumsum()
    
    # Create figure
    fig = go.Figure()
    
    # Add cumulative GEX line (cyan/teal color like reference)
    fig.add_trace(
        go.Scatter(
            x=df['strike'],
            y=df['cumulative_gex'],
            mode='lines',
            name='GEX Cumulativo',
            line=dict(color=COLORS['CIANO_NEON'], width=2.5),
            fill='tozeroy',
            fillcolor='rgba(0, 212, 255, 0.2)',
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>GEX Acumulado:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color=COLORS['GRADE_SUTIL'], line_width=1)
    
    # Add spot price vertical line
    fig.add_vline(
        x=spot_price,
        line_width=2,
        line_dash="dash",
        line_color=COLORS['AMARELO_OURO'],
    )
    
    # Add spot price annotation
    fig.add_annotation(
        x=spot_price,
        y=1.05,
        yref='paper',
        text=f"Spot: R$ {spot_price:.2f}",
        showarrow=False,
        font=dict(color=COLORS['TEXTO_PRINCIPAL'], size=12),
        bgcolor=COLORS['FUNDO_CARDS'],
        borderpad=4
    )
    
    # Update layout - Brokeberg theme
    fig.update_layout(
        title={
            'text': title,
            'x': 0,
            'xanchor': 'left',
            'font': {'size': 20, 'color': COLORS['TEXTO_PRINCIPAL'], 'family': 'Segoe UI, sans-serif'}
        },
        xaxis_title="Strike",
        yaxis_title="GEX Acumulado",
        template='brokeberg',
        paper_bgcolor=COLORS['FUNDO_ESCURO'],
        plot_bgcolor=COLORS['FUNDO_ESCURO'],
        showlegend=False,
        height=400,
        margin=dict(t=80, b=60, l=80, r=40),
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            tickangle=45,
            range=[spot_price - 50, spot_price + 50],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            zeroline=True,
            zerolinecolor=COLORS['GRADE_SUTIL'],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        )
    )
    
    return fig


def create_metrics_panel(metrics: Dict, spot_price: float) -> go.Figure:
    """
    Create a metrics panel similar to the reference image.
    Shows: Gamma Score, Gamma Atual, Gamma Mínimo, Flip, Gamma Máximo
    """
    # Create a figure with indicators
    fig = make_subplots(
        rows=1, cols=5,
        specs=[[{"type": "indicator"}] * 5],
        horizontal_spacing=0.02
    )
    
    gamma_score = metrics.get('gamma_score', 0)
    gamma_atual = metrics.get('gamma_atual', 0)
    gamma_min = metrics.get('gamma_min_negativo', 0)
    gamma_max = metrics.get('gamma_max_positivo', 0)
    flip = metrics.get('flip_point', spot_price)
    
    # Gamma Score gauge
    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=gamma_score,
            title={'text': "Gamma Score [σ]", 'font': {'size': 14, 'color': COLORS['TEXTO_PRINCIPAL']}},
            number={'font': {'size': 24, 'color': COLORS['CIANO_NEON']}},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': COLORS['TEXTO_SECUNDARIO']},
                'bar': {'color': COLORS['AMARELO_OURO']},
                'bgcolor': COLORS['GRADE_SUTIL'],
                'borderwidth': 0,
                'steps': [
                    {'range': [-1, 0], 'color': 'rgba(255,75,75,0.3)'},  # VERMELHO_NEON with alpha
                    {'range': [0, 1], 'color': 'rgba(57,229,140,0.3)'}   # VERDE_NEON with alpha
                ],
                'threshold': {
                    'line': {'color': COLORS['TEXTO_PRINCIPAL'], 'width': 2},
                    'thickness': 0.75,
                    'value': gamma_score
                }
            }
        ),
        row=1, col=1
    )
    
    # Format gamma atual
    if abs(gamma_atual) >= 1e6:
        gamma_atual_str = f"{gamma_atual/1e6:.1f}M"
    elif abs(gamma_atual) >= 1e3:
        gamma_atual_str = f"{gamma_atual/1e3:.1f}k"
    else:
        gamma_atual_str = f"{gamma_atual:.0f}"
    
    # Gamma Atual
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gamma_atual,
            title={'text': "Gamma Atual", 'font': {'size': 14, 'color': COLORS['TEXTO_PRINCIPAL']}},
            number={'font': {'size': 28, 'color': COLORS['TEXTO_PRINCIPAL']}, 'valueformat': '.2s'}
        ),
        row=1, col=2
    )
    
    # Gamma Mínimo Negativo
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gamma_min,
            title={'text': "Gamma Mínimo<br>Negativo", 'font': {'size': 14, 'color': COLORS['TEXTO_PRINCIPAL']}},
            number={'font': {'size': 28, 'color': COLORS['CIANO_NEON']}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=3
    )
    
    # Flip Point
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=flip,
            title={'text': "Flip", 'font': {'size': 14, 'color': COLORS['TEXTO_PRINCIPAL']}},
            number={'font': {'size': 28, 'color': COLORS['CIANO_NEON']}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=4
    )
    
    # Gamma Máximo Positivo
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gamma_max,
            title={'text': "Gamma Máximo<br>Positivo", 'font': {'size': 14, 'color': COLORS['TEXTO_PRINCIPAL']}},
            number={'font': {'size': 28, 'color': COLORS['CIANO_NEON']}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=5
    )
    
    fig.update_layout(
        paper_bgcolor=COLORS['FUNDO_ESCURO'],
        plot_bgcolor=COLORS['FUNDO_ESCURO'],
        height=150,
        margin=dict(t=40, b=20, l=20, r=20),
        showlegend=False
    )
    
    return fig


def create_full_dashboard(
    gex_data: pd.DataFrame,
    spot_price: float,
    date_str: str = ""
) -> Tuple[go.Figure, go.Figure, Dict]:
    """
    Create full dashboard with chart and metrics panel.
    
    Returns:
        Tuple of (main_chart, metrics_panel, metrics_dict)
    """
    # Calculate metrics
    metrics = calculate_metrics(gex_data, spot_price)
    
    # Create main chart
    title = f"Market Gamma - BOVA11"
    if date_str:
        title += f" ({date_str})"
    
    main_chart = create_market_gamma_chart(gex_data, spot_price, title)
    
    # Create metrics panel
    metrics_panel = create_metrics_panel(metrics, spot_price)
    
    return main_chart, metrics_panel, metrics


def create_open_interest_chart(
    options_df: pd.DataFrame,
    spot_price: float,
    title: str = "Open Interest por Strike",
    bucket_size: float = 1.0
) -> go.Figure:
    """
    Create Open Interest chart by strike, showing CALL and PUT bars side by side.
    
    Args:
        options_df: DataFrame with columns 'strike', 'type', 'open_interest'
        spot_price: Current spot price for reference line
        title: Chart title
        bucket_size: Size of strike buckets for aggregation
    """
    if options_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    df = options_df.copy()
    
    # Bucket strikes
    df['strike_bucket'] = (df['strike'] / bucket_size).round() * bucket_size
    
    # Aggregate by strike bucket and type
    call_oi = df[df['type'] == 'CALL'].groupby('strike_bucket')['open_interest'].sum().reset_index()
    call_oi.columns = ['strike', 'call_oi']
    
    put_oi = df[df['type'] == 'PUT'].groupby('strike_bucket')['open_interest'].sum().reset_index()
    put_oi.columns = ['strike', 'put_oi']
    
    # Merge
    oi_data = pd.merge(call_oi, put_oi, on='strike', how='outer').fillna(0)
    oi_data = oi_data.sort_values('strike').reset_index(drop=True)
    
    # Create figure
    fig = go.Figure()
    
    # Add CALL bars (positive, cyan)
    fig.add_trace(
        go.Bar(
            x=oi_data['strike'],
            y=oi_data['call_oi'],
            name='CALL OI',
            marker_color=COLORS['CIANO_NEON'],
            opacity=0.8,
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>Call OI:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add PUT bars (negative to show below axis, red)
    fig.add_trace(
        go.Bar(
            x=oi_data['strike'],
            y=-oi_data['put_oi'],  # Negative to show below zero line
            name='PUT OI',
            marker_color=COLORS['VERMELHO_NEON'],
            opacity=0.8,
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>Put OI:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color=COLORS['GRADE_SUTIL'], line_width=1)
    
    # Add spot price vertical line
    fig.add_vline(
        x=spot_price,
        line_width=2,
        line_dash="solid",
        line_color=COLORS['VERDE_NEON'],
    )
    
    # Add spot price annotation
    fig.add_annotation(
        x=spot_price,
        y=1.05,
        yref='paper',
        text=f"Spot: R$ {spot_price:.2f}",
        showarrow=False,
        font=dict(color=COLORS['TEXTO_PRINCIPAL'], size=12),
        bgcolor=COLORS['FUNDO_CARDS'],
        borderpad=4
    )
    
    # Update layout
    fig.update_layout(
        title={
            'text': title,
            'x': 0,
            'xanchor': 'left',
            'font': {'size': 20, 'color': COLORS['TEXTO_PRINCIPAL'], 'family': 'Segoe UI, sans-serif'}
        },
        xaxis_title="Strike",
        yaxis_title="Open Interest",
        template='brokeberg',
        paper_bgcolor=COLORS['FUNDO_ESCURO'],
        plot_bgcolor=COLORS['FUNDO_ESCURO'],
        barmode='relative',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=COLORS['TEXTO_SECUNDARIO'])
        ),
        height=500,
        margin=dict(t=100, b=60, l=80, r=40),
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            tickangle=45,
            range=[spot_price - 50, spot_price + 50],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            zeroline=True,
            zerolinecolor=COLORS['GRADE_SUTIL'],
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        )
    )
    
    return fig


def create_oi_by_expiry_chart(
    options_df: pd.DataFrame,
    title: str = "Open Interest por Vencimento"
) -> go.Figure:
    """
    Create Open Interest chart by expiry date, showing CALL and PUT bars grouped.
    
    Args:
        options_df: DataFrame with columns 'expiry', 'type', 'open_interest'
        title: Chart title
    """
    if options_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    df = options_df.copy()
    
    # Filter valid expiries
    df = df[df['expiry'].notna()]
    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados de vencimento", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    # Aggregate by expiry and type
    call_oi = df[df['type'] == 'CALL'].groupby('expiry')['open_interest'].sum().reset_index()
    call_oi.columns = ['expiry', 'call_oi']
    
    put_oi = df[df['type'] == 'PUT'].groupby('expiry')['open_interest'].sum().reset_index()
    put_oi.columns = ['expiry', 'put_oi']
    
    # Merge
    oi_data = pd.merge(call_oi, put_oi, on='expiry', how='outer').fillna(0)
    oi_data = oi_data.sort_values('expiry').reset_index(drop=True)
    
    # Format expiry dates for display
    oi_data['expiry_str'] = oi_data['expiry'].apply(lambda x: x.strftime('%d/%m/%Y'))
    
    # Create figure
    fig = go.Figure()
    
    # Add CALL bars (cyan)
    fig.add_trace(
        go.Bar(
            x=oi_data['expiry_str'],
            y=oi_data['call_oi'],
            name='CALL',
            marker_color=COLORS['CIANO_NEON'],
            opacity=0.85,
            hovertemplate='<b>Vencimento:</b> %{x}<br><b>Call OI:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add PUT bars (red)
    fig.add_trace(
        go.Bar(
            x=oi_data['expiry_str'],
            y=oi_data['put_oi'],
            name='PUT',
            marker_color=COLORS['VERMELHO_NEON'],
            opacity=0.85,
            hovertemplate='<b>Vencimento:</b> %{x}<br><b>Put OI:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Update layout
    fig.update_layout(
        title={
            'text': title,
            'x': 0,
            'xanchor': 'left',
            'font': {'size': 20, 'color': COLORS['TEXTO_PRINCIPAL'], 'family': 'Segoe UI, sans-serif'}
        },
        xaxis_title="Vencimento",
        yaxis_title="Open Interest",
        template='brokeberg',
        paper_bgcolor=COLORS['FUNDO_ESCURO'],
        plot_bgcolor=COLORS['FUNDO_ESCURO'],
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=COLORS['TEXTO_SECUNDARIO'])
        ),
        height=400,
        margin=dict(t=100, b=80, l=80, r=40),
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickangle=45,
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS['GRADE_SUTIL'],
            tickformat=',.0f',
            tickfont=dict(color=COLORS['TEXTO_SECUNDARIO'])
        )
    )
    
    return fig


# Keep old functions for backward compatibility
def create_gex_chart(gex_data: pd.DataFrame, spot_price: float, title: str = "") -> go.Figure:
    """Backward compatible function - now uses new style."""
    return create_market_gamma_chart(gex_data, spot_price, title)


def create_detailed_gex_chart(gex_data: pd.DataFrame, spot_price: float, title: str = "") -> go.Figure:
    """Backward compatible function."""
    return create_market_gamma_chart(gex_data, spot_price, title)


if __name__ == "__main__":
    # Test with sample data
    sample = pd.DataFrame({
        'strike': [145, 150, 155, 158, 160, 162, 165, 168, 170, 172, 175, 178, 180],
        'total_gex': [2e6, 3e6, 5e6, 8e6, 10e6, 5e6, -2e6, -8e6, -10e6, -7e6, -5e6, -3e6, -1e6],
        'call_gex': [-2e6, -3e6, -4e6, -5e6, -6e6, -8e6, -10e6, -12e6, -10e6, -8e6, -6e6, -4e6, -2e6],
        'put_gex': [4e6, 6e6, 9e6, 13e6, 16e6, 13e6, 8e6, 4e6, 0, 1e6, 1e6, 1e6, 1e6]
    })
    
    main_chart, metrics_panel, metrics = create_full_dashboard(sample, spot_price=161.57, date_str="16/01/2026")
    
    print("Metrics:", metrics)
    metrics_panel.show()
    main_chart.show()
