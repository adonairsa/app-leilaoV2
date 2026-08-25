import streamlit as st
import pdfplumber
import re
import os
import requests
import json
import base64
import difflib
import hashlib
from io import BytesIO

# ==================== API KEYS ====================
def obter_api_keys():
    ds_keys = []
    ant_keys = []
    try:
        if hasattr(st, "secrets"):
            for key_name in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"]:
                if key_name in st.secrets:
                    val = st.secrets[key_name]
                    if isinstance(val, (list, tuple)): ds_keys.extend(val)
                    elif isinstance(val, str): ds_keys.append(val)

            for key_name in ["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "CLAUDE_API_KEY"]:
                if key_name in st.secrets:
                    val = st.secrets[key_name]
                    if isinstance(val, (list, tuple)): ant_keys.extend(val)
                    elif isinstance(val, str): ant_keys.append(val)
    except Exception:
        pass

    if not ds_keys:
        env_val = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEYS") or ""
        if env_val: ds_keys.extend(env_val.split(","))

    if not ant_keys:
        env_val = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEYS") or os.environ.get("CLAUDE_API_KEY") or ""
        if env_val: ant_keys.extend(env_val.split(","))

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

# ==================== PROCESSAMENTO DA O.E. ====================
@st.cache_data(ttl=7200, show_spinner=False)
def processar_pdf_texto(file_bytes):
    paginas = []
    if not file_bytes:
        return paginas
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text(layout=True) or page.extract_text() or ""
                paginas.append(texto)
    except Exception:
        pass
    return paginas

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
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150, qualidade=85):
    if not file_bytes or num_pagina < 0:
        return None
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            if 0 <= num_pagina < len(pdf.pages):
                img = pdf.pages[num_pagina].to_image(resolution=resolucao).original
                buffer = BytesIO()
                img.convert("RGB").save(buffer, format="JPEG", quality=qualidade)
                return buffer.getvalue()
    except Exception:
        return None
    return None

# ==================== DEEPSEEK LÊ A O.E. ====================
def deepseek_ler_ordem(texto_oe_completo, ds_keys):
    if not ds_keys:
        return [], {}

    prompt = f"""
    Você está lendo uma ORDEM DE ENTRADA (O.E.) de leilão.
    TEXTO DA O.E.:
    {texto_oe_completo[:6000]}

    Extraia TODOS os lotes na ordem em que aparecem.
    Retorne JSON:
    {{
        "lotes": [
            {{
                "lote": "01",
                "posicao": "1º A ENTRAR",
                "qtd": "1",
                "idade": "15m",
                "peso": "514Kg",
                "categoria": "Novilha",
                "produto": "50% de: TIANAH FIV DO HEJ",
                "nome_animal": "TIANAH FIV DO HEJ",
                "porcentagem_venda": "50%",
                "raca": "Nelore",
                "vendedor": "HEJ",
                "info_reproducao": "",
                "tipo_reproducao": ""
            }}
        ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    for api_key in ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
                dados = json.loads(content)

                sequencia = []
                mapa = {}
                for lote in dados.get("lotes", []):
                    lt = lote.get("lote", "")
                    if lt:
                        sequencia.append(lt)
                        mapa[lt] = lote
                return sequencia, mapa
        except Exception:
            continue

    return [], {}

# ==================== CLAUDE INDEXA IMAGEM DO CATÁLOGO ====================
def claude_indexar_pagina_catalogo(img_bytes, ant_keys):
    if not img_bytes or not ant_keys:
        return None

    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    url = "https://api.anthropic.com/v1/messages"

    instrucao = """Esta é uma página de um CATÁLOGO de leilão.
    
    Se for a ficha de um lote, extraia:
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

    Se a página NÃO for a ficha de um lote, retorne "numero_lote": null.

    Retorne APENAS um JSON válido:
    {
      "numero_lote": "01",
      "nome_animal": "",
      "registro": "",
      "raca": "",
      "sexo": "",
      "nascimento": "",
      "pelagem": "",
      "vendedor": "",
      "pai": "",
      "mae": "",
      "avo_paterno": "",
      "avo_paterna": "",
      "avo_materno": "",
      "avo_materna": "",
      "observacoes": "",
      "especie_emoji": "🐴"
    }
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
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            res_json = response.json()
            if response.status_code == 200 and 'content' in res_json:
                txt_parts = [c['text'] for c in res_json['content'] if c.get('type') == 'text']
                texto = "\n".join(txt_parts).strip()
                texto = re.sub(r"^```json|
