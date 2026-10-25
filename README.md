# Customer Churn MLOps

A compact, reproducible customer-churn classifier with a typed FastAPI service and responsive browser UI. It is an example decision-support product, not an autonomous retention or eligibility system.

## Data and intended use

The included telco churn sample contains 3,333 customer rows and 20 original columns; training uses 19 predictors and `Churn?` as the target. The `Phone` identifier is excluded. The project preserves `churn.csv`, `cleaned_dt.csv`, and the original notebook. Use the data only if you are authorized to access and process it. Do not send customer data or secrets to this application or publish the dataset/model without appropriate approval. Features and model quality may encode historical bias; validate before any operational use. No production-scale, fairness, or causal claim is made.

## Architecture

- `app/model.py`: deterministic feature cleaning, stratified 80/20 split (`random_state=42`), train-only preprocessing, balanced logistic regression, metrics, joblib artifact and metadata.
- `app/api.py`: FastAPI health/readiness/metadata/prediction endpoints; strict schemas, bounded values, no arbitrary paths or shell execution.
- `frontend/`: static responsive form/UI served by FastAPI.
- `k8s/customer-churn.yaml`: isolated namespace, non-root Deployment, Service, and Traefik/cert-manager Ingress template.

## Local run

Requires Python 3.12. Create an isolated environment and install pinned direct dependencies:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m app.model --data churn.csv --output artifacts
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Reproducible model seed and split are fixed. Metadata `created_at_utc` and artifact hash naturally vary across training runs; the model procedure, row split, and evaluation are deterministic for fixed dependency versions and input bytes.

Run verification:

```sh
python -m pytest -q
ruff check app tests
```

## Training and model evaluation

```sh
python -m app.model --data churn.csv --output artifacts
```

Training validates the expected columns and boolean-like target; it excludes `Phone`, splits with stratification before fitting imputation/scaling/one-hot encoding, and evaluates the untouched test partition. `artifacts/metadata.json` records test metrics, split counts, seed, feature names, software version, and model checksum. The reported holdout scores are estimates on this small sample, not guaranteed deployment performance. The threshold is 0.50; tune only using an explicitly separate validation process, never the held-out test set.

## API contract

- `GET /health`: process liveness (`200`).
- `GET /ready`: model loaded (`200`) or unavailable (`503`).
- `GET /metadata`: training metadata (`200`) or unavailable (`503`).
- `POST /predict`: JSON object containing all 19 model features, using the original CSV column names. Integers/numbers have range limits; plan fields accept `yes`/`no`; `State` must be two letters. Extra/missing/invalid fields receive FastAPI `422` validation errors. Output: `churn`, `churn_probability` (0–1), `risk_level`, `threshold`, plain-language review signals, and model version. An absent model returns `503`; model internals are not exposed.

Example:

```sh
curl -s http://127.0.0.1:8000/predict -H 'content-type: application/json' -d '{"State":"CA","Account Length":120,"Area Code":415,"Int\u0027l Plan":"no","VMail Plan":"no","VMail Message":0,"Day Mins":180,"Day Calls":100,"Day Charge":30.6,"Eve Mins":200,"Eve Calls":100,"Eve Charge":17,"Night Mins":200,"Night Calls":100,"Night Charge":9,"Intl Mins":10,"Intl Calls":4,"Intl Charge":2.7,"CustServ Calls":1}'
```

The explanation is a small, transparent indicator heuristic, not a model explanation or causal attribution.

## Container

```sh
docker build -t customer-churn-mlops:local .
docker run --rm -p 8000:8000 customer-churn-mlops:local
# or
 docker compose up --build
```

The image trains its model during build from the included sample, runs as non-root, and includes a readiness healthcheck. Production builds should use a reviewed, immutable image tag and a controlled, approved training-data/artifact process.

## Kubernetes / Singapore k3s deployment prerequisites

`k8s/customer-churn.yaml` is the deployment contract. The current Singapore deployment uses the dedicated `customer-churn` namespace and hostname `customer-churn.aljufairi.org`. Before changing or recreating it:

1. Review/authorize image distribution and build/publish the image in a trusted pipeline; use an immutable image tag.
2. The deployment template targets `customer-churn.aljufairi.org`, Traefik, and the existing `cloudflare-issuer`; update them only if the approved hostname or cluster conventions differ.
3. Review namespace quotas, DNS/TLS, resource limits, network policies, and data/privacy approval. The model artifact ships inside the image; no AWS credentials or cloud dependency is configured.
4. Apply only after cluster-owner approval: `kubectl apply -f k8s/customer-churn.yaml`; verify `kubectl -n customer-churn rollout status deploy/customer-churn`, Service/Ingress and `/ready` externally. The current rollout was imported directly into k3s containerd from immutable image tag `f9af89972cdbb8b5b9e38b1142ec24ac5a069d4a`; its local image ID is `sha256:54ccbb741eb1e252870f7f1e6b65f537abb7384de2e52532f0a616bcc178c201`.

Rollback: `kubectl -n customer-churn rollout undo deployment/customer-churn` restores the previous ReplicaSet. To remove only this application: `kubectl delete -f k8s/customer-churn.yaml` (this includes its dedicated namespace). Do not apply against unrelated namespaces.

## Limits

One small public sample dataset and one fixed split do not establish robustness, calibration, drift tolerance, fairness, business value, or production scale. No online retraining, AWS/Lambda, authentication, user identity, per-customer persistence, or request logging is implemented. Restrict network access and add identity/access controls before exposing beyond a trusted environment.

## Live deployment and privacy

Live demo: https://customer-churn.aljufairi.org

This application source branch is based on exact deployed commit 1e2c19014d4bb37afe45abb7af24b83a19807c39; the default branch currently contains the older notebook only. Do not replace notebook history or claim source parity from main.

Only the `/` landing page sends a privacy-minimized pageview to metrics.aljufairi.org. Form values, predictions, API paths, queries and fragments are not collected. No cookies/storage/replay. Designer icons are served under /static/.
