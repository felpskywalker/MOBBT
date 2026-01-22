"""
Opcoes.net.br Scraper Module
Extracts comprehensive options data (Ticker, Strike, Expiry, IV, Open Interest) from a single page.
Avoids multiple requests and B3 pagination issues.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
from datetime import datetime, timedelta
import re

# Cache para dados do opcoes.net (evita abrir browser múltiplas vezes)
_opcoes_cache = {
    'data': {},      # ticker -> parsed DataFrame
    'timestamp': {}  # ticker -> datetime
}
CACHE_EXPIRY_MINUTES = 5

def get_chrome_driver() -> webdriver.Chrome:
    """Create and configure Chrome WebDriver.
    
    Supports both:
    - Local development with webdriver-manager
    - Streamlit Cloud with system-installed Chromium
    """
    import shutil
    import os
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Use headless mode for production
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Check for system Chromium (Streamlit Cloud / Linux)
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable'
    ]
    
    chromedriver_paths = [
        '/usr/bin/chromedriver',
        '/usr/lib/chromium/chromedriver',
        '/usr/lib/chromium-browser/chromedriver'
    ]
    
    # Find Chromium binary
    chromium_binary = None
    for path in chromium_paths:
        if os.path.exists(path):
            chromium_binary = path
            break
    
    # Find ChromeDriver
    chromedriver_path = None
    for path in chromedriver_paths:
        if os.path.exists(path):
            chromedriver_path = path
            break
    
    # Also check with shutil.which
    if not chromedriver_path:
        chromedriver_path = shutil.which('chromedriver')
    
    if chromium_binary:
        chrome_options.binary_location = chromium_binary
        print(f"[SELENIUM] Using system Chromium: {chromium_binary}")
    
    if chromedriver_path:
        print(f"[SELENIUM] Using system ChromeDriver: {chromedriver_path}")
        service = Service(chromedriver_path)
    else:
        # Fallback to webdriver-manager (local development)
        print("[SELENIUM] Using webdriver-manager for ChromeDriver")
        service = Service(ChromeDriverManager().install())
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def fetch_opcoes_net_data(ticker="BOVA11"):
    """
    Fetch all options data from opcoes.net.br for a given underlying ticker.
    Returns DataFrame with columns: ticker, type, strike, expiry, iv, open_interest, market_price
    """
    url = f"https://opcoes.net.br/opcoes/bovespa/{ticker}"
    driver = get_chrome_driver()
    
    try:
        print(f"Accessing {url}...")
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "grade-vencimentos-dates"))
        )
        time.sleep(3) # Extra wait for initial scripts
        
        # 1. Select ALL maturities (Vencimentos) using JavaScript for reliability
        print("Selecting all maturities...")
        try:
            # Use JavaScript to select all maturity checkboxes
            driver.execute_script("""
                // Select all maturity checkboxes
                var checkboxes = document.querySelectorAll('#grade-vencimentos-dates input[type="checkbox"]');
                console.log('Found ' + checkboxes.length + ' maturity checkboxes');
                checkboxes.forEach(function(cb) {
                    if (!cb.checked) {
                        cb.click();
                    }
                });
            """)
            time.sleep(2)
            
            # Trigger grid reload
            driver.execute_script("""
                try {
                    if (typeof gradeOpcoes !== 'undefined' && gradeOpcoes.CarregarGrade) {
                        gradeOpcoes.CarregarGrade();
                    }
                } catch(e) {
                    console.log('Could not reload grid: ' + e);
                }
            """)
            time.sleep(3)  # Wait for table reload
        except Exception as e:
            print(f"Error selecting maturities: {e}")
        
        # 2. Select ALL strikes (Expand Range)
        print("Expanding strike range to maximum...")
        try:
            # Opcoes.net.br uses jQuery UI Slider. We can manipulate it via JS.
            # We set values to [0, 10000] to cover everything.
            driver.execute_script("""
                try {
                    var slider = $("#strike-range");
                    var min = slider.slider("option", "min");
                    var max = slider.slider("option", "max");
                    slider.slider("values", [min, max]);
                    // Trigger change/slide event to update table
                    slider.slider("option", "change").call(slider);
                    // Also try custom trigger
                    gradeOpcoes.CarregarGrade();
                } catch(e) {
                    console.log("Error updating slider: " + e);
                }
            """)
            time.sleep(3) # Wait for table reload
        except Exception as e:
            print(f"Error expanding strike range: {e}")

        # Scroll to load all rows (Lazy loading)
        print("Loading all table rows...")
        scroll_element = driver.find_element(By.CSS_SELECTOR, ".dt-scroll-body")
        
        last_height = driver.execute_script("return arguments[0].scrollHeight", scroll_element)
        attempts = 0
        while attempts < 30: # Limit scroll attempts
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_element)
            time.sleep(1)
            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_element)
            if new_height == last_height:
                break
            last_height = new_height
            attempts += 1
            
        # DOM Extraction with CORRECT indices for multi-expiry table
        # When multiple expiries are selected, table adds "Vencimento" and "Dias úteis" columns
        # Indices verified via browser inspection:
        # 0: Ticker, 1: Vencimento (Expiry date), 2: Dias úteis, 3: Tipo (CALL/PUT)
        # 6: Strike, 9: Último (Price), 10: Var.(%), 14: Vol.Impl. (IV)
        # 15: Delta, 16: Gamma, 17: Theta($), 18: Theta(%), 19: Vega
        # 21: Cob, 22: Trav, 23: Descob
        extraction_script = """
        return (() => {
            const rows = document.querySelectorAll('.dt-scroll-body tbody tr');
            const data = [];
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 20) {
                    // Correct indices for multi-expiry table:
                    const ticker = cells[0].innerText.trim();
                    const expiry = cells[1].innerText.trim();
                    const type_raw = cells[3].innerText.trim();
                    const strike_raw = cells[6].innerText.trim();
                    const iv_raw = cells[14].innerText.trim();
                    const last_price = cells[9].innerText.trim();  // Index 9 = Último
                    
                    // Greeks from the site
                    const delta_raw = cells[15].innerText.trim();
                    const gamma_raw = cells[16].innerText.trim();
                    
                    // Open Interest components
                    const cob = cells[21].innerText.trim();
                    const trav = cells[22].innerText.trim();
                    const descob = cells[23].innerText.trim();
                    
                    // Only add if ticker looks valid
                    if (ticker && ticker.match(/^[A-Z]{4,5}/)) {
                        data.push({
                            ticker: ticker,
                            expiry: expiry,
                            type: type_raw,
                            strike: strike_raw,
                            iv: iv_raw,
                            delta: delta_raw,
                            gamma: gamma_raw,
                            cob: cob,
                            trav: trav,
                            descob: descob,
                            last_price: last_price
                        });
                    }
                }
            });
            return data;
        })();
        """
        
        raw_data = driver.execute_script(extraction_script)
        print(f"Extracted {len(raw_data)} rows.")
        return raw_data
        
    except Exception as e:
        print(f"Error extracting data: {e}")
        return []
    finally:
        driver.quit()

def clean_number(val):
    if not val or val == '-': return 0.0
    val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def parse_opcoes_net_data(raw_data):
    """Parse raw scraped data into a clean DataFrame."""
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Clean numeric columns
    df['strike'] = df['strike'].apply(clean_number)
    df['market_price'] = df['last_price'].apply(clean_number)
    
    # Clean IV - handle percentage format
    df['iv'] = df['iv'].apply(clean_number) / 100.0  # Convert 35.4 to 0.354
    
    # Clean Greeks from site (gamma and delta)
    if 'gamma' in df.columns:
        df['gamma_site'] = df['gamma'].apply(clean_number)
        # Mark invalid gamma (0 means no data)
        df['gamma_site'] = df['gamma_site'].apply(lambda x: x if x > 0 else None)
        print(f"[DEBUG] Gamma from site - valid: {df['gamma_site'].notna().sum()}/{len(df)}")
    
    if 'delta' in df.columns:
        df['delta_site'] = df['delta'].apply(clean_number)
    
    # Mark invalid market prices (0 or negative are invalid for option prices)
    df['market_price'] = df['market_price'].apply(lambda x: x if x > 0 else None)
    
    # Mark invalid IV (0% means no IV data)
    df['iv'] = df['iv'].apply(lambda x: x if x > 0.001 else None)
    
    # Calculate Total Open Interest
    df['cob'] = df['cob'].apply(clean_number)
    df['trav'] = df['trav'].apply(clean_number)
    df['descob'] = df['descob'].apply(clean_number)
    df['open_interest'] = (df['cob'] + df['trav'] + df['descob']).astype(int)
    
    # Parse expiry date from page data (format: DD/MM/YYYY)
    df['expiry'] = pd.to_datetime(df['expiry'], format='%d/%m/%Y', errors='coerce')
    
    # Normalize Type - handle various formats
    df['type'] = df['type'].str.strip().str.upper()
    
    # Debug: print unique types found
    print(f"[DEBUG] Unique type values: {df['type'].unique().tolist()}")
    print(f"[DEBUG] Sample strikes: {df['strike'].head().tolist()}")
    print(f"[DEBUG] Rows before filter: {len(df)}")
    
    # Filter out rows without valid strike
    df = df[df['strike'] > 0]
    print(f"[DEBUG] Rows after strike filter: {len(df)}")
    
    # More flexible type matching - check if 'CALL' or 'PUT' is contained
    def normalize_type(t):
        t = str(t).upper().strip()
        if 'CALL' in t or t == 'C':
            return 'CALL'
        elif 'PUT' in t or t == 'P':
            return 'PUT'
        return t
    
    df['type'] = df['type'].apply(normalize_type)
    df = df[df['type'].isin(['CALL', 'PUT'])]
    print(f"[DEBUG] Rows after type filter: {len(df)}")
    
    return df


def get_cached_options_data(ticker: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Retorna dados de opções do cache ou busca novos se expirado.
    
    Usa cache de 5 minutos para evitar múltiplas chamadas ao browser.
    
    Args:
        ticker: Ticker do ativo (ex: BOVA11)
        force_refresh: Se True, ignora cache e busca novos dados
    
    Returns:
        DataFrame com opções parseadas
    """
    global _opcoes_cache
    
    ticker_upper = ticker.upper().replace('.SA', '')
    now = datetime.now()
    
    # Verificar cache
    if not force_refresh and ticker_upper in _opcoes_cache['data']:
        cached_time = _opcoes_cache['timestamp'].get(ticker_upper)
        if cached_time and (now - cached_time) < timedelta(minutes=CACHE_EXPIRY_MINUTES):
            print(f"[CACHE] Using cached data for {ticker_upper} (age: {(now - cached_time).seconds}s)")
            return _opcoes_cache['data'][ticker_upper]
    
    # Buscar novos dados
    print(f"[CACHE] Fetching fresh data for {ticker_upper}...")
    raw_data = fetch_opcoes_net_data(ticker_upper)
    if not raw_data:
        return pd.DataFrame()
    
    df = parse_opcoes_net_data(raw_data)
    
    # Salvar no cache
    if not df.empty:
        _opcoes_cache['data'][ticker_upper] = df
        _opcoes_cache['timestamp'][ticker_upper] = now
        print(f"[CACHE] Cached {len(df)} options for {ticker_upper}")
    
    return df


# ============================================================
# FUNÇÕES PARA TERM STRUCTURE E SKEW (VOLATILITY SURFACE)
# ============================================================

def get_term_structure_from_opcoes_net(ticker: str, spot_price: float = None) -> pd.DataFrame:
    """
    Extrai a estrutura a termo da IV usando dados do opcoes.net.
    Retorna IV ATM para cada vencimento disponível.
    
    Args:
        ticker: Ticker do ativo (ex: BOVA11)
        spot_price: Preço spot para determinar ATM (opcional, busca via yfinance)
    
    Returns:
        DataFrame com columns: expiry, days_to_exp, iv_put, iv_call, iv_avg, strike_atm
    """
    # Usar cache para evitar múltiplas chamadas
    df = get_cached_options_data(ticker)
    if df.empty:
        return pd.DataFrame()
    
    # Determinar spot price se não fornecido
    if spot_price is None or spot_price <= 0:
        # Buscar preço real via yfinance
        try:
            import yfinance as yf
            ticker_clean = ticker.upper().replace('.SA', '')
            stock = yf.Ticker(f"{ticker_clean}.SA")
            info = stock.info
            if 'previousClose' in info and info['previousClose']:
                spot_price = float(info['previousClose'])
            else:
                hist = stock.history(period='5d')
                if not hist.empty:
                    spot_price = float(hist['Close'].iloc[-1])
            print(f"[TERM] Spot price for {ticker}: R$ {spot_price:.2f}")
        except Exception as e:
            print(f"[TERM] Error getting spot price: {e}")
            # Fallback: usar strike mediano
            spot_price = df['strike'].median()
    
    if spot_price is None or spot_price <= 0:
        spot_price = df['strike'].median()
    
    results = []
    
    # Agrupar por vencimento
    for expiry, group in df.groupby('expiry'):
        if pd.isna(expiry):
            continue
        
        # Calcular dias até vencimento
        days_to_exp = (expiry.date() - datetime.now().date()).days
        if days_to_exp <= 0:
            continue
        
        # Encontrar strike ATM (mais próximo do spot)
        group = group.copy()
        group['dist_to_spot'] = abs(group['strike'] - spot_price)
        atm_strike = group.loc[group['dist_to_spot'].idxmin(), 'strike']
        
        # Filtrar opções ATM (dentro de 2% do spot)
        atm_range = spot_price * 0.02
        atm_options = group[abs(group['strike'] - atm_strike) <= atm_range]
        
        # Separar CALLs e PUTs
        calls = atm_options[atm_options['type'] == 'CALL']
        puts = atm_options[atm_options['type'] == 'PUT']
        
        # Pegar IV média dos ATM
        iv_call = calls['iv'].dropna().mean() if not calls.empty else None
        iv_put = puts['iv'].dropna().mean() if not puts.empty else None
        
        # IV média (prioriza PUT pois geralmente mais líquida em índices)
        if iv_put and iv_put > 0:
            iv_avg = iv_put
        elif iv_call and iv_call > 0:
            iv_avg = iv_call
        else:
            continue  # Sem IV válida
        
        results.append({
            'expiry': expiry,
            'days_to_exp': days_to_exp,
            'iv_put': iv_put * 100 if iv_put else None,  # Convert to %
            'iv_call': iv_call * 100 if iv_call else None,
            'iv': iv_avg * 100,  # IV principal (PUT ou média)
            'strike_atm': atm_strike
        })
    
    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values('days_to_exp').reset_index(drop=True)
    
    return result_df


def get_volatility_skew_from_opcoes_net(
    ticker: str, 
    spot_price: float = None,
    expiry_months: int = 1,
    option_types: list = ['PUT', 'CALL']
) -> pd.DataFrame:
    """
    Extrai o volatility skew usando dados do opcoes.net.
    Retorna IV para diferentes strikes de um vencimento específico.
    
    Args:
        ticker: Ticker do ativo (ex: BOVA11)
        spot_price: Preço spot para calcular moneyness
        expiry_months: Qual vencimento usar (1 = próximo, 2 = segundo, etc)
        option_types: Lista de tipos a incluir ['PUT'], ['CALL'], ou ['PUT', 'CALL']
    
    Returns:
        DataFrame com columns: strike, moneyness, iv, type, ticker, expiry
    """
    # Usar cache para evitar múltiplas chamadas
    df = get_cached_options_data(ticker)
    if df.empty:
        return pd.DataFrame()
    
    # Determinar spot price se não fornecido
    if spot_price is None or spot_price <= 0:
        # Buscar preço real via yfinance
        try:
            import yfinance as yf
            ticker_clean = ticker.upper().replace('.SA', '')
            stock = yf.Ticker(f"{ticker_clean}.SA")
            info = stock.info
            if 'previousClose' in info and info['previousClose']:
                spot_price = float(info['previousClose'])
            else:
                hist = stock.history(period='5d')
                if not hist.empty:
                    spot_price = float(hist['Close'].iloc[-1])
            print(f"[SKEW] Spot price for {ticker}: R$ {spot_price:.2f}")
        except Exception as e:
            print(f"[SKEW] Error getting spot price: {e}")
            spot_price = df['strike'].median()
    
    if spot_price is None or spot_price <= 0:
        spot_price = df['strike'].median()
    
    # Ordenar vencimentos e pegar o desejado
    expiries = sorted(df['expiry'].dropna().unique())
    if len(expiries) < expiry_months:
        return pd.DataFrame()
    
    target_expiry = expiries[expiry_months - 1]
    
    # Filtrar pelo vencimento e tipos
    mask = (df['expiry'] == target_expiry) & (df['type'].isin(option_types))
    filtered = df[mask].copy()
    
    if filtered.empty:
        return pd.DataFrame()
    
    # Filtrar apenas opções com IV válida
    filtered = filtered[filtered['iv'].notna() & (filtered['iv'] > 0.001)]
    
    # Calcular moneyness (% distância do spot)
    filtered['moneyness'] = ((filtered['strike'] / spot_price) - 1) * 100
    filtered['moneyness_pct'] = (filtered['strike'] / spot_price) * 100
    
    # Calcular dias até vencimento
    days_to_exp = (target_expiry.date() - datetime.now().date()).days
    
    # Filtrar strikes muito distantes (80% a 120% do spot)
    filtered = filtered[(filtered['moneyness_pct'] >= 80) & (filtered['moneyness_pct'] <= 120)]
    
    # Preparar resultado
    result = filtered[['strike', 'moneyness', 'moneyness_pct', 'iv', 'type', 'ticker']].copy()
    result['iv'] = result['iv'] * 100  # Convert to %
    result['expiry'] = target_expiry
    result['days_to_exp'] = days_to_exp
    result['spot_price'] = spot_price
    
    result = result.sort_values(['type', 'strike']).reset_index(drop=True)
    
    return result


if __name__ == "__main__":
    print("Testing Opcoes.net.br Scraper...")
    raw = fetch_opcoes_net_data()
    df = parse_opcoes_net_data(raw)
    print(f"\nTotal Options: {len(df)}")
    print(df.head())
    print("\nSample with positive OI:")
    print(df[df['open_interest'] > 0].head())
