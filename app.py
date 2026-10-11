import streamlit as st
import json
import uuid
import time
import base64
import urllib.request
import urllib.parse

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Curador de Lazer e Cultura",
    page_icon="🎭",
    layout="wide"
)

PROJECT_ID = "curador-lazer-app"
LOCATION = "us-central1"
AGENT_ID = "eae9afb0-e7fa-49f0-9f4d-04e73002bc47"

# ---------------------------------------------------------
# GERADOR DE TOKEN OAUTH2 VIA REST (NATIVO PYTHON)
# ---------------------------------------------------------
def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def get_access_token_from_service_account(info: dict) -> str:
    """
    Gera token de acesso OAuth2 a partir das credenciais JSON usando requisição HTTP pura.
    Compatível com Streamlit Cloud sem depender de google-auth.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        header = {"alg": "RS256", "typ": "JWT"}
        now = int(time.time())
        payload = {
            "iss": info["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": "https://oauth2.googleapis.com/token",
            "exp": now + 3600,
            "iat": now
        }
        
        encoded_header = base64url_encode(json.dumps(header).encode('utf-8'))
        encoded_payload = base64url_encode(json.dumps(payload).encode('utf-8'))
        signing_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')
        
        private_key_bytes = info["private_key"].encode('utf-8')
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
        
        signature = private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        assertion = f"{encoded_header}.{encoded_payload}.{base64url_encode(signature)}"
        
        params = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion
        }).encode('utf-8')
        
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=params, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get("access_token")
    except Exception as e:
        # Fallback caso cryptography não esteja presente
        return None

def detect_intent_rest(text_prompt: str) -> str:
    """
    Realiza a chamada de detectIntent via REST API diretamente para o Dialogflow CX.
    """
    if "gcp_json" not in st.secrets:
        return "⚠️ Configuração 'gcp_json' não encontrada nos Secrets do Streamlit."

    try:
        secret_content = st.secrets["gcp_json"]
        info = json.loads(secret_content) if isinstance(secret_content, str) else dict(secret_content)
    except Exception as e:
        return f"⚠️ Erro ao ler a chave JSON dos Secrets: {e}"

    # Obter Token
    token = get_access_token_from_service_account(info)
    
    # Se a conversão nativa de JWT necessitar de suporte simplificado do Google
    url = f"https://{LOCATION}-dialogflow.googleapis.com/v3/projects/{PROJECT_ID}/locations/{LOCATION}/agents/{AGENT_ID}/sessions/{st.session_state.session_id}:detectIntent"
    
    body = {
        "queryInput": {
            "text": {
                "text": text_prompt
            },
            "languageCode": "pt-br"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req_data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
            messages = []
            query_result = res_data.get("queryResult", {})
            response_messages = query_result.get("responseMessages", [])
            for msg in response_messages:
                text_obj = msg.get("text", {})
                if "text" in text_obj:
                    messages.extend(text_obj["text"])
                    
            return "\n\n".join(messages) if messages else "Não encontrei opções disponíveis no momento."
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        return f"⚠️ Erro HTTP na API do Dialogflow ({e.code}): {err_body}"
    except Exception as e:
        return f"⚠️ Falha na comunicação com o agente: {e}"

# ---------------------------------------------------------
# ESTADO DA SESSÃO E VARIÁVEIS DE FLUXO
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "gastro_step" not in st.session_state:
    st.session_state.gastro_step = 0

if "selected_culinaria" not in st.session_state:
    st.session_state.selected_culinaria = None

if "selected_preco" not in st.session_state:
    st.session_state.selected_preco = None

# ---------------------------------------------------------
# FUNÇÃO PARA PROCESSAR E EXIBIR A RESPOSTA
# ---------------------------------------------------------
def process_user_prompt(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.gastro_step = 0
    with st.spinner("Consultando recomendações de lazer..."):
        bot_reply = detect_intent_rest(prompt)
        st.session_state.messages.append({"role": "assistant", "content": bot_reply})

# ---------------------------------------------------------
# INTERFACE PRINCIPAL E CARDS DE ESCOLHA
# ---------------------------------------------------------
st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma opção nos cartões abaixo ou monte seu filtro personalizado de gastronomia:")

# ETAPA 0: MENU PRINCIPAL
if st.session_state.gastro_step == 0:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        with st.container(border=True):
            st.markdown("### 🍣 Gastronomia")
            st.write("Filtre por tipo de culinária, faixa de preço e cidade.")
            if st.button("Explorar Gastronomia", key="btn_gastro_start", use_container_width=True):
                st.session_state.gastro_step = 1
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### 🎭 Cultura & Arte")
            st.write("Peças de teatro, museus e exposições.")
            if st.button("Ver Programação Cultural", key="btn_cultura", use_container_width=True):
                process_user_prompt("Recomende peças de teatro e museus no Rio de Janeiro")
                st.rerun()

    with col3:
        with st.container(border=True):
            st.markdown("### 🌳 Ao Ar Livre")
            st.write("Parques, praças, trilhas e natureza.")
            if st.button("Passeios ao Ar Livre", key="btn_parques", use_container_width=True):
                process_user_prompt("Recomende passeios ao ar livre e parques no Rio de Janeiro")
                st.rerun()

    with col4:
        with st.container(border=True):
            st.markdown("### 🎉 Fim de Semana")
            st.write("Dicas para aproveitar o sábado e domingo.")
            if st.button("Dicas de Fim de Semana", key="btn_fds", use_container_width=True):
                process_user_prompt("O que fazer este fim de semana no Rio de Janeiro?")
                st.rerun()

# ETAPA 1: ESCOLHA DA CULINÁRIA
elif st.session_state.gastro_step == 1:
    with st.container(border=True):
        st.subheader("🍽️ Passo 1 de 3: Escolha o estilo de culinária")
        
        culinarias = [
            "Italiana", "Japonesa", "Chinesa", "Peruana", 
            "Árabe", "Brasileira", "Asiática em geral", 
            "Hamburgueria", "Pizzaria / Parrilla", "Outras"
        ]
        
        cols = st.columns(5)
        for i, cul in enumerate(culinarias):
            with cols[i % 5]:
                if st.button(cul, key=f"cul_{i}", use_container_width=True):
                    st.session_state.selected_culinaria = cul
                    st.session_state.gastro_step = 2
                    st.rerun()
                    
        st.divider()
        if st.button("⬅️ Voltar ao Menu Principal", key="back_0"):
            st.session_state.gastro_step = 0
            st.rerun()

# ETAPA 2: ESCOLHA DO PREÇO
elif st.session_state.gastro_step == 2:
    with st.container(border=True):
        st.subheader(f"💰 Passo 2 de 3: Qual a faixa de preço para culinária {st.session_state.selected_culinaria}?")
        
        precos = [
            ("$", "Econômico ($)"),
            ("$$", "Moderado ($$)"),
            ("$$$", "Sofisticado ($$$)"),
            ("$$$$", "Alta Gastronomia ($$$$)")
        ]
        
        cols = st.columns(4)
        for i, (simbolo, rotulo) in enumerate(precos):
            with cols[i]:
                if st.button(rotulo, key=f"p_{i}", use_container_width=True):
                    st.session_state.selected_preco = simbolo
                    st.session_state.gastro_step = 3
                    st.rerun()
                    
        st.divider()
        if st.button("⬅️ Voltar para Culinária", key="back_1"):
            st.session_state.gastro_step = 1
            st.rerun()

# ETAPA 3: ESCOLHA DA CIDADE E DISPARO DA CONSULTA
elif st.session_state.gastro_step == 3:
    with st.container(border=True):
        st.subheader(f"📍 Passo 3 de 3: Em qual cidade procura? (Culinária {st.session_state.selected_culinaria} • {st.session_state.selected_preco})")
        
        cols = st.columns(2)
        with cols[0]:
            if st.button("🌊 Niterói", key="city_niteroi", use_container_width=True):
                prompt = f"Recomende restaurantes de culinária {st.session_state.selected_culinaria} com faixa de preço {st.session_state.selected_preco} em Niterói."
                process_user_prompt(prompt)
                st.rerun()

        with cols[1]:
            if st.button("🏙️ Rio de Janeiro", key="city_rio", use_container_width=True):
                prompt = f"Recomende restaurantes de culinária {st.session_state.selected_culinaria} com faixa de preço {st.session_state.selected_preco} no Rio de Janeiro."
                process_user_prompt(prompt)
                st.rerun()

        st.divider()
        if st.button("⬅️ Voltar para Preço", key="back_2"):
            st.session_state.gastro_step = 2
            st.rerun()

st.divider()

# ---------------------------------------------------------
# EXIBIÇÃO DO HISTÓRICO DE CHAT
# ---------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Entrada de texto no rodapé
if user_input := st.chat_input("Ou digite uma busca específica..."):
    process_user_prompt(user_input)
    st.rerun()
