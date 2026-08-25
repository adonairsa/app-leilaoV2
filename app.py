import streamlit as st
import pdfplumber
import re
import os
import requests
import base64
from io import BytesIO

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={'Get Help': None, 'Report a bug': None, 'About': None}
)

# ==================== CSS COM BANNERS DE ALTO IMPACTO ====================
css_code = """
<style>
    #MainMenu {visibility: hidden; display: none;}
    footer {visibility: hidden; display: none;}
    [data-testid="stToolbar"] {display: none;}
    [data-testid="stDecoration"] {display: none;}
    .viewerBadge_container__1QSob {display: none !important;}
    a[href*="streamlit"] {display: none !important;}
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    header[data-testid="stHeader"] {display: none;}
    .main {padding: 0;}
    
    .lote-destaque {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 20px;
        border-radius: 18px;
        text-align: center;
        font-size: 52px;
        font-weight: bold;
        margin-bottom: 12px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }
    .ordem-indicador {
        background: #16A34A;
        color: white;
        padding: 12px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        margin: 8px 0;
        font-size: 20px;
    }
    
    /* BANNERS PRINCIPAIS DE REPRODUÇÃO E VENDA */
    .banner-parida {
        background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%);
        color: #FFFFFF !important;
        padding: 18px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 22px !important;
        font-weight: 900 !important;
        text-align: center;
        border: 3px solid #A855F7;
        box-shadow: 0 4px 15px rgba(126, 34, 206, 0.4);
    }
    .banner-prenhez {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);
        color: #FFFFFF !important;
        padding: 18px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 22px !important;
        font-weight: 900 !important;
        text-align: center;
        border: 3px solid #EF4444;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4);
    }
    .banner-inseminacao {
        background: linear-gradient(135deg, #D97706 0%, #92400E 100%);
        color: #FFFFFF !important;
        padding: 18px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 22px !important;
        font-weight: 900 !important;
        text-align: center;
        border: 3px solid #F59E0B;
        box-shadow: 0 4px 15px rgba(217, 119, 6, 0.4);
    }
    .banner-venda {
        background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%);
        color: #000000 !important;
        padding: 16px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 24px !important;
        font-weight: 900 !important;
        text-align: center;
        border: 3px solid #FACC15;
    }
    
    .animal-info {
        background: #1E293B;
        color: white;
        padding: 15px;
        border-radius: 12px;
        margin: 5px 0;
        border: 1px solid #334155;
    }
    .nome-animal-box {
        background: #0284C7;
        color: white;
        padding: 14px;
        border-radius: 12px;
        margin-bottom: 12px;
        font-size: 22px;
        font-weight: bold;
        text-align: center;
    }
    
    .ai-consideracoes-box {
        background-color: #1E1B4B !important;
        padding: 20px;
        border-radius: 15px;
        margin-top: 15px;
        border-left: 8px solid #818CF8;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .ai-consideracoes-box, .ai-consideracoes-box * {
        color: #FFFFFF !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
    }

    .gatilho-card {
        background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%);
        color: white;
        padding: 14px;
        border-radius: 12px;
        font-size: 18px;
        margin: 6px 0;
        font-weight: bold;
    }
    .stButton > button {
        min-height: 55px;
        font-size: 20px;
        border-radius: 12px;
    }
    .catalogo-header {
        background: #F59E0B;
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 18px;
    }
</style>
"""

st.markdown(css_code, unsafe_allow_html=True)

# ==================== BUSCA SEGURA DE API KEY ====================
def obter_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except:
        pass
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

# ==================== PROCESSAMENTO DE PDF ====================
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

@st.cache_data(show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina):
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if 0 <= num_pagina < len(pdf.pages):
                img = pdf.pages[num_pagina].to_image(resolution=150).original
                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                return buffer.getvalue()
    except:
        return None
    return None

@st.cache_data
def encontrar_pagina_catalogo(texto_cat_tuple, num_lote):
    texto_cat = list(texto_cat_tuple)
    for idx, pagina in enumerate(texto_cat):
        if re.search(rf"\b(lote|lt)?\s*0*{int(num_lote)}\b", pagina, re.IGNORECASE):
            return idx, pagina
    return -1, ""

# ==================== EXTRAÇÃO DA ORDEM DE ENTRADA ====================
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

# ==================== ENRIQUECIMENTO DE DADOS LENDO O CATÁLOGO ====================
def enriquecer_dados_com_catalogo(dados_lote, texto_pagina_cat):
    if not texto_pagina_cat or not dados_lote:
        return dados_lote
    
    dados_atualizados = dados_lote.copy()
    
    if not dados_atualizados.get("info_reproducao"):
        linhas = texto_pagina_cat.split('\n')
        for l in linhas:
            l_clean = l.strip()
            m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", l_clean, re.IGNORECASE)
            if m_repro:
                texto_repro = m_repro.group(0).strip()
                dados_atualizados["info_reproducao"] = texto_repro
                txt_low = texto_repro.lower()
                if "parida" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "parida"
                elif "prenh" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "prenhez"
                elif "inseminada" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "inseminacao"
                break
                
    return dados_atualizados

# ==================== ANÁLISE ESTRUTURADA DA IA (FORMATO SOLICITADO) ====================
@st.cache_data(show_spinner=False)
def analisar_lote_com_gemini(img_bytes, num_lote, dados_lote, texto_pagina_cat, api_key):
    if not api_key:
        return "⚠️ Insira a GEMINI_API_KEY nos Secrets do Streamlit para ativar a análise inteligente."

    prompt_text = f"""
    Você é um zootecnista e leiloeiro de elite no agronegócio.
    Analise a imagem da folha do LOTE {num_lote} no catálogo, o texto impresso do catálogo e a Ordem de Entrada.

    DADOS DO LOTE:
    - Lote: {num_lote}
    - Animal/Produto: {dados_lote.get('nome_animal') or dados_lote.get('produto', 'N/A')}
    - Oferta: {dados_lote.get('porcentagem_venda', '100%')}
    - Status Reprodutivo: {dados_lote.get('info_reproducao', 'N/A')}
    - Categoria / Peso / Idade: {dados_lote.get('categoria', 'N/A')} - {dados_lote.get('peso', 'N/A')} - {dados_lote.get('idade', 'N/A')}

    TEXTO EXTRAÍDO DO CATÁLOGO:
    {texto_pagina_cat[:1200] if texto_pagina_cat else "Consulte a imagem do catálogo."}

    Gere uma análise técnica ESTRUTURADA E COMERCIAL para leitura rápida do leiloeiro no microfone.
    Siga OBRIGATORIAMENTE esta estrutura exata de tópicos:

    📌 **APRESENTAÇÃO DO LOTE**
    [Breve apresentação do animal, categoria, peso/idade e porcentagem de venda].

    🐂 **GENÉTICA DO PAI**
    [Nome do pai + principais raçadores/linhagens consagradas e campeãs presentes na linha paterna].

    🐄 **GENÉTICA DA MÃE**
    [Nome da mãe + principais raçadores/matrizes consagradas e campeãs presentes na linha materna].

    💉 **GENÉTICA DA REPRODUÇÃO / PRENHEZ**
    [Detalhes do acasalamento: nome do touro da inseminação/prenhez/parto, linhagem dele, previsão e valor do ventre].
    """

    api_key_clean = api_key.strip()
    headers = {"Content-Type": "application/json"}
    modelos = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-pro"]

    # 1. TENTA ENVIO DA IMAGEM + TEXTO
    if img_bytes:
        base64_image = base64.b64encode(img_bytes).decode('utf-8')
        payload_img = {
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
                ]
            }]
        }
        for ver in ["v1beta", "v1"]:
            for mod in modelos:
                try:
                    url = f"https://generativelanguage.googleapis.com/{ver}/models/{mod}:generateContent?key={api_key_clean}"
                    response = requests.post(url, headers=headers, json=payload_img, timeout=20)
                    if response.status_code == 200:
                        res_json = response.json()
                        if 'candidates' in res_json and res_json['candidates']:
                            return res_json['candidates'][0]['content']['parts'][0]['text']
                except:
                    pass

    # 2. FALLBACK APENAS TEXTO
    payload_txt = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }
    for ver in ["v1beta", "v1"]:
        for mod in modelos:
            try:
                url = f"https://generativelanguage.googleapis.com/{ver}/models/{mod}:generateContent?key={api_key_clean}"
                response = requests.post(url, headers=headers, json=payload_txt, timeout=20)
                if response.status_code == 200:
                    res_json = response.json()
                    if 'candidates' in res_json and res_json['candidates']:
                        return res_json['candidates'][0]['content']['parts'][0]['text']
            except:
                pass

    return "Não foi possível conectar à API do Gemini no momento. Verifique se a chave cadastrada nos Secrets está ativa."

# ==================== GATILHOS DE CANTA ====================
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

# ==================== INTERFACE PRINCIPAL ====================
st.title("PAINEL DO LEILOEIRO PRO")

api_key = obter_api_key()

with st.sidebar:
    st.header("Arquivos")
    file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe")
    file_cat = st.file_uploader("Catálogo do Leilão (PDF)", type="pdf", key="cat")
    
    st.markdown("---")
    modo_ordenacao = st.radio("Escolha a ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0)
    mostrar_preview = st.checkbox("MOSTRAR PREVIEW VISUAL DO CATÁLOGO", value=True)

texto_oe = processar_pdf(file_oe.getvalue()) if file_oe else []
texto_cat = processar_pdf(file_cat.getvalue()) if file_cat else []

sequencia_oe, mapa_oe = extrair_dados_oe(tuple(texto_oe))

if sequencia_oe:
    lista_lotes = sequencia_oe.copy() if modo_ordenacao == "ORDEM DE ENTRADA" else sorted(sequencia_oe, key=lambda x: int(x))
    ordem_atual = modo_ordenacao
else:
    lista_lotes = []
    ordem_atual = "NENHUM LOTE ENCONTRADO"

if 'lote_idx' not in st.session_state:
    st.session_state.lote_idx = 0

if not lista_lotes:
    st.warning("Carregue a Ordem de Entrada (PDF) para começar!")
    st.stop()

if st.session_state.lote_idx >= len(lista_lotes):
    st.session_state.lote_idx = 0

# BARRA DE NAVEGAÇÃO
ordem_texto = f"{ordem_atual} | Lote {st.session_state.lote_idx + 1} de {len(lista_lotes)}"
st.markdown(f'<div class="ordem-indicador">{ordem_texto}</div>', unsafe_allow_html=True)

col_prev, col_next = st.columns(2)
with col_prev:
    if st.button("ANTERIOR", use_container_width=True, key="prev_btn"):
        st.session_state.lote_idx = max(0, st.session_state.lote_idx - 1)
        st.rerun()

with col_next:
    if st.button("PRÓXIMO", use_container_width=True, key="next_btn"):
        st.session_state.lote_idx = min(len(lista_lotes) - 1, st.session_state.lote_idx + 1)
        st.rerun()

lote_selecionado = st.selectbox("Ir para o lote:", options=lista_lotes, index=st.session_state.lote_idx, key="select_lote")
st.session_state.lote_idx = lista_lotes.index(lote_selecionado)

num_lote = lista_lotes[st.session_state.lote_idx]
dados_lote_oe = mapa_oe.get(num_lote, {})

pagina_catalogo, texto_pagina_catalogo = encontrar_pagina_catalogo(tuple(texto_cat), num_lote) if texto_cat else (-1, "")
img_pagina_bytes = obter_imagem_bytes_pagina(file_cat.getvalue(), pagina_catalogo) if (file_cat and pagina_catalogo >= 0) else None

# ENRIQUECE OS DADOS DA OE COM INFORMAÇÕES DO CATÁLOGO
dados_lote = enriquecer_dados_com_catalogo(dados_lote_oe, texto_pagina_catalogo)

# LAYOUT PRINCIPAL
col_esquerda, col_direita = st.columns([1, 1])

# COLUNA ESQUERDA (DADOS DE PISTA E GATILHOS)
with col_esquerda:
    lote_texto = f"LOTE {num_lote}"
    posicao_texto = dados_lote.get("posicao", f"{st.session_state.lote_idx + 1}º")
    
    # 1. BANNER DO LOTE
    st.markdown(f'<div class="lote-destaque">{lote_texto}<br><span style="font-size: 24px;">{posicao_texto}</span></div>', unsafe_allow_html=True)
    
    # 2. BANNERS DE REPRODUÇÃO E OFERTA (% DE VENDA / PARIDA / PRENHE / INSEMINADA)
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
    
    # 3. FICHA TÉCNICA
    if dados_lote:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria","-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca","-")}</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso","-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade","-")}</div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd","-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor","-")}</div>', unsafe_allow_html=True)

    # 4. GATILHOS DE MIC
    st.markdown("### 🎙️ GATILHOS PARA O MICROFONE")
    gatilhos = gerar_gatilhos(dados_lote)
    for g in gatilhos:
        st.markdown(f'<div class="gatilho-card">{g}</div>', unsafe_allow_html=True)

# COLUNA DIREITA (PREVIEW VISUAL DO CATÁLOGO + CONSIDERAÇÕES DA IA LOGO ABAIXO)
with col_direita:
    if mostrar_preview and img_pagina_bytes:
        st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO VISUAL - PÁGINA {pagina_catalogo + 1}</div>', unsafe_allow_html=True)
        st.image(img_pagina_bytes, use_container_width=True)
    elif mostrar_preview and file_cat:
        st.info("Lote não localizado na busca visual do catálogo.")
    elif mostrar_preview and not file_cat:
        st.info("Suba o arquivo do catálogo no menu lateral para abrir o preview visual.")

    # 🤖 CONSIDERAÇÕES DA IA (EXATAMENTE COM A ESTRUTURA PEDIDA)
    if img_pagina_bytes or texto_pagina_catalogo:
        with st.spinner("🤖 Gemini analisando a árvore e o acasalamento do lote..."):
            analise_ia = analisar_lote_com_gemini(img_pagina_bytes, num_lote, dados_lote, texto_pagina_catalogo, api_key)
            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DA IA (LINHAGEM & REPRODUÇÃO)</h3>
                <div>{analise_ia}</div>
            </div>
            ''', unsafe_allow_html=True)
