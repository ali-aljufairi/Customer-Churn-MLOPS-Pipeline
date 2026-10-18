from fastapi.testclient import TestClient

from app import api


def test_health_and_unready(monkeypatch):
    with TestClient(api.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        monkeypatch.setattr(api.app.state, "model", None)
        monkeypatch.setattr(api.app.state, "metadata", None)
        assert client.get("/ready").status_code == 503
        assert client.get("/metadata").status_code == 503


def test_prediction_and_validation():
    with TestClient(api.app) as client:
        assert client.get("/").status_code == 200
        assert "Churn Signal" in client.get("/").text
        if client.get("/ready").status_code != 200:
            # Missing artifact is an explicit, safe unready state.
            assert client.post("/predict", json={}).status_code == 422
            return
        payload = {
            "State": "CA", "Account Length": 120, "Area Code": 415, "Int'l Plan": "no",
            "VMail Plan": "no", "VMail Message": 0, "Day Mins": 180, "Day Calls": 100,
            "Day Charge": 30.6, "Eve Mins": 200, "Eve Calls": 100, "Eve Charge": 17,
            "Night Mins": 200, "Night Calls": 100, "Night Charge": 9, "Intl Mins": 10,
            "Intl Calls": 4, "Intl Charge": 2.7, "CustServ Calls": 1,
        }
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert 0 <= data["churn_probability"] <= 1
        assert data["risk_level"] in {"low", "moderate", "high"}
        assert data["explanation"]
        assert client.post("/predict", json={**payload, "Area Code": -1}).status_code == 422
        assert client.post("/predict", json={**payload, "unexpected": 1}).status_code == 422

        class BrokenModel:
            def predict_proba(self, _frame):
                raise RuntimeError("private implementation detail")

        api.app.state.model = BrokenModel()
        failed = client.post("/predict", json=payload)
        assert failed.status_code == 500
        assert failed.json()["detail"] == "Prediction failed"
        assert "private implementation detail" not in failed.text
