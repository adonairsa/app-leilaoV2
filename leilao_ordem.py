import streamlit as st
import pdfplumber
import re
import os
import requests
from io import BytesIO

def obter_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except:
        pass
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

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
    dados_por_lote = {}
    
    if not texto_oe:
        return sequencia, dados_por_lote
    
    for pagina in texto_oe:
        for linha in pagina.split('\n'):
            linha_limpa = linha.strip()
            if not linha_limpa or re.search(r"QTD\s+IDADE\s+PESO", linha_limpa, re.IGNORECASE) or re.search(r"O\.E\.\s*LT", linha_limpa, re.IGNORECASE):
                continue
            
            m_posicao = re.match(r"^(\d{1,3})\s*[º°]?\s+(\d{1,3})\s+", linha_limpa)
            if m_posicao:
                posicao = int(m_posicao.group(1))
                numero_lote = int(m_posicao.group(2))
                
                if 1 <= numero_lote <= 500:
                    lt_num = f"{numero_lote:02d}"
                    if lt_num not in sequencia:
                        sequencia.append(lt_num)
                    
                    restante = linha_limpa[m_posicao.end():].strip()
                    parts = restante.split()
                    
                    dados = {
                        "lote": lt_num, "posicao": f"{posicao}º A ENTRAR",
                        "qtd": "", "idade": "", "peso": "", "categoria": "",
                        "produto": "", "vendedor": "", "raca": "", "info_reproducao": "",
                        "tipo_reproducao": "", "nome_animal": "", "porcentagem_venda": "",
                        "linha_completa": linha_limpa
                    }
                    
                    m_porcentagem = re.search(r"(\d+%)\s*de:\s*(.+?)(?=\s+(?:parida|prenhe|prenha|inseminada|nelore|angus|girolando)|\s*$)", linha_limpa, re.IGNORECASE)
                    if m_porcentagem:
                        dados["porcentagem_venda"] = m_porcentagem.group(1)
                        dados["nome_animal"] = m_porcentagem.group(2).strip()
                    
                    m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", linha_limpa, re.IGNORECASE)
                    if m_repro:
                        texto_repro = m_repro.group(0).strip()
                        dados["info_reproducao"] = texto_repro
                        txt_low = texto_repro.lower()
                        if "parida" in txt_low:
                            dados["tipo_reproducao"] = "parida"
                        elif "prenh" in txt_low:
                            dados["tipo_reproducao"] = "prenhez"
                        elif "inseminada" in txt_low:
                            dados["tipo_reproducao"] = "inseminacao"
                    
                    if len(parts) >= 1: dados["qtd"] = parts[0]
                    if len(parts) >= 2: dados["idade"] = parts[1]
                    if len(parts) >= 3: dados["peso"] = parts[2]
                    if len(parts) >= 4: dados["categoria"] = parts[3]
                    
                    if len(parts) >= 5:
                        produto_parts, vendedor_encontrado = [], False
                        for part in parts[4:]:
                            if part.lower() in ["nelore", "angus", "girolando", "holandês"]:
                                dados["raca"] = part
                                vendedor_encontrado = True
                                continue
                            if vendedor_encontrado:
                                dados["vendedor"] += " " + part if dados["vendedor"] else part
                            else:
                                produto_parts.append(part)
                        dados["produto"] = " ".join(produto_parts)
                    
                    dados_por_lote[lt_num] = dados
    return sequencia, dados_por_lote

@st.cache_data(show_spinner=False)
def analisar_lote_oe_com_gemini(num_lote, dados_lote, api_key):
    if not api_key:
        return "⚠️ Insira a GEMINI_API_KEY nos Secrets do Streamlit."

    api_key_clean = api_key.strip()
    headers = {"Content-Type": "application/json"}

    prompt_text = f"""
    Você é um zootecnista e leiloeiro de elite no agronegócio.
    Analise a linha inteira de dados da ORDEM DE ENTRADA do LOTE {num_lote}:

    LINHA DE DADOS DADOS:
    {dados_lote.get('linha_completa', '')}

    - Lote: {num_lote}
    - Animal/Produto: {dados_lote.get('nome_animal') or dados_lote.get('produto', 'N/A')}
    - Oferta: {dados_lote.get('porcentagem_venda', '100%')}
    - Status Reprodutivo: {dados_lote.get('info_reproducao', 'N/A')}
    - Categoria / Peso / Idade: {dados_lote.get('categoria', 'N/A')} - {dados_lote.get('peso', 'N/A')} - {dados_lote.get('idade', 'N/A')}

    Gere um parecer estruturado para a canta no microfone:

    📌 **APRESENTAÇÃO DO LOTE**
    [Apresentação do animal, categoria, peso/idade e porcentagem de venda].

    🐂 **GENÉTICA DO PAI**
    [Linhagem do pai do lote, indicando se é touro provado/campeão e a raça].

    com **GENÉTICA DA MÃE**
    [Linhagem da mãe do lote e o valor dessa barriga/matriz].

    💉 **GENÉTICA DA REPRODUÇÃO / PRENHEZ**
    [Análise do touro da inseminação, prenhez ou parto, valorizando o bezerro e a previsão de parto].
    """

    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key_clean}"

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        res_json = response.json()

        if response.status_code == 200 and 'candidates' in res_json:
            return res_json['candidates'][0]['content']['parts'][0]['text']
        else:
            erro_msg = res_json.get('error', {}).get('message', response.text)
            return f"⚠️ Erro da API Google ({response.status_code}): {erro_msg}"
    except Exception as e:
        return f"⚠️ Erro de Conexão: {str(e)}"

def gerar_gatilhos(dados_lote):
    gatilhos = []
    if not dados_lote:
        return ["ANIMAL SELECIONADO!", "QUALIDADE GARANTIDA!", "OPORTUNIDADE NA PISTA!"]
    categoria = dados_lote.get("categoria", "").lower()
    if dados_lote.get("porcentagem_venda"):
        gatilhos.append(f"OFERTA DE {dados_lote['porcentagem_venda']} DO LOTE!")
    if dados_lote.get("info_reproducao"):
        gatilhos.append(f"STATUS: {dados_lote['info_reproducao']}")
    if "novilha" in categoria or "bezerra" in categoria:
        gatilhos.append("FÊMEA DE CABECEIRA E FUTURO DO REBANHO!")
    if "vaca" in categoria:
        gatilhos.append("MATRIZ COMPROVADA E PRODUTIVA!")
    gatilhos.extend(["PROCEDÊNCIA COMPROVADA!", "LIQUIDEZ IMEDIATA NA PISTA!"])
    return gatilhos[:4]

def run():
    css_code = """
    <style>
        .lote-destaque { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px; border-radius: 18px; text-align: center; font-size: 52px; font-weight: bold; margin-bottom: 12px; }
        .ordem-indicador { background: #16A34A; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin: 8px 0; font-size: 20px; }
        .banner-parida { background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #A855F7; }
        .banner-prenhez { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #EF4444; }
        .banner-inseminacao { background: linear-gradient(135deg, #D97706 0%, #92400E 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #F59E0B; }
        .banner-venda { background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%); color: #000000 !important; padding: 16px; border-radius: 14px; margin-bottom: 12px; font-size: 24px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .animal-info { background: #1E293B; color: white; padding: 15px; border-radius: 12px; margin: 5px 0; border: 1px solid #334155; }
        .nome-animal-box { background: #0284C7; color: white; padding: 14px; border-radius: 12px; margin-bottom: 12px; font-size: 22px; font-weight: bold; text-align: center; }
        .ai-consideracoes-box { background-color: #1E1B4B !important; padding: 20px; border-radius: 15px; margin-top: 5px; border-left: 8px solid #818CF8; }
        .ai-consideracoes-box, .ai-consideracoes-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.6 !important; }
        .gatilho-card { background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%); color: white; padding: 14px; border-radius: 12px; font-size: 18px; margin: 6px 0; font-weight: bold; }
    </style>
    """
    st.markdown(css_code, unsafe_allow_html=True)

    api_key = obter_api_key()

    with st.sidebar:
        st.header("Arquivo - Modo Ordem")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe_somente")
        st.markdown("---")
        modo_ordenacao = st.radio("Escolha a ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0, key="ordem_somente")

    texto_oe = processar_pdf(file_oe.getvalue()) if file_oe else []
    sequencia_oe, mapa_oe = extrair_dados_oe(tuple(texto_oe))

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
    dados_lote = mapa_oe.get(num_lote, {})

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        lote_texto = f"LOTE {num_lote}"
        posicao_texto = dados_lote.get("posicao", f"{st.session_state.lote_idx_oe + 1}º")
        st.markdown(f'<div class="lote-destaque">{lote_texto}<br><span style="font-size: 24px;">{posicao_texto}</span></div>', unsafe_allow_html=True)
        
        if dados_lote.get("porcentagem_venda"):
            st.markdown(f'<div class="banner-venda">💎 OFERTA DE {dados_lote["porcentagem_venda"]} DO ANIMAL</div>', unsafe_allow_html=True)
        
        if dados_lote.get("info_reproducao"):
            tipo_rep = dados_lote.get("tipo_reproducao")
            if tipo_rep == "parida":
                st.markdown(f'<div class="banner-parida">🍼 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
            elif tipo_rep == "prenhez":
                st.markdown(f'<div class="banner-prenhez">🤰 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="banner-inseminacao">💉 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)

        if dados_lote.get("nome_animal"):
            st.markdown(f'<div class="nome-animal-box">🐂 {dados_lote["nome_animal"]}</div>', unsafe_allow_html=True)
        
        if dados_lote:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria","-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca","-")}</div>', unsafe_allow_html=True)
            with c2:
                st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso","-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade","-")}</div>', unsafe_allow_html=True)
            with c3:
                st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd","-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor","-")}</div>', unsafe_allow_html=True)

        st.markdown("### 🎙️ GATILHOS PARA O MICROFONE")
        gatilhos = gerar_gatilhos(dados_lote)
        for g in gatilhos:
            st.markdown(f'<div class="gatilho-card">{g}</div>', unsafe_allow_html=True)

    with col_direita:
        with st.spinner("🤖 Gemini analisando a linhagem na Ordem de Entrada..."):
            analise_ia = analisar_lote_oe_com_gemini(num_lote, dados_lote, api_key)
            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DA IA (LINHAGEM & REPRODUÇÃO)</h3>
                <div>{analise_ia}</div>
            </div>
            ''', unsafe_allow_html=True)
