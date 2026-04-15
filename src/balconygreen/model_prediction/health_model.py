import numpy as np # type: ignore
import pandas as pd # type: ignore
import torch # type: ignore
import torch.nn as nn # type: ignore

from torch.utils.data import Dataset, DataLoader # type: ignore
from sklearn.preprocessing import StandardScaler # type: ignore
from sklearn.metrics import mean_absolute_error, mean_squared_error # type: ignore
from pathlib import Path # type: ignore

import joblib # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PLANT_MODEL_V6 = (
    PROJECT_ROOT
    / "model_prediction"
    / "Models"
    / "health_risk_model"
    / "plant_model_v6.pth"
)


SCALAR_SENSOR = (
    PROJECT_ROOT
    / "model_prediction"
    / "Models"
    / "health_risk_model"
    / "scaler_sensor.pkl"
)


SCALER_STATE = (
    PROJECT_ROOT
    / "model_prediction"
    / "Models"
    / "health_risk_model"
    / "scaler_state.pkl"
)



# =====================================================
# 1. TARGET ENGINEERING (V6 FIXED)
# =====================================================
def create_health_targets(df):
    df = df.copy()

    # smoothed health
    df["health_score"] = df["overall_health_on_ext"].ewm(span=5).mean()

    # # normalize 0–1
    # df["health_score"] = (
    #     df["health_score"] - df["health_score"].min()
    # ) / (df["health_score"].max() - df["health_score"].min() + 1e-8)

    df["health_velocity"] = df["health_score"].diff().fillna(0)
    df["health_acceleration"] = df["health_velocity"].diff().fillna(0)

    horizon = 5

    df["future_health"] = df["health_score"].shift(-horizon)
    df["future_velocity"] = df["health_velocity"].shift(-horizon)
    df["future_acceleration"] = df["health_acceleration"].shift(-horizon)

    # stable risk signal (clipped)
    df["risk_score"] = (0.5 * (1 - df["future_health"]/100) +
    0.3 * abs(df["future_velocity"]/100) +
    0.2 * abs(df["future_acceleration"])/100)

    df = df.dropna()

    return df


# =====================================================
# 2. FEATURES
# =====================================================
def add_features(df):
    df = df.copy()

    df["temp_change"] = df["temperature"].diff().fillna(0)
    df["humidity_change"] = df["humidity"].diff().fillna(0)
    df["soil_change"] = df["soil_moisture"].diff().fillna(0)

    return df


SENSOR_COLS = [
    "temperature",
    "humidity",
    "soil_moisture",
    "temp_change",
    "humidity_change",
    "soil_change"
]

STATE_COLS = [
    "health_score",
    "health_velocity",
    "health_acceleration"
]


# =====================================================
# 3. SEQUENCE CREATION
# =====================================================
def create_sequences(df, window=25):

    Xs, Xstate = [], []
    y_health, y_risk = [], []

    sensor = df[SENSOR_COLS].values
    state = df[STATE_COLS].values

    for i in range(window, len(df)):
        Xs.append(sensor[i-window:i])
        Xstate.append(state[i-window:i])

        y_health.append(df["future_health"].iloc[i])
        y_risk.append(df["risk_score"].iloc[i])

    return (
        np.array(Xs),
        np.array(Xstate),
        np.array(y_health),
        np.array(y_risk)
    )


# =====================================================
# 4. DATASET
# =====================================================
class PlantDataset(Dataset):
    def __init__(self, Xs, Xstate, yh, yr):
        self.Xs = torch.tensor(Xs, dtype=torch.float32)
        self.Xstate = torch.tensor(Xstate, dtype=torch.float32)
        self.yh = torch.tensor(yh, dtype=torch.float32)
        self.yr = torch.tensor(yr, dtype=torch.float32)

    def __len__(self):
        return len(self.yh)

    def __getitem__(self, idx):
        return self.Xs[idx], self.Xstate[idx], self.yh[idx], self.yr[idx]


# =====================================================
# 5. MODEL (FIXED OUTPUT RANGE)
# =====================================================
class PlantModelV6(nn.Module):
    def __init__(self, sensor_dim, state_dim, hidden=64):
        super().__init__()

        self.sensor_gru = nn.GRU(sensor_dim, hidden, num_layers=2, batch_first=True, dropout=0.2)
        self.state_gru = nn.GRU(state_dim, hidden, num_layers=2, batch_first=True, dropout=0.2)

        self.attn = nn.Linear(hidden * 2, 1)

        # ✅ FIXED: bounded outputs
        self.health_head = nn.Sequential(
            nn.Linear(hidden * 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()   # 0–1
        )

        self.risk_head = nn.Sequential(
            nn.Linear(hidden * 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Tanh()      # -1 to 1
        )

    def forward(self, xs, xstate):

        s_out, _ = self.sensor_gru(xs)
        h_out, _ = self.state_gru(xstate)

        x = torch.cat([s_out, h_out], dim=-1)

        attn = torch.softmax(self.attn(x), dim=1)
        context = torch.sum(attn * x, dim=1)

        health = self.health_head(context).squeeze()
        risk = self.risk_head(context).squeeze()

        return health, risk


# =====================================================
# 6. TRAINING
# =====================================================
def run_training(df, window=25, epochs=30, batch_size=32):

    # IMPORTANT: correct order
    df = add_features(df)
    df = create_health_targets(df)

    df = df.sort_index().reset_index(drop=True)

    Xs, Xstate, yh, yr = create_sequences(df, window)

    split = int(len(Xs) * 0.7)

    Xs_tr, Xs_te = Xs[:split], Xs[split:]
    Xst_tr, Xst_te = Xstate[:split], Xstate[split:]
    yh_tr, yh_te = yh[:split], yh[split:]
    yr_tr, yr_te = yr[:split], yr[split:]

    scaler_s = StandardScaler()
    scaler_st = StandardScaler()

    Xs_tr = scaler_s.fit_transform(Xs_tr.reshape(-1, Xs_tr.shape[-1])).reshape(Xs_tr.shape)
    Xs_te = scaler_s.transform(Xs_te.reshape(-1, Xs_te.shape[-1])).reshape(Xs_te.shape)

    Xst_tr = scaler_st.fit_transform(Xst_tr.reshape(-1, Xst_tr.shape[-1])).reshape(Xst_tr.shape)
    Xst_te = scaler_st.transform(Xst_te.reshape(-1, Xst_te.shape[-1])).reshape(Xst_te.shape)

    train_loader = DataLoader(
        PlantDataset(Xs_tr, Xst_tr, yh_tr, yr_tr),
        batch_size=batch_size,
        shuffle=True
    )

    test_loader = DataLoader(
        PlantDataset(Xs_te, Xst_te, yh_te, yr_te),
        batch_size=batch_size,
        shuffle=False
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = PlantModelV6(len(SENSOR_COLS), len(STATE_COLS)).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    loss_h = nn.MSELoss()
    loss_r = nn.HuberLoss()

    for epoch in range(epochs):

        model.train()
        total_loss = 0

        for xs, xst, yh_b, yr_b in train_loader:
            xs, xst = xs.to(device), xst.to(device)
            yh_b, yr_b = yh_b.to(device), yr_b.to(device)

            optimizer.zero_grad()

            pred_h, pred_r = model(xs, xst)

            loss = 0.8 * loss_h(pred_h, yh_b) + 1.2 * loss_r(pred_r, yr_b)

            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        # evaluation
        model.eval()
        ph, th, pr, tr = [], [], [], []

        with torch.no_grad():
            for xs, xst, yh_b, yr_b in test_loader:
                xs, xst = xs.to(device), xst.to(device)

                h, r = model(xs, xst)

                ph.extend(h.cpu().numpy())
                th.extend(yh_b.numpy())

                pr.extend(r.cpu().numpy())
                tr.extend(yr_b.numpy())

        ph, th = np.array(ph), np.array(th)
        pr, tr = np.array(pr), np.array(tr)

        rmse = np.sqrt(mean_squared_error(th, ph))
        mae = mean_absolute_error(th, ph)
        risk_mae = mean_absolute_error(tr, pr)

        print(
            f"Epoch {epoch+1} | Loss {total_loss:.4f} | "
            f"RMSE {rmse:.5f} | MAE {mae:.5f} | RiskMAE {risk_mae:.5f}"
        )

    return model, scaler_s, scaler_st



def load_pipeline(
    model_path=PLANT_MODEL_V6,
    scaler_s_path=SCALAR_SENSOR,
    scaler_st_path=SCALER_STATE
):
    model = PlantModelV6(len(SENSOR_COLS), len(STATE_COLS))
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()

    scaler_s = joblib.load(scaler_s_path)
    scaler_st = joblib.load(scaler_st_path)

    return model, scaler_s, scaler_st


model_GRU, scaler_s, scaler_st = load_pipeline()





def run_inference(
    df,
    model=model_GRU,
    scaler_s=scaler_s,
    scaler_st=scaler_st,
    window=25
):
    """
    Runs inference on plant dataframe.
    Returns: dict with predictions + interpreted signals
    """

    model.eval()

    # -----------------------------
    # ✅ MATCH TRAINING PIPELINE
    # -----------------------------
    df = add_features(df)
    df = create_health_targets(df)
    df = df.sort_index().reset_index(drop=True)

    

    if len(df) < window:
        raise ValueError(f"Need at least {window} rows, got {len(df)}")

    # -----------------------------
    # LAST WINDOW
    # -----------------------------
    sensor = df[SENSOR_COLS].values[-window:]
    state = df[STATE_COLS].values[-window:]

    # -----------------------------
    # SCALING
    # -----------------------------
    sensor = scaler_s.transform(sensor)
    state = scaler_st.transform(state)

    sensor = torch.tensor(sensor[np.newaxis, :, :], dtype=torch.float32)
    state = torch.tensor(state[np.newaxis, :, :], dtype=torch.float32)

    # -----------------------------
    # MODEL PREDICTION
    # -----------------------------
    with torch.no_grad():
        pred_health, pred_risk = model(sensor, state)

    
    pred_health = float(pred_health.item())  # 0–1
    pred_risk = float(pred_risk.item())

    latest_health = float(df["health_score"].iloc[-1]) / 100  # normalize

    # trend
    delta = pred_health - latest_health

    if delta > 0.02:
        trend = "improving"
    elif delta < -0.02:
        trend = "declining"
    else:
        trend = "stable"

    # risk
    risk_score = abs(pred_risk)
    
    
    if risk_score > 0.3:
        alert = "high_risk"
    elif risk_score > 0.1:
        alert = "moderate_risk"
    else:
        alert = "low_risk"

    # status
    if pred_health < 0.2:
        status = "critical"
    elif alert == "high_risk":
        status = "warning"
    elif trend == "declining":
        status = "warning"
    else:
        status = "healthy"

    confidence = float(np.clip(1 - abs(delta), 0, 1))

    # -----------------------------
    # FINAL OUTPUT
    # -----------------------------
    return {
        "mode": "latest",

        "status": status,
        "trend": trend,

        "prediction": {
            "health_score": pred_health,
            "health_pct": pred_health * 100,
            "risk": risk_score
        },

        "current": {
            "health_score": latest_health,
            "health_pct": latest_health * 100
        },

        "alert": {
            "level": alert,
            "confidence": confidence
        }
    }