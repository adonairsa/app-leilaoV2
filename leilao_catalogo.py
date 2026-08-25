import streamlit as st
import pdfplumber
import re
import os
import requests
import json
import time
import base64
import concurrent.futures
from io import BytesIO

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== CSS ====================
css_code = """
<style>
    #MainMenu {visibility: hidden; display: none;}
    footer {visibility: hidden; display: none;}
    [data-testid="stToolbar"] {display: none;}
    .block-container {padding-top: 1rem;}
    
    .lote-destaque {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 20px;
        border-radius: 18px;
        text-align: center;
        font-size: 52px;
        font-weight: bold;
        margin-bottom: 12px;
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
    .banner-reproducao {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%);
        color: white !important;
        padding: 18px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 22px !important;
        font-weight: 900 !important;
        text-align: center;
        border: 3px solid #EF4444;
    }
    .banner-venda {
        background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%);
        color: #000 !important;
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
    .gatilho-card {
        background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%);
        color: white;
        padding: 14px;
        border-radius: 12px;
        font-size: 18px;
        margin: 6px 0;
        font-weight: bold;
    }
    .catalogo-preview {
        border: 2px solid #F59E0B;
        border-radius: 12px;
        padding: 10px;
        margin: 10px 0;
    }
    .status-box {
        padding: 10px;
        border-radius: 8px;
        margin: 5px 0;
        font-size: 14px;
    }
    .status-ok {
        background: #065F46;
        color: #6EE7B7;
    }
</style>
"""
st.markdown(css_code, unsafe_allow_html=True)

# ==================== OBTÉM API KEYS ====================
def obter_api_keys():
    ds_keys = []
    ant_keys = []
    
    try:
        if "DEEPSEEK_API_KEY" in st.secrets:
            ds_keys.append(st.secrets["DEEPSEEK_API_KEY"])
        if "ANTHROPIC_API_KEY" in st.secrets:
            ant_keys.append(st.secrets["ANTHROPIC_API_KEY"])
    except:
        pass
    
    return ds_keys, ant_keys

# ==================== PROCESSAMENTO DE PDF ====================
@st.cache_data(ttl=7200, show_spinner=False)
def processar_pdf(file_bytes):
    paginas = []
    if not file_bytes:
        return paginas
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text(layout=True) or page.extract_text() or ""
                paginas.append(texto)
    except:
        pass
    return paginas

@st.cache_data(show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina):
    if not file_bytes or num_pagina < 0:
        return None
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if 0 <= num_pagina < len(pdf.pages):
                img = pdf.pages[num_pagina].to_image(resolution=100).original
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=70)
                return buffer.getvalue()
    except:
        return None
    return None

# ==================== AUTO-DETECÇÃO DA PÁGINA DO CATÁLOGO ====================
@st.cache_data
def encontrar_pagina_catalogo_auto(texto_cat_tuple, num_lote, dados_lote):
    """
    Detecta automaticamente a página correta do catálogo
    Usa MÚLTIPLAS estratégias para encontrar o lote certo
    """
    texto_cat = list(texto_cat_tuple)
    
    if not texto_cat:
        return -1, ""
    
    num_clean = re.sub(r"\D", "", str(num_lote or ""))
    nome_animal = dados_lote.get("nome_animal", "") or dados_lote.get("produto", "")
    
    # ESTRATÉGIA 1: Procura "LOTE XX" exato
    if num_clean:
        n_int = int(num_clean)
        patterns = [
            rf"\bLOTE\s*0*{n_int}\b",
            rf"\bLT\s*0*{n_int}\b",
        ]
        
        for pattern in patterns:
            for idx, pagina in enumerate(texto_cat):
                if pagina and re.search(pattern, pagina, re.IGNORECASE):
                    return idx, pagina
    
    # ESTRATÉGIA 2: Procura pelo nome do animal
    if nome_animal:
        ignore_words = {"LIVRE", "ACASALAMENTO", "PRENHEZ", "PRENHA", "PARIDA",
                       "HARAS", "FAZENDA", "OFERTA", "VENDAS", "LEILAO", "LOTE",
                       "VIRTUAL", "PROMETIDA", "TERRA"}
        
        palavras = [p.upper() for p in re.findall(r"\b[A-Za-zÀ-ÿ]{4,}\b", nome_animal)
                   if p.upper() not in ignore_words]
        
        if palavras:
            melhores = []
            for idx, pagina in enumerate(texto_cat):
                if pagina:
                    pag_upper = pagina.upper()
                    matches = sum(1 for p in palavras if p in pag_upper)
                    if matches > 0:
                        melhores.append((matches, idx, pagina))
            
            if melhores:
                melhores.sort(key=lambda x: x[0], reverse=True)
                return melhores[0][1], melhores[0][2]
    
    # ESTRATÉGIA 3: Procura número do lote isolado
    if num_clean:
        pattern = rf"\b{int(num_clean)}\b"
        for idx, pagina in enumerate(texto_cat):
            if pagina and re.search(pattern, pagina):
                # Verifica se não é a O.E. (procura por cabeçalhos de O.E.)
                if not re.search(r"QTD\s+IDADE\s+PESO", pagina, re.IGNORECASE):
                    return idx, pagina
    
    return -1, ""

# ==================== EXTRAÇÃO DA O.E. ====================
@st.cache_data(ttl=7200, show_spinner=False)
def extrair_dados_oe_pdf(file_bytes):
    sequencia = []
    dados_por_lote = {}
    
    if not file_bytes:
        return sequencia, dados_por_lote
    
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text(layout=True) or page.extract_text() or ""
                
                if not texto:
                    continue
                
                for linha in texto.split('\n'):
                    linha_limpa = linha.strip()
                    
                    if not linha_limpa:
                        continue
                    
                    if re.search(r"QTD\s+IDADE\s+PESO\s+CATEGORIA", linha_limpa, re.IGNORECASE):
                        continue
                    
                    if re.search(r"O\.E\.\s*LT", linha_limpa, re.IGNORECASE):
                        continue
                    
                    if re.search(r"\d{2}/\d{2}/\d{4}", linha_limpa):
                        continue
                    
                    m_pos = re.match(r"^(\d{1,3})\s*[º°]?\s+(\d{1,3})\s+", linha_limpa)
                    
                    if m_pos:
                        pos_num = int(m_pos.group(1))
                        num_lote = int(m_pos.group(2))
                        
                        if 1 <= num_lote <= 999:
                            lt_num = f"{num_lote:02d}"
                            
                            if lt_num not in sequencia:
                                sequencia.append(lt_num)
                            
                            restante = linha_limpa[m_pos.end():].strip()
                            parts = restante.split()
                            
                            dados = {
                                "lote": lt_num,
                                "posicao": f"{pos_num}º A ENTRAR",
                                "qtd": parts[0] if len(parts) > 0 else "",
                                "idade": parts[1] if len(parts) > 1 else "",
                                "peso": parts[2] if len(parts) > 2 else "",
                                "categoria": parts[3] if len(parts) > 3 else "",
                                "produto": "",
                                "vendedor": "",
                                "raca": "",
                                "nome_animal": "",
                                "porcentagem_venda": "",
                                "info_reproducao": "",
                                "tipo_reproducao": "",
                                "linha_completa": linha_limpa
                            }
                            
                            # Produto
                            if len(parts) > 4:
                                produto_parts = []
                                vendedor_encontrado = False
                                
                                for part in parts[4:]:
                                    part_lower = part.lower()
                                    
                                    if part_lower in ["nelore", "angus", "girolando", "holandês"]:
                                        dados["raca"] = part
                                        vendedor_encontrado = True
                                        continue
                                    
                                    if vendedor_encontrado:
                                        dados["vendedor"] = (dados["vendedor"] + " " + part).strip()
                                    else:
                                        produto_parts.append(part)
                                
                                dados["produto"] = " ".join(produto_parts)
                            
                            # Porcentagem
                            m_perc = re.search(r"(\d+%)\s*de:\s*(.+)", linha_limpa, re.IGNORECASE)
                            if m_perc:
                                dados["porcentagem_venda"] = m_perc.group(1)
                                dados["nome_animal"] = m_perc.group(2).strip()
                            
                            # Reprodução
                            linha_lower = linha_limpa.lower()
                            
                            if "inseminada" in linha_lower:
                                m_insem = re.search(r"inseminada\s+(?:do|de)\s+([^|]+)", linha_limpa, re.IGNORECASE)
                                if m_insem:
                                    dados["info_reproducao"] = f"Inseminada do {m_insem.group(1).strip()}"
                                    dados["tipo_reproducao"] = "inseminacao"
                            
                            if "prenhe" in linha_lower or "prenha" in linha_lower:
                                m_prenhe = re.search(r"prenhe\s+(?:do|de)\s+([^|]+?)(?:\s*\.\s*prev\.?\s*de\s*parto:?\s*([^|]+))?", linha_limpa, re.IGNORECASE)
                                if m_prenhe:
                                    dados["info_reproducao"] = f"Prenhe do {m_prenhe.group(1).strip()}"
                                    if m_prenhe.group(2):
                                        dados["info_reproducao"] += f" - Prev. parto: {m_prenhe.group(2).strip()}"
                                    dados["tipo_reproducao"] = "prenhez"
                            
                            if "parida" in linha_lower:
                                dados["info_reproducao"] = "Parida"
                                dados["tipo_reproducao"] = "parida"
                            
                            dados_por_lote[lt_num] = dados
    
    except Exception as e:
        st.error(f"Erro ao extrair O.E.: {str(e)}")
    
    return sequencia, dados_por_lote

# ==================== OCR COM CLAUDE (SÓ CATÁLOGO) ====================
def extrair_texto_imagem_claude(img_bytes, ant_keys):
    """Claude lê APENAS a imagem do CATÁLOGO"""
    if not img_bytes or not ant_keys:
        return ""
    
    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    url = "https://api.anthropic.com/v1/messages"
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2000,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image
                    }
                },
                {
                    "type": "text",
                    "text": """Esta é uma página do CATÁLOGO do leilão.
                    Transcreva TODO o texto visível:
                    - Nome do animal
                    - Número do lote
                    - Raça/Espécie
                    - Categoria
                    - Pelagem
                    - Pai, Mãe, Avôs (genealogia)
                    - Vendedor
                    - Observações
                    
                    Formato: Texto simples."""
                }
            ]
        }]
    }
    
    for api_key in ant_keys:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            
            if response.status_code == 200 and 'content' in res_json:
                txt_parts = [c['text'] for c in res_json['content'] if c.get('type') == 'text']
                return "\n".join(txt_parts)
                
        except:
            continue
    
    return ""

# ==================== ANÁLISE COM DEEPSEEK ====================
def analisar_com_deepseek(num_lote, dados_lote, texto_catalogo_pdf, texto_ocr_claude, ds_keys):
    """DeepSeek analisa e gera resposta final"""
    if not ds_keys:
        return None, "Configure DEEPSEEK_API_KEY"
    
    prompt_system = """Você é um Leiloeiro Rural de Elite.
    Analise os dados e crie uma apresentação perfeita.
    
    Retorne JSON:
    {
        "nome_animal": "...",
        "especie_emoji": "🐴/🐂/🐄/🫏",
        "encartes": [{"titulo": "...", "valor": "..."}],
        "apresentacao": "...",
        "genetica_pai": "...",
        "genetica_mae": "...",
        "reproducao": "...",
        "gatilhos": ["...", "...", "..."]
    }"""
    
    prompt_user = f"""
    LOTE: {num_lote}
    
    DADOS DA ORDEM:
    {dados_lote.get('linha_completa', '')}
    
    TEXTO DO CATÁLOGO (OCR CLAUDE):
    {texto_ocr_claude[:2000]}
    
    TEXTO DO CATÁLOGO (PDF):
    {texto_catalogo_pdf[:2000]}
    
    Analise e retorne JSON.
    """
    
    url = "https://api.deepseek.com/chat/completions"
    
    for api_key in ds_keys:
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
            "temperature": 0.3
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
                return json.loads(content), ""
            else:
                return None, res_json.get('error', {}).get('message', 'Erro')
                
        except Exception as e:
            return None, str(e)
    
    return None, "Nenhuma chave funcionou"

# ==================== INTERFACE PRINCIPAL ====================
def run():
    ds_keys, ant_keys = obter_api_keys()
    
    # Sidebar
    with st.sidebar:
        st.header("📂 Arquivos")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe")
        file_cat = st.file_uploader("Catálogo do Leilão (PDF)", type="pdf", key="cat")
        
        st.markdown("---")
        modo_ordenacao = st.radio("Ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0)
        
        st.markdown("---")
        st.markdown("**Status APIs:**")
        if ds_keys:
            st.markdown('✅ DeepSeek OK', unsafe_allow_html=True)
        if ant_keys:
            st.markdown('✅ Claude OK', unsafe_allow_html=True)
    
    # Processa arquivos
    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None
    
    texto_cat = processar_pdf(file_bytes_cat)
    sequencia_oe, mapa_oe = extrair_dados_oe_pdf(file_bytes_oe)
    
    # Lista de lotes
    if sequencia_oe:
        if modo_ordenacao == "ORDEM NUMÉRICA":
            lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x)))
        else:
            lista_lotes = sequencia_oe.copy()
    else:
        lista_lotes = []
    
    if not lista_lotes:
        st.warning("Carregue a Ordem de Entrada!")
        st.stop()
    
    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0
    
    # Navegação
    st.markdown(f'<div class="ordem-indicador">{modo_ordenacao} | Lote {st.session_state.lote_idx + 1} de {len(lista_lotes)}</div>', unsafe_allow_html=True)
    
    col_prev, col_next = st.columns(2)
    
    with col_prev:
        if st.button("⬅️ ANTERIOR", use_container_width=True):
            st.session_state.lote_idx = max(0, st.session_state.lote_idx - 1)
            st.rerun()
    
    with col_next:
        if st.button("PRÓXIMO ➡️", use_container_width=True):
            st.session_state.lote_idx = min(len(lista_lotes) - 1, st.session_state.lote_idx + 1)
            st.rerun()
    
    num_lote = lista_lotes[st.session_state.lote_idx]
    dados_lote = mapa_oe.get(num_lote, {})
    
    # AUTO-DETECÇÃO (SEM OPÇÃO MANUAL)
    pagina_detectada = -1
    texto_pagina_catalogo = ""
    
    if texto_cat and file_bytes_cat:
        pagina_detectada, texto_pagina_catalogo = encontrar_pagina_catalogo_auto(
            tuple(texto_cat), num_lote, dados_lote
        )
        
        if pagina_detectada >= 0:
            st.success(f"📖 Catálogo: Página {pagina_detectada + 1} (auto-detectada)")
        else:
            st.warning("⚠️ Página do catálogo não encontrada automaticamente")
    
    # Imagem da página detectada
    img_pagina_bytes = None
    if pagina_detectada >= 0 and file_bytes_cat:
        img_pagina_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
    
    # Layout
    col_esq, col_dir = st.columns([1, 1])
    
    with col_esq:
        st.markdown(f'<div class="lote-destaque">LOTE {num_lote}<br><span style="font-size: 24px;">{dados_lote.get("posicao", "")}</span></div>', unsafe_allow_html=True)
        
        if dados_lote.get("porcentagem_venda"):
            st.markdown(f'<div class="banner-venda">💎 VENDA DE {dados_lote["porcentagem_venda"]}</div>', unsafe_allow_html=True)
        
        if dados_lote.get("info_reproducao"):
            st.markdown(f'<div class="banner-reproducao">{dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
        
        # Processa IA
        with st.spinner("🤖 Analisando catálogo..."):
            texto_ocr_claude = ""
            if img_pagina_bytes and ant_keys:
                texto_ocr_claude = extrair_texto_imagem_claude(img_pagina_bytes, ant_keys)
            
            if ds_keys and texto_ocr_claude:
                dados_ia, erro = analisar_com_deepseek(
                    num_lote, dados_lote, texto_pagina_catalogo, texto_ocr_claude, ds_keys
                )
                
                if dados_ia:
                    for enc in dados_ia.get("encartes", []):
                        if enc.get("valor"):
                            st.markdown(f'<div class="animal-info"><strong>{enc["titulo"]}:</strong> {enc["valor"]}</div>', unsafe_allow_html=True)
                    
                    st.markdown("### 🎯 GATILHOS")
                    for g in dados_ia.get("gatilhos", []):
                        st.markdown(f'<div class="gatilho-card">{g}</div>', unsafe_allow_html=True)
    
    with col_dir:
        # Mostra imagem do CATÁLOGO (nunca da O.E.)
        if img_pagina_bytes:
            st.markdown(f'<div class="catalogo-preview">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}</div>', unsafe_allow_html=True)
            st.image(img_pagina_bytes, use_container_width=True)
        
        # Texto OCR
        if texto_ocr_claude:
            with st.expander("📖 Texto transcrito pelo Claude"):
                st.text(texto_ocr_claude[:2000])

if __name__ == "__main__":
    run()
