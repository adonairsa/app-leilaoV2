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
    .status-badge {
        background: #334155;
        color: white;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 13px;
        margin: 2px;
        display: inline-block;
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
    except Exception:
        pass
    return ds_keys, ant_keys

# ==================== HELPERS ====================
def normalizar_lote(valor):
    """Normaliza número de lote pra comparação: '01', 'Lote 1', 1 -> '1'."""
    if valor is None:
        return ""
    digitos = re.sub(r"\D", "", str(valor))
    return str(int(digitos)) if digitos else ""

def hash_bytes(b):
    if not b:
        return ""
    return hashlib.md5(b).hexdigest()

# ==================== PROCESSAMENTO DA O.E. (texto) ====================
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

# ==================== CATÁLOGO: RENDERIZAÇÃO DE PÁGINAS EM IMAGEM ====================
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

    Extraia TODOS os lotes, na ordem em que aparecem. Cada linha geralmente segue o padrão:
    [posição] [lote] [qtd] [idade] [peso] [categoria] [produto/animal] [vendedor]

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
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
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

# ==================== CLAUDE INDEXA UMA PÁGINA DO CATÁLOGO ====================
def claude_indexar_pagina_catalogo(img_bytes, ant_keys):
    """Lê uma página (imagem) do catálogo e retorna os dados estruturados do lote,
    já em JSON. Usado pra construir o índice completo do catálogo uma única vez.
    Retorna (dados, erro) — erro é None quando deu tudo certo."""
    if not img_bytes:
        return None
    if not ant_keys:
        return None

    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    url = "https://api.anthropic.com/v1/messages"

    instrucao = """Esta é uma página de um CATÁLOGO de leilão. Pode ser a capa, uma página
    de regras/informações, ou a ficha de UM animal/lote específico.

    Se for a ficha de um lote, extraia:
    - numero_lote (apenas o número, ex: "01")
    - nome_animal
    - registro
    - raca
    - sexo
    - nascimento
    - pelagem
    - vendedor
    - pai
    - mae
    - avo_paterno (pai do pai)
    - avo_paterna (mãe do pai)
    - avo_materno (pai da mãe)
    - avo_materna (mãe da mãe)
    - observacoes (ex: "ventre para livre acasalamento", "somente reprodução",
      "treinado em 3 tambores", "castrado", previsão de parto, etc — tudo que
      estiver escrito como observação/status do lote)

    Se a página NÃO for a ficha de um lote (capa, regras, índice), retorne
    "numero_lote": null e os outros campos vazios.

    Retorne APENAS um JSON válido, sem texto antes ou depois, no formato:
    {
      "numero_lote": "01" ou null,
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
      "observacoes": ""
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
                # remove possíveis blocos ```json
                texto = re.sub(r"^
