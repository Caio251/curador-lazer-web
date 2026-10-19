import streamlit as st
import json
import uuid
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
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
TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")

# Dicionário de tradução de Gêneros do TMDB
TMDB_GENRES = {
    28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime",
    99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia",
    36: "História", 27: "Terror", 10402: "Música", 9648: "Mistério",
    10749: "Romance", 878: "Ficção Científica", 10770: "Cinema TV",
    53: "Thriller", 10752: "Guerra", 37: "Faroeste"
}

# ---------------------------------------------------------
# CLIENTE DIALOGFLOW
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
# CONSULTA DE FILMES NO TMDB
# ---------------------------------------------------------
def fetch_tmdb_movies(mode: str, month_offset: int = 0) -> str:
    if not TMDB_API_KEY:
        return "⚠️ Chave de API do TMDB não configurada nos Secrets."

    today = datetime.now()

    if mode == "cartaz":
        url = "https://api.themoviedb.org/3/movie/now_playing"
        params = {"api_key": TMDB_API_KEY, "language": "pt-BR", "region": "BR", "page": 1}
    else: # Estreias por Mês
        target_month = today + relativedelta(months=month_offset)
        start_date = target_month.replace(day=1).strftime("%Y-%m-%d")
        
        # Último dia do mês alvo
        next_month_first = (target_month + relativedelta(months=1)).replace(day=1)
        end_date = (next_month_first - relativedelta(days=1)).strftime("%Y-%m-%d")

        url = "https://api.themoviedb.org/3/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "pt-BR",
            "region": "BR",
            "sort_by": "popularity.desc",
            "primary_release_date.gte": start_date,
            "primary_release_date.lte": end_date,
            "page": 1
        }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return f"⚠️ Erro ao consultar TMDB (Status {response.status_code})."

        results = response.json().get("results", [])[:6]
        if not results:
            return "Nenhum filme encontrado para o período selecionado."

        out = []
        for m in results:
            title = m.get("title", "Sem título")
            overview = m.get("overview", "Sinopse não disponível em português.")
            genre_ids = m.get("genre_ids", [])
            genres = [TMDB_GENRES.get(g_id, "Outros") for g_id in genre_ids]
            genre_str = ", ".join(genres) if genres else "Não informado"

            if len(overview) > 160:
                overview = overview[:157] + "..."

            out.append(f"🎬 **{title}**\n* **Gênero:** {genre_str}\n* **Sinopse:** _{overview}_\n")

        return "\n---\n".join(out)
    except Exception as e:
        return f"⚠️ Falha na comunicação com TMDB: {e}"

# ---------------------------------------------------------
# ESTADO DA SESSÃO
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "active_flow" not in st.session_state:
    st.session_state.active_flow = None
if "current_step" not in st.session_state:
    st.session_state.current_step = 0

# Variáveis do fluxo de Gastronomia
if "gastro_cidade" not in st.session_state:
    st.session_state.gastro_cidade = None
if "gastro_bairro" not in st.session_state:
    st.session_state.gastro_bairro = None
if "gastro_culinaria" not in st.session_state:
    st.session_state.gastro_culinaria = None

def reset_flow():
    st.session_state.active_flow = None
    st.session_state.current_step = 0
    st.session_state.gastro_cidade = None
    st.session_state.gastro_bairro = None
    st.session_state.gastro_culinaria = None

def send_user_message(prompt):
    st.session_state.messages.append({"role": "user", "content": prompt})
    reset_flow()
    with st.spinner("Consultando recomendações..."):
        bot_reply = detect_intent(prompt)
        st.session_state.messages.append({"role": "assistant", "content": bot_reply})

# ---------------------------------------------------------
# INTERFACE PRINCIPAL
# ---------------------------------------------------------
st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma opção nos cartões abaixo ou monte seu filtro personalizado:")

# MENU PRINCIPAL (ETAPA 0)
if st.session_state.current_step == 0:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        with st.container(border=True):
            st.markdown("### 🍣 Gastronomia")
            st.write("Filtre por Cidade, Bairro, Culinária e Preço.")
            if st.button("Explorar Gastronomia", key="btn_gastro", use_container_width=True):
                st.session_state.active_flow = "gastronomia"
                st.session_state.current_step = 1
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### 🎬 Cultura & Arte")
            st.write("Consulte filmes em cartaz e futuras estreias.")
            if st.button("Ver Programação de Cinema", key="btn_cultura", use_container_width=True):
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
# FLUXO DE CULTURA & ARTE (CINEMA)
# ---------------------------------------------------------
elif st.session_state.active_flow == "cultura":
    # Passo 1: Seleção de Categoria (Cinema)
    if st.session_state.current_step == 1:
        with st.container(border=True):
            st.subheader("🎭 Cultura & Arte - Passo 1 de 3")
            if st.button("🎬 Cinema", key="btn_cinema_select", use_container_width=True):
                st.session_state.current_step = 2
                st.rerun()
            st.divider()
            if st.button("⬅️ Voltar ao Menu Principal"):
                reset_flow()
                st.rerun()

    # Passo 2: Cartaz ou Estreias
    elif st.session_state.current_step == 2:
        with st.container(border=True):
            st.subheader("🎬 Passo 2 de 3: Escolha o tipo de programação")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🍿 Cartaz", key="btn_cartaz", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("cartaz")
                    st.session_state.messages.append({"role": "user", "content": "Filmes em Cartaz nos cinemas"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            with col_b:
                if st.button("✨ Estreias", key="btn_estreias", use_container_width=True):
                    st.session_state.current_step = 3
                    st.rerun()

            st.divider()
            if st.button("⬅️ Voltar"):
                st.session_state.current_step = 1
                st.rerun()

    # Passo 3: Escolha do Mês para Estreias
    elif st.session_state.current_step == 3:
        with st.container(border=True):
            st.subheader("📅 Passo 3 de 3: Escolha o mês das estreias")
            
            # Cálculo dos meses dinâmicos
            dt_now = datetime.now()
            m1 = dt_now.strftime("%B/%Y").capitalize()
            m2 = (dt_now + relativedelta(months=1)).strftime("%B/%Y").capitalize()
            m3 = (dt_now + relativedelta(months=2)).strftime("%B/%Y").capitalize()

            cols = st.columns(3)
            with cols[0]:
                if st.button(f"📅 {m1} (Mês Atual)", key="m1", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 0)
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m1}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            with cols[1]:
                if st.button(f"📅 {m2} (Próximo Mês)", key="m2", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 1)
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m2}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            with cols[2]:
                if st.button(f"📅 {m3}", key="m3", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 2)
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m3}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Opções"):
                st.session_state.current_step = 2
                st.rerun()

# ---------------------------------------------------------
# FLUXO DE GASTRONOMIA (4 ETAPAS COM BAIRROS ORDENADOS)
# ---------------------------------------------------------
elif st.session_state.active_flow == "gastronomia":
    # Passo 1: Cidade
    if st.session_state.current_step == 1:
        with st.container(border=True):
            st.subheader("🍣 Gastronomia - Passo 1 de 4: Escolha a cidade")
            cols = st.columns(2)
            with cols[0]:
                if st.button("🌊 Niterói", key="g_nit", use_container_width=True):
                    st.session_state.gastro_cidade = "Niterói"
                    st.session_state.current_step = 2
                    st.rerun()
            with cols[1]:
                if st.button("🏙️ Rio de Janeiro", key="g_rio", use_container_width=True):
                    st.session_state.gastro_cidade = "Rio de Janeiro"
                    st.session_state.current_step = 2
                    st.rerun()

            st.divider()
            if st.button("⬅️ Voltar ao Menu Principal"):
                reset_flow()
                st.rerun()

    # Passo 2: Região / Bairro (Ordenados Alfabeticamente)
    elif st.session_state.current_step == 2:
        with st.container(border=True):
            st.subheader(f"📍 Passo 2 de 4: Escolha o bairro em {st.session_state.gastro_cidade}")

            if st.session_state.gastro_cidade == "Rio de Janeiro":
                bairros = [
                    "Aterro do Flamengo", "Botafogo", "Catete", "Copacabana", 
                    "Gávea", "Glória", "Humaitá", "Ipanema", "Jardim Botânico", 
                    "Lagoa", "Laranjeiras", "Leblon", "Leme"
                ]
            else:
                bairros = ["Centro", "Icaraí", "Ingá", "Região Oceânica", "São Francisco"]

            cols = st.columns(4)
            for i, b in enumerate(bairros):
                with cols[i % 4]:
                    if st.button(b, key=f"bairro_{i}", use_container_width=True):
                        st.session_state.gastro_bairro = b
                        st.session_state.current_step = 3
                        st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Cidades"):
                st.session_state.current_step = 1
                st.rerun()

    # Passo 3: Opções de Culinária (Sem Parrilla e Churrasco)
    elif st.session_state.current_step == 3:
        with st.container(border=True):
            st.subheader(f"🍽️ Passo 3 de 4: Escolha a culinária em {st.session_state.gastro_bairro}")

            culinarias = [
                "Italiana", "Japonesa", "Chinesa", "Peruana", 
                "Árabe", "Brasileira", "Asiática em geral", 
                "Hamburgueria", "Pizzaria", "Outras"
            ]

            cols = st.columns(5)
            for i, cul in enumerate(culinarias):
                with cols[i % 5]:
                    if st.button(cul, key=f"cul_{i}", use_container_width=True):
                        st.session_state.gastro_culinaria = cul
                        st.session_state.current_step = 4
                        st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Bairros"):
                st.session_state.current_step = 2
                st.rerun()

    # Passo 4: Faixa de Preço e Disparo para o Dialogflow CX
    elif st.session_state.current_step == 4:
        with st.container(border=True):
            st.subheader(f"💰 Passo 4 de 4: Faixa de preço para culinária {st.session_state.gastro_culinaria} ({st.session_state.gastro_bairro})")

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
                        prompt = f"Recomende restaurantes de culinária {st.session_state.gastro_culinaria} com faixa de preço {simbolo} no bairro {st.session_state.gastro_bairro}, {st.session_state.gastro_cidade}."
                        send_user_message(prompt)
                        st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Culinárias"):
                st.session_state.current_step = 3
                st.rerun()

st.divider()

# ---------------------------------------------------------
# EXIBIÇÃO DO CHAT E INPUT LIVRE
# ---------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Ou digite uma busca específica..."):
    send_user_message(user_input)
    st.rerun()
