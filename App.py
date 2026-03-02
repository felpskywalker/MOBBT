
import streamlit as st
from streamlit_option_menu import option_menu
from datetime import datetime
from src.config import configurar_tema_brokeberg


# Configuração da Página deve ser a PRIMEIRA coisa
st.set_page_config(layout="wide", page_title="Brokeberg Terminal")

# Configurar Tema
configurar_tema_brokeberg()

# --- Autenticação Persistente com query_params ---
import bcrypt
import hashlib

# Chave secreta para gerar token (pode ser qualquer string única)
AUTH_TOKEN_SECRET = "brokeberg_2026_secret_token_key"

def generate_auth_token(username: str) -> str:
    """Gera um token de autenticação baseado no usuário e secret."""
    return hashlib.sha256(f"{username}:{AUTH_TOKEN_SECRET}".encode()).hexdigest()[:16]  # Token curto para URL

def check_password():
    """Verifica se a senha está correta, usando query_params para persistência."""
    
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verifica senha com bcrypt."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    
    # Pega credenciais do secrets
    try:
        stored_password = st.secrets["credentials"]["usernames"]["felps"]["password"]
        stored_name = st.secrets["credentials"]["usernames"]["felps"]["name"]
        expected_token = generate_auth_token("felps")
    except KeyError:
        st.error("❌ Credenciais não configuradas. Verifique os secrets.")
        st.stop()
        return False
    
    # Já está autenticado na sessão?
    if st.session_state.get("authenticated", False):
        return True
    
    # Tenta recuperar token do query_params (URL)
    url_token = st.query_params.get("auth", None)
    
    # Se token existe e é válido, autentica automaticamente
    if url_token == expected_token:
        st.session_state["authenticated"] = True
        st.session_state["name"] = stored_name
        return True
    
    # Se não tem token válido, mostra tela de login
    st.markdown("## 🔐 Brokeberg Terminal")
    st.markdown("---")
    
    with st.form("login_form"):
        password = st.text_input("Senha", type="password", placeholder="Digite sua senha...")
        submit = st.form_submit_button("Entrar", use_container_width=True)
        
        if submit:
            if verify_password(password, stored_password):
                st.session_state["authenticated"] = True
                st.session_state["name"] = stored_name
                # Adiciona token na URL para persistência
                st.query_params["auth"] = expected_token
                st.rerun()
            else:
                st.error("❌ Senha incorreta!")
    
    st.info("💡 **Dica:** Após fazer login, salve a URL nos favoritos para acesso rápido!")
    
    return False

# Verifica autenticação
if not check_password():
    st.stop()

# Se chegou aqui, está autenticado!

# --- Sidebar Navegação ---
with st.sidebar:
    st.title("Brokeberg Terminal")
    st.caption(f"Bem-vindo, **{st.session_state.get('name', 'Usuário')}**!")
    if st.button("🚪 Sair", use_container_width=True):
        # Limpa query_params e session state
        st.query_params.clear()
        st.session_state["authenticated"] = False
        st.session_state["name"] = None
        st.rerun()
    st.markdown("---")
    st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    pagina_selecionada = option_menu(
        menu_title="Monitoramento",
        options=[
            "Início",
            "Juros Brasil",
            "Crédito Privado",
            "Amplitude",
            "Volatilidade IV",
            "GEX Gamma",
            "Sentimento Opções",
            "Calendário",
            "Econômicos BR",
            "Commodities",
            "Internacional",
            "Ações BR",
            "Radar de Insiders",
            "Calculadora Put",
            "Screener Put",
            "Merger Arbitrage",
            "Exportador DFP",
            "Minha Carteira",
            "RRG Setorial",
        ],
        icons=[
            "house",
            "graph-up-arrow",
            "wallet2",
            "water",
            "activity",
            "lightning",
            "emoji-sunglasses",
            "calendar-event",
            "bar-chart-line-fill",
            "box-seam",
            "globe-americas",
            "kanban-fill",
            "person-check-fill",
            "calculator",
            "search",
            "arrow-left-right",
            "file-earmark-spreadsheet",
            "bookmark-star",
            "diagram-3",
        ],
        menu_icon="speedometer2",
        default_index=0,
        styles={
            "container": {"padding": "5px !important", "background-color": "transparent"},
            "icon": {"color": "#636EFA", "font-size": "20px"},
            "nav-link": {"font-size": "16px", "text-align": "left", "margin": "0px", "--hover-color": "#262830"},
            "nav-link-selected": {"background-color": "#333952"},
        }
    )

# --- Roteamento ---

if pagina_selecionada == "Início":
    st.header("Bem-vindo ao Brokeberg Terminal")
    st.markdown("---")
    st.info("Selecione uma ferramenta no menu lateral para começar a análise.")
    st.markdown("""
    ### Ferramentas Disponíveis:
    * **Juros Brasil:** Curvas de juros reais, nominais e spreads.
    * **Crédito Privado:** Spreads de debêntures (IDEX JGP).
    * **Volatilidade IV:** Análise de IV (VXEWZ) e IV/HV Spread.
    * **Correlações:** Regime de mercado, matriz de correlação e beta.
    * **Econômicos BR:** Indicadores macroeconômicos do BCB.
    * **Commodities:** Painel de preços de commodities.
    * **Internacional:** Indicadores do FRED (EUA).
    * **Ações BR:** Análise de Ratio (Long & Short).
    * **Radar de Insiders:** Monitoramento CVM.
    * **Calculadora Put:** Estruturação de venda de opções.
    * **Exportador DFP:** Exporte demonstrativos financeiros de empresas listadas.
    """)

elif pagina_selecionada == "Juros Brasil":
    from src.pages import dashboard_tesouro
    dashboard_tesouro.render()

elif pagina_selecionada == "Crédito Privado":
    from src.pages import credito_privado
    credito_privado.render()

elif pagina_selecionada == "Amplitude":
    from src.pages import market_breadth
    market_breadth.render()

elif pagina_selecionada == "Volatilidade IV":
    from src.pages import volatilidade_iv
    volatilidade_iv.render()

elif pagina_selecionada == "GEX Gamma":
    from src.pages import gex_calculator
    gex_calculator.render()

elif pagina_selecionada == "Sentimento Opções":
    from src.pages import sentimento_opcoes
    sentimento_opcoes.render()

elif pagina_selecionada == "Calendário":
    from src.pages import event_calendar
    event_calendar.render()

elif pagina_selecionada == "Econômicos BR":
    from src.pages import economicos_br
    economicos_br.render()

elif pagina_selecionada == "Commodities":
    from src.pages import dashboard_commodities
    dashboard_commodities.render()

elif pagina_selecionada == "Internacional":
    from src.pages import dashboard_internacional
    dashboard_internacional.render()

elif pagina_selecionada == "Ações BR":
    from src.pages import acoes_br
    acoes_br.render()

elif pagina_selecionada == "Radar de Insiders":
    from src.pages import radar_insiders
    radar_insiders.render()

elif pagina_selecionada == "Calculadora Put":
    from src.pages import calculadora_put
    calculadora_put.render()

elif pagina_selecionada == "Screener Put":
    from src.pages import screener_put
    screener_put.render()

elif pagina_selecionada == "Merger Arbitrage":
    from src.pages import merger_arbitrage
    merger_arbitrage.render()

elif pagina_selecionada == "Exportador DFP":
    from src.pages import exportador_dfp
    exportador_dfp.render()

elif pagina_selecionada == "Minha Carteira":
    from src.pages import minha_carteira
    minha_carteira.render()

elif pagina_selecionada == "RRG Setorial":
    from src.pages import rrg_chart
    rrg_chart.render()
