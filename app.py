from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import requests

app = Flask(__name__)
app.secret_key = "nancy_secret_key"

TMDB_API_KEY = "0116eadbeb85dd7ca5aec701cbf704e1"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

# ---------- LOAD LOCAL DATABASE ----------
try:
    df = pd.read_csv("Movies.csv")
    df.fillna("", inplace=True)
    df["Title"] = df["Title"].str.strip().str.lower()
except:
    df = pd.DataFrame(columns=["Title"])


# ---------- MOVIE DETAILS ----------
def get_movie_details(movie_id):

    params = {
        "api_key": TMDB_API_KEY,
        "append_to_response": "credits,keywords,watch/providers"
    }

    response = requests.get(f"{TMDB_BASE_URL}/movie/{movie_id}", params=params)

    if response.status_code != 200:
        return None

    data = response.json()

    actors = [c["name"] for c in data["credits"]["cast"][:5]]

    genre_ids = [g["id"] for g in data["genres"]]
    genre_names = [g["name"] for g in data["genres"]]

    keywords = [k["name"] for k in data["keywords"]["keywords"]]

    # -------- DIRECTOR --------
    director = ""
    for crew in data["credits"]["crew"]:
        if crew["job"] == "Director":
            director = crew["name"]
            break

    # -------- OTT PROVIDERS (India) --------
    ott_list = []

    providers = data.get("watch/providers", {}).get("results", {}).get("IN", {})

    for category in ["flatrate", "rent", "buy"]:
        for p in providers.get(category, []):
            ott_list.append(p["provider_name"])

    ott_list = list(set(ott_list))

    if ott_list:
        providers_text = ", ".join(ott_list)
    else:
        providers_text = "Not Available"

    return {
        "id": movie_id,
        "title": data["title"],
        "year": data.get("release_date", "")[:4],
        "overview": data.get("overview", ""),
        "poster": POSTER_BASE + data["poster_path"] if data.get("poster_path") else "",
        "genre_ids": genre_ids,
        "genre_names": ", ".join(genre_names),
        "actors": actors,
        "actors_text": ", ".join(actors),
        "keywords": keywords,
        "director": director,
        "providers": providers_text,
        "popularity": data.get("popularity", 0)
    }


# ---------- SIMILARITY SCORE ----------
def calculate_similarity(base, other):

    score = 0

    genre_match = len(set(base["genre_ids"]) & set(other["genre_ids"]))
    score += genre_match * 5

    actor_match = len(set(base["actors"]) & set(other["actors"]))
    score += actor_match * 3

    keyword_match = len(set(base["keywords"]) & set(other["keywords"]))
    score += keyword_match * 2

    if base["director"] == other["director"] and base["director"] != "":
        score += 4

    pop_diff = abs(base["popularity"] - other["popularity"])
    if pop_diff < 15:
        score += 1

    return score


# ---------- NETFLIX STYLE RECOMMENDATIONS ----------
def get_netflix_style_recommendations(base_movie):

    genre_ids = ",".join(map(str, base_movie["genre_ids"]))

    discover = requests.get(
        f"{TMDB_BASE_URL}/discover/movie",
        params={
            "api_key": TMDB_API_KEY,
            "with_genres": genre_ids,
            "sort_by": "popularity.desc",
            "vote_count.gte": 100
        }
    ).json()

    candidates = discover.get("results", [])[:60]

    scored_movies = []

    for m in candidates:

        if m["id"] == base_movie["id"]:
            continue

        details = get_movie_details(m["id"])

        if not details:
            continue

        score = calculate_similarity(base_movie, details)

        details["score"] = score

        details["database"] = (
            "Available"
            if not df[df["Title"] == details["title"].lower()].empty
            else "Not Available"
        )

        scored_movies.append(details)

    scored_movies = sorted(scored_movies, key=lambda x: x["score"], reverse=True)

    return scored_movies[:10]


# ---------- ROUTES ----------
@app.route("/")
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def do_login():
    session["user"] = request.form.get("name", "User")
    return redirect(url_for("home"))


@app.route("/home")
def home():

    if "user" not in session:
        return redirect(url_for("login"))

    return render_template(
        "index.html",
        user=session["user"],
        searched_movie=False
    )


@app.route("/search", methods=["POST"])
def search():

    if "user" not in session:
        return redirect(url_for("login"))

    query = request.form.get("query")

    response = requests.get(
        f"{TMDB_BASE_URL}/search/movie",
        params={"api_key": TMDB_API_KEY, "query": query}
    )

    results = response.json().get("results", [])

    if not results:
        return render_template(
            "index.html",
            user=session["user"],
            error="Movie not found!"
        )

    base_movie = get_movie_details(results[0]["id"])

    recommendations = get_netflix_style_recommendations(base_movie)

    return render_template(
        "index.html",
        user=session["user"],
        searched_movie=True,
        base_movie=base_movie,
        recommended=recommendations
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)