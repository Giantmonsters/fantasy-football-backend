from fastapi import FastAPI
import pandas as pd
from sklearn.linear_model import LinearRegression
import uvicorn

app = FastAPI()

df = pd.read_csv("data/fantasy_stats.csv")
features = ["targets", "receptions", "yards", "tds"]
X = df[features]
y = df["fantasy_points"]
model = LinearRegression()
model.fit(X, y)

@app.get("/players")
def get_players():
    return [{"player": name} for name in df["player"].tolist()]

@app.get("/predict/{player_name}")
def predict_player(player_name: str):
    try:
        player = df[df["player"].str.lower() == player_name.lower()]
        if player.empty:
            return {"error": "Player not found"}
        X_player = player[features]
        predicted = model.predict(X_player)[0]
        actual = float(player["fantasy_points"].values[0])
        position = str(player["position"].values[0])
        image_url = str(player["image_url"].values[0])  # ✅ NEW
        return {
            "player": player_name,
            "predicted_points": float(predicted),
            "actual_points": actual,
            "position": position,
            "image_url": image_url  # ✅ NEW
        }
    except Exception as e:
        print(f"Error predicting {player_name}: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)