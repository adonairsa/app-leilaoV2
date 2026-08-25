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
    .cache-info {
        background: #1E293B;
        color: #94A3B8;
        padding: 8px;
        border-radius: 8px;
        font-size: 12px;
        margin: 5px 0;
        text-align: center;
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
    if valor is None:
        return ""
    digitos = re.sub(r"\D", "", str(valor))
    return str(int(digitos)) if digitos else ""

def hash_bytes(b):
    if not b:
        return ""
    return hashlib.md5(b).hexdigest()

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

# ==================== CATÁLOGO: RENDERIZAÇÃO ====================
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

# ==================== CLAUDE INDEXA PÁGINA ====================
def claude_indexar_pagina_catalogo(img_bytes, ant_keys):
    if not img_bytes:
        return None
    if not ant_keys:
        return None

    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    url = "https://api.anthropic.com/v1/messages"

    instrucao = """Esta é uma página de um CATÁLOGO de leilão.

    Se for a ficha de um lote, extraia:
    - numero_lote
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

    Se NÃO for ficha de lote, retorne "numero_lote": null.

    Retorne APENAS JSON válido.
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
                texto = re.sub(r"^```json|```$", "", texto.strip(), flags=re.MULTILINE).strip()
                try:
                    return json.loads(texto)
                except Exception:
                    match = re.search(r"\{.*\}", texto, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
        except Exception:
            continue

    return None

# ==================== ÍNDICE DO CATÁLOGO ====================
@st.cache_data(ttl=7200, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, ant_keys, max_paginas=60):
    indice = {}
    total = min(contar_paginas_pdf(file_bytes_cat), max_paginas)
    if total == 0 or not ant_keys:
        return indice, total

    progresso = st.progress(0, text="Indexando catálogo...")
    for i in range(total):
        img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, i)
        dados = claude_indexar_pagina_catalogo(img_bytes, ant_keys)
        if dados and dados.get("numero_lote"):
            chave = normalizar_lote(dados["numero_lote"])
            if chave:
                dados["_pagina"] = i
                indice[chave] = dados
        progresso.progress((i + 1) / total, text=f"Indexando catálogo... página {i + 1}/{total}")
    progresso.empty()
    return indice, total

def encontrar_no_indice(num_lote_oe, nome_animal_oe, indice):
    chave = normalizar_lote(num_lote_oe)
    if chave in indice:
        return indice[chave]

    if nome_animal_oe:
        melhor_match = None
        melhor_score = 0.0
        for dados in indice.values():
            nome_cat = dados.get("nome_animal", "")
            if not nome_cat:
                continue
            score = difflib.SequenceMatcher(None, nome_animal_oe.upper(), nome_cat.upper()).ratio()
            if score > melhor_score:
                melhor_score = score
                melhor_match = dados
        if melhor_match and melhor_score > 0.55:
            return melhor_match

    return None

# ==================== DEEPSEEK CRUZA ====================
def deepseek_cruzar(num_lote, dados_ordem, dados_catalogo, ds_keys):
    if not ds_keys:
        return None

    prompt = f"""
    Você é um locutor de leilão. Cruze as informações do LOTE {num_lote}.

    DADOS DA ORDEM:
    {json.dumps(dados_ordem, ensure_ascii=False, indent=2)}

    DADOS DO CATÁLOGO:
    {json.dumps(dados_catalogo, ensure_ascii=False, indent=2)}

    Gere:
    1. "abertura": frase curta animada
    2. "encartes": dados importantes
    3. "gatilhos": 3 gatilhos de pista
    4. "observacao_destaque": resumo de observações

    Retorne APENAS JSON.
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
            "temperature": 0.4
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                return json.loads(res_json['choices'][0]['message']['content'])
        except Exception:
            continue

    return None

# ==================== PRECARREGAMENTO DOS PRÓXIMOS 3 LOTES ====================
# Cache em session_state para não repetir processamento
if 'cache_lotes_precarregados' not in st.session_state:
    st.session_state.cache_lotes_precarregados = {}

def precarregar_proximos_lotes(idx_atual, lista_lotes, mapa_oe, indice_catalogo, ds_keys):
    """
    Precarrega os próximos 3 lotes em segundo plano usando ThreadPoolExecutor
    """
    proximos_indices = [idx_atual + i for i in range(1, 4) if (idx_atual + i) < len(lista_lotes)]
    
    if not proximos_indices or not ds_keys:
        return
    
    def _processar_lote(i):
        num_lt = lista_lotes[i]
        
        # Verifica se já está em cache
        chave_cache = f"{num_lt}"
        if chave_cache in st.session_state.cache_lotes_precarregados:
            return
        
        dados_lt = mapa_oe.get(num_lt, {})
        dados_cat = encontrar_no_indice(num_lt, dados_lt.get("nome_animal", ""), indice_catalogo)
        
        if dados_cat and ds_keys:
            try:
                dados_finais = deepseek_cruzar(num_lt, dados_lt, dados_cat, ds_keys)
                if dados_finais:
                    st.session_state.cache_lotes_precarregados[chave_cache] = {
                        "dados_catalogo": dados_cat,
                        "dados_finais": dados_finais,
                        "pagina": dados_cat.get("_pagina", -1)
                    }
            except Exception:
                pass
    
    # Executa em paralelo
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(_processar_lote, proximos_indices)

def obter_dados_cache(num_lote):
    """Busca dados do cache se existirem"""
    chave = f"{num_lote}"
    return st.session_state.cache_lotes_precarregados.get(chave)

# ==================== RENDERIZAR PEDIGREE ====================
def renderizar_pedigree(dados_catalogo):
    if not dados_catalogo:
        return
    pai = dados_catalogo.get("pai", "")
    mae = dados_catalogo.get("mae", "")
    ap = dados_catalogo.get("avo_paterno", "")
    apm = dados_catalogo.get("avo_paterna", "")
    am = dados_catalogo.get("avo_materno", "")
    amm = dados_catalogo.get("avo_materna", "")

    if not any([pai, mae, ap, apm, am, amm]):
        return

    html = '<div class="pedigree-card"><table>'
    html += f'<tr><td><strong>PAI</strong></td><td>{pai or "-"}</td>' \
            f'<td><strong>AVÔ PATERNO</strong></td><td>{ap or "-"}</td></tr>'
    html += f'<tr><td></td><td></td>' \
            f'<td><strong>AVÓ PATERNA</strong></td><td>{apm or "-"}</td></tr>'
    html += f'<tr><td><strong>MÃE</strong></td><td>{mae or "-"}</td>' \
            f'<td><strong>AVÔ MATERNO</strong></td><td>{am or "-"}</td></tr>'
    html += f'<tr><td></td><td></td>' \
            f'<td><strong>AVÓ MATERNA</strong></td><td>{amm or "-"}</td></tr>'
    html += '</table></div>'
    st.markdown(html, unsafe_allow_html=True)

# ==================== MAIN ====================
def run():
    ds_keys, ant_keys = obter_api_keys()

    with st.sidebar:
        st.header("📂 Arquivos")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe")
        file_cat = st.file_uploader("Catálogo (PDF)", type="pdf", key="cat")

        st.markdown("---")
        modo_ordenacao = st.radio("Ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0)
        max_paginas_catalogo = st.number_input(
            "Máx. de páginas do catálogo pra indexar", min_value=1, max_value=300, value=60
        )

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None

    texto_oe = processar_pdf_texto(file_bytes_oe)

    sequencia_oe = []
    mapa_oe = {}

    if texto_oe and ds_keys:
        with st.spinner("🤖 DeepSeek lendo a O.E..."):
            texto_oe_completo = "\n".join(texto_oe)
            sequencia_oe, mapa_oe = deepseek_ler_ordem(texto_oe_completo, ds_keys)

    if not sequencia_oe:
        st.warning("Carregue a O.E. e configure o DeepSeek!")
        st.stop()

    # Índice do catálogo
    indice_catalogo = {}
    total_paginas_cat = 0
    if file_bytes_cat and ant_keys:
        indice_catalogo, total_paginas_cat = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), ant_keys, max_paginas_catalogo
        )

    if modo_ordenacao == "ORDEM NUMÉRICA":
        lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x) or 0))
    else:
        lista_lotes = sequencia_oe.copy()

    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0

    # Navegação
    st.markdown(
        f'<div class="ordem-indicador">{modo_ordenacao} | Lote {st.session_state.lote_idx + 1} de {len(lista_lotes)}</div>',
        unsafe_allow_html=True
    )

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

    # Verifica cache primeiro
    cache_dados = obter_dados_cache(num_lote)
    
    if cache_dados:
        dados_catalogo = cache_dados.get("dados_catalogo")
        dados_finais = cache_dados.get("dados_finais")
        pagina_detectada = cache_dados.get("pagina", -1)
        st.markdown(f'<div class="cache-info">⚡ Carregado do cache</div>', unsafe_allow_html=True)
    else:
        # Processa normalmente
        dados_catalogo = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo)
        pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1
        
        if file_bytes_cat and indice_catalogo and pagina_detectada < 0:
            st.warning(f"⚠️ Lote {num_lote} não encontrado no catálogo.")
        
        dados_finais = None
        if dados_catalogo and ds_keys:
            with st.spinner("🔄 Cruzando informações..."):
                dados_finais = deepseek_cruzar(num_lote, dados_lote, dados_catalogo, ds_keys)
        
        # Salva no cache
        if dados_finais:
            st.session_state.cache_lotes_precarregados[f"{num_lote}"] = {
                "dados_catalogo": dados_catalogo,
                "dados_finais": dados_finais,
                "pagina": pagina_detectada
            }
    
    # PRECARREGA OS PRÓXIMOS 3 LOTES EM SEGUNDO PLANO
    precarregar_proximos_lotes(
        st.session_state.lote_idx, lista_lotes, mapa_oe, indice_catalogo, ds_keys
    )

    # ==================== LAYOUT ====================
    col_esquerda, col_direita = st.columns([1, 1])

    # ---------- COLUNA ESQUERDA ----------
    with col_esquerda:
        if dados_finais and dados_finais.get("abertura"):
            st.markdown(
                f'<div class="abertura-box">🎙️ "{dados_finais["abertura"]}"</div>',
                unsafe_allow_html=True
            )
        if dados_finais and dados_finais.get("observacao_destaque"):
            st.markdown(
                f'<div class="ai-consideracoes-box"><h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 OBSERVAÇÃO</h3>'
                f'<div>{dados_finais["observacao_destaque"]}</div></div>',
                unsafe_allow_html=True
            )

        if file_bytes_cat and pagina_detectada >= 0:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}</div>', unsafe_allow_html=True)
            img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
            if img_bytes:
                st.image(img_bytes, use_container_width=True)

    # ---------- COLUNA DIREITA ----------
    with col_direita:
        st.markdown(
            f'<div class="lote-destaque">LOTE {num_lote}<br>'
            f'<span style="font-size: 24px;">{dados_lote.get("posicao", "")}</span></div>',
            unsafe_allow_html=True
        )

        if dados_lote.get("porcentagem_venda"):
            st.markdown(f'<div class="banner-venda">💎 VENDA DE {dados_lote["porcentagem_venda"]}</div>', unsafe_allow_html=True)

        if dados_lote.get("info_reproducao"):
            st.markdown(f'<div class="banner-reproducao">{dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)

        nome_exibir = (dados_catalogo or {}).get("nome_animal") or dados_lote.get("nome_animal", "")
        if nome_exibir:
            st.markdown(f'<div class="nome-animal-box">🐴 {nome_exibir}</div>', unsafe_allow_html=True)

        st.markdown("### 📋 INFORMAÇÕES DO LOTE")

        if dados_finais and dados_finais.get("encartes"):
            encartes_validos = [e for e in dados_finais["encartes"] if e.get("valor")]
            cols = st.columns(min(3, max(1, len(encartes_validos))))
            for idx, enc in enumerate(encartes_validos):
                col = cols[idx % len(cols)]
                with col:
                    st.markdown(
                        f'<div class="animal-info"><strong>{enc["titulo"]}:</strong><br>{enc["valor"]}</div>',
                        unsafe_allow_html=True
                    )
        elif dados_catalogo:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(
                    f'<div class="animal-info"><strong>RAÇA:</strong><br>{dados_catalogo.get("raca", "-")}<br><br>'
                    f'<strong>SEXO:</strong><br>{dados_catalogo.get("sexo", "-")}</div>',
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown(
                    f'<div class="animal-info"><strong>PELAGEM:</strong><br>{dados_catalogo.get("pelagem", "-")}<br><br>'
                    f'<strong>NASCIMENTO:</strong><br>{dados_catalogo.get("nascimento", "-")}</div>',
                    unsafe_allow_html=True
                )
            with col3:
                st.markdown(
                    f'<div class="animal-info"><strong>REGISTRO:</strong><br>{dados_catalogo.get("registro", "-")}<br><br>'
                    f'<strong>VENDEDOR:</strong><br>{dados_catalogo.get("vendedor", "-")}</div>',
                    unsafe_allow_html=True
                )
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(
                    f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}<br><br>'
                    f'<strong>RAÇA:</strong><br>{dados_lote.get("raca", "-")}</div>',
                    unsafe_allow_html=True
                )
            with col2:
                st.markdown(
                    f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso", "-")}<br><br>'
                    f'<strong>IDADE:</strong><br>{dados_lote.get("idade", "-")}</div>',
                    unsafe_allow_html=True
                )
            with col3:
                st.markdown(
                    f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd", "-")}<br><br>'
                    f'<strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>',
                    unsafe_allow_html=True
                )

        if dados_catalogo:
            st.markdown("### 🧬 GENEALOGIA")
            renderizar_pedigree(dados_catalogo)

        st.markdown("### 🎤 GATILHOS DE PISTA")
        if dados_finais and dados_finais.get("gatilhos"):
            for g in dados_finais["gatilhos"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)
        else:
            for g in ["ANIMAL SELECIONADO!", "PROCEDÊNCIA GARANTIDA!", "OPORTUNIDADE ÚNICA!"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()
