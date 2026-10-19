import streamlit as st
import requests

TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")

def fetch_tmdb_movies(category: str) -> str:
    """
    Busca filmes na API do TMDB com suporte a filmes nacionais e internacionais.
    Categorias aceitas: 'Em cartaz', 'Pré-venda', 'Estreias'
    """
    if not TMDB_API_KEY:
        return "⚠️ Chave de API do TMDB não configurada nos Secrets."

    # Define o endpoint com base na seleção
    if category == "Em cartaz":
        url = "https://api.themoviedb.org/3/movie/now_playing"
    elif category in ["Pré-venda", "Estreias"]:
        url = "https://api.themoviedb.org/3/movie/upcoming"
    else:
        url = "https://api.themoviedb.org/3/movie/popular"

    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR",
        "region": "BR",
        "page": 1
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return f"⚠️ Erro ao consultar TMDB (Status {response.status_code})."

        data = response.json()
        results = data.get("results", [])[:6] # Pega os 6 principais filmes

        if not results:
            return "Nenhum filme encontrado para essa categoria no momento."

        out = [f"🎬 **Filmes ({category}) nos cinemas do Brasil:**\n"]
        for m in results:
            title = m.get("title", "Sem título")
            overview = m.get("overview", "Sem sinopse disponível.")
            release_date = m.get("release_date", "Data N/A")
            rating = m.get("vote_average", 0)

            # Trunca sinopse longa
            if len(overview) > 150:
                overview = overview[:147] + "..."

            out.append(f"• **{title}** (Estreia: {release_date} | Nota: {rating:.1f}/10)\n  _{overview}_\n")

        return "\n".join(out)
    except Exception as e:
        return f"⚠️ Falha na conexão com TMDB: {e}"
