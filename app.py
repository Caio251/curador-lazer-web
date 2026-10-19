import streamlit as st
import json
import uuid
import requests
import logging
import os
import re
import random
import unicodedata
from zoneinfo import ZoneInfo
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
GOOGLE_PLACES_API_KEY = st.secrets.get("GOOGLE_PLACES_API_KEY", "")
TIMEZONE = ZoneInfo("America/Sao_Paulo")
logger = logging.getLogger("curador_lazer")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# Mapeamento e tradução de Gêneros do TMDB
TMDB_GENRES = {
    28: "Ação", 12: "Aventura", 16: "Animação", 35: "Comédia", 80: "Crime",
    99: "Documentário", 18: "Drama", 10751: "Família", 14: "Fantasia",
    36: "História", 27: "Terror", 10402: "Música", 9648: "Mistério",
    10749: "Romance", 878: "Ficção Científica", 10770: "Cinema TV",
    53: "Thriller", 10752: "Guerra", 37: "Faroeste"
}

# Mapeamento de meses em português
MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

# ---------------------------------------------------------
# AUTENTICAÇÃO E CLIENTE DIALOGFLOW CX
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
    except Exception:
        logger.exception("Falha na inicialização do cliente Dialogflow")
        return None, "Não foi possível conectar ao serviço de recomendações."

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
            if message.text and message.text.text:
                bot_responses.extend(message.text.text)
                
        return "\n\n".join(bot_responses) if bot_responses else "Não encontrei opções disponíveis no momento para essa busca."
    except Exception:
        logger.exception("Falha na consulta ao Dialogflow")
        return "⚠️ Não foi possível consultar as recomendações agora. Tente novamente."

# ---------------------------------------------------------
# CONSULTA DE FILMES NO TMDB (V3.0 COM PÔSTERES E EXCEÇÕES)
# ---------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_tmdb_movies(mode: str, month_offset: int = 0, _cache_date: str = "") -> str:
    # _cache_date evita reutilizar resultados de outro dia no cache.
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY ausente")
        return "⚠️ Serviço de filmes indisponível no momento."
    if mode not in ("cartaz", "estreias") or month_offset not in (0, 1, 2):
        return "⚠️ Filtro de cinema inválido."

    today = datetime.now(TIMEZONE)

    if mode == "cartaz":
        url = "https://api.themoviedb.org/3/movie/now_playing"
        params = {"api_key": TMDB_API_KEY, "language": "pt-BR", "region": "BR", "page": 1}
    else:
        target_month = today + relativedelta(months=month_offset)
        start_date = target_month.replace(day=1).strftime("%Y-%m-%d")
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
        response.raise_for_status()
        results = response.json().get("results", [])[:6]
        if not results:
            return "Nenhum filme encontrado para o período selecionado."

        out = []
        for m in results:
            title = m.get("title", "Sem título")
            
            # Tratamento de sinopse vazia ou espaços em branco
            overview_raw = m.get("overview", "")
            overview = overview_raw.strip() if overview_raw and overview_raw.strip() else "Sinopse não disponível em português."
            
            genre_ids = m.get("genre_ids", [])
            genres = [TMDB_GENRES.get(g_id, "Outros") for g_id in genre_ids]
            genre_str = ", ".join(genres) if genres else "Não informado"
            
            poster_path = m.get("poster_path")
            poster_markdown = f"![Pôster](https://image.tmdb.org/t/p/w185{poster_path})\n\n" if poster_path else ""

            out.append(f"{poster_markdown}🎬 **{title}**\n* **Gênero:** {genre_str}\n* **Sinopse:** _{overview}_\n")

        return "\n---\n".join(out)
    except requests.exceptions.Timeout:
        return "⚠️ A consulta ao TMDB demorou muito para responder. Tente novamente em instantes."
    except (requests.exceptions.RequestException, ValueError, TypeError, AttributeError):
        logger.exception("Falha na consulta ou interpretação dos dados TMDB")
        return "⚠️ Não foi possível consultar os filmes agora. Tente novamente."

# ---------------------------------------------------------
# GOOGLE PLACES (NEW) — BUSCA GASTRONÔMICA
# Sem cache ou armazenamento persistente de dados do Places.
# ---------------------------------------------------------
# Validação conservadora do endereço retornado pelo Google Places.
# "Região Oceânica" não é bairro administrativo: corresponde a vários bairros.
BAIRROS_REGIAO_OCEANICA = (
    "Itaipu", "Itacoatiara", "Piratininga", "Camboinhas", "Engenho do Mato",
    "Serra Grande", "Maravista", "Santo Antônio", "Jacaré", "Cafubá"
)


def endereco_na_regiao(endereco: str, cidade: str, bairro: str) -> bool:
    """Aceita apenas endereços que mencionem cidade e bairro explicitamente.

    É um filtro conservador por texto, não uma verificação de limites oficiais.
    """
    if not endereco or endereco == "Endereço indisponível":
        return False
    e = normalizar(endereco)
    if normalizar(cidade) not in e:
        return False
    if bairro == "Qualquer Bairro":
        return True
    if bairro == "Região Oceânica":
        return any(normalizar(b) in e for b in BAIRROS_REGIAO_OCEANICA)
    # Evita correspondências parciais como 'Leme' dentro de outra palavra.
    return bool(re.search(r"(?<!\w)" + re.escape(normalizar(bairro)) + r"(?!\w)", e))


def fetch_places(cidade: str, bairro: str, culinaria: str):
    if not GOOGLE_PLACES_API_KEY:
        return None, "A chave GOOGLE_PLACES_API_KEY não está configurada nos Secrets."

    local = f"{bairro}, {cidade}" if bairro != "Qualquer Bairro" else cidade
    termo = "restaurantes" if culinaria == "Outras" else f"restaurantes de culinária {culinaria}"
    payload = {
        "textQuery": f"{termo} em {local}, RJ, Brasil",
        "languageCode": "pt-BR",
        "regionCode": "BR",
        "pageSize": 20,
        "includedType": "restaurant",
        "strictTypeFiltering": False,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.googleMapsUri,"
            "places.businessStatus"
        ),
    }
    try:
        response = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            json=payload, headers=headers, timeout=12
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Formato de resposta inesperado")
        places = []
        for place in data.get("places", []):
            if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                continue
            places.append({
                "id": place.get("id", ""),
                "nome": place.get("displayName", {}).get("text", "Nome indisponível"),
                "endereco": place.get("formattedAddress", "Endereço indisponível"),
                "avaliacao": place.get("rating"),
                "total_avaliacoes": place.get("userRatingCount"),
                "maps_url": place.get("googleMapsUri", ""),
                "situacao": place.get("businessStatus", ""),
            })
        logger.info("Consulta Places concluída: %d resultados", len(places))
        return places, None
    except (requests.exceptions.RequestException, ValueError, TypeError, KeyError):
        logger.exception("Falha na consulta Places")
        return None, "Não foi possível consultar os restaurantes. Verifique a API, a chave, o faturamento e os logs."


def escolher_restaurantes(candidatos, anteriores=(), quantidade=3):
    """Sorteia sem reposição; evita a seleção anterior quando possível."""
    unicos = list({p["id"]: p for p in candidatos if p.get("id")}.values())
    anteriores = set(anteriores)
    novos = [p for p in unicos if p["id"] not in anteriores]
    rng = random.SystemRandom()
    if len(novos) >= quantidade:
        return rng.sample(novos, quantidade)
    # Prioriza inéditos, mas completa a lista quando a base é pequena.
    selecionados = rng.sample(novos, len(novos))
    restantes = [p for p in unicos if p["id"] in anteriores]
    selecionados.extend(rng.sample(restantes, min(quantidade - len(selecionados), len(restantes))))
    return selecionados


def pesquisar_restaurantes(cidade, bairro, culinaria, preco_label="Não informado", repetir=False):
    """Fluxo único para o menu, a busca livre e o botão de nova seleção."""
    filtros = {"cidade": cidade, "bairro": bairro, "culinaria": culinaria, "preco": preco_label}
    anteriores = st.session_state.get("last_place_ids", []) if st.session_state.get("last_place_filters") == filtros else []
    st.session_state.messages.append({"role": "user", "content": (
        "Surpreenda-me novamente com outros restaurantes" if repetir else
        f"Restaurantes de culinária {culinaria} em {bairro if bairro != 'Qualquer Bairro' else cidade} ({cidade})"
    )})
    with st.spinner("Consultando restaurantes no Google Places..."):
        places, error = fetch_places(cidade, bairro, culinaria)
    if error:
        st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error}"})
        return
    # Não relaxar silenciosamente o bairro: resultados sem endereço comprovável
    # são excluídos. A API pode retornar locais de bairros vizinhos.
    places_validos = [p for p in places if endereco_na_regiao(p["endereco"], cidade, bairro)]
    excluidos = len(places) - len(places_validos)
    escolhidos = escolher_restaurantes(places_validos, anteriores)
    st.session_state.last_place_filters = filtros
    st.session_state.last_place_ids = [p["id"] for p in escolhidos]
    st.session_state.messages.append({
        "role": "assistant", "kind": "places", "places": escolhidos,
        **filtros,
        "total_candidatos": len(places_validos),
        "total_excluidos": excluidos,
    })


def search_gastronomia(preco_label: str):
    pesquisar_restaurantes(st.session_state.gastro_cidade, st.session_state.gastro_bairro,
                           st.session_state.gastro_culinaria, preco_label)
    reset_flow()


def normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


BAIRROS_RIO = ["Aterro do Flamengo", "Botafogo", "Catete", "Copacabana", "Gávea",
               "Glória", "Humaitá", "Ipanema", "Jardim Botânico", "Lagoa",
               "Laranjeiras", "Leblon", "Leme"]
BAIRROS_NIT = ["Centro", "Icaraí", "Ingá", "Região Oceânica", "São Francisco"]
CULINARIAS = ["Italiana", "Japonesa", "Chinesa", "Peruana", "Árabe", "Brasileira",
             "Asiática em geral", "Hamburgueria", "Pizzaria"]


def extrair_filtros_gastronomia(texto, filtros_anteriores=None):
    """Roteamento conservador: não supõe cidade para pedidos sem contexto."""
    t = normalizar(texto)
    anterior = filtros_anteriores or {}
    contexto = bool(anterior)
    repeticao = bool(re.search(r"\b(outro|outra|outros|outras|novamente|mais opcoes|surpreenda)\b", t))
    palavras = ("restaurante", "comer", "jantar", "almocar", "almoco", "gastronomia",
                "culinaria", "hamburguer", "pizza", "sushi", "sushis", "rodizio")
    culinaria = next((c for c in CULINARIAS if normalizar(c) in t), None)
    if "japones" in t or "japonesa" in t or "sushi" in t:
        culinaria = "Japonesa"
    elif "italiano" in t or "italiana" in t:
        culinaria = "Italiana"
    elif "chines" in t or "chinesa" in t:
        culinaria = "Chinesa"
    elif "arabe" in t:
        culinaria = "Árabe"
    elif "hamburguer" in t:
        culinaria = "Hamburgueria"
    elif "pizza" in t:
        culinaria = "Pizzaria"
    eh_gastro = any(p in t for p in palavras) or bool(culinaria) or (contexto and repeticao)
    if not eh_gastro:
        return None
    cidade = None
    if "niteroi" in t:
        cidade = "Niterói"
    elif "rio de janeiro" in t or "carioca" in t:
        cidade = "Rio de Janeiro"
    bairro = None
    for b in BAIRROS_RIO + BAIRROS_NIT:
        if normalizar(b) in t:
            bairro = b
            if not cidade:
                cidade = ("Niterói" if b in BAIRROS_NIT and b != "Centro" else
                          None if b == "Centro" else "Rio de Janeiro")
            break
    cidade = cidade or anterior.get("cidade")
    bairro = bairro or (anterior.get("bairro") if cidade == anterior.get("cidade") else "Qualquer Bairro")
    culinaria = culinaria or anterior.get("culinaria") or "Outras"
    if not cidade:
        return {"needs_city": True, "culinaria": culinaria}
    return {"cidade": cidade, "bairro": bairro or "Qualquer Bairro", "culinaria": culinaria,
            "preco": anterior.get("preco", "Não informado")}


# ---------------------------------------------------------
# ESTADO DA SESSÃO E REINICIALIZAÇÃO
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "active_flow" not in st.session_state:
    st.session_state.active_flow = None
if "current_step" not in st.session_state:
    st.session_state.current_step = 0

if "gastro_cidade" not in st.session_state:
    st.session_state.gastro_cidade = None
if "gastro_bairro" not in st.session_state:
    st.session_state.gastro_bairro = None
if "gastro_culinaria" not in st.session_state:
    st.session_state.gastro_culinaria = None

def clear_conversation():
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.last_place_filters = None
    st.session_state.last_place_ids = []
    reset_flow()


def reset_flow():
    st.session_state.active_flow = None
    st.session_state.current_step = 0
    st.session_state.gastro_cidade = None
    st.session_state.gastro_bairro = None
    st.session_state.gastro_culinaria = None

def send_user_message(prompt):
    filtros = extrair_filtros_gastronomia(prompt, st.session_state.get("last_place_filters"))
    if filtros:
        if filtros.get("needs_city"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.messages.append({"role": "assistant", "content":
                "Para pesquisar restaurantes reais, informe a cidade (Rio de Janeiro ou Niterói) e, se desejar, o bairro."})
        else:
            pesquisar_restaurantes(
                cidade=filtros["cidade"],
                bairro=filtros["bairro"],
                culinaria=filtros["culinaria"],
                preco_label=filtros.get("preco", "Não informado"),
            )
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("Consultando recomendações..."):
            bot_reply = detect_intent(prompt)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    reset_flow()

# ---------------------------------------------------------
# BARRA LATERAL (SIDEBAR)
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Opções")
    if st.button("🗑️ Limpar Conversa", use_container_width=True):
        clear_conversation()
        st.rerun()

# ---------------------------------------------------------
# INTERFACE PRINCIPAL
# ---------------------------------------------------------
st.title("🎭 Curador de Lazer e Cultura")
st.caption("Escolha uma opção nos cartões abaixo ou monte seu filtro personalizado:")

# Campo inline: evita que o chat fixo no rodapé provoque saltos de rolagem.
with st.container():
    with st.form("busca_livre_form", clear_on_submit=True):
        entrada_livre = st.text_input("Busca livre", placeholder="Ex.: restaurantes japoneses em Botafogo")
        enviar = st.form_submit_button("Pesquisar")
    if enviar and entrada_livre.strip():
        send_user_message(entrada_livre.strip())
        st.rerun()

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

    elif st.session_state.current_step == 2:
        with st.container(border=True):
            st.subheader("🎬 Passo 2 de 3: Escolha o tipo de programação")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🍿 Cartaz", key="btn_cartaz", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("cartaz", _cache_date=datetime.now(TIMEZONE).date().isoformat())
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

    elif st.session_state.current_step == 3:
        with st.container(border=True):
            st.subheader("📅 Passo 3 de 3: Escolha o mês das estreias")
            
            dt_now = datetime.now(TIMEZONE)
            dt_m2 = dt_now + relativedelta(months=1)
            dt_m3 = dt_now + relativedelta(months=2)

            # Nomes dos meses garantidos em Português
            m1 = f"{MESES_PT[dt_now.month]}/{dt_now.year}"
            m2 = f"{MESES_PT[dt_m2.month]}/{dt_m2.year}"
            m3 = f"{MESES_PT[dt_m3.month]}/{dt_m3.year}"

            cols = st.columns(3)
            with cols[0]:
                if st.button(f"📅 {m1} (Mês Atual)", key="m1", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 0, _cache_date=datetime.now(TIMEZONE).date().isoformat())
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m1}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            with cols[1]:
                if st.button(f"📅 {m2} (Próximo Mês)", key="m2", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 1, _cache_date=datetime.now(TIMEZONE).date().isoformat())
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m2}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            with cols[2]:
                if st.button(f"📅 {m3}", key="m3", use_container_width=True):
                    bot_reply = fetch_tmdb_movies("estreias", 2, _cache_date=datetime.now(TIMEZONE).date().isoformat())
                    st.session_state.messages.append({"role": "user", "content": f"Estreias de cinema em {m3}"})
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    reset_flow()
                    st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Opções"):
                st.session_state.current_step = 2
                st.rerun()

# ---------------------------------------------------------
# FLUXO DE GASTRONOMIA (4 ETAPAS COM BAIRROS)
# ---------------------------------------------------------
elif st.session_state.active_flow == "gastronomia":
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

    elif st.session_state.current_step == 2:
        with st.container(border=True):
            st.subheader(f"📍 Passo 2 de 4: Escolha o bairro em {st.session_state.gastro_cidade}")

            if st.session_state.gastro_cidade == "Rio de Janeiro":
                bairros = [
                    "Qualquer Bairro", "Aterro do Flamengo", "Botafogo", "Catete", "Copacabana", 
                    "Gávea", "Glória", "Humaitá", "Ipanema", "Jardim Botânico", 
                    "Lagoa", "Laranjeiras", "Leblon", "Leme"
                ]
            else:
                bairros = ["Qualquer Bairro", "Centro", "Icaraí", "Ingá", "Região Oceânica", "São Francisco"]

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

    elif st.session_state.current_step == 3:
        with st.container(border=True):
            bairro_txt = f"em {st.session_state.gastro_bairro}" if st.session_state.gastro_bairro != "Qualquer Bairro" else f"em {st.session_state.gastro_cidade}"
            st.subheader(f"🍽️ Passo 3 de 4: Escolha a culinária {bairro_txt}")

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

    elif st.session_state.current_step == 4:
        with st.container(border=True):
            st.subheader(f"💰 Passo 4 de 4: Preferência de preço ({st.session_state.gastro_culinaria})")
            st.caption("Nesta entrega, o preço é apenas uma preferência registrada; a API ainda não verifica nem filtra valores de cardápio.")

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
                        search_gastronomia(rotulo)
                        st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Culinárias"):
                st.session_state.current_step = 3
                st.rerun()

st.divider()

# Histórico em região delimitada, sem chat_input fixo no rodapé.
st.subheader("Histórico de recomendações")
with st.container(height=420, border=True):
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg.get("kind") == "places":
                st.markdown("**Três sugestões sorteadas do Google Places**")
                st.caption(f"Busca: {msg['culinaria']} · {msg['bairro']} · {msg['cidade']}")
                st.caption("O preço não foi validado. Confirme localização, funcionamento e valores antes de visitar.")
                if not msg["places"]:
                    st.info("Não encontrei restaurantes cujo endereço confirme a região escolhida. Tente outro bairro ou 'Qualquer Bairro'.")
                for place in msg["places"]:
                    with st.container(border=True):
                        st.markdown(f"**{place['nome']}**")
                        st.write(place["endereco"])
                        if place["avaliacao"] is not None:
                            st.write(f"Avaliação Google: {place['avaliacao']}/5 · {place['total_avaliacoes'] or 0} avaliações")
                        if place["situacao"] == "CLOSED_TEMPORARILY":
                            st.warning("Marcado como temporariamente fechado")
                        if place["maps_url"]:
                            st.link_button("Ver no Google Maps", place["maps_url"])
                if idx == len(st.session_state.messages) - 1 and msg["places"]:
                    if st.button("Surpreenda-me novamente", key=f"repeat_{idx}"):
                        pesquisar_restaurantes(msg["cidade"], msg["bairro"], msg["culinaria"], msg["preco"], repetir=True)
                        st.rerun()
                st.caption(f"Dados: Google Maps. {msg.get('total_excluidos', 0)} resultado(s) descartado(s) por não confirmar a região no endereço.")
                st.caption("Filtro geográfico conservador por endereço; não equivale a limites oficiais de bairros. O Google pode omitir o bairro no endereço de locais válidos.")
            else:
                st.markdown(msg["content"])
