import streamlit as st
import pdfplumber
import re
import requests
import json
import base64
import difflib
import hashlib
import concurrent.futures
from io import BytesIO

# ==================== API KEYS ====================
def obter_api_keys():
    ds_keys = []
    ant_keys = []
    try:
        if hasattr(st, "secrets"):
            for k in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"]:
                if k in st.secrets:
                    val = st.secrets[k]
                    if isinstance(val, (list, tuple)):
                        ds_keys.extend(val)
                    elif isinstance(val, str):
                        ds_keys.append(val)

            for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "CLAUDE_API_KEY"]:
                if k in st.secrets:
                    val = st.secrets[k]
                    if isinstance(val, (list, tuple)):
                        ant_keys.extend(val)
                    elif isinstance(val, str):
                        ant_keys.append(val)
    except Exception:
        pass

    clean_ds = [str(x).strip().strip("'\"") for x in ds_keys if str(x).strip()]
    clean_ant = [str(x).strip().strip("'\"") for x in ant_keys if str(x).strip()]

    return clean_ds, clean_ant

# ==================== HELPERS ====================
def normalizar_lote(valor):
    if valor is None:
        return ""
    digitos = re.sub(r"\D", "", str(valor))
    return str(int(digitos)) if digitos else ""

def hash_bytes(b):
    return hashlib.md5(b).hexdigest() if b else ""

# ==================== PROCESSAMENTO DE O.E. ====================
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
                    
                    m = re.search(r"\b(?:LOTE|LT)?[\s:\.\-]*0*(\d{1,3})\b", linha_clean, re.IGNORECASE)
                    if m:
                        num_lote = str(int(m.group(1)))
                        if num_lote not in sequencia and int(num_lote) > 0:
                            sequencia.append(num_lote)
                            
                            m_pos = re.search(r"(\d{1,2}º?\s*A?\s*ENTRAR)", linha_clean, re.IGNORECASE)
                            posicao = m_pos.group(1).upper() if m_pos else f"{len(sequencia)}º A ENTRAR"

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

# ==================== RENDERIZAR IMAGEM PDF ====================
@st.cache_data(ttl=7200, show_spinner=False)
def contar_paginas_pdf(file_bytes):
    if not file_bytes:
        return 0
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0

@st.cache_data(ttl=7200, show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150):
    if not file_bytes or num_pagina < 0:
        return None
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

# ==================== CLAUDE VISÃO ====================
def claude_indexar_pagina_catalogo(img_bytes, ant_keys):
    if not img_bytes or not ant_keys:
        return None

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
                texto = "\n".join(txt_parts).strip()
                texto = re.sub(r"^```json|
