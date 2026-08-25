import streamlit as st

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Importação segura para evitar erros caso os arquivos não estejam na raiz
try:
    import leilao_catalogo
except ModuleNotFoundError:
    leilao_catalogo = None

try:
    import leilao_ordem
except ModuleNotFoundError:
    leilao_ordem = None

if "tela_ativa" not in st.session_state:
    st.session_state.tela_ativa = "menu"

# ==================== TELA PRINCIPAL (MENU) ====================
if st.session_state.tela_ativa == "menu":
    st.markdown("""
    <style>
        .title-menu {
            text-align: center;
            font-size: 42px;
            font-weight: bold;
            margin-top: 30px;
            margin-bottom: 40px;
            color: #4F46E5;
        }
        .stButton > button {
            min-height: 120px;
            font-size: 24px;
            font-weight: bold;
            border-radius: 20px;
            margin: 10px 0;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="title-menu">🐂 PAINEL DO LEILOEIRO PRO</div>', unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; margin-bottom: 30px;'>Selecione o formato do leilão para iniciar:</h3>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📖 ORDEM DE ENTRADA + CATÁLOGO\n\n(Leilão completo com PDF do Catálogo)", use_container_width=True):
            st.session_state.tela_ativa = "catalogo"
            st.rerun()

    with col2:
        if st.button("📋 APENAS ORDEM DE ENTRADA\n\n(Leilão rápido sem PDF do Catálogo)", use_container_width=True):
            st.session_state.tela_ativa = "ordem"
            st.rerun()

# ==================== MÓDULOS SELECIONADOS ====================
else:
    with st.sidebar:
        if st.button("⬅️ VOLTAR AO MENU INICIAL", use_container_width=True):
            st.session_state.tela_ativa = "menu"
            st.rerun()
        st.markdown("---")

    if st.session_state.tela_ativa == "catalogo":
        if leilao_catalogo:
            leilao_catalogo.run()
        else:
            st.error("⚠️ O arquivo 'leilao_catalogo.py' não foi encontrado na pasta principal (raiz) do repositório no GitHub.")
            
    elif st.session_state.tela_ativa == "ordem":
        if leilao_ordem:
            leilao_ordem.run()
        else:
            st.error("⚠️ O arquivo 'leilao_ordem.py' não foi encontrado na pasta principal (raiz) do repositório no GitHub.")
