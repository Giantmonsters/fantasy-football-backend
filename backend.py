from fastapi import FastAPI
import requests
import uvicorn
from datetime import datetime, timedelta

app = FastAPI()

PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"

STATS_URL = "https://api.sleeper.app/v1/stats/nfl/regular/2025"
PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/2025"

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

# ✅ Manual ESPN ID overrides for players missing ESPN ID in Sleeper
ESPN_ID_OVERRIDES = {
    "9493": "4426515",   # Puka Nacua
    "9488": "4430878",   # Jaxon Smith-Njigba
    "7523": "4360310",   # Trevor Lawrence
    "7547": "4374302",   # Amon-Ra St. Brown
    "8130": "4361307",   # Trey McBride
    "7564": "4362628",   # Ja'Marr Chase
    "8138": "4379399",   # James Cook
    "9226": "4429160",   # De'Von Achane
    "9509": "4430807",   # Bijan Robinson
    "9221": "4429795",   # Jahmyr Gibbs
    "11564": "4431452",  # Drake Maye
    "11560": "4431611",  # Caleb Williams
    "11563": "4426338",  # Bo Nix
    "12508": "4689114",  # Jaxson Dart
    "9228": "4685720",   # Bryce Young
    "9224": "4362238",   # Chase Brown
    "8150": "4430737",   # Kyren Williams
    "7543": "4239996",   # Travis Etienne
    "12527": "4890973",  # Ashton Jeanty
    "8155": "4427366",   # Breece Hall
    "7588": "4361579",   # Javonte Williams
    "8137": "4426354",   # George Pickens
    "8144": "4361370",   # Chris Olave
    "9997": "4429615",   # Zay Flowers
    "7569": "4258173",   # Nico Collins
    "7525": "4241478",   # DeVonta Smith
    "8112": "4426502",   # Drake London
    "8148": "4426388",   # Jameson Williams
    "7553": "4360248",   # Kyle Pitts
    "11604": "4432665",  # Brock Bowers
}

# ✅ ESPN team slugs (Sleeper abbreviation -> ESPN roster-endpoint slug).
# Only Washington differs (Sleeper: WAS, ESPN: wsh).
ESPN_TEAM_SLUGS = {
    "ARI": "ari", "ATL": "atl", "BAL": "bal", "BUF": "buf", "CAR": "car",
    "CHI": "chi", "CIN": "cin", "CLE": "cle", "DAL": "dal", "DEN": "den",
    "DET": "det", "GB": "gb", "HOU": "hou", "IND": "ind", "JAX": "jax",
    "KC": "kc", "LAC": "lac", "LAR": "lar", "LV": "lv", "MIA": "mia",
    "MIN": "min", "NE": "ne", "NO": "no", "NYG": "nyg", "NYJ": "nyj",
    "PHI": "phi", "PIT": "pit", "SEA": "sea", "SF": "sf", "TB": "tb",
    "TEN": "ten", "WAS": "wsh",
}

_cache = None
_cache_time = None
CACHE_DURATION = timedelta(hours=6)

# ✅ Cache of every player's real ESPN headshot, pulled straight from
# ESPN's own team roster data. This covers kickers and any depth/rookie
# player that isn't in the hand-curated ESPN_ID_OVERRIDES list above,
# instead of falling back to Sleeper's often-missing thumbnail CDN.
_espn_roster_cache = None
_espn_roster_cache_time = None


def calculate_age(birth_date_str):
    if not birth_date_str:
        return None
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except:
        return None


def get_espn_roster_map():
    """Fetch every NFL team's roster from ESPN and build a
    {lowercased full name: {espn_id, image_url}} lookup. This is the
    canonical, always-current source of headshots, so it's used as a
    fallback whenever Sleeper doesn't have an espn_id for a player
    (this is especially common for kickers)."""
    global _espn_roster_cache, _espn_roster_cache_time
    if (_espn_roster_cache is not None and _espn_roster_cache_time and
            datetime.now() - _espn_roster_cache_time < CACHE_DURATION):
        return _espn_roster_cache

    print("Fetching ESPN roster headshot map...")
    name_map = {}
    for slug in ESPN_TEAM_SLUGS.values():
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{slug}/roster"
            resp = requests.get(url, timeout=10).json()
            for group in resp.get("athletes", []):
                for athlete in group.get("items", []):
                    full_name = athlete.get("fullName", "")
                    headshot = (athlete.get("headshot") or {}).get("href")
                    espn_id = str(athlete.get("id", "")) if athlete.get("id") else None
                    if full_name and (headshot or espn_id):
                        name_map[full_name.lower()] = {
                            "espn_id": espn_id,
                            "image_url": headshot,
                        }
        except Exception as e:
            print(f"Failed ESPN roster fetch for {slug}: {e}")
            continue

    _espn_roster_cache = name_map
    _espn_roster_cache_time = datetime.now()
    print(f"Built ESPN roster map with {len(name_map)} players")
    return name_map


def get_player_data():
    global _cache, _cache_time
    if _cache and _cache_time and datetime.now() - _cache_time < CACHE_DURATION:
        return _cache

    print("Fetching fresh data from Sleeper...")
    players = requests.get(PLAYERS_URL).json()
    stats = requests.get(STATS_URL).json()
    projections = requests.get(PROJECTIONS_URL).json()
    espn_roster_map = get_espn_roster_map()

    result = []
    for player_id, player in players.items():
        if not player.get('active'):
            continue
        if player.get('position') not in POSITIONS:
            continue

        player_stats = stats.get(player_id, {})
        player_proj = projections.get(player_id, {})

        position = player.get('position', '')
        if position in ["K", "DEF"]:
            actual = player_stats.get('pts_std', 0)
            predicted = player_proj.get('pts_std', 0)
        else:
            actual = player_stats.get('pts_ppr', 0)
            predicted = player_proj.get('pts_ppr', 0)

        if actual == 0:
            continue

        player_name = player.get('full_name', '')
        if position == 'DEF' and not player_name:
            player_name = f"{player.get('team', '')} D/ST"

        espn_id = player.get('espn_id') or ESPN_ID_OVERRIDES.get(player_id)
        roster_match = espn_roster_map.get(player_name.lower())

        if position == 'DEF':
            image_url = f"https://a.espncdn.com/i/teamlogos/nfl/500/{player.get('team', '').lower()}.png"
        elif espn_id:
            image_url = f"https://a.espncdn.com/i/headshots/nfl/players/full/{espn_id}.png"
        elif roster_match and roster_match.get("image_url"):
            # ✅ Fallback for kickers / depth players missing an espn_id:
            # use ESPN's own roster headshot instead of Sleeper's thumb CDN.
            image_url = roster_match["image_url"]
            espn_id = roster_match.get("espn_id") or espn_id
        else:
            image_url = f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"

        result.append({
            "player": player_name,
            "position": position,
            "team": player.get('team', 'FA'),
            "age": calculate_age(player.get('birth_date')),
            "years_exp": player.get('years_exp', 0),
            "college": player.get('college', None),  # ✅ College added
            "injury_status": player.get('injury_status', None),
            "injury_notes": player.get('injury_notes', None),
            "actual_points": round(actual, 1),
            "predicted_points": round(predicted, 1),
            "last_week_actual": round(actual, 1),
            "last_week_predicted": round(predicted, 1),
            "this_week_projected": round(predicted, 1),
            "image_url": image_url,
            "espn_id": str(espn_id) if espn_id else None
        })

    result.sort(key=lambda x: x['actual_points'], reverse=True)
    _cache = result
    _cache_time = datetime.now()
    print(f"Cached {len(result)} players")
    return result


@app.get("/players")
def get_players():
    data = get_player_data()
    return [{"player": p["player"]} for p in data]


@app.get("/all_players")
def get_all_players():
    return get_player_data()


@app.get("/predict/{player_name}")
def predict_player(player_name: str):
    try:
        data = get_player_data()
        player = next((p for p in data if p["player"].lower() == player_name.lower()), None)
        if not player:
            return {"error": "Player not found"}
        return player
    except Exception as e:
        return {"error": str(e)}


@app.get("/news/{espn_id}")
def get_player_news(espn_id: str):
    try:
        url = f"https://site.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{espn_id}/overview"
        response = requests.get(url).json()
        news_items = []
        news = response.get('news', [])
        if isinstance(news, dict):
            news = news.get('items', [])
        for item in news[:5]:
            news_items.append({
                "headline": item.get('headline', ''),
                "description": item.get('description', ''),
                "published": item.get('lastModified', ''),
                "link": item.get('links', {}).get('web', {}).get('href', '')
            })
        return {"news": news_items}
    except Exception as e:
        return {"news": [], "error": str(e)}


@app.on_event("startup")
async def startup_event():
    print("Preloading ESPN roster headshot map...")
    get_espn_roster_map()
    print("Preloading player cache on startup...")
    get_player_data()
    print("Cache ready!")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)