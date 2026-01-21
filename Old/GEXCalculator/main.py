"""
GEX Calculator - Main Script
Calculates and visualizes Gamma Exposure for BOVA11 options.
Market Gamma style visualization with smooth curves and metrics panel.
"""

import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

# from b3_scraper import get_options_data
from opcoes_net_scraper import fetch_opcoes_net_data, parse_opcoes_net_data
from gex_calculator import calculate_gex_dataframe, aggregate_gex_by_strike
from visualization import create_full_dashboard


def get_spot_price(ticker: str = "BOVA11.SA") -> float:
    """
    Get current spot price using yfinance.
    
    Args:
        ticker: Yahoo Finance ticker symbol
    
    Returns:
        Current spot price
    """
    print(f"Fetching spot price for {ticker}...")
    stock = yf.Ticker(ticker)
    
    # Try to get the most recent price
    hist = stock.history(period="1d")
    
    if not hist.empty:
        spot = hist['Close'].iloc[-1]
    else:
        # Fallback to info
        info = stock.info
        spot = info.get('regularMarketPrice', info.get('previousClose', 0))
    
    print(f"Spot price: R$ {spot:.2f}")
    return float(spot)


def get_last_trading_date() -> str:
    """
    Get the last trading date (most recent weekday before today).
    
    Returns:
        Date string in DD/MM/YYYY format
    """
    today = datetime.now()
    trading_date = today - timedelta(days=1)  # Start with yesterday
    
    # Keep going back until we hit a weekday
    while trading_date.weekday() >= 5:  # Saturday=5, Sunday=6
        trading_date = trading_date - timedelta(days=1)
    
    return trading_date.strftime('%d/%m/%Y')


def main():
    """Main execution function."""
    print("=" * 60)
    print("GEX Calculator - BOVA11 (Market Gamma Style)")
    print("=" * 60)
    
    # 1. Get spot price
    spot_price = get_spot_price("BOVA11.SA")
    
    # 2. Get options data from Opcoes.net.br
    print(f"\nFetching options data from Opcoes.net.br...")
    raw_data = fetch_opcoes_net_data("BOVA11")
    options_df = parse_opcoes_net_data(raw_data)
    
    reference_date = get_last_trading_date() # Matches data source (yesterday's close)
    
    if options_df.empty:
        print("ERROR: No options data found!")
        return
    
    print(f"Found {len(options_df)} options")
    
    print(f"\nOptions summary:")
    print(f"  Total options: {len(options_df)}")
    print(f"  Calls: {len(options_df[options_df['type'] == 'CALL'])}")
    print(f"  Puts: {len(options_df[options_df['type'] == 'PUT'])}")
    print(f"  Unique strikes: {options_df['strike'].nunique()}")
    
    # 3. Calculate GEX
    print("\nCalculating GEX...")
    # Fetch prices=False because we already have price and IV from scraper
    gex_df = calculate_gex_dataframe(options_df, spot_price, fetch_prices=False)
    
    # 4. Aggregate by strike with bucketing (R$ 1.00 buckets for smoother curves)
    gex_by_strike = aggregate_gex_by_strike(gex_df, bucket_size=1.0)
    
    # Show all strikes (no filtering)
    # User requested: show ALL options regardless of strike
    filtered_gex = gex_by_strike.copy()
    
    print(f"\nTotal strikes in chart: {len(filtered_gex)}")
    
    # 5. Create Market Gamma style dashboard
    print("\nGenerating Market Gamma dashboard...")
    
    main_chart, metrics_panel, metrics = create_full_dashboard(
        filtered_gex,
        spot_price,
        date_str=reference_date
    )
    
    # Show metrics panel first, then main chart
    metrics_panel.show()
    main_chart.show()
    
    # 6. Print metrics summary
    print("\n" + "=" * 60)
    print("Market Gamma Metrics:")
    print("=" * 60)
    print(f"  Gamma Score:          {metrics.get('gamma_score', 0):.2f}")
    print(f"  Gamma Atual:          {metrics.get('gamma_atual', 0):,.0f}")
    print(f"  Flip Point:           R$ {metrics.get('flip_point', 0):.2f}")
    print(f"  Gamma Mín. Negativo:  R$ {metrics.get('gamma_min_negativo', 0):.2f}")
    print(f"  Gamma Máx. Positivo:  R$ {metrics.get('gamma_max_positivo', 0):.2f}")
    print(f"  Spot atual:           R$ {spot_price:.2f}")
    
    # 7. Full data summary
    print("\n" + "=" * 60)
    print("GEX Summary:")
    print("=" * 60)
    total_gex = gex_by_strike['total_gex'].sum()
    print(f"  Total GEX: R$ {total_gex:,.0f}")
    print(f"  Total Call GEX: R$ {gex_by_strike['call_gex'].sum():,.0f}")
    print(f"  Total Put GEX: R$ {gex_by_strike['put_gex'].sum():,.0f}")
    
    print("\n[OK] Analise concluida!")


if __name__ == "__main__":
    main()
