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
# AUTENTICAÇÃO E CLIENTE DIALOGFLOW EM CACHE
# ---------------------------------------------------------
@st.cache_resource
def get_dialogflow_client():
    # Lê a chave JSON armazenada nos Secrets do Streamlit (gcp_json)
    if "gcp_json" in st.secrets:
        service_account_info = json.loads(st.secrets["gcp_json"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
    else:
        # Fallback para credenciais padrão do ambiente local, se disponível
        credentials = None

    client_options = {"api_endpoint": f"{LOCATION}-dialogflow.googleapis.com"}
    return dialogflow.SessionsClient(credentials=credentials, client_options=client_options)

def detect_intent(text_prompt):
    session_client = get_dialogflow_client()
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

# ---------------------------------------------------------
# INICIALIZAÇÃO DA SESSÃO E HISTÓRICO
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "prompt_to_send" not in st.session_state:
    st.session_state.prompt_to_send = None

# ---------------------------------------------------------
# INTERFACE DO USUÁRIO (CABEÇALHO E CARDS)
# ---------------------------------------------------------
st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma categoria nos cartões abaixo ou digite o seu pedido personalizado:")

col1, col2, col3, col4 = st.columns(4)

with col1:
    with st.container(border=True):
        st.markdown("### 🍣 Gastronomia")
        st.write("Restaurantes sofisticados, bares e culinárias variadas no Rio.")
        if st.button("Explorar Restaurantes", key="btn_gastronomia", use_container_width=True):
            st.session_state.prompt_to_send = "Recomende ótimos restaurantes no Rio de Janeiro"

with col2:
    with st.container(border=True):
        st.markdown("### 🎭 Cultura & Arte")
        st.write("Peças de teatro, museus, exposições e apresentações.")
        if st.button("Ver Programação Cultural", key="btn_cultura", use_container_width=True):
            st.session_state.prompt_to_send = "Recomende peças de teatro e museus no Rio de Janeiro"

with col3:
    with st.container(border=True):
        st
