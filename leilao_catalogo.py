import streamlit as st
import pdfplumber
import re
import requests
import json
import base64
import difflib
import hashlib
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
    .ai-consideracoes-box {
        background-color: #1E1B4B !important;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 15px;
        border-left: 8px solid #818CF8;
    }
    .ai-consideracoes-box, .ai-consideracoes-box * {
        color: #FFFFFF !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
    .catalogo-header {
        background: #F59E0B;
        color: white;
        padding: 10px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 18px;
        margin-bottom: 10px;
    }
    .pedigree-card {
        background: #0F172A;
        color: white;
        padding: 14px;
        border-radius: 12px;
        margin: 5px 0;
        border: 1px solid #334155;
    }
    .pedigree-card table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .pedigree-card td {
        padding: 4px 6px;
        border-bottom: 1px solid #1E293B;
    }
    .abertura-box {
        background: linear-gradient(135deg, #065F46 0%, #047857 100%);
        color: white !important;
        padding: 16px;
        border-radius: 14px;
        margin-bottom: 12px;
        font-size: 17px !important;
        font-style: italic;
        border: 2px solid #10B981;
    }
</style>
"""
st.markdown(css_code, unsafe_allow_html=True)

# ==================== API KEYS ====================
def obter_api_keys():
    ds_keys = []
    ant_keys = []
    try:
        for k in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"]:
            if k in st.secrets:
                val = st.secrets[k]
                if isinstance(val, (list, tuple)): ds_keys.extend(val)
                elif isinstance(val, str): ds_keys.append(val)

        for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "CLAUDE_API_KEY"]:
            if k in st.secrets:
                val = st.secrets[k]
                if isinstance(val, (list, tuple)): ant_keys.extend(val)
                elif isinstance(val, str): ant_keys.append(val)
    except Exception:
        pass
    return ds_keys, ant_keys

def normalizar_lote(valor):
    if valor is None:
        return ""
    digitos = re.sub(r"\D", "", str(valor))
    return str(int(digitos)) if digitos else ""

def hash_bytes(b):
    return hashlib.md5(b).hexdigest() if b else ""

# ==================== PROCESSAMENTO INSTANTÂNEO DA O.E. (PYTHON PURO) ====================
@st.cache_data(ttl=7200, show_spinner=False)
def extrair_ordem_entrada_fast(file_bytes):
    sequencia = []
    mapa = {}
    if not file_bytes:
        return sequencia, mapa

    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text() or ""
                linhas = texto.split("\n")
                for linha in linhas:
                    linha_clean = linha.strip()
                    if not linha_clean:
                        continue
                    
                    # Detecta padrões de lote na linha (ex: Lote 01, Lt 100, 1º Lote 02)
                    m = re.search(r"\b(?:LOTE|LT)?[\s:\.\-]*0*(\d{1,3})\b", linha_clean, re.IGNORECASE)
                    if m:
                        num_lote = str(int(m.group(1)))
                        if num_lote not in sequencia and int(num_lote) > 0:
                            sequencia.append(num_lote)
                            
                            # Tenta identificar partes da linha
                            m_pos = re.search(r"(\d{1,2}º?\s*A?\s*ENTRAR)", linha_clean, re.IGNORECASE)
                            posicao = m_pos.group(1).upper() if m_pos else f"{len(sequencia)}º A ENTRAR"

                            # Tenta extrair vendedor / porcentagem se houver
                            m_perc = re.search(r"(\d+%)", linha_clean)
                            porcentagem = m_perc.group(1) if m_perc else ""

                            mapa[num_lote] = {
                                "lote": num_lote,
                                "posicao": posicao,
                                "nome_animal": linha_clean,
                                "produto": linha_clean,
                                "porcentagem_venda": porcentagem,
                                "categoria": "Lote de Leilão",
                                "raca": "",
                                "vendedor": "",
                                "info_reproducao": ""
                            }
    except Exception as e:
        st.error(f"Erro ao ler PDF da Ordem: {str(e)}")

    return sequencia, mapa

# ==================== RENDERIZAR IMAGEM DO PDF ====================
@st.cache_data(ttl=7200, show_spinner=False)
def contar_paginas_pdf(file_bytes):
    if not file_bytes: return 0
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf: return len(pdf.pages)
    except Exception: return 0

@st.cache_data(ttl=7200, show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150):
    if not file_bytes or num_pagina < 0: return None
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if 0 <= num_pagina < len(pdf.pages):
                img = pdf.pages[num_pagina].to_image(resolution=resolucao).original
                buffer = BytesIO()
                img.convert("RGB").save(buffer, format="JPEG", quality=85)
                return buffer.getvalue()
    except Exception:
        return None
    return None

# ==================== CLAUDE INDEXA O CATÁLOGO VISUAL ====================
def claude_indexar_pagina_catalogo(img_bytes, ant_keys):
    if not img_bytes or not ant_keys: return None

    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    url = "https://api.anthropic.com/v1/messages"

    instrucao = """Esta é uma página de um CATÁLOGO de leilão.
    Se for a ficha de um lote, extraia em JSON:
    - numero_lote (ex: "01", "100")
    - nome_animal
    - registro
    - raca
    - sexo
    - nascimento
    - pelagem
    - vendedor
    - pai
    - mae
    - avo_paterno
    - avo_paterna
    - avo_materno
    - avo_materna
    - observacoes
    - especie_emoji (🐴 para equino, 🐂 para gado corte, 🐄 para leite, 🫏 para mula)

    Se não for ficha de lote, retorne "numero_lote": null.
    Retorne APENAS um JSON válido.
    """

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1200,
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
                {"type": "text", "text": instrucao}
            ]
        }]
    }

    for api_key in ant_keys:
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            if response.status_code == 200 and 'content' in res_json:
                txt_parts = [c['text'] for c in res_json['content'] if c.get('type') == 'text']
                texto = "\n".join(txt_parts).strip()
                texto = re.sub(r"^```json|
