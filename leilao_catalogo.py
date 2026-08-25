import streamlit as st
import pdfplumber
import re
import os
import requests
import json
import base64
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
</style>
"""
st.markdown(css_code, unsafe_allow_html=True)

# ==================== API KEYS ====================
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
                img = pdf.pages[num_pagina].to_image(resolution=80).original
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=50)
                return buffer.getvalue()
    except:
        return None
    return None

# ==================== EXTRAÇÃO O.E. (SEMPRE FUNCIONA) ====================
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
                    
                    # Padrão: "1º 16 1 15m 514Kg Novilha..."
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
        st.error(f"Erro O.E.: {str(e)}")
    
    return sequencia, dados_por_lote

# ==================== DETECÇÃO DE PÁGINA ====================
@st.cache_data
def encontrar_pagina_catalogo(texto_cat_tuple, num_lote, dados_lote):
    texto_cat = list(texto_cat_tuple)
    
    if not texto_cat:
        return -1, ""
    
    num_clean = re.sub(r"\D", "", str(num_lote or ""))
    nome_animal = dados_lote.get("nome_animal", "") or dados_lote.get("produto", "")
    
    # Estratégia 1: "LOTE XX"
    if num_clean:
        n_int = int(num_clean)
        for pattern in [rf"LOTE\s*0*{n_int}", rf"LT\s*0*{n_int}"]:
            for idx, pagina in enumerate(texto_cat):
                if pagina and re.search(pattern, pagina, re.IGNORECASE):
                    return idx, pagina
    
    # Estratégia 2: Nome do animal
    if nome_animal:
        palavras = [p.upper() for p in re.findall(r"\b[A-Za-zÀ-ÿ]{3,}\b", nome_animal)
                   if p.upper() not in {"LIVRE", "LOTE", "NELORE", "ANGUS", "VIRTUAL", "TERRA", "PROMETIDA"}]
        
        for idx, pagina in enumerate(texto_cat):
            if pagina:
                pag_upper = pagina.upper()
                matches = sum(1 for p in palavras if p in pag_upper)
                if matches > 0:
                    return idx, pagina
    
    # Estratégia 3: Número isolado
    if num_clean:
        pattern = rf"\b{int(num_clean)}\b"
        for idx, pagina in enumerate(texto_cat):
            if pagina and re.search(pattern, pagina):
                if not re.search(r"QTD\s+IDADE\s+PESO", pagina, re.IGNORECASE):
                    return idx, pagina
    
    return -1, ""

# ==================== CLAUDE LÊ CATÁLOGO ====================
def claude_ler_catalogo(img_bytes, ant_keys):
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
                    "text": "Transcreva TODO o texto desta página do catálogo. Inclua: nome do animal, lote, raça, categoria, pelagem, pai, mãe, avôs, vendedor."
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

# ==================== DEEPSEEK ANALISA ====================
def deepseek_analisar(num_lote, dados_lote, texto_catalogo, ds_keys):
    if not ds_keys:
        return None, "Sem DeepSeek"
    
    prompt = f"""
    LOTE: {num_lote}
    
    DADOS ORDEM:
    {dados_lote.get('linha_completa', '')}
    
    CATÁLOGO:
    {texto_catalogo[:3000]}
    
    Retorne JSON:
    {{
        "nome_animal": "...",
        "especie_emoji": "🐴/🐂/🐄/🫏",
        "encartes": [{{"titulo": "...", "valor": "..."}}],
        "apresentacao": "...",
        "genetica_pai": "...",
        "genetica_mae": "...",
        "reproducao": "...",
        "gatilhos": ["...", "...", "..."]
    }}
    """
    
    url = "https://api.deepseek.com/chat/completions"
    
    for api_key in ds_keys:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                return json.loads(res_json['choices'][0]['message']['content']), ""
        except:
            continue
    
    return None, "Erro DeepSeek"

# ==================== MAIN ====================
def run():
    ds_keys, ant_keys = obter_api_keys()
    
    with st.sidebar:
        st.header("📂 Arquivos")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe")
        file_cat = st.file_uploader("Catálogo (PDF)", type="pdf", key="cat")
        
        st.markdown("---")
        modo_ordenacao = st.radio("Ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0)
    
    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None
    
    texto_cat = processar_pdf(file_bytes_cat)
    sequencia_oe, mapa_oe = extrair_dados_oe_pdf(file_bytes_oe)
    
    if sequencia_oe:
        if modo_ordenacao == "ORDEM NUMÉRICA":
            lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x)))
        else:
            lista_lotes = sequencia_oe.copy()
    else:
        lista_lotes = []
    
    if not lista_lotes:
        st.warning("Carregue a O.E.!")
        st.stop()
    
    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0
    
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
    
    # MOSTRA DADOS DA O.E. PRIMEIRO (SEMPRE)
    st.markdown(f'<div class="lote-destaque">LOTE {num_lote}<br><span style="font-size: 24px;">{dados_lote.get("posicao", "")}</span></div>', unsafe_allow_html=True)
    
    if dados_lote.get("porcentagem_venda"):
        st.markdown(f'<div class="banner-venda">💎 VENDA DE {dados_lote["porcentagem_venda"]}</div>', unsafe_allow_html=True)
    
    if dados_lote.get("info_reproducao"):
        st.markdown(f'<div class="banner-reproducao">{dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
    
    # Mostra dados da O.E.
    if dados_lote:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca", "-")}</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso", "-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade", "-")}</div>', unsafe_allow_html=True)
        
        with col3:
            st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)
    
    # DETECÇÃO DA PÁGINA
    pagina_detectada = -1
    texto_pagina = ""
    
    if texto_cat and file_bytes_cat:
        pagina_detectada, texto_pagina = encontrar_pagina_catalogo(
            tuple(texto_cat), num_lote, dados_lote
        )
        
        # SE NÃO ENCONTROU, PERGUNTA AO USUÁRIO
        if pagina_detectada < 0:
            st.warning(f"⚠️ Não encontrei a página do Lote {num_lote} no catálogo automaticamente.")
            
            total_paginas = len(texto_cat)
            pagina_manual = st.number_input(
                f"Qual página do catálogo contém o Lote {num_lote}?",
                min_value=1,
                max_value=max(1, total_paginas),
                value=1,
                key=f"pagina_manual_{num_lote}"
            )
            pagina_detectada = pagina_manual - 1
            texto_pagina = texto_cat[pagina_detectada] if pagina_detectada < len(texto_cat) else ""
        else:
            st.success(f"📖 Catálogo: Página {pagina_detectada + 1} detectada")
    
    # Imagem da página
    img_bytes = None
    if pagina_detectada >= 0 and file_bytes_cat:
        img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
    
    # Layout para catálogo + IA
    if img_bytes or texto_pagina:
        col_esq, col_dir = st.columns([1, 1])
        
        with col_esq:
            st.markdown("### 🤖 ANÁLISE IA")
            
            with st.spinner("Claude lendo catálogo..."):
                texto_ocr = claude_ler_catalogo(img_bytes, ant_keys) if img_bytes else ""
                
                if texto_ocr and ds_keys:
                    dados_ia, erro = deepseek_analisar(num_lote, dados_lote, texto_ocr, ds_keys)
                    
                    if dados_ia:
                        for enc in dados_ia.get("encartes", []):
                            if enc.get("valor"):
                                st.markdown(f'<div class="animal-info"><strong>{enc["titulo"]}:</strong> {enc["valor"]}</div>', unsafe_allow_html=True)
                        
                        st.markdown("### 🎯 GATILHOS")
                        for g in dados_ia.get("gatilhos", []):
                            st.markdown(f'<div class="gatilho-card">{g}</div>', unsafe_allow_html=True)
        
        with col_dir:
            if img_bytes:
                st.markdown(f"**📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}**")
                st.image(img_bytes, use_container_width=True)
            
            if texto_ocr:
                with st.expander("📖 Texto Claude"):
                    st.text(texto_ocr[:1500])

if __name__ == "__main__":
    run()
