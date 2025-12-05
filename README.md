[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/e7FBMwSa)
[![Open in Visual Studio Code](https://classroom.github.com/assets/open-in-vscode-2e0aaae1b6195c2367325f4f02e2d04e9abb55f0b24a779b69b11b9e10269abc.svg)](https://classroom.github.com/online_ide?assignment_repo_id=21897086&assignment_repo_type=AssignmentRepo)
# Deploy FastAPI on Render

Use this repo as a template to deploy a Python [FastAPI](https://fastapi.tiangolo.com) service on Render.

See https://render.com/docs/deploy-fastapi or follow the steps below:

## Manual Steps

1. You may use this repository directly or [create your own repository from this template](https://github.com/render-examples/fastapi/generate) if you'd like to customize the code.
2. Create a new Web Service on Render.
3. Specify the URL to your new repository or this repository.
4. Render will automatically detect that you are deploying a Python service and use `pip` to download the dependencies.
5. Specify the following as the Start Command.

    ```shell
    uvicorn main:app --host 0.0.0.0 --port $PORT
    ```

6. Click Create Web Service.

Or simply click:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/render-examples/fastapi)

## Thanks

Thanks to [Harish](https://harishgarg.com) for the [inspiration to create a FastAPI quickstart for Render](https://twitter.com/harishkgarg/status/1435084018677010434) and for some sample code!

## Data export / download (for TAs & Tren)

The EmoGo backend exposes a data-export page that lets TAs and Tren view and download the three types of data collected by the frontend: vlogs, sentiments, and GPS coordinates.

- **Export page (will be assigned by Render after deployment):**

    `https://emogo-backend-shane01526.onrender.com/export`

- **Direct download endpoints (replace the host with your service domain):**
    - `/export/vlogs` — downloads `vlogs.json`
    - `/export/sentiments` — downloads `sentiments.json`
    - `/export/gps` — downloads `gps.json`

Each endpoint returns a JSON array of documents from the corresponding MongoDB collection. Example curl command to download the vlogs file (saves with the server-provided filename):

```powershell
curl -O -J https://<your-render-service>.onrender.com/export/vlogs
```

Deploying on Render
- Add `render.yaml` to the repository (already provided) so Render can use this spec when creating the service.
- In the Render dashboard, create a new Web Service and connect the repository. Set these environment variables in the service settings:
  - `MONGO_URI` (e.g., `mongodb://username:password@host:port`)
  - `MONGO_DB` (e.g., `emogo`)
- Start command (Render uses this when launching the service):

```shell
uvicorn main:app --host 0.0.0.0 --port $PORT
```

After the service is created and a deployment succeeds, Render will assign a public domain such as `https://my-service.onrender.com`. Replace `https://<your-render-service>.onrender.com` above with your actual service URL and commit the change to this README so TAs and Tren can access the export page.

Want me to deploy? I can perform the deployment for you if you provide a Render API key and grant access to the repository (or give me temporary credentials). If you prefer to deploy it yourself, follow the Render UI steps above — the `render.yaml` in this repo will be used by Render when creating the service.

The app reads MongoDB connection info from the `MONGO_URI` environment variable (default: `mongodb://localhost:27017`) and the database name from `MONGO_DB` (default: `emogo`).
