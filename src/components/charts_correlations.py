"""
Componentes de gráficos para Correlação e Regime de Mercado.
"""

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np


def gerar_heatmap_correlacao(corr_matrix: pd.DataFrame, title: str = "Matriz de Correlação"):
    """
    Gera heatmap estilizado de correlação.
    
    Args:
        corr_matrix: Matriz de correlação (DataFrame quadrado)
        title: Título do gráfico
    
    Returns:
        Figura Plotly
    """
    if corr_matrix.empty:
        fig = go.Figure()
        fig.update_layout(title_text="Sem dados disponíveis", template='brokeberg')
        return fig
    
    # Cores: vermelho para negativo, azul para positivo
    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.index,
        colorscale=[
            [0.0, '#FF4B4B'],    # Vermelho forte para -1
            [0.25, '#FF8B8B'],   # Vermelho claro
            [0.5, '#FFFFFF'],    # Branco para 0
            [0.75, '#8BC4FF'],   # Azul claro
            [1.0, '#0066FF']     # Azul forte para +1
        ],
        zmid=0,
        zmin=-1,
        zmax=1,
        text=corr_matrix.values.round(2),
        texttemplate='%{text:.2f}',
        textfont={"size": 12},
        hoverongaps=False,
        colorbar=dict(
            title="Correlação",
            tickvals=[-1, -0.5, 0, 0.5, 1],
            ticktext=['-1', '-0.5', '0', '0.5', '1']
        )
    ))
    
    fig.update_layout(
        title_text=title,
        title_x=0,
        template='brokeberg',
        xaxis=dict(side='bottom'),
        yaxis=dict(autorange='reversed'),
        height=500
    )
    
    return fig


def gerar_grafico_beta_rolling(beta_series: pd.Series, ativo: str, indice: str = "IBOV"):
    """
    Gera gráfico de beta rolling ao longo do tempo.
    
    Args:
        beta_series: Série de beta rolling
        ativo: Nome do ativo
        indice: Nome do índice de referência
    
    Returns:
        Figura Plotly
    """
    if beta_series.empty:
        fig = go.Figure()
        fig.update_layout(title_text="Sem dados disponíveis", template='brokeberg')
        return fig
    
    # Últimos 2 anos
    cutoff = beta_series.index.max() - pd.DateOffset(years=2)
    beta_plot = beta_series[beta_series.index >= cutoff]
    
    fig = go.Figure()
    
    # Linha de beta
    fig.add_trace(go.Scatter(
        x=beta_plot.index,
        y=beta_plot.values,
        mode='lines',
        name=f'Beta ({ativo} vs {indice})',
        line=dict(color='#00E676', width=2)
    ))
    
    # Linha de beta = 1 (referência)
    fig.add_hline(y=1, line_dash="dash", line_color="rgba(255,255,255,0.5)",
                  annotation_text="Beta = 1", annotation_position="bottom right")
    
    # Linha de beta = 0
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
    
    # Média do período
    beta_mean = beta_plot.mean()
    fig.add_hline(y=beta_mean, line_dash="solid", line_color="#FFB302",
                  annotation_text=f"Média: {beta_mean:.2f}", annotation_position="top right")
    
    fig.update_layout(
        title_text=f'Beta Rolling (63d) - {ativo} vs {indice}',
        title_x=0,
        template='brokeberg',
        xaxis_title="Data",
        yaxis_title="Beta",
        showlegend=False,
        height=400
    )
    
    return fig


def gerar_gauge_regime(score: int, regime: str):
    """
    Gera indicador visual de regime (gauge).
    
    Args:
        score: Score de regime (-100 a +100)
        regime: 'RISK_ON', 'RISK_OFF', ou 'NEUTRAL'
    
    Returns:
        Figura Plotly
    """
    # Cores baseadas no regime
    if regime == 'RISK_ON':
        bar_color = '#00E676'  # Verde
    elif regime == 'RISK_OFF':
        bar_color = '#FF4B4B'  # Vermelho
    else:
        bar_color = '#636EFA'  # Azul
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Regime: {regime.replace('_', ' ')}"},
        delta={'reference': 0, 'position': "bottom"},
        gauge={
            'axis': {'range': [-100, 100], 'tickvals': [-100, -50, 0, 50, 100]},
            'bar': {'color': bar_color, 'thickness': 0.75},
            'bgcolor': "rgba(255,255,255,0.1)",
            'borderwidth': 2,
            'bordercolor': "white",
            'steps': [
                {'range': [-100, -30], 'color': 'rgba(255, 75, 75, 0.3)'},
                {'range': [-30, 30], 'color': 'rgba(99, 110, 250, 0.3)'},
                {'range': [30, 100], 'color': 'rgba(0, 230, 118, 0.3)'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': score
            }
        }
    ))
    
    fig.update_layout(
        template='brokeberg',
        height=300,
        margin=dict(l=30, r=30, t=80, b=30)
    )
    
    return fig


def gerar_grafico_correlacao_ts(corr_series: pd.Series, nome_par: str):
    """
    Gera gráfico de correlação ao longo do tempo.
    
    Args:
        corr_series: Série de correlação rolling
        nome_par: Nome do par de ativos (ex: "IBOV vs EWZ")
    
    Returns:
        Figura Plotly
    """
    if corr_series.empty:
        fig = go.Figure()
        fig.update_layout(title_text="Sem dados disponíveis", template='brokeberg')
        return fig
    
    # Últimos 2 anos
    cutoff = corr_series.index.max() - pd.DateOffset(years=2)
    corr_plot = corr_series[corr_series.index >= cutoff]
    
    fig = go.Figure()
    
    # Área preenchida
    fig.add_trace(go.Scatter(
        x=corr_plot.index,
        y=corr_plot.values,
        mode='lines',
        name='Correlação',
        line=dict(color='#636EFA', width=2),
        fill='tozeroy',
        fillcolor='rgba(99, 110, 250, 0.2)'
    ))
    
    # Linhas de referência
    fig.add_hline(y=0.8, line_dash="dash", line_color="rgba(0,230,118,0.5)",
                  annotation_text="Alta (0.8)")
    fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.5)")
    fig.add_hline(y=-0.5, line_dash="dash", line_color="rgba(255,75,75,0.5)",
                  annotation_text="Negativa (-0.5)")
    
    # Média
    corr_mean = corr_plot.mean()
    fig.add_hline(y=corr_mean, line_dash="dot", line_color="#FFB302",
                  annotation_text=f"Média: {corr_mean:.2f}")
    
    fig.update_layout(
        title_text=f'Correlação Rolling (63d) - {nome_par}',
        title_x=0,
        template='brokeberg',
        xaxis_title="Data",
        yaxis_title="Correlação",
        yaxis=dict(range=[-1.1, 1.1]),
        showlegend=False,
        height=350
    )
    
    return fig
