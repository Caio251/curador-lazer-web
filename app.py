import streamlit as st
import json
import uuid
from google.oauth2 import service_account
from google.cloud import dialogflowcx_v3 as dialogflow

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Curador de Lazer e Cultura",
    page_icon="🎭",
    layout="wide"
)

# ---------------------------------------------------------
# CONFIGURAÇÕES DO AGENTE NA GOOGLE CLOUD
# ---------------------------------------------------------
PROJECT_ID = "curador-lazer-app"
LOCATION = "us-central1"
AGENT_ID = "eae9afb0-e7fa-49f0-9f4d-04e73002bc47"

# ---------------------------------------------------------
# AUTENTICAÇÃO E CLIENTE DIALOGFLOW
# ---------------------------------------------------------
@st.cache_resource
def get_dialogflow_client():
    if "gcp_json" not in st.secrets:
        return None, "Configuração de credenciais ('gcp_json') não encontrada nos Secrets do Streamlit."

    try:
        secret_content = st.secrets["gcp_json"]
        if isinstance(secret_content, str):
            service_account_info = json.loads(secret_content)
        else:
            service_account_info = dict(secret_content)

        # Autenticação oficial com escopo do Google Cloud
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        client_options = {"api_endpoint": f"{LOCATION}-dialogflow.googleapis.com"}
        client = dialogflow.SessionsClient(credentials=credentials, client_options=client_options)
        return client, None
    except Exception as e:
        return None, f"Erro ao criar credenciais GCP: {e}"

def detect_intent(text_prompt):
    session_client, err_msg = get_dialogflow_client()
    if not session_client:
        return f"⚠️ {err_msg}"

    try:
        session_path = session_client.session_path(
            project=PROJECT_ID,
            location=LOCATION,
            agent=AGENT_ID,
            session=st.session_state.session_id
        )
        
        text_input = dialogflow.TextInput(text=text_prompt)
        query_input = dialogflow.QueryInput(text=text_input, language_code="pt-br")
        
        request_dialogflow = dialogflow.DetectIntentRequest(
            session=session_path,
            query_input=query_input
        )
        
        response = session_client.detect_intent(request=request_dialogflow)
        
        bot_responses = []
        for message in response.query_result.response_messages:
            if message.text.text:
                bot_responses.extend(message.text.text)
                
        return "\n\n".join(bot_responses) if bot_responses else "Não encontrei opções disponíveis no momento."
    except Exception as e:
        return f"⚠️ Erro ao consultar o Dialogflow CX: {e}"

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
# FUNÇÃO AUXILIAR PARA ENVIAR MENSAGENS E OBTER RESPOSTA
# ---------------------------------------------------------
def send_user_message(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.gastro_step = 0
    with st.spinner("Consultando recomendações de lazer..."):
        bot_reply = detect_intent(prompt)
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
                send_user_message("Recomende peças de teatro e museus no Rio de Janeiro")
                st.rerun()

    with col3:
        with st.container(border=True):
            st.markdown("### 🌳 Ao Ar Livre")
            st.write("Parques, praças, trilhas e natureza.")
            if st.button("Passeios ao Ar Livre", key="btn_parques", use_container_width=True):
                send_user_message("Recomende passeios ao ar livre e parques no Rio de Janeiro")
                st.rerun()

    with col4:
        with st.container(border=True):
            st.markdown("### 🎉 Fim de Semana")
            st.write("Dicas para aproveitar o sábado e domingo.")
            if st.button("Dicas de Fim de Semana", key="btn_fds", use_container_width=True):
                send_user_message("O que fazer este fim de semana no Rio de Janeiro?")
                st.rerun()

# ETAPA 1: ESCOLHA DA CULINÁRIA
elif st.session_state.gastro_step == 1:
    with st.container(border=True):
        st.subheader("🍽️ Passo 1 de 3: Escolha o estilo de culinária")
        
        culinarias = [
            "Italiana", "Japonesa", "Chinesa", "Peruana", 
            "Árabe", "Brasileira", "Asiática em geral", 
            "Hamburgueria", "Pizzaria", "Outras"
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
                send_user_message(prompt)
                st.rerun()

        with cols[1]:
            if st.button("🏙️ Rio de Janeiro", key="city_rio", use_container_width=True):
                prompt = f"Recomende restaurantes de culinária {st.session_state.selected_culinaria} com faixa de preço {st.session_state.selected_preco} no Rio de Janeiro."
                send_user_message(prompt)
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

# Entrada de texto livre no rodapé
if user_input := st.chat_input("Ou digite uma busca específica..."):
    send_user_message(user_input)
    st.rerun()
