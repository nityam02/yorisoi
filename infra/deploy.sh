#!/usr/bin/env bash
# Deploy Yorisoi to Cloud Run (Tokyo) from source. Plans are stored in Firestore.
#
#   PROJECT=my-gcp-project ./infra/deploy.sh            # Gemini API key from ../.env, stored in Secret Manager
#   PROJECT=my-gcp-project USE_VERTEX=1 ./infra/deploy.sh   # Vertex AI with the project's credits instead of a key
#
# Needs: gcloud CLI, logged in (gcloud auth login), billing enabled on the project.
set -euo pipefail

PROJECT=${PROJECT:?Set PROJECT to your Google Cloud project id}
REGION=${REGION:-asia-northeast1}
SERVICE=${SERVICE:-yorisoi}
SECRET=${SECRET:-yorisoi-gemini-key}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud config set project "$PROJECT" >/dev/null
echo "Enabling APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com >/dev/null

if ! gcloud firestore databases describe --database="(default)" >/dev/null 2>&1; then
  echo "Creating Firestore database in $REGION..."
  gcloud firestore databases create --location="$REGION" >/dev/null
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$RUNTIME_SA" \
  --role=roles/datastore.user --condition=None >/dev/null

ENV_VARS="YORISOI_STORE=firestore,GOOGLE_CLOUD_PROJECT=$PROJECT"
SECRET_FLAGS=()
if [[ "${USE_VERTEX:-0}" == "1" ]]; then
  # Newest Gemini models are served from the global endpoint on Vertex AI.
  ENV_VARS="$ENV_VARS,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION:-global}"
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/aiplatform.user --condition=None >/dev/null
else
  KEY=$(grep -E '^GEMINI_API_KEY=' "$ROOT/.env" | cut -d= -f2- || true)
  [[ -n "$KEY" ]] || { echo "No GEMINI_API_KEY in $ROOT/.env (or use USE_VERTEX=1)"; exit 1; }
  if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
    gcloud secrets create "$SECRET" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "$KEY" | gcloud secrets versions add "$SECRET" --data-file=- >/dev/null
  gcloud secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/secretmanager.secretAccessor >/dev/null
  SECRET_FLAGS=(--set-secrets "GEMINI_API_KEY=$SECRET:latest")
fi

MAPS_KEY=$(grep -E '^MAPS_API_KEY=' "$ROOT/.env" | cut -d= -f2- || true)
[[ -n "$MAPS_KEY" ]] && ENV_VARS="$ENV_VARS,MAPS_API_KEY=$MAPS_KEY"

echo "Building and deploying $SERVICE to Cloud Run ($REGION)..."
gcloud run deploy "$SERVICE" --source "$ROOT" --region "$REGION" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --min-instances 1 --max-instances 3 --timeout 300 \
  --set-env-vars "$ENV_VARS" "${SECRET_FLAGS[@]}"

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "Deployed: $URL"
curl -fsS "$URL/api/health" && echo
