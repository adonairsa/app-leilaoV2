import streamlit as st
import pdfplumber
import re
import requests
import json
import base64
import difflib
import hashlib
import threading
from io import BytesIO

st.set_page_config(
    page_title="PAINEL DO LEILOEIRO PRO",
    page_icon="🐂",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== CONFIG DE LOTE (BATCH) ====================
BATCH_PAGINAS_PADRAO = 4
BATCH_LOTES_PADRAO = 8
QTD_PRE_CARREGAR = 3  # quantos lotes futuros pré-carregar em segundo plano

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
    .status-processamento {
        background: #0F172A;
        color: #94A3B8;
        padding: 10px;
        border-radius: 8px;
        font-size: 13px;
        margin-bottom: 8px;
        border: 1px solid #1E293B;
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

def extrair_json(texto):
    if not texto:
        return None
    limpo = re.sub(r"```json|```", "", texto).strip()
    try:
        return json.loads(limpo)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", limpo, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

# ==================== PROCESSAMENTO DA O.E. (texto) ====================
@st.cache_data(ttl=86400, show_spinner=False)
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
@st.cache_data(ttl=86400, show_spinner=False)
def contar_paginas_pdf(file_bytes):
    if not file_bytes:
        return 0
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0

@st.cache_data(ttl=86400, show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150, qualidade=80):
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

def _prefetch_paginas_worker(file_bytes, paginas):
    """Roda em thread separada: só esquenta o cache de obter_imagem_bytes_pagina
    pra quando o usuário clicar em 'Próximo', a imagem já estar pronta."""
    for p in paginas:
        try:
            obter_imagem_bytes_pagina(file_bytes, p)
        except Exception:
            pass

def pre_carregar_lotes_vizinhos(file_bytes_cat, lista_lotes, idx_atual, mapa_oe, indice_catalogo, qtd=QTD_PRE_CARREGAR):
    """Pré-carrega em segundo plano a imagem da página dos lotes vizinhos —
    tanto os próximos quanto os anteriores — pra navegar em qualquer direção
    (Próximo ou Anterior) sem esperar renderização."""
    if not file_bytes_cat or not indice_catalogo:
        return
    paginas_vizinhas = []
    offsets = list(range(-qtd, 0)) + list(range(1, qtd + 1))  # anteriores e próximos
    for offset in offsets:
        idx_vizinho = idx_atual + offset
        if idx_vizinho < 0 or idx_vizinho >= len(lista_lotes):
            continue
        lt_vizinho = lista_lotes[idx_vizinho]
        dados_lote_vizinho = mapa_oe.get(lt_vizinho, {})
        dados_cat_vizinho = encontrar_no_indice(lt_vizinho, dados_lote_vizinho.get("nome_animal", ""), indice_catalogo)
        if dados_cat_vizinho:
            pagina = dados_cat_vizinho.get("_pagina", -1)
            if pagina >= 0:
                paginas_vizinhas.append(pagina)
    if paginas_vizinhas:
        threading.Thread(
            target=_prefetch_paginas_worker,
            args=(file_bytes_cat, paginas_vizinhas),
            daemon=True
        ).start()

# ==================== DEEPSEEK LÊ A O.E. (CACHEADO) ====================
@st.cache_data(ttl=86400, show_spinner=False)
def deepseek_ler_ordem(texto_oe_completo, _ds_keys):
    if not _ds_keys or not texto_oe_completo:
        return [], {}, "sem chave ou sem texto"

    prompt = f"""
    Você está lendo uma ORDEM DE ENTRADA (O.E.) de leilão.

    TEXTO DA O.E.:
    {texto_oe_completo[:6000]}

    Extraia TODOS os lotes, na ordem em que aparecem. Cada linha geralmente segue o padrão:
    [posição] [lote] [qtd] [idade] [peso] [categoria] [produto/animal] [vendedor]

    Retorne APENAS JSON:
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
    ultimo_erro = ""

    for api_key in _ds_keys:
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
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                sequencia, mapa = [], {}
                for lote in dados.get("lotes", []):
                    lt = lote.get("lote", "")
                    if lt:
                        sequencia.append(lt)
                        mapa[lt] = lote
                return sequencia, mapa, None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return [], {}, ultimo_erro

# ==================== CLAUDE INDEXA UM LOTE DE PÁGINAS (BATCH) ====================
def claude_indexar_lote_paginas(imagens_bytes, _ant_keys):
    if not imagens_bytes or not _ant_keys:
        return [None] * len(imagens_bytes), "sem imagens ou sem chave"

    conteudo = []
    for idx, img in enumerate(imagens_bytes):
        b64 = base64.b64encode(img).decode('utf-8')
        conteudo.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
        })
        conteudo.append({"type": "text", "text": f"[A imagem acima é a PÁGINA {idx + 1} deste grupo]"})

    instrucao = f"""
    As imagens acima são {len(imagens_bytes)} páginas de um CATÁLOGO de leilão,
    na ordem PÁGINA 1, PÁGINA 2, etc. Cada página pode ser a capa, uma página de
    regras/informações, ou a ficha de UM animal/lote específico.

    Para CADA página, na mesma ordem, extraia (se for ficha de lote):
    numero_lote, nome_animal, registro, raca, sexo, nascimento, pelagem, vendedor,
    pai, mae, avo_paterno, avo_paterna, avo_materno, avo_materna, observacoes
    (ex: "ventre para livre acasalamento", "somente reprodução", "treinado em 3
    tambores", "castrado", previsão de parto, etc).

    Se a página NÃO for ficha de lote (capa, regras, índice), retorne
    "numero_lote": null e os outros campos vazios, mas AINDA ASSIM inclua um
    objeto pra ela no array (mesma posição/ordem).

    Retorne APENAS um JSON válido, sem texto antes ou depois, no formato:
    {{
      "paginas": [
        {{
          "pagina_ordem": 1,
          "numero_lote": "01" ou null,
          "nome_animal": "", "registro": "", "raca": "", "sexo": "",
          "nascimento": "", "pelagem": "", "vendedor": "",
          "pai": "", "mae": "", "avo_paterno": "", "avo_paterna": "",
          "avo_materno": "", "avo_materna": "", "observacoes": ""
        }}
      ]
    }}

    O array "paginas" DEVE ter exatamente {len(imagens_bytes)} itens, um por página.
    """
    conteudo.append({"type": "text", "text": instrucao})

    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 700 * len(imagens_bytes) + 400,
        "messages": [{"role": "user", "content": conteudo}]
    }

    ultimo_erro = ""
    for api_key in _ant_keys:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            res_json = response.json()
            if response.status_code == 200 and 'content' in res_json:
                txt_parts = [c['text'] for c in res_json['content'] if c.get('type') == 'text']
                texto = "\n".join(txt_parts)
                dados = extrair_json(texto)
                if not dados or "paginas" not in dados:
                    ultimo_erro = "Claude respondeu, mas não veio JSON válido"
                    continue
                paginas = dados["paginas"]
                while len(paginas) < len(imagens_bytes):
                    paginas.append(None)
                return paginas[:len(imagens_bytes)], None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return [None] * len(imagens_bytes), ultimo_erro

# ==================== CONSTRÓI ÍNDICE COMPLETO DO CATÁLOGO (CACHEADO) ====================
@st.cache_data(ttl=86400, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, _ant_keys, max_paginas, tamanho_lote):
    indice = {}
    erros = []
    total = min(contar_paginas_pdf(file_bytes_cat), max_paginas)
    if total == 0 or not _ant_keys:
        return indice, total, ["sem páginas ou sem ANTHROPIC_API_KEY"]

    progresso = st.progress(0, text="Indexando catálogo...")
    grupos = [list(range(i, min(i + tamanho_lote, total))) for i in range(0, total, tamanho_lote)]

    for g_idx, grupo in enumerate(grupos):
        imagens = [obter_imagem_bytes_pagina(file_bytes_cat, p) for p in grupo]
        imagens = [img for img in imagens if img]
        if not imagens:
            continue

        resultados, erro = claude_indexar_lote_paginas(imagens, _ant_keys)
        if erro:
            erros.append(f"Grupo páginas {grupo[0]+1}-{grupo[-1]+1}: {erro}")

        for pos, pagina_real in enumerate(grupo):
            if pos >= len(resultados):
                continue
            dados = resultados[pos]
            if dados and dados.get("numero_lote"):
                chave = normalizar_lote(dados["numero_lote"])
                if chave:
                    dados["_pagina"] = pagina_real
                    indice[chave] = dados

        progresso.progress((g_idx + 1) / len(grupos), text=f"Indexando catálogo... grupo {g_idx + 1}/{len(grupos)}")

    progresso.empty()
    return indice, total, erros

def encontrar_no_indice(num_lote_oe, nome_animal_oe, indice):
    chave = normalizar_lote(num_lote_oe)
    if chave in indice:
        return indice[chave]

    if nome_animal_oe:
        melhor_match, melhor_score = None, 0.0
        for dados in indice.values():
            nome_cat = dados.get("nome_animal", "")
            if not nome_cat:
                continue
            score = difflib.SequenceMatcher(None, nome_animal_oe.upper(), nome_cat.upper()).ratio()
            if score > melhor_score:
                melhor_score, melhor_match = score, dados
        if melhor_match and melhor_score > 0.55:
            return melhor_match

    return None

# ==================== DEEPSEEK GERA ABERTURA/GATILHOS PRA VÁRIOS LOTES DE UMA VEZ ====================
def deepseek_processar_lotes_batch(lotes_info, _ds_keys):
    if not _ds_keys or not lotes_info:
        return {}, "sem chave ou sem lotes"

    prompt = f"""
    Você é um locutor de leilão de gado/cavalos experiente. Para CADA lote abaixo,
    gere um material de apoio pra cantar o lote na pista.

    LOTES (JSON):
    {json.dumps(lotes_info, ensure_ascii=False, indent=2)}

    Para cada lote gere:
    - "abertura": frase curta (máx. 25 palavras), animada, citando o nome do
      animal e algo que se destaque.
    - "encartes": lista com 3-4 dados importantes pra mostrar em tela
      (ex: CATEGORIA/RAÇA, PELAGEM, VENDEDOR, PESO/IDADE/STATUS).
    - "gatilhos": 3 gatilhos curtos de pista (frases de impacto).
    - "observacao_destaque": 1 frase resumindo algo relevante das observações
      (reprodução, treino, previsão de parto), ou "" se não houver nada.

    Retorne APENAS JSON:
    {{
      "resultados": [
        {{
          "lote": "01",
          "abertura": "...",
          "encartes": [{{"titulo": "CATEGORIA", "valor": "..."}}],
          "gatilhos": ["...", "...", "..."],
          "observacao_destaque": "..."
        }}
      ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    ultimo_erro = ""
    for api_key in _ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados or "resultados" not in dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                mapa = {}
                for r in dados["resultados"]:
                    lt = r.get("lote")
                    if lt:
                        mapa[normalizar_lote(lt)] = r
                return mapa, None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return {}, ultimo_erro

@st.cache_data(ttl=86400, show_spinner=False)
def preparar_todos_cruzamentos(lista_lotes, mapa_oe, indice_catalogo, _ds_keys, tamanho_lote):
    resultado_final = {}
    erros = []

    lotes_com_catalogo = []
    for num_lote in lista_lotes:
        dados_ordem = mapa_oe.get(num_lote, {})
        dados_cat = encontrar_no_indice(num_lote, dados_ordem.get("nome_animal", ""), indice_catalogo)
        if dados_cat:
            lotes_com_catalogo.append({
                "lote": num_lote,
                "ordem": dados_ordem,
                "catalogo": {k: v for k, v in dados_cat.items() if k != "_pagina"}
            })

    if not lotes_com_catalogo or not _ds_keys:
        return resultado_final, ["nenhum lote casado com o catálogo, ou sem DEEPSEEK_API_KEY"]

    grupos = [lotes_com_catalogo[i:i + tamanho_lote] for i in range(0, len(lotes_com_catalogo), tamanho_lote)]

    progresso = st.progress(0, text="Gerando aberturas e gatilhos...")
    for g_idx, grupo in enumerate(grupos):
        mapa_resultado, erro = deepseek_processar_lotes_batch(grupo, _ds_keys)
        if erro:
            erros.append(f"Grupo lotes {[g['lote'] for g in grupo]}: {erro}")
        resultado_final.update(mapa_resultado)
        progresso.progress((g_idx + 1) / len(grupos), text=f"Gerando aberturas... grupo {g_idx + 1}/{len(grupos)}")
    progresso.empty()

    return resultado_final, erros

# ==================== CARD DE PEDIGREE ====================
def renderizar_pedigree(dados_catalogo):
    if not dados_catalogo:
        return
    pai, mae = dados_catalogo.get("pai", ""), dados_catalogo.get("mae", "")
    ap, apm = dados_catalogo.get("avo_paterno", ""), dados_catalogo.get("avo_paterna", "")
    am, amm = dados_catalogo.get("avo_materno", ""), dados_catalogo.get("avo_materna", "")

    if not any([pai, mae, ap, apm, am, amm]):
        return

    html = '<div class="pedigree-card"><table>'
    html += f'<tr><td><strong>PAI</strong></td><td>{pai or "-"}</td><td><strong>AVÔ PATERNO</strong></td><td>{ap or "-"}</td></tr>'
    html += f'<tr><td></td><td></td><td><strong>AVÓ PATERNA</strong></td><td>{apm or "-"}</td></tr>'
    html += f'<tr><td><strong>MÃE</strong></td><td>{mae or "-"}</td><td><strong>AVÔ MATERNO</strong></td><td>{am or "-"}</td></tr>'
    html += f'<tr><td></td><td></td><td><strong>AVÓ MATERNA</strong></td><td>{amm or "-"}</td></tr>'
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
        max_paginas_catalogo = st.number_input("Máx. de páginas do catálogo", min_value=1, max_value=300, value=60)
        tamanho_lote_paginas = st.number_input("Páginas por chamada (Claude)", min_value=1, max_value=8, value=BATCH_PAGINAS_PADRAO)
        tamanho_lote_cruzamento = st.number_input("Lotes por chamada (DeepSeek)", min_value=1, max_value=20, value=BATCH_LOTES_PADRAO)

        st.markdown("---")
        if st.button("🔄 Reprocessar tudo (limpar cache)", use_container_width=True):
            construir_indice_catalogo.clear()
            preparar_todos_cruzamentos.clear()
            deepseek_ler_ordem.clear()
            st.rerun()

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None

    texto_oe = processar_pdf_texto(file_bytes_oe)

    sequencia_oe, mapa_oe = [], {}
    if texto_oe and ds_keys:
        texto_oe_completo = "\n".join(texto_oe)
        with st.spinner("🤖 Lendo a O.E. (só na 1ª vez, depois fica em cache)..."):
            sequencia_oe, mapa_oe, erro_oe = deepseek_ler_ordem(texto_oe_completo, tuple(ds_keys))
        if erro_oe:
            st.error(f"Erro ao ler a O.E.: {erro_oe}")

    if not sequencia_oe:
        st.warning("Carregue a O.E. e configure o DeepSeek!")
        st.stop()

    indice_catalogo, total_paginas_cat, erros_indice = {}, 0, []
    if file_bytes_cat and ant_keys:
        indice_catalogo, total_paginas_cat, erros_indice = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), tuple(ant_keys),
            max_paginas_catalogo, tamanho_lote_paginas
        )
    elif file_bytes_cat and not ant_keys:
        st.warning("Catálogo carregado, mas falta ANTHROPIC_API_KEY pra indexar as páginas.")

    dados_finais_todos, erros_cruzamento = {}, []
    if indice_catalogo and ds_keys:
        dados_finais_todos, erros_cruzamento = preparar_todos_cruzamentos(
            tuple(sequencia_oe), mapa_oe, indice_catalogo, tuple(ds_keys), tamanho_lote_cruzamento
        )

    with st.expander("🛠️ Status do processamento (debug)"):
        st.markdown(f'<div class="status-processamento">'
                     f'Lotes na O.E.: {len(sequencia_oe)}<br>'
                     f'Páginas do catálogo indexadas: {len(indice_catalogo)} de {total_paginas_cat}<br>'
                     f'Lotes com abertura/gatilhos gerados: {len(dados_finais_todos)}'
                     f'</div>', unsafe_allow_html=True)
        if erros_indice:
            st.error("Erros na indexação do catálogo:")
            for e in erros_indice:
                st.text(f"• {e}")
        if erros_cruzamento:
            st.error("Erros ao gerar aberturas/gatilhos:")
            for e in erros_cruzamento:
                st.text(f"• {e}")

    if modo_ordenacao == "ORDEM NUMÉRICA":
        lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x) or 0))
    else:
        lista_lotes = sequencia_oe.copy()

    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0

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

    dados_catalogo = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo)
    dados_finais = dados_finais_todos.get(normalizar_lote(num_lote))
    pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1

    # pré-carrega em segundo plano a imagem dos lotes vizinhos (antes e depois)
    pre_carregar_lotes_vizinhos(file_bytes_cat, lista_lotes, st.session_state.lote_idx, mapa_oe, indice_catalogo)

    if file_bytes_cat and indice_catalogo and pagina_detectada < 0:
        st.warning(f"⚠️ Lote {num_lote} não encontrado automaticamente no catálogo. Escolha a página manualmente:")
        pagina_manual = st.number_input(
            "Página do catálogo:", min_value=1, max_value=max(1, total_paginas_cat),
            value=1, key=f"pag_{num_lote}"
        )
        pagina_detectada = pagina_manual - 1

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        if dados_finais and dados_finais.get("abertura"):
            st.markdown(f'<div class="abertura-box">🎙️ "{dados_finais["abertura"]}"</div>', unsafe_allow_html=True)
        if dados_finais and dados_finais.get("observacao_destaque"):
            st.markdown(
                f'<div class="ai-consideracoes-box"><h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 OBSERVAÇÃO</h3>'
                f'<div>{dados_finais["observacao_destaque"]}</div></div>', unsafe_allow_html=True
            )

        if file_bytes_cat and pagina_detectada >= 0:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}</div>', unsafe_allow_html=True)
            img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada, resolucao=150, qualidade=85)
            if img_bytes:
                st.image(img_bytes, use_container_width=True)

        if dados_catalogo:
            with st.expander("📖 Dados extraídos do catálogo (bruto)"):
                st.json({k: v for k, v in dados_catalogo.items() if k != "_pagina"})

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
                with cols[idx % len(cols)]:
                    st.markdown(f'<div class="animal-info"><strong>{enc["titulo"]}:</strong><br>{enc["valor"]}</div>', unsafe_allow_html=True)
        elif dados_catalogo:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f'<div class="animal-info"><strong>RAÇA:</strong><br>{dados_catalogo.get("raca", "-")}<br><br><strong>SEXO:</strong><br>{dados_catalogo.get("sexo", "-")}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PELAGEM:</strong><br>{dados_catalogo.get("pelagem", "-")}<br><br><strong>NASCIMENTO:</strong><br>{dados_catalogo.get("nascimento", "-")}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="animal-info"><strong>REGISTRO:</strong><br>{dados_catalogo.get("registro", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_catalogo.get("vendedor", "-")}</div>', unsafe_allow_html=True)
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca", "-")}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso", "-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade", "-")}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)

        if dados_catalogo:
            st.markdown("### 🧬 GENEALOGIA")
            renderizar_pedigree(dados_catalogo)
            if dados_catalogo.get("observacoes"):
                st.markdown(f'<span class="status-badge">📌 {dados_catalogo["observacoes"]}</span>', unsafe_allow_html=True)

        st.markdown("### 🎤 GATILHOS DE PISTA")
        if dados_finais and dados_finais.get("gatilhos"):
            for g in dados_finais["gatilhos"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)
        else:
            for g in ["ANIMAL SELECIONADO: Qualidade superior!",
                      "PROCEDÊNCIA GARANTIDA: Origem comprovada!",
                      "OPORTUNIDADE ÚNICA: Preço imperdível!"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()        text-align: center;
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
    .status-processamento {
        background: #0F172A;
        color: #94A3B8;
        padding: 10px;
        border-radius: 8px;
        font-size: 13px;
        margin-bottom: 8px;
        border: 1px solid #1E293B;
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

def extrair_json(texto):
    """Extrai o primeiro objeto/array JSON válido de um texto que pode vir
    com ```json ... ``` ou com texto antes/depois."""
    if not texto:
        return None
    limpo = re.sub(r"```json|```", "", texto).strip()
    try:
        return json.loads(limpo)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", limpo, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

# ==================== PROCESSAMENTO DA O.E. (texto) ====================
@st.cache_data(ttl=86400, show_spinner=False)
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
@st.cache_data(ttl=86400, show_spinner=False)
def contar_paginas_pdf(file_bytes):
    if not file_bytes:
        return 0
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0

@st.cache_data(ttl=86400, show_spinner=False)
def obter_imagem_bytes_pagina(file_bytes, num_pagina, resolucao=150, qualidade=80):
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

# ==================== DEEPSEEK LÊ A O.E. (CACHEADO) ====================
@st.cache_data(ttl=86400, show_spinner=False)
def deepseek_ler_ordem(texto_oe_completo, _ds_keys):
    """_ds_keys tem underscore de propósito: o Streamlit não tenta fazer hash
    dele (é só uma credencial, não faz parte do resultado). O cache é
    baseado no texto da O.E. — mesma O.E. nunca chama a API de novo."""
    if not _ds_keys or not texto_oe_completo:
        return [], {}, "sem chave ou sem texto"

    prompt = f"""
    Você está lendo uma ORDEM DE ENTRADA (O.E.) de leilão.

    TEXTO DA O.E.:
    {texto_oe_completo[:6000]}

    Extraia TODOS os lotes, na ordem em que aparecem. Cada linha geralmente segue o padrão:
    [posição] [lote] [qtd] [idade] [peso] [categoria] [produto/animal] [vendedor]

    Retorne APENAS JSON:
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
    ultimo_erro = ""

    for api_key in _ds_keys:
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
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                sequencia, mapa = [], {}
                for lote in dados.get("lotes", []):
                    lt = lote.get("lote", "")
                    if lt:
                        sequencia.append(lt)
                        mapa[lt] = lote
                return sequencia, mapa, None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return [], {}, ultimo_erro

# ==================== CLAUDE INDEXA UM LOTE DE PÁGINAS (BATCH) ====================
def claude_indexar_lote_paginas(imagens_bytes, _ant_keys):
    """Manda VÁRIAS páginas numa única chamada ao Claude e recebe um array
    de JSONs, um por página, na mesma ordem. Reduz drasticamente o número
    de chamadas em relação a 1 chamada por página."""
    if not imagens_bytes or not _ant_keys:
        return [None] * len(imagens_bytes), "sem imagens ou sem chave"

    conteudo = []
    for idx, img in enumerate(imagens_bytes):
        b64 = base64.b64encode(img).decode('utf-8')
        conteudo.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
        })
        conteudo.append({"type": "text", "text": f"[A imagem acima é a PÁGINA {idx + 1} deste grupo]"})

    instrucao = f"""
    As imagens acima são {len(imagens_bytes)} páginas de um CATÁLOGO de leilão,
    na ordem PÁGINA 1, PÁGINA 2, etc. Cada página pode ser a capa, uma página de
    regras/informações, ou a ficha de UM animal/lote específico.

    Para CADA página, na mesma ordem, extraia (se for ficha de lote):
    numero_lote, nome_animal, registro, raca, sexo, nascimento, pelagem, vendedor,
    pai, mae, avo_paterno, avo_paterna, avo_materno, avo_materna, observacoes
    (ex: "ventre para livre acasalamento", "somente reprodução", "treinado em 3
    tambores", "castrado", previsão de parto, etc).

    Se a página NÃO for ficha de lote (capa, regras, índice), retorne
    "numero_lote": null e os outros campos vazios, mas AINDA ASSIM inclua um
    objeto pra ela no array (mesma posição/ordem).

    Retorne APENAS um JSON válido, sem texto antes ou depois, no formato:
    {{
      "paginas": [
        {{
          "pagina_ordem": 1,
          "numero_lote": "01" ou null,
          "nome_animal": "", "registro": "", "raca": "", "sexo": "",
          "nascimento": "", "pelagem": "", "vendedor": "",
          "pai": "", "mae": "", "avo_paterno": "", "avo_paterna": "",
          "avo_materno": "", "avo_materna": "", "observacoes": ""
        }}
      ]
    }}

    O array "paginas" DEVE ter exatamente {len(imagens_bytes)} itens, um por página.
    """
    conteudo.append({"type": "text", "text": instrucao})

    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 700 * len(imagens_bytes) + 400,
        "messages": [{"role": "user", "content": conteudo}]
    }

    ultimo_erro = ""
    for api_key in _ant_keys:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            res_json = response.json()
            if response.status_code == 200 and 'content' in res_json:
                txt_parts = [c['text'] for c in res_json['content'] if c.get('type') == 'text']
                texto = "\n".join(txt_parts)
                dados = extrair_json(texto)
                if not dados or "paginas" not in dados:
                    ultimo_erro = "Claude respondeu, mas não veio JSON válido"
                    continue
                paginas = dados["paginas"]
                # garante o mesmo tamanho da entrada, preenchendo o que faltar
                while len(paginas) < len(imagens_bytes):
                    paginas.append(None)
                return paginas[:len(imagens_bytes)], None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return [None] * len(imagens_bytes), ultimo_erro

# ==================== CONSTRÓI ÍNDICE COMPLETO DO CATÁLOGO (CACHEADO) ====================
@st.cache_data(ttl=86400, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, _ant_keys, max_paginas, tamanho_lote):
    indice = {}
    erros = []
    total = min(contar_paginas_pdf(file_bytes_cat), max_paginas)
    if total == 0 or not _ant_keys:
        return indice, total, ["sem páginas ou sem ANTHROPIC_API_KEY"]

    progresso = st.progress(0, text="Indexando catálogo...")
    grupos = [list(range(i, min(i + tamanho_lote, total))) for i in range(0, total, tamanho_lote)]

    for g_idx, grupo in enumerate(grupos):
        imagens = [obter_imagem_bytes_pagina(file_bytes_cat, p) for p in grupo]
        imagens = [img for img in imagens if img]
        if not imagens:
            continue

        resultados, erro = claude_indexar_lote_paginas(imagens, _ant_keys)
        if erro:
            erros.append(f"Grupo páginas {grupo[0]+1}-{grupo[-1]+1}: {erro}")

        for pos, pagina_real in enumerate(grupo):
            if pos >= len(resultados):
                continue
            dados = resultados[pos]
            if dados and dados.get("numero_lote"):
                chave = normalizar_lote(dados["numero_lote"])
                if chave:
                    dados["_pagina"] = pagina_real
                    indice[chave] = dados

        progresso.progress((g_idx + 1) / len(grupos), text=f"Indexando catálogo... grupo {g_idx + 1}/{len(grupos)}")

    progresso.empty()
    return indice, total, erros

def encontrar_no_indice(num_lote_oe, nome_animal_oe, indice):
    chave = normalizar_lote(num_lote_oe)
    if chave in indice:
        return indice[chave]

    if nome_animal_oe:
        melhor_match, melhor_score = None, 0.0
        for dados in indice.values():
            nome_cat = dados.get("nome_animal", "")
            if not nome_cat:
                continue
            score = difflib.SequenceMatcher(None, nome_animal_oe.upper(), nome_cat.upper()).ratio()
            if score > melhor_score:
                melhor_score, melhor_match = score, dados
        if melhor_match and melhor_score > 0.55:
            return melhor_match

    return None

# ==================== DEEPSEEK GERA ABERTURA/GATILHOS PRA VÁRIOS LOTES DE UMA VEZ ====================
def deepseek_processar_lotes_batch(lotes_info, _ds_keys):
    """lotes_info: lista de dicts {"lote":..., "ordem":..., "catalogo":...}.
    Retorna dict {lote: {abertura, encartes, gatilhos, observacao_destaque}}."""
    if not _ds_keys or not lotes_info:
        return {}, "sem chave ou sem lotes"

    prompt = f"""
    Você é um locutor de leilão de gado/cavalos experiente. Para CADA lote abaixo,
    gere um material de apoio pra cantar o lote na pista.

    LOTES (JSON):
    {json.dumps(lotes_info, ensure_ascii=False, indent=2)}

    Para cada lote gere:
    - "abertura": frase curta (máx. 25 palavras), animada, citando o nome do
      animal e algo que se destaque.
    - "encartes": lista com 3-4 dados importantes pra mostrar em tela
      (ex: CATEGORIA/RAÇA, PELAGEM, VENDEDOR, PESO/IDADE/STATUS).
    - "gatilhos": 3 gatilhos curtos de pista (frases de impacto).
    - "observacao_destaque": 1 frase resumindo algo relevante das observações
      (reprodução, treino, previsão de parto), ou "" se não houver nada.

    Retorne APENAS JSON:
    {{
      "resultados": [
        {{
          "lote": "01",
          "abertura": "...",
          "encartes": [{{"titulo": "CATEGORIA", "valor": "..."}}],
          "gatilhos": ["...", "...", "..."],
          "observacao_destaque": "..."
        }}
      ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    ultimo_erro = ""
    for api_key in _ds_keys:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            res_json = response.json()
            if response.status_code == 200 and 'choices' in res_json:
                dados = extrair_json(res_json['choices'][0]['message']['content'])
                if not dados or "resultados" not in dados:
                    ultimo_erro = "DeepSeek respondeu, mas não veio JSON válido"
                    continue
                mapa = {}
                for r in dados["resultados"]:
                    lt = r.get("lote")
                    if lt:
                        mapa[normalizar_lote(lt)] = r
                return mapa, None
            else:
                ultimo_erro = f"HTTP {response.status_code}: {res_json.get('error', res_json)}"
        except Exception as e:
            ultimo_erro = str(e)

    return {}, ultimo_erro

@st.cache_data(ttl=86400, show_spinner=False)
def preparar_todos_cruzamentos(lista_lotes, mapa_oe, indice_catalogo, _ds_keys, tamanho_lote):
    """Processa TODOS os lotes de uma vez, em lotes (batches), e cacheia o
    resultado inteiro. Depois disso, navegar entre lotes é só lookup em
    dicionário — nenhuma chamada de IA é feita."""
    resultado_final = {}
    erros = []

    lotes_com_catalogo = []
    for num_lote in lista_lotes:
        dados_ordem = mapa_oe.get(num_lote, {})
        dados_cat = encontrar_no_indice(num_lote, dados_ordem.get("nome_animal", ""), indice_catalogo)
        if dados_cat:
            lotes_com_catalogo.append({
                "lote": num_lote,
                "ordem": dados_ordem,
                "catalogo": {k: v for k, v in dados_cat.items() if k != "_pagina"}
            })

    if not lotes_com_catalogo or not _ds_keys:
        return resultado_final, ["nenhum lote casado com o catálogo, ou sem DEEPSEEK_API_KEY"]

    grupos = [lotes_com_catalogo[i:i + tamanho_lote] for i in range(0, len(lotes_com_catalogo), tamanho_lote)]

    progresso = st.progress(0, text="Gerando aberturas e gatilhos...")
    for g_idx, grupo in enumerate(grupos):
        mapa_resultado, erro = deepseek_processar_lotes_batch(grupo, _ds_keys)
        if erro:
            erros.append(f"Grupo lotes {[g['lote'] for g in grupo]}: {erro}")
        resultado_final.update(mapa_resultado)
        progresso.progress((g_idx + 1) / len(grupos), text=f"Gerando aberturas... grupo {g_idx + 1}/{len(grupos)}")
    progresso.empty()

    return resultado_final, erros

# ==================== CARD DE PEDIGREE ====================
def renderizar_pedigree(dados_catalogo):
    if not dados_catalogo:
        return
    pai, mae = dados_catalogo.get("pai", ""), dados_catalogo.get("mae", "")
    ap, apm = dados_catalogo.get("avo_paterno", ""), dados_catalogo.get("avo_paterna", "")
    am, amm = dados_catalogo.get("avo_materno", ""), dados_catalogo.get("avo_materna", "")

    if not any([pai, mae, ap, apm, am, amm]):
        return

    html = '<div class="pedigree-card"><table>'
    html += f'<tr><td><strong>PAI</strong></td><td>{pai or "-"}</td><td><strong>AVÔ PATERNO</strong></td><td>{ap or "-"}</td></tr>'
    html += f'<tr><td></td><td></td><td><strong>AVÓ PATERNA</strong></td><td>{apm or "-"}</td></tr>'
    html += f'<tr><td><strong>MÃE</strong></td><td>{mae or "-"}</td><td><strong>AVÔ MATERNO</strong></td><td>{am or "-"}</td></tr>'
    html += f'<tr><td></td><td></td><td><strong>AVÓ MATERNA</strong></td><td>{amm or "-"}</td></tr>'
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
        max_paginas_catalogo = st.number_input("Máx. de páginas do catálogo", min_value=1, max_value=300, value=60)
        tamanho_lote_paginas = st.number_input("Páginas por chamada (Claude)", min_value=1, max_value=8, value=BATCH_PAGINAS_PADRAO)
        tamanho_lote_cruzamento = st.number_input("Lotes por chamada (DeepSeek)", min_value=1, max_value=20, value=BATCH_LOTES_PADRAO)

        st.markdown("---")
        if st.button("🔄 Reprocessar tudo (limpar cache)", use_container_width=True):
            construir_indice_catalogo.clear()
            preparar_todos_cruzamentos.clear()
            deepseek_ler_ordem.clear()
            st.rerun()

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    file_bytes_cat = file_cat.getvalue() if file_cat else None

    texto_oe = processar_pdf_texto(file_bytes_oe)

    sequencia_oe, mapa_oe = [], {}
    if texto_oe and ds_keys:
        texto_oe_completo = "\n".join(texto_oe)
        with st.spinner("🤖 Lendo a O.E. (só na 1ª vez, depois fica em cache)..."):
            sequencia_oe, mapa_oe, erro_oe = deepseek_ler_ordem(texto_oe_completo, tuple(ds_keys))
        if erro_oe:
            st.error(f"Erro ao ler a O.E.: {erro_oe}")

    if not sequencia_oe:
        st.warning("Carregue a O.E. e configure o DeepSeek!")
        st.stop()

    # ---- índice do catálogo (imagem -> JSON), roda 1 vez e fica em cache ----
    indice_catalogo, total_paginas_cat, erros_indice = {}, 0, []
    if file_bytes_cat and ant_keys:
        indice_catalogo, total_paginas_cat, erros_indice = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), tuple(ant_keys),
            max_paginas_catalogo, tamanho_lote_paginas
        )
    elif file_bytes_cat and not ant_keys:
        st.warning("Catálogo carregado, mas falta ANTHROPIC_API_KEY pra indexar as páginas.")

    # ---- cruzamento de TODOS os lotes de uma vez, roda 1 vez e fica em cache ----
    dados_finais_todos, erros_cruzamento = {}, []
    if indice_catalogo and ds_keys:
        dados_finais_todos, erros_cruzamento = preparar_todos_cruzamentos(
            tuple(sequencia_oe), mapa_oe, indice_catalogo, tuple(ds_keys), tamanho_lote_cruzamento
        )

    with st.expander("🛠️ Status do processamento (debug)"):
        st.markdown(f'<div class="status-processamento">'
                     f'Lotes na O.E.: {len(sequencia_oe)}<br>'
                     f'Páginas do catálogo indexadas: {len(indice_catalogo)} de {total_paginas_cat}<br>'
                     f'Lotes com abertura/gatilhos gerados: {len(dados_finais_todos)}'
                     f'</div>', unsafe_allow_html=True)
        if erros_indice:
            st.error("Erros na indexação do catálogo:")
            for e in erros_indice:
                st.text(f"• {e}")
        if erros_cruzamento:
            st.error("Erros ao gerar aberturas/gatilhos:")
            for e in erros_cruzamento:
                st.text(f"• {e}")

    if modo_ordenacao == "ORDEM NUMÉRICA":
        lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x) or 0))
    else:
        lista_lotes = sequencia_oe.copy()

    if 'lote_idx' not in st.session_state:
        st.session_state.lote_idx = 0
    if st.session_state.lote_idx >= len(lista_lotes):
        st.session_state.lote_idx = 0

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

    # --- tudo abaixo é só LOOKUP, nenhuma chamada de IA acontece aqui ---
    dados_catalogo = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo)
    dados_finais = dados_finais_todos.get(normalizar_lote(num_lote))
    pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1

    if file_bytes_cat and indice_catalogo and pagina_detectada < 0:
        st.warning(f"⚠️ Lote {num_lote} não encontrado automaticamente no catálogo. Escolha a página manualmente:")
        pagina_manual = st.number_input(
            "Página do catálogo:", min_value=1, max_value=max(1, total_paginas_cat),
            value=1, key=f"pag_{num_lote}"
        )
        pagina_detectada = pagina_manual - 1

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        if dados_finais and dados_finais.get("abertura"):
            st.markdown(f'<div class="abertura-box">🎙️ "{dados_finais["abertura"]}"</div>', unsafe_allow_html=True)
        if dados_finais and dados_finais.get("observacao_destaque"):
            st.markdown(
                f'<div class="ai-consideracoes-box"><h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 OBSERVAÇÃO</h3>'
                f'<div>{dados_finais["observacao_destaque"]}</div></div>', unsafe_allow_html=True
            )

        if file_bytes_cat and pagina_detectada >= 0:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}</div>', unsafe_allow_html=True)
            img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada, resolucao=150, qualidade=85)
            if img_bytes:
                st.image(img_bytes, use_container_width=True)

        if dados_catalogo:
            with st.expander("📖 Dados extraídos do catálogo (bruto)"):
                st.json({k: v for k, v in dados_catalogo.items() if k != "_pagina"})

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
                with cols[idx % len(cols)]:
                    st.markdown(f'<div class="animal-info"><strong>{enc["titulo"]}:</strong><br>{enc["valor"]}</div>', unsafe_allow_html=True)
        elif dados_catalogo:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f'<div class="animal-info"><strong>RAÇA:</strong><br>{dados_catalogo.get("raca", "-")}<br><br><strong>SEXO:</strong><br>{dados_catalogo.get("sexo", "-")}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PELAGEM:</strong><br>{dados_catalogo.get("pelagem", "-")}<br><br><strong>NASCIMENTO:</strong><br>{dados_catalogo.get("nascimento", "-")}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="animal-info"><strong>REGISTRO:</strong><br>{dados_catalogo.get("registro", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_catalogo.get("vendedor", "-")}</div>', unsafe_allow_html=True)
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca", "-")}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso", "-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade", "-")}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)

        if dados_catalogo:
            st.markdown("### 🧬 GENEALOGIA")
            renderizar_pedigree(dados_catalogo)
            if dados_catalogo.get("observacoes"):
                st.markdown(f'<span class="status-badge">📌 {dados_catalogo["observacoes"]}</span>', unsafe_allow_html=True)

        st.markdown("### 🎤 GATILHOS DE PISTA")
        if dados_finais and dados_finais.get("gatilhos"):
            for g in dados_finais["gatilhos"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)
        else:
            for g in ["ANIMAL SELECIONADO: Qualidade superior!",
                      "PROCEDÊNCIA GARANTIDA: Origem comprovada!",
                      "OPORTUNIDADE ÚNICA: Preço imperdível!"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()        background: #16A34A;
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
        return None, "sem imagem da página"
    if not ant_keys:
        return None, "ANTHROPIC_API_KEY não configurada"

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
        "model": "claude-sonnet-5",
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

# ==================== CONSTRÓI ÍNDICE COMPLETO DO CATÁLOGO ====================
@st.cache_data(ttl=7200, show_spinner=False)
def construir_indice_catalogo(file_bytes_cat, hash_arquivo, ant_keys, max_paginas=60):
    """Percorre todas as páginas do catálogo (imagem), lê cada uma com o Claude
    e monta um dicionário {numero_lote_normalizado: dados}. Roda uma vez por
    arquivo (cacheado)."""
    indice = {}
    total = min(contar_paginas_pdf(file_bytes_cat), max_paginas)
    if total == 0 or not ant_keys:
        return indice, total

    progresso = st.progress(0, text="Indexando catálogo (lendo imagens com IA)...")
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
    """Tenta casar o lote da O.E. com o índice do catálogo: primeiro por número
    de lote, depois por similaridade de nome."""
    chave = normalizar_lote(num_lote_oe)
    if chave in indice:
        return indice[chave], -1

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
            return melhor_match, -1

    return None, -1

# ==================== DEEPSEEK CRUZA E GERA APRESENTAÇÃO ====================
def deepseek_cruzar(num_lote, dados_ordem, dados_catalogo, ds_keys):
    if not ds_keys:
        return None

    prompt = f"""
    Você é um locutor de leilão de gado/cavalos experiente. Cruze as informações
    do LOTE {num_lote} abaixo e gere um material de apoio pra cantar o lote.

    DADOS DA ORDEM DE ENTRADA:
    {json.dumps(dados_ordem, ensure_ascii=False, indent=2)}

    DADOS DO CATÁLOGO:
    {json.dumps(dados_catalogo, ensure_ascii=False, indent=2)}

    Gere:
    1. "abertura": UMA frase curta (máx. 25 palavras), animada, pra abrir o lote
       na pista — cite o nome do animal e algo que se destaque (genealogia forte,
       treino, categoria).
    2. "encartes": lista com os dados mais importantes pra mostrar em tela
       (CATEGORIA/RAÇA, PELAGEM, VENDEDOR, e outro campo relevante que existir
       como PESO, IDADE ou STATUS).
    3. "gatilhos": 3 gatilhos curtos de pista (frases de impacto, não repetir a
       abertura).
    4. "observacao_destaque": se houver algo relevante nas observações do
       catálogo (reprodução, treino, previsão de parto), resuma em 1 frase.

    Retorne APENAS JSON:
    {{
        "abertura": "...",
        "encartes": [
            {{"titulo": "CATEGORIA", "valor": "..."}},
            {{"titulo": "PELAGEM", "valor": "..."}},
            {{"titulo": "VENDEDOR", "valor": "..."}}
        ],
        "gatilhos": ["...", "...", "..."],
        "observacao_destaque": "..."
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

# ==================== CARD DE PEDIGREE ====================
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

    # Índice completo do catálogo (imagem -> JSON por lote), construído uma vez
    indice_catalogo = {}
    total_paginas_cat = 0
    if file_bytes_cat and ant_keys:
        indice_catalogo, total_paginas_cat = construir_indice_catalogo(
            file_bytes_cat, hash_bytes(file_bytes_cat), ant_keys, max_paginas_catalogo
        )
    elif file_bytes_cat and not ant_keys:
        st.warning("Catálogo carregado, mas falta a chave da Anthropic (ANTHROPIC_API_KEY) pra indexar as páginas.")

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

    # Casa o lote da O.E. com o índice do catálogo
    dados_catalogo, _ = encontrar_no_indice(num_lote, dados_lote.get("nome_animal", ""), indice_catalogo)
    pagina_detectada = dados_catalogo.get("_pagina", -1) if dados_catalogo else -1

    if file_bytes_cat and indice_catalogo and pagina_detectada < 0:
        st.warning(f"⚠️ Lote {num_lote} não encontrado automaticamente no catálogo. Escolha a página manualmente:")
        pagina_manual = st.number_input(
            "Página do catálogo:", min_value=1, max_value=max(1, total_paginas_cat),
            value=1, key=f"pag_{num_lote}"
        )
        pagina_detectada = pagina_manual - 1

    dados_finais = None
    if dados_catalogo and ds_keys:
        with st.spinner("🔄 Cruzando informações..."):
            dados_finais = deepseek_cruzar(num_lote, dados_lote, dados_catalogo, ds_keys)

    # ==================== LAYOUT ====================
    col_esquerda, col_direita = st.columns([1, 1])

    # ---------- COLUNA ESQUERDA: catálogo + IA ----------
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
            img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada, resolucao=150, qualidade=85)
            if img_bytes:
                st.image(img_bytes, use_container_width=True)

        if dados_catalogo:
            with st.expander("📖 Dados extraídos do catálogo (bruto)"):
                st.json(dados_catalogo)

    # ---------- COLUNA DIREITA: lote em cards ----------
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

        # ---- Encartes (cards) ----
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

        # ---- Pedigree ----
        if dados_catalogo:
            st.markdown("### 🧬 GENEALOGIA")
            renderizar_pedigree(dados_catalogo)
            if dados_catalogo.get("observacoes"):
                st.markdown(
                    f'<span class="status-badge">📌 {dados_catalogo["observacoes"]}</span>',
                    unsafe_allow_html=True
                )

        # ---- Gatilhos de pista ----
        st.markdown("### 🎤 GATILHOS DE PISTA")
        if dados_finais and dados_finais.get("gatilhos"):
            for g in dados_finais["gatilhos"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)
        else:
            gatilhos_genericos = [
                "ANIMAL SELECIONADO: Qualidade superior!",
                "PROCEDÊNCIA GARANTIDA: Origem comprovada!",
                "OPORTUNIDADE ÚNICA: Preço imperdível!"
            ]
            for g in gatilhos_genericos:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()
