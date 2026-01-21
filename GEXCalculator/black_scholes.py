"""
Black-Scholes Model Implementation
Calculates option Greeks, specifically Gamma for GEX calculation.
"""

import numpy as np
from scipy.stats import norm


def calculate_d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate d1 parameter from Black-Scholes model.
    
    Args:
        S: Spot price
        K: Strike price
        T: Time to expiration (in years)
        r: Risk-free rate
        sigma: Volatility
    
    Returns:
        d1 value
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return d1


def calculate_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Gamma of an option using Black-Scholes.
    Gamma = phi(d1) / (S * sigma * sqrt(T))
    where phi is the standard normal PDF.
    
    Args:
        S: Spot price
        K: Strike price  
        T: Time to expiration (in years)
        r: Risk-free rate
        sigma: Volatility
    
    Returns:
        Gamma value
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    d1 = calculate_d1(S, K, T, r, sigma)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma


def calculate_delta_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Delta for a Call option.
    Delta_call = N(d1)
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = calculate_d1(S, K, T, r, sigma)
    return norm.cdf(d1)


def calculate_delta_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Delta for a Put option.
    Delta_put = N(d1) - 1
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = calculate_d1(S, K, T, r, sigma)
    return norm.cdf(d1) - 1


def calculate_d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate d2 parameter from Black-Scholes model."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = calculate_d1(S, K, T, r, sigma)
    return d1 - sigma * np.sqrt(T)


def calculate_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Vega of an option (same for calls and puts).
    Vega = S * phi(d1) * sqrt(T)
    Returns Vega per 1% change in volatility.
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    d1 = calculate_d1(S, K, T, r, sigma)
    return S * norm.pdf(d1) * np.sqrt(T) / 100


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Black-Scholes call option price.
    C = S*N(d1) - K*e^(-rT)*N(d2)
    """
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    
    d1 = calculate_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    
    call = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return call


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate Black-Scholes put option price.
    P = K*e^(-rT)*N(-d2) - S*N(-d1)
    """
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    
    d1 = calculate_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    
    put = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return put


def calculate_implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = 'CALL',
    max_iterations: int = 100,
    tolerance: float = 1e-6
) -> float:
    """
    Calculate implied volatility using Newton-Raphson method.
    
    Args:
        market_price: Observed market price of the option
        S: Spot price
        K: Strike price
        T: Time to expiration (years)
        r: Risk-free rate
        option_type: 'CALL' or 'PUT'
        max_iterations: Maximum iterations for convergence
        tolerance: Price tolerance for convergence
    
    Returns:
        Implied volatility as decimal (e.g., 0.25 for 25%)
        Returns None if calculation fails
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    
    # Check intrinsic value bounds
    if option_type.upper() == 'CALL':
        intrinsic = max(S - K * np.exp(-r * T), 0)
        price_func = bs_call_price
    else:
        intrinsic = max(K * np.exp(-r * T) - S, 0)
        price_func = bs_put_price
    
    # Market price below intrinsic value - no valid IV
    if market_price < intrinsic - tolerance:
        return None
    
    # Initial guess using approximation (Brenner & Subrahmanyam 1988)
    sigma = np.sqrt(2 * np.pi / T) * market_price / S
    sigma = max(0.01, min(sigma, 5.0))  # Bound initial guess
    
    for i in range(max_iterations):
        # Calculate model price
        model_price = price_func(S, K, T, r, sigma)
        
        # Calculate difference
        diff = model_price - market_price
        
        # Check convergence
        if abs(diff) < tolerance:
            return sigma
        
        # Calculate Vega (sensitivity to volatility)
        d1 = calculate_d1(S, K, T, r, sigma)
        vega = S * norm.pdf(d1) * np.sqrt(T)
        
        # Avoid division by very small vega
        if abs(vega) < 1e-10:
            # Use bisection fallback
            if diff > 0:
                sigma = sigma * 0.9
            else:
                sigma = sigma * 1.1
            continue
        
        # Newton-Raphson update
        sigma = sigma - diff / vega
        
        # Bound sigma to reasonable range
        sigma = max(0.001, min(sigma, 10.0))
    
    # Failed to converge - return last estimate if reasonable
    if 0.01 < sigma < 5.0:
        return sigma
    return None


if __name__ == "__main__":
    # Test the calculations
    S = 125.0  # Spot
    K = 120.0  # Strike
    T = 30/365  # 30 days
    r = 0.1375  # 13.75% risk-free rate
    sigma = 0.22  # 22% volatility
    
    d1 = calculate_d1(S, K, T, r, sigma)
    gamma = calculate_gamma(S, K, T, r, sigma)
    
    print(f"Spot: {S}, Strike: {K}")
    print(f"Time to Expiry: {T*365:.0f} days")
    print(f"d1: {d1:.4f}")
    print(f"Gamma: {gamma:.6f}")
