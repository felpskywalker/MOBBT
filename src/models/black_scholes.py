"""
Black-Scholes Model Implementation
Unified module for option pricing, Greeks calculation, and implied volatility.
"""

import numpy as np
from scipy.stats import norm


# =============================================================================
# CORE PARAMETERS
# =============================================================================

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


def calculate_d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate d2 parameter from Black-Scholes model."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = calculate_d1(S, K, T, r, sigma)
    return d1 - sigma * np.sqrt(T)


# =============================================================================
# OPTION PRICING
# =============================================================================

def black_scholes_put(S, K, T, r, sigma):
    """
    Calcula preço teórico de PUT usando Black-Scholes.
    
    Args:
        S: Preço do ativo
        K: Strike
        T: Tempo até vencimento em anos
        r: Taxa livre de risco anual (decimal)
        sigma: Volatilidade (decimal)
    """
    if T <= 0:
        return max(K - S, 0)
    
    d1 = calculate_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return put_price


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Alias for black_scholes_put."""
    return black_scholes_put(S, K, T, r, sigma)


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


# =============================================================================
# GREEKS
# =============================================================================

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


def calculate_greeks(S, K, T, r, sigma, option_type='put'):
    """
    Calcula as Gregas (Delta, Gamma, Vega, Theta) para uma opção.
    Retorna um dicionário com os valores.
    """
    d1 = calculate_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T) if T > 0 and sigma > 0 else 0
    
    # Common Greeks
    gamma = calculate_gamma(S, K, T, r, sigma)
    vega = calculate_vega(S, K, T, r, sigma)
    
    if option_type == 'put':
        delta = norm.cdf(d1) - 1 if T > 0 else 0
        theta_annual = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                        + r * K * np.exp(-r * T) * norm.cdf(-d2)) if T > 0 else 0
        theta_daily = theta_annual / 365
    else:  # call
        delta = norm.cdf(d1) if T > 0 else 0
        theta_annual = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) 
                        - r * K * np.exp(-r * T) * norm.cdf(d2)) if T > 0 else 0
        theta_daily = theta_annual / 365
        
    prob_exercise = abs(delta) * 100
    
    return {
        'delta': delta,
        'gamma': gamma,
        'vega': vega,
        'theta_daily': theta_daily,
        'param_iv': sigma,
        'prob_exercise': prob_exercise
    }


# =============================================================================
# IMPLIED VOLATILITY
# =============================================================================

def implied_volatility(market_price, S, K, T, r, max_iter=100, tol=1e-5):
    """
    Calcula volatilidade implícita usando Newton-Raphson (para PUTs).
    """
    sigma = 0.3  # Chute inicial
    for i in range(max_iter):
        price = black_scholes_put(S, K, T, r, sigma)
        d1 = calculate_d1(S, K, T, r, sigma)
        vega = S * norm.pdf(d1) * np.sqrt(T)
        
        if vega < 1e-10:
            break
            
        diff = market_price - price
        if abs(diff) < tol:
            return sigma
        sigma = sigma + diff / vega
        sigma = max(0.01, min(sigma, 3.0))  # Limita entre 1% e 300%
    return sigma


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
