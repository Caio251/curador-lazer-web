import streamlit as st
import json
import uuid
from google.oauth2 import service_account
from google.cloud import dialogflowcx_v3 as dialogflow

# CONFIGURAÇÕES DA GCP
PROJECT_ID = "curador-lazer-app"
LOCATION = "us-central1"
AGENT_ID = "eae9afb0-e7fa-49f0-9f4d-04e73002bc47"

# CARREGA AS CREDENCIAIS DO STREAMLIT SECRETS
@st.cache_resource
def get_dialogflow_client():
    # Lê a chave JSON armazenada na aba Secrets do Streamlit
    service_account_info = json.loads(st.secrets["gcp_json"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    
    client_options = {"api_endpoint": f"{LOCATION}-dialogflow.googleapis.com"}
    return dialogflow.SessionsClient(credentials=credentials, client_options=client_options)

def detect_intent(text_prompt):
    session_client = get_dialogflow_client(LOCATION)
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
    return "\n\n".join(bot_responses) if bot_responses else "Não encontrei opções disponíveis."

# SESSÃO E HISTÓRICO DE CONVERSA
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "prompt_to_send" not in st.session_state:
    st.session_state.prompt_to_send = None

st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma opção nos cartões abaixo ou digite o seu pedido personalizado:")

# CARDS INTERATIVOS
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
        st.markdown("### 🌳 Ao Ar Livre")
        st.write("Parques, praças, trilhas e passeios na natureza.")
        if st.button("Passeios ao Ar Livre", key="btn_parques", use_container_width=True):
            st.session_state.prompt_to_send = "Recomende passeios ao ar livre e parques no Rio de Janeiro"

with col4:
    with st.container(border=True):
        st.markdown("### 🎉 Fim de Semana")
        st.write("Dicas especiais para aproveitar o sábado e domingo.")
        if st.button("Dicas de Fim de Semana", key="btn_fds", use_container_width=True):
            st.session_state.prompt_to_send = "O que fazer este fim de semana no Rio de Janeiro?"

st.divider()

# HISTÓRICO DO CHAT
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ou digite uma busca específica (ex: Restaurante italiano romântico em Botafogo)...")

final_prompt = None
if st.session_state.prompt_to_send:
    final_prompt = st.session_state.prompt_to_send
    st.session_state.prompt_to_send = None
elif user_input:
    final_prompt = user_input

if final_prompt:
    st.session_state.messages.append({"role": "user", "content": final_prompt})
    with st.chat_message("user"):
        st.markdown(final_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultando recomendações de lazer..."):
            bot_reply = detect_intent(final_prompt)
            st.markdown(bot_reply)

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    st.rerun()
