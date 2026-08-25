import streamlit as st
import pdfplumber
import re
import os
import requests
import time
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

@st.cache_data
def extrair_dados_oe(texto_oe_tuple):
    texto_oe = list(texto_oe_tuple)
    sequencia = []
    dados_por_lote = {}
    
    if not texto_oe:
        return sequencia, dados_por_lote
    
    for pagina in texto_oe:
        for linha in pagina.split('\n'):
            linha_limpa = linha.strip()
            if not linha_limpa or re.search(r"QTD\s+IDADE\s+PESO", linha_limpa, re.IGNORECASE) or re.search(r"O\.E\.\s*\|?\s*LT", linha_limpa, re.IGNORECASE) or re.search(r"PROGRAMA\s+LEILÕES", linha_limpa, re.IGNORECASE):
                continue
            
            if '|' in linha_limpa:
                parts = [p.strip() for p in linha_limpa.split('|') if p.strip()]
                if len(parts) >= 3:
                    raw_pos = re.sub(r"\D", "", parts[0])
                    raw_lt = re.sub(r"\D", "", parts[1])
                    if raw_lt and raw_lt.isdigit():
                        numero_lote = int(raw_lt)
                        posicao = int(raw_pos) if raw_pos.isdigit() else 1
                        lt_num = f"{numero_lote:02d}"
                        
                        qtd, idade, peso, categoria, pelagem, produto, vendedor = "", "", "", "", "", "", ""
                        
                        if len(parts) == 8:
                            qtd, idade, peso, categoria, produto, vendedor = parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]
                        elif len(parts) == 6:
                            categoria, pelagem, produto, vendedor = parts[2], parts[3], parts[4], parts[5]
                        else:
                            categoria = parts[2] if len(parts) > 2 else ""
                            produto = parts[-2] if len(parts) > 4 else (parts[3] if len(parts) > 3 else "")
                            vendedor = parts[-1] if len(parts) > 3 else ""

                        if lt_num not in sequencia:
                            sequencia.append(lt_num)
                        
                        nome_animal = produto
                        porcentagem_venda = ""
                        m_porcentagem = re.search(r"(\d+%)\s*de:\s*(.+)", produto, re.IGNORECASE)
                        if m_porcentagem:
                            porcentagem_venda = m_porcentagem.group(1)
                            nome_animal = m_porcentagem.group(2).strip()
                            
                        info_repro, tipo_repro = "", ""
                        m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", f"{categoria} {produto}", re.IGNORECASE)
                        if m_repro:
                            info_repro = m_repro.group(0).strip()
                            txt_low = info_repro.lower()
                            if "parida" in txt_low: tipo_repro = "parida"
                            elif "prenh" in txt_low: tipo_repro = "prenhez"
                            elif "inseminada" in txt_low: tipo_repro = "inseminacao"
                            
                        dados_por_lote[lt_num] = {
                            "lote": lt_num,
                            "posicao": f"{posicao}º A ENTRAR",
                            "qtd": qtd, "idade": idade, "peso": peso,
                            "categoria": categoria, "pelagem": pelagem,
                            "produto": produto, "nome_animal": nome_animal,
                            "porcentagem_venda": porcentagem_venda,
                            "vendedor": vendedor, "info_reproducao": info_repro,
                            "tipo_reproducao": tipo_repro,
                            "linha_completa": linha_limpa
                        }
                        continue

            m_posicao = re.match(r"^(\d{1,3})\s*[º°]?\s+(\d{1,3})\s+", linha_limpa)
            if m_posicao:
                posicao = int(m_posicao.group(1))
                numero_lote = int(m_posicao.group(2))
                if 1 <= numero_lote <= 999:
                    lt_num = f"{numero_lote:02d}"
                    if lt_num not in sequencia:
                        sequencia.append(lt_num)
                    
                    restante = linha_limpa[m_posicao.end():].strip()
                    parts = restante.split()
                    
                    dados = {
                        "lote": lt_num, "posicao": f"{posicao}º A ENTRAR",
                        "qtd": parts[0] if len(parts)>0 else "",
                        "idade": parts[1] if len(parts)>1 else "",
                        "peso": parts[2] if len(parts)>2 else "",
                        "categoria": parts[3] if len(parts)>3 else "",
                        "pelagem": "", "produto": " ".join(parts[4:-1]) if len(parts)>5 else "",
                        "vendedor": parts[-1] if len(parts)>4 else "",
                        "info_reproducao": "", "tipo_reproducao": "",
                        "nome_animal": "", "porcentagem_venda": "",
                        "linha_completa": linha_limpa
                    }
                    
                    m_porcentagem = re.search(r"(\d+%)\s*de:\s*(.+?)(?=\s+(?:parida|prenhe|prenha|inseminada|nelore|angus|girolando)|\s*$)", linha_limpa, re.IGNORECASE)
                    if m_porcentagem:
                        dados["porcentagem_venda"] = m_porcentagem.group(1)
                        dados["nome_animal"] = m_porcentagem.group(2).strip()
                    else:
                        dados["nome_animal"] = dados["produto"]
                        
                    m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", linha_limpa, re.IGNORECASE)
                    if m_repro:
                        texto_repro = m_repro.group(0).strip()
                        dados["info_reproducao"] = texto_repro
                        txt_low = texto_repro.lower()
                        if "parida" in txt_low: dados["tipo_reproducao"] = "parida"
                        elif "prenh" in txt_low: dados["tipo_reproducao"] = "prenhez"
                        elif "inseminada" in txt_low: dados["tipo_reproducao"] = "inseminacao"
                        
                    dados_por_lote[lt_num] = dados
    return sequencia, dados_por_lote

def enriquecer_dados_com_catalogo(dados_lote, texto_pagina_cat):
    if not texto_pagina_cat or not dados_lote:
        return dados_lote
    dados_atualizados = dados_lote.copy()
    if not dados_atualizados.get("info_reproducao"):
        linhas = texto_pagina_cat.split('\n')
        for l in linhas:
            l_clean = l.strip()
            m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", l_clean, re.IGNORECASE)
            if m_repro:
                texto_repro = m_repro.group(0).strip()
                dados_atualizados["info_reproducao"] = texto_repro
                txt_low = texto_repro.lower()
                if "parida" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "parida"
                elif "prenh" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "prenhez"
                elif "inseminada" in txt_low:
                    dados_atualizados["tipo_reproducao"] = "inseminacao"
                break
    return dados_atualizados

@st.cache_data(show_spinner=False)
def analisar_lote_unificado_catalogo(num_lote, dados_lote, texto_pagina_cat, api_keys):
    if not api_keys:
        return "⚠️ Nenhuma chave DEEPSEEK_API_KEY encontrada nos Secrets do Streamlit.", []

    prompt_text = f"""
    Você é um zootecnista e leiloeiro de elite no agronegócio (Nelore/Zebu, Equinos Quarto de Milha, etc.).
    Analise os DADOS extraídos do LOTE {num_lote} e o TEXTO COMPLETO DA PÁGINA DO CATÁLOGO:

    DADOS DA ORDEM:
    - Animal/Produto: {dados_lote.get('nome_animal') or dados_lote.get('produto', 'N/A')}
    - Oferta: {dados_lote.get('porcentagem_venda', '100%')}
    - Categoria: {dados_lote.get('categoria', 'N/A')}
    - Pelagem: {dados_lote.get('pelagem', 'N/A')}
    - Peso/Idade: {dados_lote.get('peso', 'N/A')} | {dados_lote.get('idade', 'N/A')}
    - Status Reprodutivo: {dados_lote.get('info_reproducao', 'N/A')}
    - Vendedor: {dados_lote.get('vendedor', 'N/A')}

    TEXTO EXTRAÍDO DO CATÁLOGO:
    {texto_pagina_cat[:2000] if texto_pagina_cat else 'N/A'}

    REGRAS CRÍTICAS:
    1. É PROIBIDO usar saudações (Boa noite, Olá, etc.).
    2. É PROIBIDO dizer que faltam informações. Adapte a canta para o tipo de animal (se for cavalo, exalte velocidade/trabalho/pelagem; se for bovino, exalte carcaça/matriz/genealogia).
    3. Seja ULTRA-DIRETO. Frases curtas.

    Gere a resposta EXATAMENTE neste formato:

    📌 **APRESENTAÇÃO DO LOTE**
    [Venda agressiva exaltando os pontos fortes em 1 frase]

    🐂 **GENÉTICA / PEDIGREE**
    [Linhagem paterna e materna identificada no texto do catálogo em 1 frase]

    💉 **REPRODUÇÃO / PRENHEZ**
    [Status reprodutivo ou touro acasalado, se houver]

    ---GATILHOS---
    [Gatilho de canta curto 1 desenhado para o lote]
    [Gatilho de canta curto 2 desenhado para o lote]
    [Gatilho de canta curto 3 desenhado para o lote]
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
                {"role": "system", "content": "Você é um especialista em leilões agropecuários."},
                {"role": "user", "content": prompt_text}
            ],
            "temperature": 0.3
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            res_json = response.json()
            
            if response.status_code == 200 and 'choices' in res_json:
                resposta_completa = res_json['choices'][0]['message']['content']
                if "---GATILHOS---" in resposta_completa:
                    partes = resposta_completa.split("---GATILHOS---")
                    consideracoes = partes[0].strip()
                    gatilhos_limpos = [g.strip('- *123.') for g in partes[1].strip().split('\n') if g.strip()]
                    return consideracoes, gatilhos_limpos[:4]
                else:
                    return resposta_completa.strip(), []
            
            msg_erro = res_json.get('error', {}).get('message', response.text)
            erros.append(f"Chave ...{api_key[-6:]}: {msg_erro}")

            if response.status_code == 429:
                time.sleep(1)
                continue
                
        except Exception as e:
            erros.append(f"Erro na conexão: {str(e)}")
            continue

    detalhe_erro = erros[-1] if erros else "Erro de comunicação com a API DeepSeek."
    return f"⚠️ Erro ao consultar o DeepSeek. Detalhe: {detalhe_erro}", []

def gerar_gatilhos_padrao(dados_lote):
    gatilhos = []
    if not dados_lote:
        return ["ANIMAL SELECIONADO!", "QUALIDADE GARANTIDA!", "OPORTUNIDADE NA PISTA!"]
    categoria = dados_lote.get("categoria", "").lower()
    pelagem = dados_lote.get("pelagem", "").upper()
    
    if dados_lote.get("porcentagem_venda"):
        gatilhos.append(f"OFERTA DE {dados_lote['porcentagem_venda']} DO LOTE!")
    if pelagem:
        gatilhos.append(f"PELAGEM: {pelagem} DE DESTAQUE!")
    if dados_lote.get("info_reproducao"):
        gatilhos.append(f"STATUS: {dados_lote['info_reproducao']}")
    if "novilha" in categoria or "bezerra" in categoria or "fêmea" in categoria:
        gatilhos.append("FÊMEA DE CABECEIRA E FUTURO DO REBANHO!")
    elif "macho" in categoria or "garrão" in categoria:
        gatilhos.append("MACHO DE MUITA ESTRUTURA E RAÇA!")
    gatilhos.extend(["PROCEDÊNCIA COMPROVADA!", "LIQUIDEZ IMEDIATA NA PISTA!"])
    return gatilhos[:4]

def run():
    css_code = """
    <style>
        .lote-destaque { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px; border-radius: 18px; text-align: center; font-size: 52px; font-weight: bold; margin-bottom: 12px; }
        .ordem-indicador { background: #16A34A; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin: 8px 0; font-size: 20px; }
        .banner-parida { background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #A855F7; }
        .banner-prenhez { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #EF4444; }
        .banner-inseminacao { background: linear-gradient(135deg, #D97706 0%, #92400E 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #F59E0B; }
        .banner-venda { background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%); color: #000000 !important; padding: 16px; border-radius: 14px; margin-bottom: 12px; font-size: 24px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .animal-info { background: #1E293B; color: white; padding: 15px; border-radius: 12px; margin: 5px 0; border: 1px solid #334155; }
        .nome-animal-box { background: #0284C7; color: white; padding: 14px; border-radius: 12px; margin-bottom: 12px; font-size: 22px; font-weight: bold; text-align: center; }
        .ai-consideracoes-box { background-color: #1E1B4B !important; padding: 20px; border-radius: 15px; margin-top: 15px; border-left: 8px solid #818CF8; }
        .ai-consideracoes-box, .ai-consideracoes-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.6 !important; }
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

    texto_oe = processar_pdf(file_oe.getvalue()) if file_oe else []
    texto_cat = processar_pdf(file_cat.getvalue()) if file_cat else []

    sequencia_oe, mapa_oe = extrair_dados_oe(tuple(texto_oe))

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

    dados_lote = enriquecer_dados_com_catalogo(dados_lote_oe, texto_pagina_catalogo)

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        lote_texto = f"LOTE {num_lote}"
        posicao_texto = dados_lote.get("posicao", f"{st.session_state.lote_idx_cat + 1}º")
        st.markdown(f'<div class="lote-destaque">{lote_texto}<br><span style="font-size: 24px;">{posicao_texto}</span></div>', unsafe_allow_html=True)
        
        if dados_lote.get("porcentagem_venda"):
            st.markdown(f'<div class="banner-venda">💎 OFERTA DE {dados_lote["porcentagem_venda"]} DO ANIMAL</div>', unsafe_allow_html=True)
        
        if dados_lote.get("info_reproducao"):
            tipo_rep = dados_lote.get("tipo_reproducao")
            if tipo_rep == "parida":
                st.markdown(f'<div class="banner-parida">🍼 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
            elif tipo_rep == "prenhez":
                st.markdown(f'<div class="banner-prenhez">🤰 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="banner-inseminacao">💉 {dados_lote["info_reproducao"]}</div>', unsafe_allow_html=True)

        if dados_lote.get("nome_animal"):
            st.markdown(f'<div class="nome-animal-box">🐂 {dados_lote["nome_animal"]}</div>', unsafe_allow_html=True)
        
        if dados_lote:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f'<div class="animal-info"><strong>CATEGORIA:</strong><br>{dados_lote.get("categoria","-")}<br><br><strong>PELAGEM/RAÇA:</strong><br>{dados_lote.get("pelagem") or dados_lote.get("raca","-")}</div>', unsafe_allow_html=True)
            with c2:
                st.markdown(f'<div class="animal-info"><strong>PESO:</strong><br>{dados_lote.get("peso","-")}<br><br><strong>IDADE:</strong><br>{dados_lote.get("idade","-")}</div>', unsafe_allow_html=True)
            with c3:
                st.markdown(f'<div class="animal-info"><strong>QTD:</strong><br>{dados_lote.get("qtd","-") or "1"}<br><br><strong>VENDEDOR:</strong><br>{dados_lote.get("vendedor","-")}</div>', unsafe_allow_html=True)

        st.markdown("### 🎙️ GATILHOS DE PISTA")
        gatilhos = gerar_gatilhos_padrao(dados_lote)
        for g in gatilhos:
            st.markdown(f'<div class="gatilho-card">{g}</div>', unsafe_allow_html=True)

    with col_direita:
        if mostrar_preview and img_pagina_bytes:
            st.markdown(f'<div class="catalogo-header">📖 CATÁLOGO VISUAL - PÁGINA {pagina_catalogo + 1}</div>', unsafe_allow_html=True)
            st.image(img_pagina_bytes, use_container_width=True)

        if img_pagina_bytes or texto_pagina_catalogo:
            with st.spinner("🤖 DeepSeek elaborando a canta e os gatilhos..."):
                analise_ia, gatilhos_ia = analisar_lote_unificado_deepseek(img_pagina_bytes, num_lote, dados_lote, texto_pagina_catalogo, api_keys)
                
                if gatilhos_ia:
                    st.markdown("### 🎯 GATILHOS ESPECÍFICOS DO LOTE (IA)")
                    for gat in gatilhos_ia:
                        st.markdown(f'<div class="gatilho-ia-card">🔥 {gat}</div>', unsafe_allow_html=True)
                        
                st.markdown(f'''
                <div class="ai-consideracoes-box">
                    <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DA IA (LINHAGEM & REPRODUÇÃO)</h3>
                    <div>{analise_ia}</div>
                </div>
                ''', unsafe_allow_html=True)
