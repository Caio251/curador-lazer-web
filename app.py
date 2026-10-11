import streamlit as st
import json
import uuid
from google.cloud import dialogflowcx_v3 as dialogflow

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
# AUTENTICAÇÃO E CLIENTE DIALOGFLOW
# ---------------------------------------------------------
@st.cache_resource
def get_dialogflow_client():
    if "gcp_json" not in st.secrets:
        return None, "Configuração 'gcp_json' não encontrada nos Secrets."

    try:
        secret_content = st.secrets["gcp_json"]
        service_account_info = json.loads(secret_content) if isinstance(secret_content, str) else dict(secret_content)

        client_options = {"api_endpoint": f"{LOCATION}-dialogflow.googleapis.com"}
        client = dialogflow.SessionsClient.from_service_account_info(
            info=service_account_info,
            client_options=client_options
        )
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

# Variáveis do fluxo guiado
if "active_flow" not in st.session_state:
    st.session_state.active_flow = None # Pode ser 'gastronomia' ou 'cultura'
if "current_step" not in st.session_state:
    st.session_state.current_step = 0
if "user_cidade" not in st.session_state:
    st.session_state.user_cidade = None
if "user_categoria" not in st.session_state:
    st.session_state.user_categoria = None
if "user_detalhe" not in st.session_state:
    st.session_state.user_detalhe = None

def reset_flow():
    st.session_state.active_flow = None
    st.session_state.current_step = 0
    st.session_state.user_cidade = None
    st.session_state.user_categoria = None
    st.session_state.user_detalhe = None

def send_user_message(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    reset_flow()
    with st.spinner("Consultando recomendações..."):
        bot_reply = detect_intent(prompt)
        st.session_state.messages.append({"role": "assistant", "content": bot_reply})

# ---------------------------------------------------------
# INTERFACE PRINCIPAL E CARDS DE ESCOLHA
# ---------------------------------------------------------
st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma opção nos cartões abaixo ou digite sua busca livre no chat:")

# MENU PRINCIPAL (ETAPA 0)
if st.session_state.current_step == 0:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        with st.container(border=True):
            st.markdown("### 🍣 Gastronomia")
            st.write("Filtre restaurantes por cidade, culinária e preço.")
            if st.button("Explorar Gastronomia", key="btn_gastro", use_container_width=True):
                st.session_state.active_flow = "gastronomia"
                st.session_state.current_step = 1
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### 🎭 Cultura & Arte")
            st.write("Cinema, teatro e museus por cidade e status.")
            if st.button("Ver Programação Cultural", key="btn_cultura", use_container_width=True):
                st.session_state.active_flow = "cultura"
                st.session_state.current_step = 1
                st.rerun()

    with col3:
        with st.container(border=True):
            st.markdown("### 🌳 Ao Ar Livre")
            st.write("Parques, praças, trilhas e natureza.")
            if st.button("Passeios ao Ar Livre", key="btn_parques", use_container_width=True):
                send_user_message("Recomende passeios ao ar livre e parques")
                st.rerun()

    with col4:
        with st.container(border=True):
            st.markdown("### 🎉 Fim de Semana")
            st.write("Dicas para aproveitar o sábado e domingo.")
            if st.button("Dicas de Fim de Semana", key="btn_fds", use_container_width=True):
                send_user_message("O que fazer este fim de semana?")
                st.rerun()

# ---------------------------------------------------------
# FLUXO UNIFICADO (GASTRONOMIA E CULTURA)
# ---------------------------------------------------------
else:
    flow_title = "🍣 Gastronomia" if st.session_state.active_flow == "gastronomia" else "🎭 Cultura & Arte"
    
    # ETAPA 1: ESCOLHA DA CIDADE
    if st.session_state.current_step == 1:
        with st.container(border=True):
            st.subheader(f"{flow_title} - Passo 1 de 3: Escolha a cidade")
            cols = st.columns(2)
            
            with cols[0]:
                if st.button("🌊 Niterói", key="city_nit", use_container_width=True):
                    st.session_state.user_cidade = "Niterói"
                    st.session_state.current_step = 2
                    st.rerun()
            with cols[1]:
                if st.button("🏙️ Rio de Janeiro", key="city_rio", use_container_width=True):
                    st.session_state.user_cidade = "Rio de Janeiro"
                    st.session_state.current_step = 2
                    st.rerun()
                    
            st.divider()
            if st.button("⬅️ Voltar ao Menu Principal"):
                reset_flow()
                st.rerun()

    # ETAPA 2: ESCOLHA DA CATEGORIA
    elif st.session_state.current_step == 2:
        with st.container(border=True):
            st.subheader(f"{flow_title} - Passo 2 de 3: Escolha a categoria em {st.session_state.user_cidade}")
            
            if st.session_state.active_flow == "gastronomia":
                opcoes = ["Italiana", "Japonesa", "Chinesa", "Peruana", "Árabe", "Brasileira", "Asiática em geral", "Hamburgueria", "Pizzaria", "Outras"]
            else:
                opcoes = ["Cinema", "Teatro", "Museu"]
            
            cols = st.columns(5 if st.session_state.active_flow == "gastronomia" else 3)
            for i, op in enumerate(opcoes):
                with cols[i % len(cols)]:
                    if st.button(op, key=f"cat_{i}", use_container_width=True):
                        st.session_state.user_categoria = op
                        st.session_state.current_step = 3
                        st.rerun()
                        
            st.divider()
            if st.button("⬅️ Voltar para Cidades"):
                st.session_state.current_step = 1
                st.rerun()

    # ETAPA 3: ESCOLHA DO DETALHE E DISPARO
    elif st.session_state.current_step == 3:
        with st.container(border=True):
            if st.session_state.active_flow == "gastronomia":
                st.subheader(f"💰 Passo 3 de 3: Qual a faixa de preço para {st.session_state.user_categoria}?")
                opcoes_detalhe = [
                    ("$", "Econômico ($)"),
                    ("$$", "Moderado ($$)"),
                    ("$$$", "Sofisticado ($$$)"),
                    ("$$$$", "Alta Gastronomia ($$$$)")
                ]
            else:
                st.subheader(f"📅 Passo 3 de 3: Qual o status da atração para {st.session_state.user_categoria}?")
                opcoes_detalhe = [
                    ("Em cartaz", "🎬 Em cartaz"),
                    ("Pré-venda", "🎟️ Pré-venda"),
                    ("Estreias", "✨ Estreias")
                ]
            
            cols = st.columns(len(opcoes_detalhe))
            for i, (valor_prompt, rotulo_botao) in enumerate(opcoes_detalhe):
                with cols[i]:
                    if st.button(rotulo_botao, key=f"det_{i}", use_container_width=True):
                        # Montagem do prompt com base no fluxo
                        if st.session_state.active_flow == "gastronomia":
                            prompt = f"Recomende restaurantes de culinária {st.session_state.user_categoria} com faixa de preço {valor_prompt} em {st.session_state.user_cidade}."
                        else:
                            prompt = f"Quais são as opções de {st.session_state.user_categoria} {valor_prompt.lower()} em {st.session_state.user_cidade}?"
                        
                        send_user_message(prompt)
                        st.rerun()
                        
            st.divider()
            if st.button("⬅️ Voltar para Categorias"):
                st.session_state.current_step = 2
                st.rerun()

st.divider()

# ---------------------------------------------------------
# EXIBIÇÃO DO HISTÓRICO DE CHAT E INPUT LIVRE
# ---------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Ou digite uma busca específica..."):
    send_user_message(user_input)
    st.rerun()
