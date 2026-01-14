
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

# Importar Páginas
from src.pages import (
    dashboard_tesouro,
    credito_privado,
    market_breadth,
    economicos_br,
    dashboard_commodities,
    dashboard_internacional,
    acoes_br,
    radar_insiders,
    calculadora_put,
    screener_put,
    exportador_dfp,
    volatilidade_iv,
    minha_carteira
)

# --- Sidebar Nuvegação ---
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
            "Econômicos BR",
            "Commodities",
            "Internacional",
            "Ações BR",
            "Radar de Insiders",
            "Calculadora Put",
            "Screener Put",
            "Exportador DFP",
            "Minha Carteira",
        ],
        icons=[
            "house",
            "graph-up-arrow",
            "wallet2",
            "water",
            "activity",
            "bar-chart-line-fill",
            "box-seam",
            "globe-americas",
            "kanban-fill",
            "person-check-fill",
            "calculator",
            "search",
            "file-earmark-spreadsheet",
            "bookmark-star",
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
    * **Amplitude:** Análise de Market Breadth (MM200, IFR, Highs/Lows).
    * **Econômicos BR:** Indicadores macroeconômicos do BCB.
    * **Commodities:** Painel de preços de commodities.
    * **Internacional:** Indicadores do FRED (EUA).
    * **Ações BR:** Análise de Ratio (Long & Short).
    * **Radar de Insiders:** Monitoramento CVM.
    * **Calculadora Put:** Estruturação de venda de opções.
    * **Exportador DFP:** Exporte demonstrativos financeiros de empresas listadas.
    """)

elif pagina_selecionada == "Juros Brasil":
    dashboard_tesouro.render()

elif pagina_selecionada == "Crédito Privado":
    credito_privado.render()

elif pagina_selecionada == "Amplitude":
    market_breadth.render()

elif pagina_selecionada == "Volatilidade IV":
    volatilidade_iv.render()

elif pagina_selecionada == "Econômicos BR":
    economicos_br.render()

elif pagina_selecionada == "Commodities":
    dashboard_commodities.render()

elif pagina_selecionada == "Internacional":
    dashboard_internacional.render()

elif pagina_selecionada == "Ações BR":
    acoes_br.render()

elif pagina_selecionada == "Radar de Insiders":
    radar_insiders.render()

elif pagina_selecionada == "Calculadora Put":
    calculadora_put.render()

elif pagina_selecionada == "Screener Put":
    screener_put.render()

elif pagina_selecionada == "Exportador DFP":
    exportador_dfp.render()

elif pagina_selecionada == "Minha Carteira":
    minha_carteira.render()
