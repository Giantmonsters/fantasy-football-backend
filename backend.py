from fastapi import FastAPI
import requests
import uvicorn
from datetime import datetime, timedelta

app = FastAPI()

# ✅ Sleeper API endpoints
PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
STATS_URL = "https://api.sleeper.app/v1/stats/nfl/regular/2025"
PROJECTIONS_URL = "https://api.sleeper.app/v1/projections/nfl/regular/2025"

POSITIONS = ["QB", "RB", "WR", "TE"]

# ✅ Cache
_cache = None
_cache_time = None
CACHE_DURATION = timedelta(hours=6)

def get_player_data():
    global _cache, _cache_time
    
    # Return cached data if fresh
    if _cache and _cache_time and datetime.now() - _cache_time < CACHE_DURATION:
        print("Returning cached data")
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
        
        actual = player_stats.get('pts_ppr', 0)
        predicted = player_proj.get('pts_ppr', 0)
        
        if actual == 0:
            continue
        
        espn_id = player.get('espn_id')
        image_url = f"https://a.espncdn.com/i/headshots/nfl/players/full/{espn_id}.png" if espn_id else ""
        
        result.append({
            "player": player.get('full_name', ''),
            "position": player.get('position', ''),
            "actual_points": round(actual, 1),
            "predicted_points": round(predicted,