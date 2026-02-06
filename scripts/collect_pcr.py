#!/usr/bin/env python3
"""
Script de coleta diária de Put-Call Ratio.

Roda via GitHub Actions de madrugada para coletar dados do dia anterior.
Não usa Streamlit - roda standalone com variáveis de ambiente.

Uso:
    SUPABASE_URL=xxx SUPABASE_KEY=yyy python scripts/collect_pcr.py
"""

import os
import sys
from datetime import datetime, date, timedelta

# Adicionar src ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

# Imports do projeto
from src.data_loaders.opcoes_net import fetch_opcoes_net_data, parse_opcoes_net_data
from src.data_loaders.pcr import calcular_pcr, calcular_max_pain, salvar_pcr_supabase


def get_spot_price_yfinance(ticker: str) -> float:
    """Busca preço spot via yfinance."""
    try:
        import yfinance as yf
        stock = yf.Ticker(f"{ticker}.SA")
        hist = stock.history(period="2d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"Erro ao buscar preço de {ticker}: {e}")
    return None


def main():
    print("=" * 60)
    print("Coleta Diária de Put-Call Ratio")
    print(f"Executado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Verificar variáveis de ambiente
    if not os.environ.get('SUPABASE_URL') or not os.environ.get('SUPABASE_KEY'):
        print("❌ ERRO: SUPABASE_URL e SUPABASE_KEY devem estar definidos!")
        sys.exit(1)
    
    # Ativos para coletar (apenas BOVA11 para economizar espaço)
    tickers = ['BOVA11']
    
    # Data de referência (dia anterior se for de madrugada)
    data_ref = date.today()
    if datetime.now().hour < 10:
        # Se for antes das 10h, pegar dados de ontem
        data_ref = date.today() - timedelta(days=1)
    
    # Ajustar para dia útil (pular fim de semana)
    while data_ref.weekday() >= 5:  # 5=sábado, 6=domingo
        data_ref -= timedelta(days=1)
    
    print(f"\n📅 Data de referência: {data_ref.strftime('%d/%m/%Y')}")
    
    resultados = []
    
    for ticker in tickers:
        print(f"\n🔄 Processando {ticker}...")
        
        try:
            # Buscar dados de opções
            raw_data = fetch_opcoes_net_data(ticker)
            options_df = parse_opcoes_net_data(raw_data)
            
            if options_df.empty:
                print(f"  ⚠️ Sem dados para {ticker}")
                continue
            
            print(f"  ✓ {len(options_df)} opções carregadas")
            
            # Calcular PCR
            pcr_data = calcular_pcr(options_df)
            print(f"  ✓ PCR OI: {pcr_data.get('pcr_oi', 'N/A')}")
            
            # Buscar spot price
            spot_price = get_spot_price_yfinance(ticker)
            print(f"  ✓ Spot: R$ {spot_price:.2f}" if spot_price else "  ⚠️ Spot não disponível")
            
            # Calcular Max Pain
            max_pain_strike, _ = calcular_max_pain(options_df, spot_price)
            print(f"  ✓ Max Pain: R$ {max_pain_strike:.2f}" if max_pain_strike else "  ⚠️ Max Pain não calculado")
            
            # Salvar no Supabase
            sucesso = salvar_pcr_supabase(
                data=data_ref,
                ticker=ticker,
                pcr_data=pcr_data,
                max_pain_strike=max_pain_strike,
                spot_price=spot_price
            )
            
            if sucesso:
                print(f"  ✅ Salvo no Supabase!")
                resultados.append({'ticker': ticker, 'status': 'OK', 'pcr': pcr_data.get('pcr_oi')})
            else:
                print(f"  ❌ Erro ao salvar")
                resultados.append({'ticker': ticker, 'status': 'ERRO', 'pcr': None})
                
        except Exception as e:
            print(f"  ❌ Erro: {e}")
            resultados.append({'ticker': ticker, 'status': 'ERRO', 'pcr': None})
    
    # Resumo
    print("\n" + "=" * 60)
    print("📊 RESUMO")
    print("=" * 60)
    
    for r in resultados:
        status_icon = "✅" if r['status'] == 'OK' else "❌"
        pcr_str = f"PCR={r['pcr']:.3f}" if r['pcr'] else ""
        print(f"  {status_icon} {r['ticker']}: {r['status']} {pcr_str}")
    
    ok_count = sum(1 for r in resultados if r['status'] == 'OK')
    print(f"\n📈 Coletados com sucesso: {ok_count}/{len(tickers)}")
    
    # Exit code baseado no sucesso
    if ok_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
