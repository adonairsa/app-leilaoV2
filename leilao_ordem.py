import streamlit as st
import pdfplumber
import re
import os
import requests
import time
from io import BytesIO

def obter_api_keys():
    chaves = []
    try:
        if "GEMINI_API_KEYS" in st.secrets:
            raw_keys = st.secrets["GEMINI_API_KEYS"]
            chaves = [k.strip() for k in raw_keys.split(",") if k.strip()]
        elif "GEMINI_API_KEY" in st.secrets:
            chaves = [st.secrets["GEMINI_API_KEY"].strip()]
    except:
        pass
        
    if not chaves:
        env_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")
        if env_keys:
            chaves = [k.strip() for k in env_keys.split(",") if k.strip()]
            
    return chaves if chaves else [""]

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
    condicoes_leilao = []
    
    if not texto_oe:
        return sequencia, dados_por_lote, ""
    
    for pagina in texto_oe:
        linhas = pagina.split('\n')
        col_map = {}
        
        for linha in linhas:
            linha_limpa = linha.strip()
            if not linha_limpa:
                continue
                
            # Captura termos e regras gerais do leilão (ex: parcelas, frete, comissão)
            if re.search(r"(condição|parcela|desconto|comissão|frete|pagamento|lance vezes)", linha_limpa, re.IGNORECASE):
                if linha_limpa not in condicoes_leilao:
                    condicoes_leilao.append(linha_limpa)
            
            # Detecta linha de cabeçalho dinamicamente
            if any(h in linha_limpa.upper() for h in ['LT', 'LOTE', 'CATEGORIA', 'PRODUTO', 'ANIMAL', 'VENDEDOR']):
                parts_header = [p.strip().upper() for p in (linha_limpa.split('|') if '|' in linha_limpa else re.split(r'\s{2,}', linha_limpa))]
                for idx, part in enumerate(parts_header):
                    if re.search(r"\b(LT|LOTE)\b", part): col_map['lote'] = idx
                    elif re.search(r"\b(O\.?E\.?|POSIÇÃO|ORDEM)\b", part): col_map['posicao'] = idx
                    elif 'QTD' in part: col_map['qtd'] = idx
                    elif 'IDADE' in part: col_map['idade'] = idx
                    elif 'PESO' in part: col_map['peso'] = idx
                    elif 'CATEGORIA' in part: col_map['categoria'] = idx
                    elif 'PELAGEM' in part: col_map['pelagem'] = idx
                    elif 'PRODUTO' in part or 'ANIMAL' in part: col_map['produto'] = idx
                    elif 'VENDEDOR' in part: col_map['vendedor'] = idx
                continue

            # Processa linhas de dados usando delimitador '|' ou múltiplos espaços
            parts = [p.strip() for p in (linha_limpa.split('|') if '|' in linha_limpa else re.split(r'\s{2,}', linha_limpa))]
            
            if len(parts) >= 3:
                lt_val = ""
                if 'lote' in col_map and col_map['lote'] < len(parts):
                    raw_lt = re.sub(r"\D", "", parts[col_map['lote']])
                    if raw_lt and 1 <= int(raw_lt) <= 999:
                        lt_val = f"{int(raw_lt):02d}"
                
                if not lt_val:
                    for p_idx in [0, 1]:
                        if p_idx < len(parts):
                            raw_lt = re.sub(r"\D", "", parts[p_idx])
                            if raw_lt and 1 <= int(raw_lt) <= 999:
                                lt_val = f"{int(raw_lt):02d}"
                                break

                if lt_val:
                    if lt_val not in sequencia:
                        sequencia.append(lt_val)
                    
                    pos_val = parts[col_map['posicao']] if 'posicao' in col_map and col_map['posicao'] < len(parts) else parts[0]
                    qtd_val = parts[col_map['qtd']] if 'qtd' in col_map and col_map['qtd'] < len(parts) else ""
                    idade_val = parts[col_map['idade']] if 'idade' in col_map and col_map['idade'] < len(parts) else ""
                    peso_val = parts[col_map['peso']] if 'peso' in col_map and col_map['peso'] < len(parts) else ""
                    cat_val = parts[col_map['categoria']] if 'categoria' in col_map and col_map['categoria'] < len(parts) else ""
                    pelagem_val = parts[col_map['pelagem']] if 'pelagem' in col_map and col_map['pelagem'] < len(parts) else ""
                    prod_val = parts[col_map['produto']] if 'produto' in col_map and col_map['produto'] < len(parts) else ""
                    vend_val = parts[col_map['vendedor']] if 'vendedor' in col_map and col_map['vendedor'] < len(parts) else parts[-1]

                    if not prod_val and len(parts) > 3:
                        prod_val = parts[3]

                    nome_anim = prod_val
                    porcentagem = ""
                    m_perc = re.search(r"(\d+%)\s*de:\s*(.+)", prod_val, re.IGNORECASE)
                    if m_perc:
                        porcentagem = m_perc.group(1)
                        nome_anim = m_perc.group(2).strip()

                    info_repro, tipo_repro = "", ""
                    m_repro = re.search(r"\b(parida|prenhe|prenha|inseminada)\b.*", f"{cat_val} {prod_val}", re.IGNORECASE)
                    if m_repro:
                        info_repro = m_repro.group(0).strip()
                        txt_l = info_repro.lower()
                        if "parida" in txt_l: tipo_repro = "parida"
                        elif "prenh" in txt_l: tipo_repro = "prenhez"
                        elif "inseminada" in txt_l: tipo_repro = "inseminacao"

                    dados_por_lote[lt_val] = {
                        "lote": lt_val,
                        "posicao": pos_val,
                        "qtd": qtd_val,
                        "idade": idade_val,
                        "peso": peso_val,
                        "categoria": cat_val,
                        "pelagem": pelagem_val,
                        "produto": prod_val,
                        "nome_animal": nome_anim,
                        "porcentagem_venda": porcentagem,
                        "vendedor": vend_val,
                        "info_reproducao": info_repro,
                        "tipo_reproducao": tipo_repro,
                        "linha_completa": linha_limpa
                    }

    return sequencia, dados_por_lote, " | ".join(condicoes_leilao[:4])

@st.cache_data(show_spinner=False)
def analisar_lote_unificado_gemini(num_lote, dados_lote, condicoes_leilao, api_keys):
    if not api_keys or api_keys[0] == "":
        return "⚠️ Insira a GEMINI_API_KEYS nos Secrets do Streamlit.", []

    headers = {"Content-Type": "application/json"}
    prompt_text = f"""
    Você é um zootecnista e leiloeiro de elite no agronegócio (Gado Nelore/Zebu, Equinos Quarto de Milha, etc.).
    Analise os dados extraídos dinamicamente da ORDEM DE ENTRADA do LOTE {num_lote}:

    DADOS DO LOTE:
    - Animal/Produto: {dados_lote.get('nome_animal') or dados_lote.get('produto', 'N/A')}
    - Oferta: {dados_lote.get('porcentagem_venda', '100%')}
    - Categoria: {dados_lote.get('categoria', 'N/A')}
    - Pelagem (se houver): {dados_lote.get('pelagem', 'N/A')}
    - Peso/Idade: {dados_lote.get('peso', 'N/A')} | {dados_lote.get('idade', 'N/A')}
    - Status Reprodutivo: {dados_lote.get('info_reproducao', 'N/A')}
    - Vendedor: {dados_lote.get('vendedor', 'N/A')}
    - Condições do Leilão: {condicoes_leilao if condicoes_leilao else 'N/A'}
    - Linha Bruta: {dados_lote.get('linha_completa', '')}

    REGRAS CRÍTICAS:
    1. É PROIBIDO usar saudações (Boa noite, Olá, etc.).
    2. É PROIBIDO dizer que faltam informações. Adapte o discurso para o tipo de animal (se for cavalo, exalte pelagem/potencial de sela/trabalho; se for bovino, exalte peso/carcaça/matriz/doadora).
    3. Seja ULTRA-DIRETO. Frases curtas.

    Gere a resposta EXATAMENTE neste formato:

    📌 **APRESENTAÇÃO DO LOTE**
    [Venda agressiva exaltando os pontos fortes em 1 frase]

    🐂 **GENÉTICA / PEDIGREE**
    [Linhagem ou informações da árvore genealógica, se houver]

    💉 **REPRODUÇÃO / PRENHEZ**
    [Status reprodutivo ou acasalamento, se houver]

    ---GATILHOS---
    [Gatilho de canta curto 1 desenhado para o lote]
    [Gatilho de canta curto 2 desenhado para o lote]
    [Gatilho de canta curto 3 desenhado para o lote]
    """

    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    modelos = ["gemini-1.5-flash", "gemini-1.5-pro"]
    ultimo_erro = ""

    for mod in modelos:
        for tentativa in range(2):
            for api_key in api_keys:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=25)
                    res_json = response.json()
                    
                    if response.status_code == 200 and 'candidates' in res_json:
                        resposta_completa = res_json['candidates'][0]['content']['parts'][0]['text']
                        if "---GATILHOS---" in resposta_completa:
                            partes = resposta_completa.split("---GATILHOS---")
                            consideracoes = partes[0].strip()
                            gatilhos_limpos = [g.strip('- *123.') for g in partes[1].strip().split('\n') if g.strip()]
                            return consideracoes, gatilhos_limpos[:4]
                        else:
                            return resposta_completa.strip(), []
                            
                    elif response.status_code == 429:
                        ultimo_erro = "Cota limite alcançada."
                        continue
                        
                    elif response.status_code == 404:
                        ultimo_erro = f"Modelo {mod} indisponível."
                        break
                        
                    else:
                        ultimo_erro = res_json.get('error', {}).get('message', response.text)
                        continue 
                        
                except Exception as e:
                    ultimo_erro = str(e)
                    continue

            if "Cota" in ultimo_erro:
                time.sleep(5)
            elif "indisponível" in ultimo_erro:
                break
            else:
                break

    return f"⚠️ Erro de Conexão ou Limite Atingido. Detalhe: {ultimo_erro}", []

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
    elif "macho" in categoria or "garRão" in categoria:
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
    sequencia_oe, mapa_oe, condicoes_leilao = extrair_dados_oe(tuple(texto_oe))

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
        lote_texto = f"LOTE {num_lote}"
        posicao_texto = dados_lote.get("posicao", f"{st.session_state.lote_idx_oe + 1}º")
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
        with st.spinner("🤖 Gemini elaborando a canta e os gatilhos..."):
            analise_ia, gatilhos_ia = analisar_lote_unificado_gemini(num_lote, dados_lote, condicoes_leilao, api_keys)
            
            st.markdown(f'''
            <div class="ai-consideracoes-box">
                <h3 style="margin-top:0; color:#818CF8; font-size:18px;">🤖 CONSIDERAÇÕES DA IA (LINHAGEM & REPRODUÇÃO)</h3>
                <div>{analise_ia}</div>
            </div>
            ''', unsafe_allow_html=True)

            if gatilhos_ia:
                st.markdown("### 🎯 GATILHOS ESPECÍFICOS DO LOTE (IA)")
                for gat in gatilhos_ia:
                    st.markdown(f'<div class="gatilho-ia-card">🔥 {gat}</div>', unsafe_allow_html=True)
