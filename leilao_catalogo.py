import streamlit as st
import pdfplumber
import re
import os
import requests
import json
import time
import concurrent.futures
from io import BytesIO

def obter_api_keys():
    chaves_brutas = []
    try:
        for secret_name in ["DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"]:
            if secret_name in st.secrets:
                val = st.secrets[secret_name]
                if isinstance(val, (list, tuple)):
                    chaves_brutas.extend(val)
                elif isinstance(val, str):
                    chaves_brutas.extend(val.split(","))
    except Exception:
        pass

    if not chaves_brutas:
        env_val = os.environ.get("DEEPSEEK_API_KEYS") or os.environ.get("DEEPSEEK_API_KEY") or ""
        if env_val:
            chaves_brutas.extend(env_val.split(","))

    chaves_limpas = []
    for item in chaves_brutas:
        s = str(item).strip()
        s_clean = re.sub(r"[\[\]'\" \n\r\t]", "", s)
        if s_clean and s_clean not in chaves_limpas:
            chaves_limpas.append(s_clean)

    return chaves_limpas

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

@st.cache_data(ttl=7200, show_spinner=False)
def extrair_dados_oe_pdf(file_bytes):
    sequencia = []
    dados_por_lote = {}

    if not file_bytes:
        return sequencia, dados_por_lote

    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                table_success = False

                if tables:
                    for table in tables:
                        headers_atuais = []
                        col_map = {}
                        
                        for row in table:
                            if not row:
                                continue
                            clean_row = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
                            
                            if not any(clean_row) or "PROGRAMA" in " ".join(clean_row).upper():
                                continue

                            row_str_upper = " ".join(clean_row).upper()

                            if any(h in row_str_upper for h in ['LT', 'LOTE', 'CATEGORIA', 'PRODUTO', 'ANIMAL', 'VENDEDOR']):
                                headers_atuais = [c if c else f"COLUNA_{i+1}" for i, c in enumerate(clean_row)]
                                col_map = {}
                                for idx, cell in enumerate(clean_row):
                                    c_u = cell.upper()
                                    if re.search(r"\bO\.?E\.?\b", c_u) or "ORDEM" in c_u or "POSIÇ" in c_u:
                                        col_map["oe"] = idx
                                    elif re.search(r"\b(LT|LOTE)\b", c_u):
                                        col_map["lote"] = idx
                                    elif "QTD" in c_u or "QUANT" in c_u:
                                        col_map["qtd"] = idx
                                    elif "IDADE" in c_u:
                                        col_map["idade"] = idx
                                    elif "PESO" in c_u:
                                        col_map["peso"] = idx
                                    elif "CATEGORIA" in c_u:
                                        col_map["categoria"] = idx
                                    elif "PELAGEM" in c_u:
                                        col_map["pelagem"] = idx
                                    elif "PRODUTO" in c_u or "ANIMAL" in c_u:
                                        col_map["produto"] = idx
                                    elif "VENDEDOR" in c_u or "PROPRIET" in c_u:
                                        col_map["vendedor"] = idx
                                continue

                            lt_col = col_map.get("lote", 1 if len(clean_row) > 1 else 0)
                            raw_lt = clean_row[lt_col] if lt_col < len(clean_row) else ""
                            clean_lt = re.sub(r"\D", "", raw_lt)

                            if not clean_lt:
                                for idx in [1, 0, 2]:
                                    if idx < len(clean_row):
                                        val = re.sub(r"\D", "", clean_row[idx])
                                        if val and 1 <= int(val) <= 999:
                                            clean_lt = val
                                            break

                            if clean_lt and clean_lt.isdigit():
                                numero_lote = int(clean_lt)
                                lt_num = f"{numero_lote:02d}"

                                oe_col = col_map.get("oe", 0)
                                raw_oe = clean_row[oe_col] if oe_col < len(clean_row) else ""
                                clean_oe = re.sub(r"\D", "", raw_oe)
                                posicao_fmt = f"{int(clean_oe)}º A ENTRAR" if clean_oe else (raw_oe if raw_oe else f"{len(sequencia)+1}º A ENTRAR")

                                pares_rotulados = []
                                for idx, val in enumerate(clean_row):
                                    if val:
                                        nome_col = headers_atuais[idx] if idx < len(headers_atuais) and headers_atuais[idx] else f"CAMPO_{idx+1}"
                                        pares_rotulados.append(f"{nome_col}: {val}")
                                linha_contextualizada = " | ".join(pares_rotulados)

                                def get_val(key):
                                    return clean_row[col_map[key]] if key in col_map and col_map[key] < len(clean_row) else ""

                                qtd = get_val("qtd")
                                idade = get_val("idade")
                                peso = get_val("peso")
                                categoria = get_val("categoria")
                                pelagem = get_val("pelagem")
                                produto = get_val("produto")
                                vendedor = get_val("vendedor")

                                if not produto:
                                    if len(clean_row) == 6:
                                        categoria = categoria or clean_row[2]
                                        pelagem = pelagem or clean_row[3]
                                        produto = clean_row[4]
                                        vendedor = vendedor or clean_row[5]
                                    elif len(clean_row) == 8:
                                        produto = clean_row[6]
                                        vendedor = vendedor or clean_row[7]

                                nome_animal = produto
                                porcentagem_venda = ""
                                m_perc = re.search(r"(\d+%)\s*de:\s*(.+)", produto, re.IGNORECASE)
                                if m_perc:
                                    porcentagem_venda = m_perc.group(1)
                                    nome_animal = m_perc.group(2).strip()

                                info_repro, tipo_repro = "", ""
                                m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", f"{categoria} {produto}", re.IGNORECASE)
                                if m_repro:
                                    info_repro = m_repro.group(0).strip()
                                    txt_low = info_repro.lower()
                                    if "parida" in txt_low: tipo_repro = "parida"
                                    elif "prenh" in txt_low: tipo_repro = "prenhez"
                                    elif "inseminada" in txt_low: tipo_repro = "inseminacao"

                                if lt_num not in sequencia:
                                    sequencia.append(lt_num)

                                dados_por_lote[lt_num] = {
                                    "lote": lt_num,
                                    "posicao": posicao_fmt,
                                    "qtd": qtd,
                                    "idade": idade,
                                    "peso": peso,
                                    "categoria": categoria,
                                    "pelagem": pelagem,
                                    "produto": produto,
                                    "nome_animal": nome_animal,
                                    "porcentagem_venda": porcentagem_venda,
                                    "vendedor": vendedor,
                                    "info_reproducao": info_repro,
                                    "tipo_reproducao": tipo_repro,
                                    "linha_contextualizada": linha_contextualizada,
                                    "linha_completa": " | ".join([c for c in clean_row if c])
                                }
                                table_success = True

                if not table_success:
                    texto = page.extract_text(layout=True) or page.extract_text() or ""
                    if texto:
                        for linha in texto.split('\n'):
                            linha_limpa = linha.strip()
                            if not linha_limpa or "PROGRAMA" in linha_limpa.upper():
                                continue

                            m_pos = re.match(r"^(\d{1,3})\s*[º°]?\s+(\d{1,3})\s+", linha_limpa)
                            if m_pos:
                                pos_num = int(m_pos.group(1))
                                num_lote = int(m_pos.group(2))
                                if 1 <= num_lote <= 999:
                                    lt_num = f"{num_lote:02d}"
                                    if lt_num not in sequencia:
                                        sequencia.append(lt_num)
                                    restante = linha_limpa[m_pos.end():].strip().split()
                                    
                                    dados_por_lote[lt_num] = {
                                        "lote": lt_num,
                                        "posicao": f"{pos_num}º A ENTRAR",
                                        "qtd": restante[0] if len(restante)>0 else "",
                                        "idade": restante[1] if len(restante)>1 else "",
                                        "peso": restante[2] if len(restante)>2 else "",
                                        "categoria": restante[3] if len(restante)>3 else "",
                                        "pelagem": "",
                                        "produto": " ".join(restante[4:-1]) if len(restante)>5 else (restante[4] if len(restante)>4 else ""),
                                        "vendedor": restante[-1] if len(restante)>4 else "",
                                        "info_reproducao": "", "tipo_reproducao": "",
                                        "nome_animal": " ".join(restante[4:-1]) if len(restante)>5 else "",
                                        "porcentagem_venda": "", 
                                        "linha_contextualizada": f"LINHA COMPLETA: {linha_limpa}",
                                        "linha_completa": linha_limpa
                                    }
    except Exception as e:
        st.error(f"Erro ao extrair PDF: {str(e)}")

    return sequencia, dados_por_lote

@st.cache_data(show_spinner=False)
def analisar_lote_catalogo_deepseek(num_lote, dados_lote, texto_pagina_cat, api_keys):
    if not api_keys:
        return None, "⚠️ Nenhuma chave DEEPSEEK_API_KEY encontrada nos Secrets do Streamlit."

    prompt_system = """Você é um Leiloeiro Rural e Zootecnista de Elite no Brasil.
    Sua missão é ler as informações da Ordem de Entrada e do Catálogo de um Lote e organizar os dados visuais para o leiloeiro na pista."""

    prompt_user = f"""
    Analise o LOTE {num_lote}:
    📍 DADOS DA ORDEM ROTULADOS (CHAVE: VALOR):
    {dados_lote.get('linha_contextualizada', dados_lote.get('linha_completa', ''))}

    TEXTO DO CATÁLOGO DO LOTE:
    {texto_pagina_cat[:2000] if texto_pagina_cat else 'N/A'}

    INSTRUÇÕES CRÍTICAS DE LEILOEIRO:
    1. Crie uma lista de "ENCARTES" (cartões de informação) prioritários para aparecer na tela.
    2. Coloque APENAS o que existir com valor preenchido na Ordem ou no Catálogo e que agregue valor ao lote (ex: CATEGORIA, PELAGEM, PESO, IDADE, VENDEDOR, QTD, REGISTRO/RG, AVALIAÇÃO/iABCZ/IQG).
    3. NUNCA invente peso ou idade se o campo não existir nos textos.
    4. Crie uma canta de venda agressiva ressaltando linhagem materna e paterna do catálogo.

    Retorne EXATAMENTE um JSON válido com a seguinte estrutura:
    {{
        "posicao_entrada": "{dados_lote.get('posicao')}",
        "nome_animal": "{dados_lote.get('nome_animal') or dados_lote.get('produto', '')}",
        "porcentagem_venda": "{dados_lote.get('porcentagem_venda', '')}",
        "status_reproducao": "{dados_lote.get('info_reproducao', '')}",
        "tipo_reproducao": "{dados_lote.get('tipo_reproducao', '')}",
        "encartes": [
            {{"titulo": "CATEGORIA", "valor": "..."}},
            {{"titulo": "PELAGEM", "valor": "..."}},
            {{"titulo": "PESO/IDADE", "valor": "..."}},
            {{"titulo": "VENDEDOR", "valor": "..."}}
        ],
        "apresentacao": "Frase agressiva de canta...",
        "genetica_pai": "Linhagem paterna identificada no catálogo ou vazio",
        "genetica_mae": "Linhagem materna identificada no catálogo ou vazio",
        "reproducao_detalhe": "Detalhe da prenhez ou acasalamento do catálogo ou vazio",
        "gatilhos": [
            "Gatilho curto 1",
            "Gatilho curto 2",
            "Gatilho curto 3"
        ]
    }}
    """

    url = "https://api.deepseek.com/chat/completions"
    erros = []

    for api_key in api_keys:
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
            "temperature": 0.2
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
                dados_ia = json.loads(content)
                return dados_ia, ""
            
            msg_erro = res_json.get('error', {}).get('message', response.text)
            erros.append(f"Chave ...{api_key[-6:]}: {msg_erro}")

            if response.status_code == 429:
                time.sleep(1)
                continue
                
        except Exception as e:
            erros.append(f"Erro na conexão: {str(e)}")
            continue

    detalhe_erro = erros[-1] if erros else "Erro de comunicação com a API DeepSeek."
    return None, f"⚠️ Erro ao consultar o DeepSeek. Detalhe: {detalhe_erro}"

def precarregar_proximos_lotes_cat(idx_atual, lista_lotes, mapa_oe, texto_cat, api_keys):
    proximos_indices = [idx_atual + i for i in range(1, 4) if (idx_atual + i) < len(lista_lotes)]
    if not proximos_indices or not api_keys:
        return
        
    def _carregar(i):
        num_lt = lista_lotes[i]
        dados_lt = mapa_oe.get(num_lt, {})
        _, txt_pag = encontrar_pagina_catalogo(tuple(texto_cat), num_lt) if texto_cat else (-1, "")
        analisar_lote_catalogo_deepseek(num_lt, dados_lt, txt_pag, api_keys)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(_carregar, proximos_indices)

def run():
    css_code = """
    <style>
        .lote-destaque { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px; border-radius: 18px; text-align: center; font-size: 52px; font-weight: bold; margin-bottom: 12px; }
        .ordem-indicador { background: #16A34A; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin: 8px 0; font-size: 20px; }
        .banner-parida { background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #A855F7; }
        .banner-prenhez { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #EF4444; }
        .banner-inseminacao { background: linear-gradient(135deg, #D97706 0%, #92400E 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .banner-venda { background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%); color: #000000 !important; padding: 16px; border-radius: 14px; margin-bottom: 12px; font-size: 24px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .animal-info { background: #1E293B; color: white; padding: 15px; border-radius: 12px; margin: 5px 0; border: 1px solid #334155; min-height: 90px; }
        .nome-animal-box { background: #0284C7; color: white; padding: 14px; border-radius: 12px; margin-bottom: 12px; font-size: 22px; font-weight: bold; text-align: center; }
        .ai-consideracoes-box { background-color: #1E1B4B !important; padding: 20px; border-radius: 15px; margin-top: 15px; border-left: 8px solid #818CF8; }
        .ai-consideracoes-box, .ai-consideracoes-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.6 !important; }
        .oe-dados-box { background-color: #0F172A !important; padding: 20px; border-radius: 15px; margin-top: 15px; border-left: 8px solid #34D399; }
        .oe-dados-box, .oe-dados-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.8 !important; }
        .gatilho-card { background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%); color: white; padding: 14px; border-radius: 12px; font-size: 18px; margin: 6px 0; font-weight: bold; }
        .gatilho-ia-card { background: linear-gradient(135deg, #059669 0%, #047857 100%); color: white !important; padding: 16px; border-radius: 14px; font-size: 19px !important; margin: 8px 0; font-weight: bold !important; border-left: 6px solid #34D399; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
        .catalogo-header { background: #F59E0B; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 18px; }
    </style>
    """
    st.markdown(css_code, unsafe_allow_html=True)

    api_keys = obter_api_keys()

    with st.sidebar:
        st.header("Arquivos - Modo Catálogo")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe_cat")
        file_cat = st.file_uploader("Catálogo do Leilão (PDF)", type="pdf", key="cat_cat")
        st.markdown("---")
        modo_ordenacao = st.radio("Escolha a ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0, key="ordem_cat")
        mostrar_preview = st.checkbox("MOSTRAR PREVIEW VISUAL DO CATÁLOGO", value=True)

    file_bytes_oe = file_oe.getvalue() if file_oe else None
    texto_cat = processar_pdf(file_cat.getvalue()) if file_cat else []

    sequencia_oe, mapa_oe = extrair_dados_oe_pdf(file_bytes_oe)

    if sequencia_oe:
        lista_lotes = sequencia_oe.copy() if modo_ordenacao == "ORDEM DE ENTRADA" else sorted(sequencia_oe, key=lambda x: int(x))
        ordem_atual = modo_ordenacao
    else:
        lista_lotes = []
        ordem_atual = "NENHUM LOTE ENCONTRADO"

    if 'lote_idx_cat' not in st.session_state:
        st.session_state.lote_idx_cat = 0

    if not lista_lotes:
        st.warning("Carregue a Ordem de Entrada e o Catálogo em PDF no menu lateral para começar!")
        st.stop()

    if st.session_state.lote_idx_cat >= len(lista_lotes):
        st.session_state.lote_idx_cat = 0

    ordem_texto = f"{ordem_atual} | Lote {st.session_state.lote_idx_cat + 1} de {len(lista_lotes)}"
    st.markdown(f'<div class="ordem-indicador">{ordem_texto}</div>', unsafe_allow_html=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("ANTERIOR", use_container_width=True, key="prev_cat"):
            st.session_state.lote_idx_cat = max(0, st.session_state.lote_idx_cat - 1)
            st.rerun()

    with col_next:
        if st.button("PRÓXIMO", use_container_width=True, key="next_cat"):
            st.session_state.lote_idx_cat = min(len(lista_lotes) - 1, st.session_state.lote_idx_cat + 1)
            st.rerun()

    lote_selecionado = st.selectbox("Ir para o lote:", options=lista_lotes, index=st.session_state.lote_idx_cat, key="sel_cat")
    st.session_state.lote_idx_cat = lista_lotes.index(lote_selecionado)

    num_lote = lista_lotes[st.session_state.lote_idx_cat]
    dados_lote_oe = mapa_oe.get(num_lote, {})

    pagina_catalogo, texto_pagina_catalogo = encontrar_pagina_catalogo(tuple(texto_cat), num_lote) if texto_cat else (-1, "")
    img_pagina_bytes = obter_imagem_bytes_pagina(file_cat.getvalue(), pagina_catalogo) if (file_cat and pagina_catalogo >= 0) else None

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        with st.spinner("🤖 Leiloeiro IA cruzando Ordem + Catálogo..."):
            dados_ia, erro_ia = analisar_lote_catalogo_deepseek(num_lote, dados_lote_oe, texto_pagina_catalogo, api_keys)

        if dados_ia:
            lote_texto = f"LOTE {num_lote}"
            posicao_texto = dados_ia.get("posicao_entrada", dados_lote_oe.get("posicao", f"{st.session_state.lote_idx_cat + 1}º A ENTRAR"))
            st.markdown(f'<div class="lote-destaque">{lote_texto}<br><span style="font-size: 24px;">{posicao_texto}</span></div>', unsafe_allow_html=True)
            
            if dados_ia.get("porcentagem_venda"):
                st.markdown(f'<div class="banner-venda">💎 OFERTA DE {dados_ia["porcentagem_venda"]} DO ANIMAL</div>', unsafe_allow_html=True)
            
            if dados_ia.get("status_reproducao"):
                tipo_rep = dados_ia.get("tipo_reproducao", "").lower()
                if "parida" in tipo_rep:
                    st.markdown(f'<div class="banner-parida">🍼 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)
                elif "prenh" in tipo_rep:
                    st.markdown(f'<div class="banner-prenhez">🤰 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="banner-inseminacao">💉 {dados_ia["status_reproducao"]}</div>', unsafe_allow_html=True)

            if dados_ia.get("nome_animal"):
                st.markdown(f'<div class="nome-animal-box">🐂 {dados_ia["nome_animal"]}</div>', unsafe_allow_html=True)

            encartes = [e for e in dados_ia.get("encartes", []) if e.get("valor") and str(e.get("valor")).strip() not in ["-", "N/A", ""]]
            if encartes:
                num_encartes = len(encartes)
                cols_count = min(3, max(1, num_encartes))
                cols = st.columns(cols_count)
                
                for idx, enc in enumerate(encartes):
                    col_target = cols[idx % cols_count]
                    with col_target:
                        st.markdown(f'''
                        <div class="animal-info">
                            <strong>{enc.get("titulo", "DADO").upper()}:</strong><br>
                            {enc.get("valor", "-")}
                        </div>
                        ''', unsafe_allow_html=True)

            st.markdown("### 🎙️ GATILHOS DE PISTA (IA)")
            gatilhos = dados_ia.get("gatilhos", [])
            for g in gatilhos:
                st.markdown(f'<div class="gatilho-card">🔥 {g}</div>', unsafe_allow_html=True)

    with col_direita:
        if mostrar_preview and img_pagina_bytes:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO VISUAL - PÁGINA {pagina_catalogo + 1}</div>', unsafe_allow_html=True)
            st.image(img_pagina_bytes, use_container_width=True)

        if dados_ia:
            canta_html = f"📌 **APRESENTAÇÃO:** {dados_ia.get('apresentacao', '')}<br><br>"
            if dados_ia.get('genetica_pai'): canta_html += f"🐂 **GENÉTICA DO PAI:** {dados_ia.get('genetica_pai')}<br><br>"
            if dados_ia.get('genetica_mae'): canta_html += f"🐄 **GENÉTICA DA MÃE:** {dados_ia.get('genetica_mae')}<br><br>"
            if dados_ia.get('reproducao_detalhe'): canta_html += f"💉 **REPRODUÇÃO:** {dados_ia.get('reproducao_detalhe')}"

            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DO LEILOEIRO (IA)</h3>
                <div>{canta_html}</div>
            </div>
            ''', unsafe_allow_html=True)

        elif erro_ia:
            st.error(erro_ia)

        linha_ctx = dados_lote_oe.get('linha_contextualizada', '')
        if linha_ctx:
            itens = linha_ctx.split(' | ')
            oe_formatted = "<br>".join([f"• <b>{it.split(':', 1)[0]}:</b> {it.split(':', 1)[1]}" if ':' in it else f"• <b>DADO:</b> {it}" for it in itens])
        else:
            oe_formatted = dados_lote_oe.get('linha_completa', 'Nenhum dado encontrado na Ordem.')

        st.markdown(f'''
        <div class="oe-dados-box">
            <h3 style="margin-top:0; color:#34D399; font-size:18px;">📋 O.E. (DADOS DIRETOS DA ORDEM DE ENTRADA)</h3>
            <div>{oe_formatted}</div>
        </div>
        ''', unsafe_allow_html=True)

    # ⚡ PRÉ-CARREGAMENTO DOS PRÓXIMOS 3 LOTES EM SEGUNDO PLANO
    precarregar_proximos_lotes_cat(st.session_state.lote_idx_cat, lista_lotes, mapa_oe, texto_cat, api_keys)
