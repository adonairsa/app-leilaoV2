import streamlit as st
import pdfplumber
import re
import os
import requests
import json
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

@st.cache_data
def extrair_dados_oe(texto_oe_tuple):
    texto_oe = list(texto_oe_tuple)
    sequencia = []
    dados_por_lote = {}
    
    if not texto_oe:
        return sequencia, dados_por_lote
    
    for pagina in texto_oe:
        linhas = pagina.split('\n')
        col_map = {}
        
        for linha in linhas:
            linha_limpa = linha.strip()
            if not linha_limpa or "PROGRAMA" in linha_limpa.upper():
                continue

            # 1. Identifica a linha de cabeçalho e mapeia o índice exato de cada coluna
            if any(h in linha_limpa.upper() for h in ['LT', 'LOTE', 'CATEGORIA', 'PRODUTO', 'ANIMAL', 'VENDEDOR']):
                if '|' in linha_limpa:
                    raw_headers = [h.strip().upper() for h in linha_limpa.split('|')]
                    if raw_headers and raw_headers[0] == '': raw_headers.pop(0)
                    if raw_headers and raw_headers[-1] == '': raw_headers.pop()
                else:
                    raw_headers = [h.strip().upper() for h in re.split(r'\s{2,}', linha_limpa) if h.strip()]
                
                col_map = {}
                for idx, h in enumerate(raw_headers):
                    if re.search(r"\bO\.?E\.?\b", h) or "ORDEM" in h or "POSIÇ" in h:
                        col_map["oe"] = idx
                    elif re.search(r"\b(LT|LOTE)\b", h):
                        col_map["lote"] = idx
                    elif "QTD" in h or "QUANT" in h:
                        col_map["qtd"] = idx
                    elif "IDADE" in h:
                        col_map["idade"] = idx
                    elif "PESO" in h:
                        col_map["peso"] = idx
                    elif "CATEGORIA" in h:
                        col_map["categoria"] = idx
                    elif "PELAGEM" in h:
                        col_map["pelagem"] = idx
                    elif "PRODUTO" in h or "ANIMAL" in h:
                        col_map["produto"] = idx
                    elif "VENDEDOR" in h or "PROPRIET" in h:
                        col_map["vendedor"] = idx
                continue

            # 2. Processa a linha de dados mantendo as células vazias
            if '|' in linha_limpa:
                parts = [p.strip() for p in linha_limpa.split('|')]
                if parts and parts[0] == '': parts.pop(0)
                if parts and parts[-1] == '': parts.pop()
                
                if len(parts) >= 2:
                    oe_idx = col_map.get("oe", 0)
                    lt_idx = col_map.get("lote", 1 if len(parts) > 1 else 0)
                    
                    raw_oe = parts[oe_idx] if oe_idx < len(parts) else parts[0]
                    raw_lt = parts[lt_idx] if lt_idx < len(parts) else (parts[1] if len(parts) > 1 else parts[0])
                    
                    clean_oe = re.sub(r"\D", "", raw_oe)
                    clean_lt = re.sub(r"\D", "", raw_lt)

                    if clean_lt and clean_lt.isdigit():
                        numero_lote = int(clean_lt)
                        lt_num = f"{numero_lote:02d}"
                        posicao_fmt = f"{int(clean_oe)}º A ENTRAR" if clean_oe else raw_oe
                        
                        if lt_num not in sequencia:
                            sequencia.append(lt_num)

                        def get_val(key):
                            return parts[col_map[key]] if key in col_map and col_map[key] < len(parts) else ""

                        qtd = get_val("qtd")
                        idade = get_val("idade")
                        peso = get_val("peso")
                        categoria = get_val("categoria")
                        pelagem = get_val("pelagem")
                        produto = get_val("produto")
                        vendedor = get_val("vendedor")

                        if not produto and len(parts) > 3:
                            produto = parts[-2]

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
                            "linha_completa": linha_limpa
                        }
                        continue

            # 3. Processamento de contingência para texto corrido sem separador '|'
            m_pos = re.match(r"^(\d{1,3})\s*[º°]?\s+(\d{1,3})\s+", linha_limpa)
            if m_pos:
                pos_num = int(m_pos.group(1))
                numero_lote = int(m_pos.group(2))
                if 1 <= numero_lote <= 999:
                    lt_num = f"{numero_lote:02d}"
                    if lt_num not in sequencia:
                        sequencia.append(lt_num)
                    
                    restante = linha_limpa[m_pos.end():].strip()
                    parts = restante.split()
                    
                    dados = {
                        "lote": lt_num,
                        "posicao": f"{pos_num}º A ENTRAR",
                        "qtd": parts[0] if len(parts)>0 else "",
                        "idade": parts[1] if len(parts)>1 else "",
                        "peso": parts[2] if len(parts)>2 else "",
                        "categoria": parts[3] if len(parts)>3 else "",
                        "pelagem": "",
                        "produto": " ".join(parts[4:-1]) if len(parts)>5 else (parts[4] if len(parts)>4 else ""),
                        "vendedor": parts[-1] if len(parts)>4 else "",
                        "info_reproducao": "",
                        "tipo_reproducao": "",
                        "nome_animal": "",
                        "porcentagem_venda": "",
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

@st.cache_data(show_spinner=False)
def analisar_lote_leiloeiro_deepseek(num_lote, dados_lote, api_keys):
    if not api_keys:
        return None, "⚠️ Nenhuma chave DEEPSEEK_API_KEY encontrada nos Secrets do Streamlit."

    prompt_system = """Você é um Leiloeiro Rural e Zootecnista de Elite no Brasil.
    Sua missão é ler as informações de um lote de leilão (gado Nelore/Corte/Leite ou Equinos Quarto de Milha/Crioulo) e organizar a apresentação visual para a tela do leiloeiro na pista."""

    prompt_user = f"""
    Analise os dados extraídos do LOTE {num_lote}:
    - Posição de Entrada: {dados_lote.get('posicao', 'N/A')}
    - Número do Lote: {num_lote}
    - Categoria: {dados_lote.get('categoria', '')}
    - Pelagem: {dados_lote.get('pelagem', '')}
    - Produto / Animal: {dados_lote.get('nome_animal') or dados_lote.get('produto', 'N/A')}
    - Oferta: {dados_lote.get('porcentagem_venda', '100%')}
    - Qtd: {dados_lote.get('qtd', '')}
    - Peso: {dados_lote.get('peso', '')}
    - Idade: {dados_lote.get('idade', '')}
    - Status Reprodutivo: {dados_lote.get('info_reproducao', '')}
    - Vendedor: {dados_lote.get('vendedor', '')}
    - Linha Bruta PDF: {dados_lote.get('linha_completa', '')}

    INSTRUÇÕES CRÍTICAS DE LEILOEIRO:
    1. Crie uma lista de "ENCARTES" (cartões de informação) prioritários para aparecer na tela.
    2. Coloque APENAS o que existir com valor preenchido na Ordem e que agregue valor ao lote (ex: CATEGORIA, PELAGEM, PESO, IDADE, VENDEDOR, QTD).
    3. NUNCA invente peso ou idade se o campo estiver vazio ou não existir na Ordem.
    4. Crie uma canta de venda agressiva ressaltando o nome e as qualidades do lote.

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
            {{"titulo": "VENDEDOR", "valor": "..."}}
        ],
        "apresentacao": "Frase agressiva de canta...",
        "genetica_pai": "Informação do pai/linhagem se houver na linha bruta",
        "genetica_mae": "Informação da mãe/linhagem se houver na linha bruta",
        "reproducao_detalhe": "Detalhes de prenhez/inseminação se houver",
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

def run():
    css_code = """
    <style>
        .lote-destaque { background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%); color: white; padding: 20px; border-radius: 18px; text-align: center; font-size: 52px; font-weight: bold; margin-bottom: 12px; }
        .ordem-indicador { background: #16A34A; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin: 8px 0; font-size: 20px; }
        .banner-parida { background: linear-gradient(135deg, #7E22CE 0%, #581C87 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #A855F7; }
        .banner-prenhez { background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #EF4444; }
        .banner-inseminacao { background: linear-gradient(135deg, #D97706 0%, #92400E 100%); color: #FFFFFF !important; padding: 18px; border-radius: 14px; margin-bottom: 12px; font-size: 22px !important; font-weight: 900 !important; text-align: center; border: 3px solid #F59E0B; }
        .banner-venda { background: linear-gradient(135deg, #EAB308 0%, #CA8A04 100%); color: #000000 !important; padding: 16px; border-radius: 14px; margin-bottom: 12px; font-size: 24px !important; font-weight: 900 !important; text-align: center; border: 3px solid #FACC15; }
        .animal-info { background: #1E293B; color: white; padding: 15px; border-radius: 12px; margin: 5px 0; border: 1px solid #334155; min-height: 90px; }
        .nome-animal-box { background: #0284C7; color: white; padding: 14px; border-radius: 12px; margin-bottom: 12px; font-size: 22px; font-weight: bold; text-align: center; }
        .ai-consideracoes-box { background-color: #1E1B4B !important; padding: 20px; border-radius: 15px; margin-top: 5px; border-left: 8px solid #818CF8; }
        .ai-consideracoes-box, .ai-consideracoes-box * { color: #FFFFFF !important; font-size: 16px !important; line-height: 1.6 !important; }
        .gatilho-card { background: linear-gradient(90deg, #EC4899 0%, #8B5CF6 100%); color: white; padding: 14px; border-radius: 12px; font-size: 18px; margin: 6px 0; font-weight: bold; }
        .gatilho-ia-card { background: linear-gradient(135deg, #059669 0%, #047857 100%); color: white !important; padding: 16px; border-radius: 14px; font-size: 19px !important; margin: 8px 0; font-weight: bold !important; border-left: 6px solid #34D399; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
    </style>
    """
    st.markdown(css_code, unsafe_allow_html=True)

    api_keys = obter_api_keys()

    with st.sidebar:
        st.header("Arquivo - Modo Ordem")
        file_oe = st.file_uploader("Ordem de Entrada (PDF)", type="pdf", key="oe_somente")
        st.markdown("---")
        modo_ordenacao = st.radio("Escolha a ordem:", ["ORDEM DE ENTRADA", "ORDEM NUMÉRICA"], index=0, key="ordem_somente")

    texto_oe = processar_pdf(file_oe.getvalue()) if file_oe else []
    sequencia_oe, mapa_oe = extrair_dados_oe(tuple(texto_oe))

    if sequencia_oe:
        lista_lotes = sequencia_oe.copy() if modo_ordenacao == "ORDEM DE ENTRADA" else sorted(sequencia_oe, key=lambda x: int(x))
        ordem_atual = modo_ordenacao
    else:
        lista_lotes = []
        ordem_atual = "NENHUM LOTE ENCONTRADO"

    if 'lote_idx_oe' not in st.session_state:
        st.session_state.lote_idx_oe = 0

    if not lista_lotes:
        st.warning("Carregue a Ordem de Entrada (PDF) no menu lateral para começar!")
        st.stop()

    if st.session_state.lote_idx_oe >= len(lista_lotes):
        st.session_state.lote_idx_oe = 0

    ordem_texto = f"{ordem_atual} | Lote {st.session_state.lote_idx_oe + 1} de {len(lista_lotes)}"
    st.markdown(f'<div class="ordem-indicador">{ordem_texto}</div>', unsafe_allow_html=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("ANTERIOR", use_container_width=True, key="prev_oe"):
            st.session_state.lote_idx_oe = max(0, st.session_state.lote_idx_oe - 1)
            st.rerun()

    with col_next:
        if st.button("PRÓXIMO", use_container_width=True, key="next_oe"):
            st.session_state.lote_idx_oe = min(len(lista_lotes) - 1, st.session_state.lote_idx_oe + 1)
            st.rerun()

    lote_selecionado = st.selectbox("Ir para o lote:", options=lista_lotes, index=st.session_state.lote_idx_oe, key="sel_oe")
    st.session_state.lote_idx_oe = lista_lotes.index(lote_selecionado)

    num_lote = lista_lotes[st.session_state.lote_idx_oe]
    dados_lote = mapa_oe.get(num_lote, {})

    col_esquerda, col_direita = st.columns([1, 1])

    with col_esquerda:
        with st.spinner("🤖 Leiloeiro IA analisando o lote..."):
            dados_ia, erro_ia = analisar_lote_leiloeiro_deepseek(num_lote, dados_lote, api_keys)

        if dados_ia:
            lote_texto = f"LOTE {num_lote}"
            posicao_texto = dados_ia.get("posicao_entrada", dados_lote.get("posicao", f"{st.session_state.lote_idx_oe + 1}º A ENTRAR"))
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

            # RENDERIZAÇÃO DINÂMICA DOS ENCARTES GERADOS PELA IA
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
