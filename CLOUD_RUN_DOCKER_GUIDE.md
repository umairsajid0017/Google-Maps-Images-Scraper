# Google Maps Images Scraper Cloud Run Guide

This guide covers a Docker-based deployment for the Google Maps Images Scraper on Google Cloud Run.

Current deployed service:

```txt
Project: discoverbaku
Region: us-central1
Service: google-maps-images-scraper
URL: https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app
Artifact Registry repository: cloud-run-source-deploy
Image: us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy/google-maps-images-scraper
```

## New Installation

Install these tools on the PC:

```txt
Docker Desktop
Google Cloud CLI
Git
```

Confirm Docker is running:

```powershell
docker version
docker ps
```

Login to Google Cloud:

```powershell
gcloud auth login
gcloud config set project discoverbaku
```

Enable the required Google Cloud APIs:

```powershell
gcloud services enable artifactregistry.googleapis.com run.googleapis.com cloudbuild.googleapis.com --project discoverbaku
```

Create the Artifact Registry repository if it does not already exist:

```powershell
gcloud artifacts repositories create cloud-run-source-deploy `
  --project discoverbaku `
  --repository-format docker `
  --location us-central1 `
  --description "Docker images for Cloud Run deployments"
```

Configure Docker authentication for Artifact Registry:

```powershell
gcloud auth configure-docker us-central1-docker.pkg.dev
```

Build the Docker image from this folder:

```powershell
docker build -t us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy/google-maps-images-scraper:latest .
```

Push the image:

```powershell
docker push us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy/google-maps-images-scraper:latest
```

Deploy to Cloud Run:

```powershell
gcloud run deploy google-maps-images-scraper `
  --image us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy/google-maps-images-scraper:latest `
  --project discoverbaku `
  --region us-central1 `
  --platform managed `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 2 `
  --timeout 300 `
  --concurrency 4 `
  --port 5000
```

## Update Procedure

After changing the Python code, rebuild and redeploy the image.

Use a unique tag for each release:

```powershell
$tag = "release-$(Get-Date -Format yyyyMMdd-HHmmss)"
$image = "us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy/google-maps-images-scraper:$tag"
```

Build:

```powershell
docker build -t $image .
```

Push:

```powershell
docker push $image
```

Deploy:

```powershell
gcloud run deploy google-maps-images-scraper `
  --image $image `
  --project discoverbaku `
  --region us-central1 `
  --platform managed `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 2 `
  --timeout 300 `
  --concurrency 4 `
  --port 5000
```

Verify the service:

```powershell
Invoke-RestMethod "https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app/status"
```

If deploying through GitHub Actions, push to the `main` branch. The workflow in `.github/workflows/deploy-cloud-run.yml` builds the Docker image, pushes it to Artifact Registry, and deploys it to Cloud Run. The GitHub repository must have these secrets:

```txt
GCP_PROJECT_ID
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_SERVICE_ACCOUNT
```

## API Usage Guide

Base URL:

```txt
https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app
```

Start or poll a scrape job:

```http
GET /scrape?location=Baku%20Old%20City&max_images=20
```

PowerShell example:

```powershell
Invoke-RestMethod "https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app/scrape?location=Baku%20Old%20City&max_images=20"
```

Query parameters:

```txt
location      Required. Place name to search in Google Maps.
max_images    Optional. Maximum image count to collect. Default: 20.
skip_images   Optional. Number of images to skip before collecting. Default: 0.
refresh       Optional. Use refresh=1 to start a new job for the same location.
```

Example with pagination-style skipping:

```powershell
Invoke-RestMethod "https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app/scrape?location=Baku%20Old%20City&max_images=20&skip_images=20&refresh=1"
```

Response fields:

```txt
success          Boolean request result.
status           queued, running, done, or error.
images           Array of image objects.
error            Error message when status is error.
queue_position   Queue position when all scraper slots are busy.
max_concurrent   Maximum active scraper jobs.
```

Each image object includes:

```txt
url
thumbUrl
description
author
width
height
```

Check overall service/job status:

```http
GET /status
```

PowerShell example:

```powershell
Invoke-RestMethod "https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app/status"
```

## See Logs and Stats and Status

Check Cloud Run service status:

```powershell
gcloud run services describe google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1
```

Get only the service URL:

```powershell
gcloud run services describe google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1 `
  --format "value(status.url)"
```

View recent Cloud Run logs:

```powershell
gcloud run services logs read google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1 `
  --limit 100
```

Follow logs live:

```powershell
gcloud beta run services logs tail google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1
```

Check running job status from the API:

```powershell
Invoke-RestMethod "https://google-maps-images-scraper-435zgfx5uq-uc.a.run.app/status" | ConvertTo-Json -Depth 5
```

Check Cloud Run revisions:

```powershell
gcloud run revisions list `
  --service google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1
```

Check deployed image:

```powershell
gcloud run services describe google-maps-images-scraper `
  --project discoverbaku `
  --region us-central1 `
  --format "value(spec.template.spec.containers[0].image)"
```

List images in Artifact Registry:

```powershell
gcloud artifacts docker images list `
  us-central1-docker.pkg.dev/discoverbaku/cloud-run-source-deploy `
  --project discoverbaku
```

Open Cloud Run metrics in Google Cloud Console:

```txt
Google Cloud Console -> Cloud Run -> google-maps-images-scraper -> Metrics
```

Useful metrics to watch:

```txt
Request count
Request latency
Container memory utilization
Container CPU utilization
Instance count
Error rate
```
