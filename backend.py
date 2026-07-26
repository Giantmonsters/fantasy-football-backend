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
    # Fixed existing overrides
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
    # QB
    "11564": "4431452",  # Drake Maye
    "11560": "4431611",  # Caleb Williams
    "11563": "4426338",  # Bo Nix
    "12508": "4689114",  # Jaxson Dart
    "9228": "4432580",   # Bryce Young
    # RB
    "9224": "4362238",   # Chase Brown
    "8150": "4430181",   # Kyren Williams
    "7543": "4239996",   # Travis Etienne
    "12527": "4685717",  # Ashton Jeanty
    "8155": "4372168",   # Breece Hall
    "7588": "4372016",   # Javonte Williams
    "8228": "4430259",   # Jaylen Warren
    # WR
    "8137": "4360622",   # George Pickens
    "8144": "4372013",   # Chris Olave
    "9997": "4430185",   # Zay Flowers
    "7569": "4372168",   # Nico Collins
    "7525": "4241389",   # DeVonta Smith
    "8112": "4372143",   # Drake London
    "8148": "4430188",   # Jameson Williams
    # TE
    "7553": "4372016",   # Kyle Pitts
    "11604": "4432665",  # Brock Bowers
}

_cache = None
_cache_time = None
CACHE_DURATION = timedelta(hours=6)

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

def get_player_data():
    global _cache, _cache_time
    if _cache and _cache_time and datetime.now() - _cache_time < CACHE_DURATION:
        return _cache

    print("Fetching fresh data from Sleeper...")
    players = requests.get(PLAYERS_URL).json()
    stats = requests.get(STATS_URL).json()
    projections = requests.get(PROJECTIONS_URL).json()

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

        # ✅ Use override if ESPN ID missing
        espn_id = player.get('espn_id') or ESPN_ID_OVERRIDES.get(player_id)

        if position == 'DEF':
            image_url = f"https://a.espncdn.com/i/teamlogos/nfl/500/{player.get('team', '').lower()}.png"
        elif espn_id:
            image_url = f"https://a.espncdn.com/i/headshots/nfl/players/full/{espn_id}.png"
        else:
            image_url = f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"

        result.append({
            "player": player_name,
            "position": position,
            "team": player.get('team', 'FA'),
            "age": calculate_age(player.get('birth_date')),
            "years_exp": player.get('years_exp', 0),
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

# ✅ Player news from ESPN
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
    print("Preloading player cache on startup...")
    get_player_data()
    print("Cache ready!")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)