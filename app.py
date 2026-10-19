import streamlit as st
import json
import uuid
import requests
import logging
import os
import re
import random
import math
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


# Pontos aproximados de referência, não polígonos oficiais de bairros.
# Coordenadas (latitude, longitude) em graus decimais.
REFERENCIAS = {
    "Rio de Janeiro": {
        "Aterro do Flamengo": (-22.9323, -43.1747),
        "Botafogo": (-22.9519, -43.1864),
        "Catete": (-22.9256, -43.1764),
        "Copacabana": (-22.9711, -43.1822),
        "Gávea": (-22.9819, -43.2380),
        "Glória": (-22.9217, -43.1750),
        "Humaitá": (-22.9556, -43.2003),
        "Ipanema": (-22.9838, -43.2045),
        "Jardim Botânico": (-22.9669, -43.2247),
        "Lagoa": (-22.9714, -43.2110),
        "Laranjeiras": (-22.9350, -43.1880),
        "Leblon": (-22.9836, -43.2233),
        "Leme": (-22.9636, -43.1678),
    },
    "Niterói": {
        "Centro": (-22.8943, -43.1151),
        "Icaraí": (-22.9056, -43.1094),
        "Ingá": (-22.9051, -43.1243),
        "São Francisco": (-22.9176, -43.0922),
        # Região Oceânica é extensa; não tem um centro adequado para raio único.
    },
}


def distancia_km(lat1, lon1, lat2, lon2):
    """Distância em linha reta pelo método de Haversine."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl / 2)**2
    return 2*r*math.asin(min(1, math.sqrt(a)))


def filtrar_por_distancia(places, cidade, bairro, raio_km):
    """Sem raio mantém candidatos; com raio exige coordenadas verificáveis."""
    if raio_km is None:
        return places
    referencia = REFERENCIAS.get(cidade, {}).get(bairro)
    if referencia is None:
        return places  # UI impede raio nesses casos
    selecionados = []
    for p in places:
        lat, lon = p.get("latitude"), p.get("longitude")
        if lat is None or lon is None:
            continue
        km = distancia_km(*referencia, lat, lon)
        if km <= raio_km:
            selecionados.append({**p, "distancia_km": round(km, 2)})
    return selecionados


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
            "places.businessStatus,places.location,places.priceLevel,places.priceRange"
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
                "latitude": place.get("location", {}).get("latitude"),
                "longitude": place.get("location", {}).get("longitude"),
                "nivel_preco": place.get("priceLevel"),
                "faixa_preco": place.get("priceRange"),
            })
        logger.info("Consulta Places concluída: %d resultados", len(places))
        return places, None
    except (requests.exceptions.RequestException, ValueError, TypeError, KeyError):
        logger.exception("Falha na consulta Places")
        return None, "Não foi possível consultar os restaurantes. Verifique a API, a chave, o faturamento e os logs."


ORCAMENTOS = {
    "Até R$ 50": (0, 50),
    "R$ 50–80": (50, 80),
    "R$ 80–120": (80, 120),
    "R$ 120–200": (120, 200),
    "Acima de R$ 200": (200, None),
    "Sem preferência": (None, None),
}


def valor_monetario(money):
    """Converte objeto Money da API em BRL, sem inferir preço por pessoa."""
    if not isinstance(money, dict) or money.get("currencyCode") != "BRL":
        return None
    try:
        return float(money.get("units", 0)) + float(money.get("nanos", 0)) / 1e9
    except (ValueError, TypeError):
        return None


def faixa_informada(place):
    price = place.get("faixa_preco") or {}
    low = valor_monetario(price.get("startPrice"))
    high = valor_monetario(price.get("endPrice"))
    return low, high


def classificar_orcamento(place, orcamento):
    """Classifica evidência monetária do Places; não comprova gasto por pessoa.

    Valores: compativel, parcial, desconhecido, incompatível, sem_filtro.
    Uma faixa sobreposta é parcial; uma faixa inteiramente contida é compatível.
    """
    if orcamento not in ORCAMENTOS or orcamento == "Sem preferência":
        return "sem_filtro"
    minimo, maximo = ORCAMENTOS[orcamento]
    low, high = faixa_informada(place)
    if low is None and high is None:
        return "desconhecido"
    if maximo is not None and low is not None and low > maximo:
        return "incompatível"
    if minimo is not None and high is not None and high < minimo:
        return "incompatível"
    # Só considerar totalmente compatível se os dois extremos são conhecidos.
    if (low is not None and high is not None
            and (minimo is None or low >= minimo)
            and (maximo is None or high <= maximo)):
        return "compativel"
    return "parcial"


def compatibilidade_orcamento(place, orcamento):
    """Compatibilidade histórica para preservar chamadas existentes."""
    classe = classificar_orcamento(place, orcamento)
    return classe != "incompatível", classe in ("compativel", "parcial")


def pontuacao(place, orcamento):
    """Peso de sorteio: avaliação suavizada e confiança no volume de avaliações."""
    rating = place.get("avaliacao")
    count = place.get("total_avaliacoes") or 0
    try:
        rating = max(0.0, min(5.0, float(rating)))
        count = max(0, int(count))
    except (TypeError, ValueError):
        rating, count = 0.0, 0
    media_suavizada = (rating * count + 4.0 * 50) / (count + 50)
    _, comprovado = compatibilidade_orcamento(place, orcamento)
    return max(0.1, (media_suavizada / 5.0) ** 4 * (1.15 if comprovado else 1.0))


def escolher_restaurantes(candidatos, anteriores=(), quantidade=3, orcamento="Sem preferência"):
    """Prioriza evidência de preço; sorteia por qualidade em cada categoria.

    Dentro de cada categoria, prefere restaurantes não mostrados na última rodada.
    """
    unicos = list({p["id"]: p for p in candidatos if p.get("id")}.values())
    anteriores = set(anteriores)
    rng = random.SystemRandom()
    selecionados = []
    grupos = ("compativel", "parcial", "desconhecido") if orcamento in ORCAMENTOS and orcamento != "Sem preferência" else ("sem_filtro",)
    for categoria in grupos:
        candidatos_categoria = [p for p in unicos if classificar_orcamento(p, orcamento) == categoria]
        for grupo in ([p for p in candidatos_categoria if p["id"] not in anteriores],
                      [p for p in candidatos_categoria if p["id"] in anteriores]):
            grupo = grupo.copy()
            while grupo and len(selecionados) < quantidade:
                pesos = [pontuacao(p, orcamento) for p in grupo]
                escolhido = rng.choices(grupo, weights=pesos, k=1)[0]
                selecionados.append(escolhido)
                grupo.remove(escolhido)
        if len(selecionados) >= quantidade:
            break
    return selecionados


def pesquisar_restaurantes(cidade, bairro, culinaria, preco_label="Não informado", repetir=False, raio_km=None):
    """Fluxo único para o menu, a busca livre e o botão de nova seleção."""
    filtros = {"cidade": cidade, "bairro": bairro, "culinaria": culinaria, "preco": preco_label, "raio_km": raio_km}
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
    places_validos = filtrar_por_distancia(places_validos, cidade, bairro, raio_km)
    orcamento = preco_label if preco_label in ORCAMENTOS else "Sem preferência"
    places_validos = [p for p in places_validos if compatibilidade_orcamento(p, orcamento)[0]]
    escolhidos = escolher_restaurantes(places_validos, anteriores, orcamento=orcamento)
    st.session_state.last_place_filters = filtros
    st.session_state.last_place_ids = [p["id"] for p in escolhidos]
    st.session_state.messages.append({
        "role": "assistant", "kind": "places", "places": escolhidos,
        **filtros,
        "total_candidatos": len(places_validos),
        "total_excluidos": excluidos,
        "total_sem_preco": sum(classificar_orcamento(p, orcamento) == "desconhecido" for p in places_validos),
    })


def search_gastronomia(preco_label: str):
    raio = st.session_state.get("raio_selecionado")
    pesquisar_restaurantes(st.session_state.gastro_cidade, st.session_state.gastro_bairro,
                           st.session_state.gastro_culinaria, preco_label, raio_km=raio)
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
    st.session_state.confirmar_limpeza = False


def reset_flow():
    st.session_state.active_flow = None
    st.session_state.current_step = 0
    st.session_state.gastro_cidade = None
    st.session_state.gastro_bairro = None
    st.session_state.gastro_culinaria = None
    st.session_state.raio_selecionado = None

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
                raio_km=filtros.get("raio_km"),
            )
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("Consultando recomendações..."):
            bot_reply = detect_intent(prompt)
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    reset_flow()

# ---------------------------------------------------------
# APRESENTAÇÃO GASTRONÔMICA — JUSTIFICATIVAS VERIFICÁVEIS
# ---------------------------------------------------------
def resumo_restaurante(place, culinaria):
    """Descreve somente a categoria buscada, sem inventar características do local."""
    categoria = (culinaria or "").strip()
    if categoria and categoria != "Outras":
        return (f"Restaurante encontrado em uma busca por {categoria.lower()}. "
                "A especialidade e os pratos disponíveis devem ser confirmados no cardápio.")
    return "Restaurante encontrado na região selecionada. Consulte o cardápio para conhecer a proposta gastronômica."


def justificativa_restaurante(place, orcamento):
    """Explica a seleção a partir de sinais efetivamente recebidos do Google Places."""
    razoes = ["Corresponde aos filtros de localização da pesquisa"]
    nota = place.get("avaliacao")
    total = place.get("total_avaliacoes") or 0
    if isinstance(nota, (int, float)) and total:
        razoes.append(f"tem nota {nota:g}/5 com {total} avaliações no Google")
    classe = classificar_orcamento(place, orcamento)
    if classe == "compativel":
        razoes.append("a faixa de preços informada está dentro do orçamento de referência")
    elif classe == "parcial":
        razoes.append("a faixa de preços informada se sobrepõe ao orçamento de referência")
    return "; ".join(razoes) + "."


def formatar_preco_restaurante(place):
    low, high = faixa_informada(place)
    def reais(valor):
        return f"R$ {valor:,.0f}".replace(",", ".")
    if low is not None and high is not None:
        return f"{reais(low)} a {reais(high)}"
    if low is not None:
        return f"A partir de {reais(low)}"
    if high is not None:
        return f"Até {reais(high)}"
    if place.get("nivel_preco"):
        return "Nível de preço disponível; valor em reais não informado"
    return "Não informado pelo Google"


# ---------------------------------------------------------
# BARRA LATERAL (SIDEBAR)
# ---------------------------------------------------------
# Ajustes visuais discretos: preservam o tema configurado pelo usuário.
st.markdown("""
<style>
.block-container {max-width: 1160px; padding-top: 1.5rem; padding-bottom: 2.5rem;}
[data-testid="stVerticalBlock"] {gap: .75rem;}
[data-testid="stButton"] button {min-height: 2.65rem; border-radius: .65rem;}
[data-testid="stForm"] {border-radius: .85rem;}
@media (max-width: 640px) {
  .block-container {padding: 1rem .85rem 2rem;}
  h1 {font-size: 1.8rem !important;}
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Preferências")
    st.caption("Gerencie sua sessão e as recomendações exibidas.")
    st.checkbox("Confirmar limpeza do histórico", key="confirmar_limpeza",
                help="Marque esta opção antes de apagar a conversa.")
    if st.button("🗑️ Limpar histórico", use_container_width=True,
                 disabled=not st.session_state.get("confirmar_limpeza", False)):
        clear_conversation()
        st.rerun()
    st.divider()
    st.caption("🔒 A limpeza remove o histórico desta sessão e reinicia o contexto das buscas.")

st.title("🎭 Curador de Lazer e Cultura")
st.caption("Descubra restaurantes, filmes e passeios. Escolha uma categoria ou faça uma busca livre.")

with st.form("busca_livre_form", clear_on_submit=True):
    entrada_livre = st.text_input("🔎 O que você procura?", placeholder="Ex.: restaurantes japoneses em Botafogo")
    enviar = st.form_submit_button("🔎 Pesquisar", use_container_width=True)
if enviar and entrada_livre.strip():
    send_user_message(entrada_livre.strip())
    st.rerun()

# MENU PRINCIPAL (ETAPA 0)
if st.session_state.current_step == 0:
    st.subheader("✨ Explore por categoria")
    col1, col2, col3, col4 = st.columns(4, gap="medium")

    with col1:
        with st.container(border=True, height=190):
            st.markdown("### 🍣 Gastronomia")
            st.write("Escolha cidade, bairro, culinária e orçamento.")
            if st.button("Explorar restaurantes", key="btn_gastro", use_container_width=True):
                st.session_state.active_flow = "gastronomia"
                st.session_state.current_step = 1
                st.rerun()

    with col2:
        with st.container(border=True, height=190):
            st.markdown("### 🎬 Cultura e Arte")
            st.write("Veja filmes em cartaz e próximas estreias.")
            if st.button("Ver filmes", key="btn_cultura", use_container_width=True):
                st.session_state.active_flow = "cultura"
                st.session_state.current_step = 1
                st.rerun()

    with col3:
        with st.container(border=True, height=190):
            st.markdown("### 🌳 Ao ar livre")
            st.write("Parques, praças, trilhas e natureza.")
            if st.button("Explorar passeios", key="btn_parques", use_container_width=True):
                send_user_message("Recomende passeios ao ar livre e parques")
                st.rerun()

    with col4:
        with st.container(border=True, height=190):
            st.markdown("### 🎉 Fim de semana")
            st.write("Encontre ideias para sábado e domingo.")
            if st.button("Ver sugestões", key="btn_fds", use_container_width=True):
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
            st.subheader(f"💰 Passo 4 de 4: Orçamento ({st.session_state.gastro_culinaria})")
            st.caption("As faixas do Google Places são indicativas e não representam necessariamente o gasto por pessoa. Locais sem informação de preço são alternativas, priorizadas apenas depois das opções com faixa monetária compatível.")

            bairro_atual = st.session_state.gastro_bairro
            referencia_disponivel = bairro_atual in REFERENCIAS.get(st.session_state.gastro_cidade, {})
            if referencia_disponivel:
                opcoes_raio = {"Somente bairro (sem raio)": None, "Até 1 km": 1.0,
                               "Até 2 km": 2.0, "Até 5 km": 5.0}
                escolha_raio = st.selectbox("Distância máxima em linha reta a partir do centro aproximado do bairro", list(opcoes_raio), key="seletor_raio")
                st.session_state.raio_selecionado = opcoes_raio[escolha_raio]
                st.caption("O filtro de bairro continua obrigatório. Distância não representa trajeto a pé ou de carro.")
            else:
                st.session_state.raio_selecionado = None
                st.caption("Raio indisponível para Qualquer Bairro e Região Oceânica; mantém-se o filtro por endereço.")

            orcamento = st.selectbox("Orçamento desejado por pessoa (referência)", list(ORCAMENTOS), index=5)
            if st.button("Buscar restaurantes", use_container_width=True):
                search_gastronomia(orcamento)
                st.rerun()

            st.divider()
            if st.button("⬅️ Voltar para Culinárias"):
                st.session_state.current_step = 3
                st.rerun()

st.divider()

# Histórico em região delimitada, sem chat_input fixo no rodapé.
st.subheader("📋 Recomendações")
if st.session_state.messages:
    st.caption("As recomendações mais recentes aparecem primeiro. O histórico fica nesta área para evitar rolagens longas na página.")
    mostrar_tudo = st.checkbox("📚 Mostrar todo o histórico", value=False, key="mostrar_historico")
    mensagens = list(enumerate(st.session_state.messages))
    if not mostrar_tudo:
        mensagens = mensagens[-2:]
    mensagens.reverse()
else:
    st.info("Suas recomendações aparecerão aqui depois da primeira pesquisa.")
    mensagens = []
with st.container(height=510, border=True):
    for idx, msg in mensagens:
        with st.chat_message(msg["role"]):
            if msg.get("kind") == "places":
                st.markdown(f"**🍽️ Restaurantes sugeridos: {len(msg['places'])}**")
                st.caption(f"Busca: {msg['culinaria']} · {msg['bairro']} · {msg['cidade']}")
                if msg.get("raio_km") is not None:
                    st.caption(f"Raio máximo: {msg['raio_km']:g} km do ponto aproximado do bairro")
                st.caption("💰 Orçamento: " + str(msg.get("preco", "Sem preferência")) + ". Preços de referência; confirme o valor por pessoa no cardápio.")
                if not msg["places"]:
                    st.info("Nenhum restaurante correspondeu aos filtros escolhidos. Tente outro bairro, aumente a distância ou escolha uma faixa de preço mais ampla.")
                for place in msg["places"]:
                    with st.container(border=True):
                        st.markdown(f"### 🍽️ {place['nome']}")
                        st.caption(f"📍 {msg['bairro']} · {msg['cidade']} — região selecionada na pesquisa")

                        st.markdown("**🍴 O que é**")
                        st.write(resumo_restaurante(place, msg.get("culinaria")))
                        st.markdown("**💡 Por que foi selecionado**")
                        st.write(justificativa_restaurante(place, msg.get("preco", "Sem preferência")))

                        coluna_preco, coluna_nota = st.columns(2, gap="medium")
                        with coluna_preco:
                            st.markdown("**💰 Preço de referência**")
                            st.write(formatar_preco_restaurante(place))
                        with coluna_nota:
                            st.markdown("**⭐ Avaliação no Google**")
                            if place.get("avaliacao") is not None:
                                st.write(f"{place['avaliacao']}/5 · {place.get('total_avaliacoes') or 0} avaliações")
                            else:
                                st.write("Não informada")

                        st.markdown("**📍 Endereço e acesso**")
                        st.write(place["endereco"])
                        if place.get("distancia_km") is not None:
                            st.caption(f"Distância em linha reta: {place['distancia_km']:.2f} km do ponto de referência do bairro.")
                        classe_preco = classificar_orcamento(place, msg.get("preco", "Sem preferência"))
                        if classe_preco == "desconhecido":
                            st.caption("Não há faixa monetária verificada para o orçamento escolhido.")
                        elif classe_preco == "parcial":
                            st.caption("A faixa de preço é parcial ou incompleta; confirme os valores antes de visitar.")
                        st.caption("Os preços são indicativos e não representam necessariamente o gasto por pessoa.")
                        if place.get("situacao") == "CLOSED_TEMPORARILY":
                            st.warning("O Google informa que este local está temporariamente fechado.")
                        if place.get("maps_url"):
                            st.link_button("🗺️ Ver no Google Maps", place["maps_url"], use_container_width=True)
                if idx == len(st.session_state.messages) - 1 and msg["places"]:
                    if st.button("🎲 Mostrar outras opções", key=f"repeat_{idx}", use_container_width=True):
                        pesquisar_restaurantes(msg["cidade"], msg["bairro"], msg["culinaria"], msg["preco"], repetir=True, raio_km=msg.get("raio_km"))
                        st.rerun()
                st.caption(f"Dados: Google Maps. {msg.get('total_excluidos', 0)} resultado(s) descartado(s) por não confirmar a região no endereço.")
                st.caption("📍 A localização é verificada pelo endereço informado pelo Google e pode não refletir os limites oficiais dos bairros.")
            else:
                st.markdown(msg["content"])
