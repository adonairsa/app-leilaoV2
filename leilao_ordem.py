import streamlit as st
import pdfplumber
import re
import os
import requests
import json
import time
from io import BytesIO

def obter_api_keys():
    chaves_brutas = []
    try:
        for secret_name in ["DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"]:
            if secret_name in st.secrets:
                val = st.secrets[secret_name]
                if isinstance(val, (list, tuple)):
                    chaves_brutas.extend(val)
                elif isinstance(val, str):
                    chaves_brutas.extend(val.split(","))
    except Exception:
        pass

    if not chaves_brutas:
        env_val = os.environ.get("DEEPSEEK_API_KEYS") or os.environ.get("DEEPSEEK_API_KEY") or ""
        if env_val:
            chaves_brutas.extend(env_val.split(","))

    chaves_limpas = []
    for item in chaves_brutas:
        s = str(item).strip()
        s_clean = re.sub(r"[\[\]'\" \n\r\t]", "", s)
        if s_clean and s_clean not in chaves_limpas:
            chaves_limpas.append(s_clean)

    return chaves_limpas

@st.cache_data(ttl=7200, show_spinner=False)
def processar_pdf(file_bytes):
    paginas = []
    if not file_bytes:
        return paginas
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text(layout=True) or page.extract_text()
                if texto:
                    paginas.append(texto)
    except Exception as e:
        st.error(f"Erro ao processar PDF: {str(e)}")
    return paginas

@st.cache_data
def extrair_dados_oe(texto_oe_tuple):
    texto_oe = list(texto_oe_tuple)
    sequencia = []
    mapa_bruto = {}
    
    if not texto_oe:
        return sequencia, mapa_bruto
    
    for pagina in texto_oe:
        for linha in pagina.split('\n'):
            linha_limpa = linha.strip()
            if not linha_limpa or "PROGRAMA" in linha_limpa.upper():
                continue

            # Busca por lote nas linhas da ordem de entrada
            m_lt = re.search(r"\b(?:LT|LOTE)?\s*0*(\d{1,3})\b", linha_limpa, re.IGNORECASE)
            parts = [p.strip() for p in (linha_limpa.split('|') if '|' in linha_limpa else re.split(r'\s{2,}', linha_limpa)) if p.strip()]
            
            if len(parts) >= 2:
                raw_lt = ""
                for p in parts[:3]:
                    num = re.sub(r"\D", "", p)
                    if num and 1 <= int(num) <= 999:
                        raw_lt = num
                        break

                if raw_lt and raw_lt.isdigit():
                    num_lote = f"{int(raw_lt):02d}"
                    if num_lote not in sequencia:
                        sequencia.append(num_lote)
                    mapa_bruto[num_lote] = {
                        "lote": num_lote,
                        "linha_bruta": linha_limpa,
                        "partes": parts
                    }

    return sequencia, mapa_bruto

@st.cache_data(show_spinner=False)
def analisar_lote_leiloeiro_deepseek(num_lote, dados_brutos, api_keys):
    if not api_keys:
        return None, "⚠️ Nenhuma chave DEEPSEEK_API_KEY encontrada nos Secrets do Streamlit."

    prompt_system = """Você é um Leiloeiro Rural e Zootecnista de Elite no Brasil.
    Sua missão é ler as informações brutas de um lote de leilão (seja gado Nelore/Corte/Leite ou Equinos Quarto de Milha/Crioulo) e organizar a apresentação visual para o leiloeiro na pista."""

    prompt_user = f"""
    Analise os dados brutos do LOTE {num_lote}:
    LINHA BRUTA DA ORDEM DE ENTRADA: {dados_brutos.get('linha_bruta', '')}
    PARTES EXTRAÍDAS: {dados_brutos.get('partes', [])}

    INSTRUÇÕES CRÍTICAS DE LEILOEIRO:
    1. Crie uma lista de "ENCARTES" (cartões de informação) prioritários para aparecer na tela.
    2. Coloque APENAS o que existir e agregar valor (ex: CATEGORIA, PELAGEM, PESO, IDADE, REPRODUÇÃO, VENDEDOR, OFERTA, QTD).
    3. NUNCA invente peso ou idade se não houver na linha bruta.
    4. Crie uma canta de venda agressiva e gatilhos de pista curtos.

    Retorne EXATAMENTE um JSON válido com a seguinte estrutura:
    {{
        "posicao_entrada": "1º A ENTRAR",
        "nome_animal": "Nome do Animal ou Descrição do Produto",
        "porcentagem_venda": "100% ou 50%",
        "status_reproducao": "Prenhe / Parida / Inseminada ou vazio",
        "tipo_reproducao": "prenhez, parida, inseminacao ou vazio",
        "encartES": [
            {{"titulo": "CATEGORIA", "valor": "Novilha"}},
            {{"titulo": "PELAGEM", "valor": "Tordilho"}},
            {{"titulo": "VENDEDOR", "valor": "Fazenda Modelo"}}
        ],
        "apresentacao": "Frase agressiva de venda para o leiloeiro destacar na pista em 1 frase.",
        "genetica_pai": "Informação do pai/linhagem paterna ou vazio",
        "genetica_mae": "Informação da mãe/linhagem materna ou vazio",
        "reproducao_detalhe": "Detalhe da prenhez ou acasalamento ou vazio",
        "gatilhos": [
            "Gatilho curto 1",
            "Gatilho curto 2",
            "Gatilho curto 3"
        ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    erros = []

    for api_key in api_keys:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
                dados_ia = json.loads(content)
                return dados_ia, ""
            
            msg_erro = res_json.get('error', {}).get('message', response.text)
            erros.append(f"Chave ...{api_key[-6:]}: {msg_erro}")

            if response.status_code == 429:
                time.sleep(1)
                continue
                
        except Exception as e:
            erros.append(f"Erro na conexão: {str(e)}")
            continue

    detalhe_erro = erros[-1] if erros else "Erro de comunicação com a API DeepSeek."
    return None, f"⚠️ Erro ao consultar o DeepSeek. Detalhe: {detalhe_erro}"

def run():
    css_code = """
    <style>
        .lote-destaque { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px; border-radius: 18px; text-align: center; font-size: 52px; font-weight: bold; margin-bottom: 12px; }
        .ordem-indicador { background: #16A34A; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin: 8px 0; font-size: 20px; }
        .banner-parida { background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #A855F7; }
        .banner-prenhez { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #EF4444; }
        .banner-inseminacao { background: linear-gradient(135deg, #D97706 0%, #92400E 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #F59E0B; }
        .banner-venda { background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%); color: #000000 !important; padding: 16px; border-radius: 14px; margin-bottom: 12px; font-size: 24px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .animal-info { background: #1E293B; color: white; padding: 15px; border-radius: 12px; margin: 5px 0; border: 1px solid #334155; min-height: 90px; }
        .nome-animal-box { background: #0284C7; color: white; padding: 14px; border-radius: 12px; margin-bottom: 12px; font-size: 22px; font-weight: bold; text-align: center; }
        .ai-consideracoes-box { background-color: #1E1B4B !important; padding: 20px; border-radius: 15px; margin-top: 5px; border-left: 8px solid #818CF8; }
        .ai-consideracoes-box, .ai-consideracoes-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.6 !important; }
        .gatilho-card { background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%); color: white; padding: 14px; border-radius: 12px; font-size: 18px; margin: 6px 0; font-weight: bold; }
        .gatilho-ia-card { background: linear-gradient(135deg, #059669 0%, #047857 100%); color: white !important; padding: 16px; border-radius: 14px; font-size: 19px !important; margin: 8px 0; font-weight: bold !important; border-left: 6px solid #34D399; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
    </style>
    """
    st.markdown(css_code, unsafe_allow_html=True)

    api_keys = obter_api_keys()

    with st.sidebar:
        st.header("Arquivo - Modo Ordem")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe_somente")
        st.markdown("---")
        modo_ordenacao = st.radio("Escolha a ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0, key="ordem_somente")

    texto_oe = processar_pdf(file_oe.getvalue()) if file_oe else []
    sequencia_oe, mapa_bruto = extrair_dados_oe(tuple(texto_oe))

    if sequencia_oe:
        lista_lotes = sequencia_oe.copy() if modo_ordenacao == "ORDEM DE ENTRADA" else sorted(sequencia_oe, key=lambda x: int(x))
        ordem_atual = modo_ordenacao
    else:
        lista_lotes = []
        ordem_atual = "NENHUM LOTE ENCONTRADO"

    if 'lote_idx_oe' not in st.session_state:
        st.session_state.lote_idx_oe = 0

    if not lista_lotes:
        st.warning("Carregue a Ordem de Entrada (PDF) no menu lateral para começar!")
        st.stop()

    if st.session_state.lote_idx_oe >= len(lista_lotes):
        st.session_state.lote_idx_oe = 0

    ordem_texto = f"{ordem_atual} | Lote {st.session_state.lote_idx_oe + 1} de {len(lista_lotes)}"
    st.markdown(f'<div class="ordem-indicador">{ordem_texto}</div>', unsafe_allow_html=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("ANTERIOR", use_container_width=True, key="prev_oe"):
            st.session_state.lote_idx_oe = max(0, st.session_state.lote_idx_oe - 1)
            st.rerun()

    with col_next:
        if st.button("PRÓXIMO", use_container_width=True, key="next_oe"):
            st.session_state.lote_idx_oe = min(len(lista_lotes) - 1, st.session_state.lote_idx_oe + 1)
            st.rerun()

    lote_selecionado = st.selectbox("Ir para o lote:", options=lista_lotes, index=st.session_state.lote_idx_oe, key="sel_oe")
    st.session_state.lote_idx_oe = lista_lotes.index(lote_selecionado)

    num_lote = lista_lotes[st.session_state.lote_idx_oe]
    dados_brutos = mapa_bruto.get(num_lote, {})

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        with st.spinner("🤖 Leiloeiro IA analisando o lote..."):
            dados_ia, erro_ia = analisar_lote_leiloeiro_deepseek(num_lote, dados_brutos, api_keys)

        if dados_ia:
            lote_texto = f"LOTE {num_lote}"
            posicao_texto = dados_ia.get("posicao_entrada", f"{st.session_state.lote_idx_oe + 1}º A ENTRAR")
            st.markdown(f'<div class="lote-destaque">{lote_texto}<br><span style="font-size: 24px;">{posicao_texto}</span></div>', unsafe_allow_html=True)
            
            if dados_ia.get("porcentagem_venda"):
                st.markdown(f'<div class="banner-venda">💎 OFERTA DE {dados_ia["porcentagem_venda"]} DO ANIMAL</div>', unsafe_allow_html=True)
            
            if dados_ia.get("status_reproducao"):
                tipo_rep = dados_ia.get("tipo_reproducao", "").lower()
                if "parida" in tipo_rep:
                    st.markdown(f'<div class="banner-parida">🍼 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)
                elif "prenh" in tipo_rep:
                    st.markdown(f'<div class="banner-prenhez">🤰 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="banner-inseminacao">💉 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)

            if dados_ia.get("nome_animal"):
                st.markdown(f'<div class="nome-animal-box">🐂 {dados_ia["nome_animal"]}</div>', unsafe_allow_html=True)

            # RENDERIZAÇÃO DINÂMICA DOS ENCARTES GERADOS PELA IA
            encartes = dados_ia.get("encartes", [])
            if encartes:
                num_encartes = len(encartes)
                cols_count = min(3, max(1, num_encartes))
                cols = st.columns(cols_count)
                
                for idx, enc in enumerate(encartes):
                    col_target = cols[idx % cols_count]
                    with col_target:
                        st.markdown(f'''
                        <div class="animal-info">
                            <strong>{enc.get("titulo", "DADO").upper()}:</strong><br>
                            {enc.get("valor", "-")}
                        </div>
                        ''', unsafe_allow_html=True)

            st.markdown("### 🎙️ GATILHOS DE PISTA (IA)")
            gatilhos = dados_ia.get("gatilhos", [])
            for g in gatilhos:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

    with col_direita:
        if dados_ia:
            canta_html = f"📌 **APRESENTAÇÃO:** {dados_ia.get('apresentacao', '')}<br><br>"
            if dados_ia.get('genetica_pai'): canta_html += f"🐂 **GENÉTICA DO PAI:** {dados_ia.get('genetica_pai')}<br><br>"
            if dados_ia.get('genetica_mae'): canta_html += f"🐄 **GENÉTICA DA MÃE:** {dados_ia.get('genetica_mae')}<br><br>"
            if dados_ia.get('reproducao_detalhe'): canta_html += f"💉 **REPRODUÇÃO:** {dados_ia.get('reproducao_detalhe')}"

            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DO LEILOEIRO (IA)</h3>
                <div>{canta_html}</div>
            </div>
            ''', unsafe_allow_html=True)
        elif erro_ia:
            st.error(erro_ia)
