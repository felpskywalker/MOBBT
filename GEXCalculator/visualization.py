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
    title: str = "Market Gamma"
) -> go.Figure:
    """
    Create Market Gamma style chart with smooth curves.
    Similar to the reference image with CALL, PUT, and CALL+PUT lines.
    """
    if gex_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5)
        return fig
    
    df = gex_data.sort_values('strike').reset_index(drop=True)
    strikes = df['strike'].values
    
    # Prepare data for each curve
    call_gex = df['call_gex'].values
    put_gex = df['put_gex'].values
    total_gex = df['total_gex'].values
    
    # Smooth the curves
    strikes_smooth_call, call_smooth = smooth_curve(strikes, call_gex)
    strikes_smooth_put, put_smooth = smooth_curve(strikes, put_gex)
    strikes_smooth_total, total_smooth = smooth_curve(strikes, total_gex)
    
    # Create figure
    fig = go.Figure()
    
    # Add CALL line (blue)
    fig.add_trace(
        go.Scatter(
            x=strikes_smooth_call,
            y=call_smooth,
            mode='lines',
            name='CALL',
            line=dict(color='#3b82f6', width=2.5),
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>Call GEX:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add PUT line (pink/red)
    fig.add_trace(
        go.Scatter(
            x=strikes_smooth_put,
            y=put_smooth,
            mode='lines',
            name='PUT',
            line=dict(color='#f472b6', width=2.5),
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>Put GEX:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add CALL+PUT line (yellow/green gradient effect - use yellow)
    fig.add_trace(
        go.Scatter(
            x=strikes_smooth_total,
            y=total_smooth,
            mode='lines',
            name='CALL + PUT',
            line=dict(color='#facc15', width=3),
            hovertemplate='<b>Strike:</b> R$ %{x:.2f}<br><b>Total GEX:</b> %{y:,.0f}<extra></extra>'
        )
    )
    
    # Add zero line
    fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.3)", line_width=1)
    
    # Add spot price vertical line
    fig.add_vline(
        x=spot_price,
        line_width=2,
        line_dash="solid",
        line_color="white",
    )
    
    # Add spot price annotation
    fig.add_annotation(
        x=spot_price,
        y=1.05,
        yref='paper',
        text=f"Spot: R$ {spot_price:.2f}",
        showarrow=False,
        font=dict(color='white', size=12),
        bgcolor='rgba(0,0,0,0.7)',
        borderpad=4
    )
    
    # Update layout - dark theme like reference
    fig.update_layout(
        title={
            'text': title,
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 24, 'color': 'white', 'family': 'Arial Black'}
        },
        xaxis_title="Strike",
        yaxis_title="GEX",
        template='plotly_dark',
        paper_bgcolor='#1a1f2e',
        plot_bgcolor='#1a1f2e',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=12)
        ),
        height=500,
        margin=dict(t=100, b=60, l=80, r=40),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.1)',
            tickformat=',.0f',
            tickangle=45,
            range=[spot_price - 50, spot_price + 50]  # Show ±50 from spot
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.1)',
            tickformat=',.0f',
            zeroline=True,
            zerolinecolor='rgba(255,255,255,0.3)'
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
            title={'text': "Gamma Score [σ]", 'font': {'size': 14, 'color': 'white'}},
            number={'font': {'size': 24, 'color': '#38bdf8'}},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': "white"},
                'bar': {'color': "#f97316"},
                'bgcolor': "rgba(255,255,255,0.1)",
                'borderwidth': 0,
                'steps': [
                    {'range': [-1, 0], 'color': 'rgba(239,68,68,0.3)'},
                    {'range': [0, 1], 'color': 'rgba(34,197,94,0.3)'}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 2},
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
            title={'text': "Gamma Atual", 'font': {'size': 14, 'color': 'white'}},
            number={'font': {'size': 28, 'color': 'white'}, 'valueformat': '.2s'}
        ),
        row=1, col=2
    )
    
    # Gamma Mínimo Negativo
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gamma_min,
            title={'text': "Gamma Mínimo<br>Negativo", 'font': {'size': 14, 'color': 'white'}},
            number={'font': {'size': 28, 'color': '#38bdf8'}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=3
    )
    
    # Flip Point
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=flip,
            title={'text': "Flip", 'font': {'size': 14, 'color': 'white'}},
            number={'font': {'size': 28, 'color': '#38bdf8'}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=4
    )
    
    # Gamma Máximo Positivo
    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gamma_max,
            title={'text': "Gamma Máximo<br>Positivo", 'font': {'size': 14, 'color': 'white'}},
            number={'font': {'size': 28, 'color': '#38bdf8'}, 'prefix': 'R$ ', 'valueformat': '.2f'}
        ),
        row=1, col=5
    )
    
    fig.update_layout(
        paper_bgcolor='#1a1f2e',
        plot_bgcolor='#1a1f2e',
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
