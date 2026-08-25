import streamlit as st
import leilao_catalogo
import leilao_ordem

# 1. Inicializa o estado do menu
if "tela_ativa" not in st.session_state:
    st.session_state.tela_ativa = "menu"

# 2. Tela Inicial com os Botões
if st.session_state.tela_ativa == "menu":
    st.title("🐂 PAINEL DO LEILOEIRO PRO")
    st.write("Selecione o formato do leilão:")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📖 ORDEM DE ENTRADA + CATÁLOGO", use_container_width=True):
            st.session_state.tela_ativa = "catalogo"
            st.rerun()

    with col2:
        if st.button("📋 APENAS ORDEM DE ENTRADA", use_container_width=True):
            st.session_state.tela_ativa = "ordem"
            st.rerun()

# 3. Direcionamento para os módulos
else:
    if st.sidebar.button("⬅️ VOLTAR AO MENU"):
        st.session_state.tela_ativa = "menu"
        st.rerun()

    if st.session_state.tela_ativa == "catalogo":
        leilao_catalogo.run()
    elif st.session_state.tela_ativa == "ordem":
        leilao_ordem.run()
