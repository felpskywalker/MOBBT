"""
Gamma Exposure (GEX) Calculator
Calculates GEX for each strike with dealer convention.
Fetches real-time Selic rate from BCB and option prices from B3.
"""

import io
import zipfile
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from typing import Tuple, Optional

try:
    from bcb import sgs
    BCB_AVAILABLE = True
except ImportError:
    BCB_AVAILABLE = False

from black_scholes import calculate_gamma, calculate_implied_volatility


# Default parameters (fallback if API fails)
DEFAULT_VOLATILITY = 0.22  # 22% annualized
DEFAULT_RISK_FREE_RATE = 0.1375  # 13.75% (Selic)
CONTRACT_MULTIPLIER = 1  # BOVA11 ETF options use 1:1 ratio

# Cache for Selic rate (to avoid multiple API calls)
_selic_cache = {'value': None, 'timestamp': None}


# =============================================================================
# BCB SELIC RATE FETCHING
# =============================================================================

def get_selic_rate(use_cache: bool = True) -> float:
    """
    Fetches current Selic target rate from BCB (SGS code 432).
    
    Args:
        use_cache: If True, reuse cached value if fetched within last hour
    
    Returns:
        Annual Selic rate as decimal (e.g., 0.1175 for 11.75%)
    """
    global _selic_cache
    
    # Check cache
    if use_cache and _selic_cache['value'] is not None:
        cache_age = (datetime.now() - _selic_cache['timestamp']).total_seconds()
        if cache_age < 3600:  # 1 hour cache
            return _selic_cache['value']
    
    if BCB_AVAILABLE:
        try:
            # SGS code 432 = Selic Meta (annual rate)
            selic = sgs.get({'selic': 432}, last=1)
            rate = selic['selic'].iloc[-1] / 100
            _selic_cache['value'] = rate
            _selic_cache['timestamp'] = datetime.now()
            print(f"[BCB] Selic rate fetched: {rate*100:.2f}%")
            return rate
        except Exception as e:
            print(f"Warning: Failed to fetch Selic from BCB lib: {e}")
    
    # Fallback: try direct API call
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        rate = float(data[0]['valor']) / 100
        _selic_cache['value'] = rate
        _selic_cache['timestamp'] = datetime.now()
        print(f"[BCB API] Selic rate fetched: {rate*100:.2f}%")
        return rate
    except Exception as e:
        print(f"Warning: Failed to fetch Selic via API: {e}. Using default {DEFAULT_RISK_FREE_RATE*100:.2f}%")
        return DEFAULT_RISK_FREE_RATE


# =============================================================================
# B3 OPTION PRICE FETCHING
# =============================================================================

def download_b3_option_data(ticker: str, date: str = None, max_days_back: int = 30) -> Optional[dict]:
    """
    Downloads option data from B3 with fallback to previous trading days.
    
    Args:
        ticker: Option ticker (e.g., 'BOVAA125' for BOVA11 Call strike 125)
        date: Starting date in format 'YYYY-MM-DD' (defaults to yesterday)
        max_days_back: Maximum days to search back for price data
    
    Returns:
        dict with 'ticker', 'last_price', 'date', 'volume', 'days_back'
        Returns None if no data found within max_days_back
    """
    from datetime import timedelta
    
    if date is None:
        start_date = datetime.now() - timedelta(days=1)  # Start from yesterday
    else:
        start_date = datetime.strptime(date, '%Y-%m-%d')
    
    # Try each day going back up to max_days_back
    for days_back in range(max_days_back + 1):
        check_date = start_date - timedelta(days=days_back)
        
        # Skip weekends
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            continue
        
        date_str = check_date.strftime('%Y-%m-%d')
        url = f"https://arquivos.b3.com.br/rapinegocios/tickercsv/{ticker}/{date_str}"
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Extract ZIP contents
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f, sep=';', encoding='latin-1')
            
            if df.empty:
                continue  # Try previous day
            
            # Parse relevant columns for price
            price_cols = ['PreçoNegócio', 'PrecoNegocio', 'Preço', 'Preco']
            last_price = None
            
            for col in price_cols:
                if col in df.columns:
                    last_price = df[col].iloc[-1]
                    break
            
            if last_price is None:
                # Try to find any price column
                price_cols_found = [c for c in df.columns if 'preco' in c.lower() or 'preço' in c.lower()]
                if price_cols_found:
                    last_price = df[price_cols_found[0]].iloc[-1]
                else:
                    continue  # Try previous day
            
            # Convert to float if string
            if isinstance(last_price, str):
                last_price = float(last_price.replace(',', '.'))
            
            # Calculate volume if available
            volume = 0
            vol_cols = ['Quantidade', 'QuantidadeNegociada', 'Volume']
            for col in vol_cols:
                if col in df.columns:
                    volume = df[col].sum()
                    break
            
            return {
                'ticker': ticker,
                'last_price': float(last_price),
                'date': date_str,
                'volume': int(volume) if volume else 0,
                'days_back': days_back
            }
            
        except requests.exceptions.HTTPError:
            continue  # Try previous day
        except Exception:
            continue  # Try previous day
    
    return None  # No price found in max_days_back days


def fetch_option_prices_batch(tickers: list, date: str = None) -> dict:
    """
    Fetches prices for multiple option tickers.
    
    Args:
        tickers: List of option tickers
        date: Date in format 'YYYY-MM-DD'
    
    Returns:
        dict mapping ticker -> dict with 'price', 'days_back' (None if not available)
    """
    results = {}
    for ticker in tickers:
        data = download_b3_option_data(ticker, date)
        if data:
            results[ticker] = {
                'price': data['last_price'],
                'days_back': data.get('days_back', 0),
                'date': data.get('date')
            }
        else:
            results[ticker] = None
    return results


def enrich_options_with_prices(options_df: pd.DataFrame, date: str = None) -> pd.DataFrame:
    """
    Enriches options DataFrame with real prices from B3.
    
    Args:
        options_df: DataFrame with 'ticker' column
        date: Date in format 'YYYY-MM-DD'
    
    Returns:
        DataFrame with added 'market_price' and 'price_date' columns
    """
    if options_df.empty or 'ticker' not in options_df.columns:
        return options_df
    
    df = options_df.copy()
    tickers = df['ticker'].unique().tolist()
    
    print(f"[B3] Fetching prices for {len(tickers)} options (searching up to D-30)...")
    results = fetch_option_prices_batch(tickers, date)
    
    # Map prices and track days_back
    def map_price(ticker):
        r = results.get(ticker)
        return r['price'] if r else None
    
    def map_days_back(ticker):
        r = results.get(ticker)
        return r['days_back'] if r else None
    
    df['market_price'] = df['ticker'].map(map_price)
    df['price_days_back'] = df['ticker'].map(map_days_back)
    
    # Statistics
    found = df['market_price'].notna().sum()
    from_previous = df[(df['market_price'].notna()) & (df['price_days_back'] > 0)]
    
    print(f"[B3] Found prices for {found}/{len(tickers)} options")
    if len(from_previous) > 0:
        print(f"[B3]   -> {len(from_previous)} prices from previous days (D-1 to D-30)")
    
    return df


# =============================================================================
# TIME CALCULATIONS
# =============================================================================

def calculate_time_to_expiry(expiry_date: datetime, reference_date: datetime = None) -> float:
    """
    Calculate time to expiry in years.
    
    Args:
        expiry_date: Option expiration date
        reference_date: Reference date (defaults to today)
    
    Returns:
        Time to expiry in years
    """
    if reference_date is None:
        reference_date = datetime.now()
    
    if isinstance(expiry_date, str):
        expiry_date = datetime.strptime(expiry_date, '%d/%m/%Y')
    
    days_to_expiry = (expiry_date - reference_date).days
    if days_to_expiry <= 0:
        return 1/365  # Minimum 1 day to avoid division by zero
    
    return days_to_expiry / 365


# =============================================================================
# GEX CALCULATIONS
# =============================================================================

def calculate_option_gex(
    spot: float,
    strike: float,
    time_to_expiry: float,
    open_interest: int,
    option_type: str,
    risk_free_rate: float = None,
    volatility: float = None
) -> float:
    """
    Calculate GEX for a single option.
    
    Formula: GEX = Gamma * OI * Multiplier * Spot * 0.01
    
    Dealer Convention:
    - Dealer sells Calls to market -> Dealer is short gamma -> Negative GEX
    - Dealer sells Puts to market -> Dealer is short gamma -> Positive GEX
    
    Args:
        spot: Current spot price
        strike: Option strike price
        time_to_expiry: Time to expiry in years
        open_interest: Number of contracts
        option_type: 'CALL' or 'PUT'
        risk_free_rate: Risk-free rate (defaults to BCB Selic)
        volatility: Volatility (defaults to DEFAULT_VOLATILITY)
    
    Returns:
        GEX value in currency units
    """
    if risk_free_rate is None:
        risk_free_rate = get_selic_rate()
    if volatility is None:
        volatility = DEFAULT_VOLATILITY
    
    gamma = calculate_gamma(
        S=spot,
        K=strike,
        T=time_to_expiry,
        r=risk_free_rate,
        sigma=volatility
    )
    
    # Base GEX calculation
    gex = gamma * open_interest * CONTRACT_MULTIPLIER * (spot ** 2) * 0.01
    
    # Apply sign convention (matching reference chart: Calls positive, Puts negative)
    if option_type == 'CALL':
        gex = gex   # Calls positive
    elif option_type == 'PUT':
        gex = -gex  # Puts negative
    
    return gex


def calculate_gex_dataframe(
    options_df: pd.DataFrame, 
    spot: float,
    risk_free_rate: float = None,
    volatility: float = None,
    fetch_prices: bool = False,
    price_date: str = None,
    use_iv: bool = True
) -> pd.DataFrame:
    """
    Calculate GEX for all options in a DataFrame.
    
    Args:
        options_df: DataFrame with columns: ticker, type, strike, expiry, open_interest
        spot: Current spot price
        risk_free_rate: Risk-free rate (defaults to BCB Selic)
        volatility: Default volatility (used when IV cannot be calculated)
        fetch_prices: If True, fetch real option prices from B3
        price_date: Date for fetching prices (YYYY-MM-DD format)
        use_iv: If True, calculate implied volatility for each option from market price
    
    Returns:
        DataFrame with added 'gamma', 'gex', 'iv' columns
    """
    if options_df.empty:
        return options_df
    
    # Get risk-free rate from BCB if not provided
    if risk_free_rate is None:
        risk_free_rate = get_selic_rate()
    if volatility is None:
        volatility = DEFAULT_VOLATILITY
    
    df = options_df.copy()
    reference_date = datetime.now()
    
    # Optionally fetch real prices from B3
    if fetch_prices:
        df = enrich_options_with_prices(df, price_date)
    
    # Calculate time to expiry for each option
    df['time_to_expiry'] = df['expiry'].apply(
        lambda x: calculate_time_to_expiry(x, reference_date) if pd.notna(x) else 30/365
    )
    
    # IV Calculation Logic
    # If 'iv' column exists and has data (from scraper), utilize it.
    # Otherwise, calculate or approximate.
    
    if 'iv' not in df.columns or use_iv:
        print("[GEX] Calculating IVs from market prices...")
        
        # First pass: Calculate IV for options with market prices
        def calc_iv_from_price(row):
            if use_iv and 'market_price' in df.columns and pd.notna(row.get('market_price')) and row['market_price'] > 0:
                iv = calculate_implied_volatility(
                    market_price=row['market_price'],
                    S=spot,
                    K=row['strike'],
                    T=row['time_to_expiry'],
                    r=risk_free_rate,
                    option_type=row['type']
                )
                if iv is not None:
                    return iv
            return None  # No IV calculated yet
        
        df['iv_calculated'] = df.apply(calc_iv_from_price, axis=1)
        
        # Merge with existing IV if available, prioritizing calculated
        if 'iv' in df.columns:
            df['iv'] = df['iv_calculated'].fillna(df['iv'])
        else:
            df['iv'] = df['iv_calculated']
            
        df['iv_source'] = df['iv_calculated'].apply(lambda x: 'MARKET' if pd.notna(x) else None)
        
        # ... (rest of simple fallback logic if needed)
    else:
        print("[GEX] Using existing IV from data source")
        df['iv_source'] = 'SOURCE'
    # Init source for existing IVs if not calculated
    if 'iv_source' not in df.columns:
         df['iv_source'] = df['iv'].apply(lambda x: 'SOURCE' if pd.notna(x) else None)

    # Count IVs available before fallback
    iv_from_market = df['iv'].notna().sum()
    
    # Second pass: Approximate IV for options without market price using nearest strike
    def get_fallback_iv(row):
        if pd.notna(row['iv']):
            return row['iv'], row['iv_source']  # Already has IV from market price
        
        # Find options of same type with valid IV
        same_type_with_iv = df[
            (df['type'] == row['type']) & 
            (df['iv'].notna())
        ]
        
        if same_type_with_iv.empty:
            return volatility, 'DEFAULT'  # No reference, use default
        
        # Find nearest strike with valid IV
        strike_diffs = abs(same_type_with_iv['strike'] - row['strike'])
        nearest_idx = strike_diffs.idxmin()
        nearest_iv = df.loc[nearest_idx, 'iv']
        
        return nearest_iv, 'NEAREST'
    
    # Apply fallback and track source
    fallback_results = df.apply(get_fallback_iv, axis=1)
    df['iv'] = fallback_results.apply(lambda x: x[0])
    df['iv_source'] = fallback_results.apply(lambda x: x[1])
    
    # Fill any remaining NaN with default volatility
    df.loc[df['iv'].isna(), 'iv_source'] = 'DEFAULT'
    df['iv'] = df['iv'].fillna(volatility)
    
    # Log IV statistics
    iv_from_nearest = (df['iv_source'] == 'NEAREST').sum()
    iv_from_default = (df['iv_source'] == 'DEFAULT').sum()
    
    print(f"[IV] IV from market prices: {iv_from_market}")
    print(f"[IV] IV from nearest strike: {iv_from_nearest}")
    print(f"[IV] IV from default ({volatility*100:.0f}%): {iv_from_default}")
    
    if iv_from_market > 0:
        market_ivs = df[df['iv_source'] == 'MARKET']['iv']
        print(f"[IV] Market IV range: {market_ivs.min()*100:.1f}% - {market_ivs.max()*100:.1f}%")
        
    # Calculate Weighted Average IV (by Open Interest)
    # This gives a much more realistic view of the market than simple mean
    try:
        total_oi = df['open_interest'].sum()
        if total_oi > 0:
            weighted_iv = (df['iv'] * df['open_interest']).sum() / total_oi
            print(f"[IV] Weighted Avg IV (by OI): {weighted_iv*100:.2f}%")
            
            # Also show simple mean for comparison (often skewed by illiquid strikes)
            print(f"[IV] Simple Mean IV: {df['iv'].mean()*100:.2f}% (skewed by illiquid options)")
    except Exception as e:
        print(f"[IV] Could not calculate weighted IV: {e}")
    
    # Calculate gamma for each option using its own IV
    df['gamma'] = df.apply(
        lambda row: calculate_gamma(
            S=spot,
            K=row['strike'],
            T=row['time_to_expiry'],
            r=risk_free_rate,
            sigma=row['iv']
        ),
        axis=1
    )
    
    # Calculate GEX for each option
    df['gex'] = df.apply(
        lambda row: calculate_option_gex(
            spot=spot,
            strike=row['strike'],
            time_to_expiry=row['time_to_expiry'],
            open_interest=row['open_interest'],
            option_type=row['type'],
            risk_free_rate=risk_free_rate,
            volatility=row['iv']
        ),
        axis=1
    )
    
    return df


def aggregate_gex_by_strike(gex_df: pd.DataFrame, bucket_size: float = 1.0) -> pd.DataFrame:
    """
    Aggregate total GEX by strike price with optional bucketing.
    
    Args:
        gex_df: DataFrame with GEX calculated for each option
        bucket_size: Size of strike buckets for aggregation (e.g., 1.0 = round to nearest R$ 1)
                    Use 0 or None for no bucketing (original strikes)
    
    Returns:
        DataFrame with strike and total_gex columns
    """
    if gex_df.empty:
        return pd.DataFrame(columns=['strike', 'total_gex', 'call_gex', 'put_gex'])
    
    df = gex_df.copy()
    
    # Apply bucketing if specified
    if bucket_size and bucket_size > 0:
        df['strike_bucket'] = (df['strike'] / bucket_size).round() * bucket_size
    else:
        df['strike_bucket'] = df['strike']
    
    # Separate calls and puts for reference
    calls = df[df['type'] == 'CALL'].groupby('strike_bucket')['gex'].sum()
    puts = df[df['type'] == 'PUT'].groupby('strike_bucket')['gex'].sum()
    
    # Total GEX by strike bucket
    total = df.groupby('strike_bucket')['gex'].sum()
    
    result = pd.DataFrame({
        'strike': total.index,
        'total_gex': total.values
    })
    
    # Add call and put breakdown
    result['call_gex'] = result['strike'].map(calls).fillna(0)
    result['put_gex'] = result['strike'].map(puts).fillna(0)
    
    result = result.sort_values('strike').reset_index(drop=True)
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("GEX Calculator - Testing BCB and B3 Integration")
    print("=" * 60)
    
    # Test BCB Selic rate fetching
    print("\n[1] Testing BCB Selic Rate Fetch...")
    selic = get_selic_rate()
    print(f"    Current Selic: {selic * 100:.2f}%")
    
    # Test B3 option price fetching
    print("\n[2] Testing B3 Option Price Fetch...")
    test_ticker = "BOVAB125"  # BOVA11 Call February strike 125
    option_data = download_b3_option_data(test_ticker)
    if option_data:
        print(f"    {test_ticker}: R$ {option_data['last_price']:.2f}")
    else:
        print(f"    {test_ticker}: No data available")
    
    # Test with sample data
    print("\n[3] Testing GEX Calculation...")
    sample_data = pd.DataFrame({
        'ticker': ['BOVAA120', 'BOVAA125', 'BOVAM120', 'BOVAM125'],
        'type': ['CALL', 'CALL', 'PUT', 'PUT'],
        'strike': [120.0, 125.0, 120.0, 125.0],
        'expiry': [datetime(2026, 1, 23)] * 4,
        'open_interest': [10000, 15000, 8000, 12000]
    })
    
    spot = 123.50
    
    gex_df = calculate_gex_dataframe(sample_data, spot, fetch_prices=False)
    print("\nOptions with GEX (using default IV):")
    print(gex_df[['ticker', 'type', 'strike', 'iv', 'gamma', 'gex']])
    
    print("\nAggregated GEX by strike:")
    agg = aggregate_gex_by_strike(gex_df)
    print(agg)
    
    # Test with real prices from B3 to calculate IV
    print("\n" + "=" * 60)
    print("[4] Testing IV Calculation with Real Prices from B3...")
    print("=" * 60)
    
    # Create sample with real tickers
    sample_with_prices = pd.DataFrame({
        'ticker': ['BOVAB120', 'BOVAB125', 'BOVAB130', 'BOVAN120', 'BOVAN125'],
        'type': ['CALL', 'CALL', 'CALL', 'PUT', 'PUT'],
        'strike': [120.0, 125.0, 130.0, 120.0, 125.0],
        'expiry': [datetime(2026, 2, 21)] * 5,  # February expiry
        'open_interest': [5000, 10000, 8000, 4000, 6000]
    })
    
    gex_df_real = calculate_gex_dataframe(
        sample_with_prices, 
        spot=123.50, 
        fetch_prices=True,
        use_iv=True
    )
    
    print("\nOptions with IV calculated from market prices:")
    cols = ['ticker', 'type', 'strike', 'market_price', 'iv', 'gamma', 'gex']
    available_cols = [c for c in cols if c in gex_df_real.columns]
    print(gex_df_real[available_cols].to_string())
    
    # Show IV statistics
    if 'iv' in gex_df_real.columns:
        iv_found = gex_df_real[gex_df_real['market_price'].notna()]['iv']
        if len(iv_found) > 0:
            print(f"\nIV Statistics (from market prices):")
            print(f"  Mean IV: {iv_found.mean()*100:.2f}%")
            print(f"  Min IV:  {iv_found.min()*100:.2f}%")
            print(f"  Max IV:  {iv_found.max()*100:.2f}%")

