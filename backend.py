from fastapi import FastAPI
import requests
import uvicorn
from datetime import datetime, timedelta

app = FastAPI()

PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"

# ✅ 2025 full season data (placeholder until 2026 season starts)
STATS_URL = "https://api.sleeper.app/v1/stats/nfl/regular/2025"
PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/2025"

# ✅ When 2026 season starts, use weekly endpoints like:
# LAST_WEEK_STATS = "https://api.sleeper.app/v1/stats/nfl/2026/1"
# LAST_WEEK_PROJ = "https://api.sleeper.app/v1/projections/nfl/2026/1"
# THIS_WEEK_PROJ = "https://api.sleeper.app/v1/projections/nfl/2026/2"

# ✅ Added K and DEF
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

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

        # ✅ Use pts_ppr for skill positions, pts_std for K and DEF
        position = player.get('position', '')
        if position in ["K", "DEF"]:
            actual = player_stats.get('pts_std', 0)
            predicted = player_proj.get('pts_std', 0)
        else:
            actual = player_stats.get('pts_ppr', 0)
            predicted = player_proj.get('pts_ppr', 0)

        if actual == 0:
            continue

        espn_id = player.get('espn_id')
        if espn_id:
            image_url = f"https://a.espncdn.com/i/headshots/nfl/players/full/{espn_id}.png"
        else:
            image_url = f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"

        result.append({
            "player": player.get('full_name', ''),
            "position": position,
            "team": player.get('team', 'FA'),
            "age": calculate_age(player.get('birth_date')),
            "years_exp": player.get('years_exp', 0),
            "injury_status": player.get('injury_status', None),
            "injury_notes": player.get('injury_notes', None),
            "actual_points": round(actual, 1),
            "predicted_points": round(predicted, 1),
            # ✅ Placeholder for weekly data - ready for September
            "last_week_actual": round(actual, 1),
            "last_week_predicted": round(predicted, 1),
            "this_week_projected": round(predicted, 1),
            "image_url": image_url
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

@app.on_event("startup")
async def startup_event():
    print("Preloading player cache on startup...")
    get_player_data()
    print("Cache ready!")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)