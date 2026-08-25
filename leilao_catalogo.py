import streamlit as st
import pdfplumber
import re
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

# ==================== DEEPSEEK LÊ A O.E. ====================
def deepseek_ler_ordem(texto_oe_completo, ds_keys):
    if not ds_keys:
        return [], {}
    
    prompt = f"""
    Você está lendo uma ORDEM DE ENTRADA (O.E.) de leilão.
    
    TEXTO DA O.E.:
    {texto_oe_completo[:5000]}
    
    Extraia TODOS os lotes. Cada linha segue o padrão:
    [posição] [lote] [qtd] [idade] [peso] [categoria] [produto/animal] [vendedor]
    
    Exemplo:
    "1º 16 1 15m 514Kg Novilha 50% de: TIANAH FIV DO HEJ Nelore HEJ"
    
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
        except:
            continue
    
    return [], {}

# ==================== DEEPSEEK ENCONTRA PÁGINA ====================
def deepseek_encontrar_pagina(texto_cat_completo, num_lote, dados_lote, ds_keys):
    if not ds_keys:
        return -1
    
    prompt = f"""
    Você tem um catálogo de leilão dividido em páginas.
    
    DADOS DO LOTE:
    Lote: {num_lote}
    Nome: {dados_lote.get('nome_animal', '')}
    Categoria: {dados_lote.get('categoria', '')}
    
    CATÁLOGO:
    """
    
    for idx, pagina in enumerate(texto_cat_completo[:30]):  # Máximo 30 páginas
        prompt += f"\n=== PÁGINA {idx + 1} ===\n{pagina[:300]}\n"
    
    prompt += """
    
    Em qual página está o lote? Retorne JSON:
    {"pagina": numero_da_pagina}
    
    Se não encontrar, retorne: {"pagina": -1}
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
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
                dados = json.loads(content)
                pagina = dados.get("pagina", -1)
                if pagina > 0:
                    return pagina - 1
        except:
            continue
    
    return -1

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
                    "text": """Esta é uma página do CATÁLOGO do leilão.
                    Transcreva TODO o texto visível:
                    - Nome do animal
                    - Número do lote
                    - Raça/Espécie
                    - Categoria
                    - Pelagem
                    - PAI, MÃE, AVÔS (genealogia completa)
                    - Vendedor/Fazenda
                    - Observações (prenhez, inseminação)
                    
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

# ==================== DEEPSEEK CRUZA ====================
def deepseek_cruzar(num_lote, dados_ordem, texto_catalogo, ds_keys):
    if not ds_keys:
        return None
    
    prompt = f"""
    Cruze as informações do LOTE {num_lote}:
    
    DADOS DA ORDEM (JSON):
    {json.dumps(dados_ordem, ensure_ascii=False, indent=2)}
    
    TEXTO DO CATÁLOGO (Claude):
    {texto_catalogo[:3000]}
    
    Crie:
    1. "apresentacao": Frase de abertura agressiva para cantar o lote
    2. "encartes": Informações importantes (CATEGORIA, PELAGEM, PESO, VENDEDOR)
    3. "gatilhos": 3-4 gatilhos de pista para manter ritmo
    4. "genetica_pai" e "genetica_mae": Se encontradas no catálogo
    
    Retorne JSON:
    {{
        "nome_animal": "...",
        "especie_emoji": "🐴/🐂/🐄/🫏",
        "apresentacao": "...",
        "encartes": [
            {{"titulo": "CATEGORIA", "valor": "..."}},
            {{"titulo": "PELAGEM", "valor": "..."}},
            {{"titulo": "PESO", "valor": "..."}},
            {{"titulo": "VENDEDOR", "valor": "..."}}
        ],
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
                return json.loads(res_json['choices'][0]['message']['content'])
        except:
            continue
    
    return None

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
    
    texto_oe = processar_pdf(file_bytes_oe)
    texto_cat = processar_pdf(file_bytes_cat)
    
    sequencia_oe = []
    mapa_oe = {}
    
    if texto_oe and ds_keys:
        with st.spinner("🤖 DeepSeek lendo a O.E..."):
            texto_oe_completo = "\n".join(texto_oe)
            sequencia_oe, mapa_oe = deepseek_ler_ordem(texto_oe_completo, ds_keys)
    
    if not sequencia_oe:
        st.warning("Carregue a O.E. e configure o DeepSeek!")
        st.stop()
    
    if modo_ordenacao == "ORDEM NUMÉRICA":
        lista_lotes = sorted(sequencia_oe, key=lambda x: int(re.sub(r"\D", "", x)))
    else:
        lista_lotes = sequencia_oe.copy()
    
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
    
    # Detecta página do catálogo
    pagina_detectada = -1
    texto_claude = ""
    dados_finais = None
    
    if texto_cat and file_bytes_cat and ds_keys:
        with st.spinner("🔍 Localizando página no catálogo..."):
            pagina_detectada = deepseek_encontrar_pagina(texto_cat, num_lote, dados_lote, ds_keys)
        
        if pagina_detectada < 0:
            st.warning(f"⚠️ Página do Lote {num_lote} não encontrada. Digite a página:")
            total_paginas = len(texto_cat)
            pagina_manual = st.number_input(
                "Página do catálogo:",
                min_value=1,
                max_value=max(1, total_paginas),
                value=1,
                key=f"pag_{num_lote}"
            )
            pagina_detectada = pagina_manual - 1
        
        img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
        
        if img_bytes and ant_keys:
            with st.spinner("🤖 Claude lendo catálogo..."):
                texto_claude = claude_ler_catalogo(img_bytes, ant_keys)
        
        if texto_claude and ds_keys:
            with st.spinner("🔄 Cruzando informações..."):
                dados_finais = deepseek_cruzar(num_lote, dados_lote, texto_claude, ds_keys)
    
    # ==================== LAYOUT: ESQUERDA = CATÁLOGO + IA | DIREITA = LOTE ====================
    col_esquerda, col_direita = st.columns([1, 1])
    
    # ==================== COLUNA ESQUERDA ====================
    with col_esquerda:
        # Considerações da IA (acima do catálogo)
        if dados_finais:
            canta_html = f"📌 **APRESENTAÇÃO:** {dados_finais.get('apresentacao', '')}<br><br>"
            if dados_finais.get('genetica_pai'):
                canta_html += f"🧬 **GENÉTICA DO PAI:** {dados_finais.get('genetica_pai')}<br><br>"
            if dados_finais.get('genetica_mae'):
                canta_html += f"🧬 **GENÉTICA DA MÃE:** {dados_finais.get('genetica_mae')}<br><br>"
            if dados_finais.get('reproducao'):
                canta_html += f"💉 **REPRODUÇÃO:** {dados_finais.get('reproducao')}"
            
            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DA IA</h3>
                <div>{canta_html}</div>
            </div>
            ''', unsafe_allow_html=True)
        
        # Catálogo
        if file_bytes_cat and pagina_detectada >= 0:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO - PÁGINA {pagina_detectada + 1}</div>', unsafe_allow_html=True)
            img_bytes = obter_imagem_bytes_pagina(file_bytes_cat, pagina_detectada)
            if img_bytes:
                st.image(img_bytes, use_container_width=True)
            
            if texto_claude:
                with st.expander("📖 Texto transcrito pelo Claude"):
                    st.text(texto_claude[:2000])
    
    # ==================== COLUNA DIREITA ====================
    with col_direita:
        # Abertura do lote
        st.markdown(f'<div class="lote-destaque">LOTE {num_lote}<br><span style="font-size: 24px;">{dados_lote.get("posicao", "")}</span></div>', unsafe_allow_html=True)
        
        if dados_lote.get("porcentagem_venda"):
            st.markdown(f'<div class="banner-venda">💎 VENDA DE {dados_lote["porcentagem_venda"]}</div>', unsafe_allow_html=True)
        
        if dados_lote.get("info_reproducao"):
            st.markdown(f'<div class="banner-reproducao">{dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
        
        if dados_lote.get("nome_animal"):
            st.markdown(f'<div class="nome-animal-box">🐂 {dados_lote["nome_animal"]}</div>', unsafe_allow_html=True)
        
        # Informações do lote (encartes)
        st.markdown("### 📋 INFORMAÇÕES DO LOTE")
        
        if dados_finais and dados_finais.get("encartes"):
            # Usa encartes da IA
            num_encartes = len([e for e in dados_finais["encartes"] if e.get("valor")])
            cols = st.columns(min(3, max(1, num_encartes)))
            
            for idx, enc in enumerate(dados_finais["encartes"]):
                if enc.get("valor"):
                    col = cols[idx % len(cols)]
                    with col:
                        st.markdown(f'<div class="animal-info"><strong>{enc["titulo"]}:</strong><br>{enc["valor"]}</div>', unsafe_allow_html=True)
        else:
            # Fallback: usa dados da O.E.
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria", "-")}<br><br><strong>RAÇA:</strong><br>{dados_lote.get("raca", "-")}</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso", "-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade", "-")}</div>', unsafe_allow_html=True)
            
            with col3:
                st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd", "-")}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor", "-")}</div>', unsafe_allow_html=True)
        
        # Gatilhos de pista (abaixo das informações)
        st.markdown("### 🎤 GATILHOS DE PISTA")
        
        if dados_finais and dados_finais.get("gatilhos"):
            for g in dados_finais["gatilhos"]:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)
        else:
            # Fallback: gatilhos genéricos
            gatilhos_genericos = [
                "ANIMAL SELECIONADO: Qualidade superior!",
                "PROCEDÊNCIA GARANTIDA: Origem comprovada!",
                "OPORTUNIDADE ÚNICA: Preço imperdível!"
            ]
            for g in gatilhos_genericos:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    run()
