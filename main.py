import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
import httpx
import zipfile
from io import BytesIO

app = FastAPI()

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB client will be created at startup
mongo_client: Optional[AsyncIOMotorClient] = None
db = None


# Pydantic models for request validation
class VlogData(BaseModel):
    media_url: Optional[str] = None
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    url: Optional[str] = None
    userId: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SentimentData(BaseModel):
    score: Optional[float] = None
    sentiment: Optional[str] = None
    value: Optional[float] = None
    polarity: Optional[float] = None
    userId: Optional[str] = None
    timestamp: Optional[str] = None
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GPSData(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    lng: Optional[float] = None
    coords: Optional[List[float]] = None
    userId: Optional[str] = None
    timestamp: Optional[str] = None
    accuracy: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


@app.on_event("startup")
async def startup_db_client():
    global mongo_client, db
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    
    try:
        mongo_client = AsyncIOMotorClient(mongo_uri)
        db_name = os.getenv("MONGO_DB", "emogo")
        db = mongo_client[db_name]
        
        # Test the connection
        await mongo_client.admin.command('ping')
        print(f"✅ Connected to MongoDB: {db_name}")
        
        # Create indexes for better query performance
        await db.vlogs.create_index("timestamp")
        await db.sentiments.create_index("timestamp")
        await db.gps.create_index("timestamp")
        print("✅ Database indexes created")
        
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        print(f"MongoDB URI: {mongo_uri}")
        # Don't fail startup, but db will be None


@app.on_event("shutdown")
async def shutdown_db_client():
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("MongoDB connection closed")


@app.get("/")
async def root():
    if db is None:
        return {
            "message": "EmoGo backend is running",
            "status": "error",
            "database": "not connected",
            "note": "Check MONGO_URI environment variable"
        }
    
    try:
        # Test database connection
        await mongo_client.admin.command('ping')
        
        # Get collection counts
        vlogs_count = await db.vlogs.count_documents({})
        sentiments_count = await db.sentiments.count_documents({})
        gps_count = await db.gps.count_documents({})
        
        return {
            "message": "EmoGo backend is running",
            "status": "ok",
            "database": "connected",
            "collections": {
                "vlogs": vlogs_count,
                "sentiments": sentiments_count,
                "gps": gps_count
            }
        }
    except Exception as e:
        return {
            "message": "EmoGo backend is running",
            "status": "error",
            "database": "connection error",
            "error": str(e)
        }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        await mongo_client.admin.command('ping')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


# ============== WRITE ENDPOINTS ==============

@app.post("/api/vlogs")
async def create_vlog(data: Dict[str, Any] = Body(...)):
    """Store a new vlog entry"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Add server timestamp if not provided
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()
        
        result = await db.vlogs.insert_one(data)
        return {
            "status": "success",
            "id": str(result.inserted_id),
            "message": "Vlog saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save vlog: {str(e)}")


@app.post("/api/sentiments")
async def create_sentiment(data: Dict[str, Any] = Body(...)):
    """Store a new sentiment entry"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Add server timestamp if not provided
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()
        
        result = await db.sentiments.insert_one(data)
        return {
            "status": "success",
            "id": str(result.inserted_id),
            "message": "Sentiment saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save sentiment: {str(e)}")


@app.post("/api/gps")
async def create_gps(data: Dict[str, Any] = Body(...)):
    """Store a new GPS coordinate entry"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Add server timestamp if not provided
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()
        
        result = await db.gps.insert_one(data)
        return {
            "status": "success",
            "id": str(result.inserted_id),
            "message": "GPS data saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save GPS data: {str(e)}")


@app.post("/api/batch")
async def create_batch(data: Dict[str, Any] = Body(...)):
    """Store multiple entries at once"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        results = {}
        timestamp = datetime.utcnow().isoformat()
        
        # Insert vlogs
        if "vlogs" in data and data["vlogs"]:
            vlogs = data["vlogs"]
            for vlog in vlogs:
                if "timestamp" not in vlog:
                    vlog["timestamp"] = timestamp
            result = await db.vlogs.insert_many(vlogs)
            results["vlogs"] = len(result.inserted_ids)
        
        # Insert sentiments
        if "sentiments" in data and data["sentiments"]:
            sentiments = data["sentiments"]
            for sentiment in sentiments:
                if "timestamp" not in sentiment:
                    sentiment["timestamp"] = timestamp
            result = await db.sentiments.insert_many(sentiments)
            results["sentiments"] = len(result.inserted_ids)
        
        # Insert GPS data
        if "gps" in data and data["gps"]:
            gps_data = data["gps"]
            for gps in gps_data:
                if "timestamp" not in gps:
                    gps["timestamp"] = timestamp
            result = await db.gps.insert_many(gps_data)
            results["gps"] = len(result.inserted_ids)
        
        return {
            "status": "success",
            "inserted": results,
            "message": "Batch data saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save batch data: {str(e)}")


# ============== READ/EXPORT ENDPOINTS ==============

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


ALLOWED_EXPORTS = {"vlogs", "sentiments", "gps"}


@app.get("/export", response_class=HTMLResponse)
async def export_index():
    """Interactive HTML page listing and visualizing the available exports."""
    html = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>EmoGo Data Export & Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <style>
            body { font-family: Arial, sans-serif; margin: 16px; }
            .status { padding: 10px; margin-bottom: 15px; border-radius: 4px; }
            .status.ok { background: #d4edda; color: #155724; }
            .status.error { background: #f8d7da; color: #721c24; }
            nav { margin-bottom: 12px; }
            .tab { display:inline-block; margin-right:8px; padding:6px 10px; background:#eee; cursor:pointer; border-radius:4px; }
            .tab.active { background:#1976d2; color:#fff; }
            .panel { display:none; margin-top:12px; }
            .panel.active { display:block; }
            #map { height: 400px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 6px; }
            pre.raw { background:#f7f7f7; padding:8px; overflow:auto; max-height:300px; }
        </style>
    </head>
    <body>
        <h1>EmoGo Data Export & Viewer</h1>
        <div id="status" class="status">Checking connection...</div>
        <p>Interactive viewer — examine and download collected vlogs, sentiments, and GPS coordinates.</p>

        <nav>
            <span class="tab active" data-tab="vlogs">Vlogs</span>
            <span class="tab" data-tab="sentiments">Sentiments</span>
            <span class="tab" data-tab="gps">GPS</span>
            <a style="margin-left:12px" href="/export/vlogs">Download vlogs (JSON)</a>
            <a style="margin-left:8px" href="/export/sentiments">Download sentiments (JSON)</a>
            <a style="margin-left:8px" href="/export/gps">Download gps (JSON)</a>
        </nav>

        <div id="vlogs" class="panel active">
            <h2>Vlogs</h2>
            <div id="vlogsList">Loading...</div>
        </div>

        <div id="sentiments" class="panel">
            <h2>Sentiments</h2>
            <canvas id="sentimentChart" height="120"></canvas>
            <h3>All records</h3>
            <div id="sentimentsTable">Loading...</div>
        </div>

        <div id="gps" class="panel">
            <h2>GPS Coordinates</h2>
            <div id="map"></div>
            <h3>All records</h3>
            <div id="gpsTable">Loading...</div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            // Check backend status
            fetch('/').then(r => r.json()).then(data => {
                const statusDiv = document.getElementById('status');
                if (data.status === 'ok') {
                    statusDiv.className = 'status ok';
                    statusDiv.innerHTML = '✅ Backend connected to database<br>' + 
                        'Collections: ' + JSON.stringify(data.collections);
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.innerHTML = '❌ ' + (data.error || 'Database not connected') + 
                        '<br>Note: ' + (data.note || 'Check MongoDB configuration');
                }
            }).catch(e => {
                document.getElementById('status').innerHTML = '❌ Failed to reach backend: ' + e.message;
                document.getElementById('status').className = 'status error';
            });

            // Tab handling
            document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
                t.classList.add('active');
                const panel = document.getElementById(t.dataset.tab);
                if (panel) panel.classList.add('active');
            }));

            async function fetchJson(path){
                const r = await fetch(path, { cache: 'no-store' });
                if(!r.ok) throw new Error('Failed to fetch '+path+' ('+r.status+')');
                return r.json();
            }

            function renderRawList(container, docs){
                if(!docs || docs.length===0){ container.innerHTML = '<em>No records</em>'; return; }
                const wrapper = document.createElement('div');
                docs.forEach(d => {
                    const pre = document.createElement('pre'); pre.className='raw'; pre.textContent = JSON.stringify(d, null, 2);
                    wrapper.appendChild(pre);
                });
                container.innerHTML = ''; container.appendChild(wrapper);
            }

            function renderTable(container, docs, keys){
                if(!docs || docs.length===0){ container.innerHTML = '<em>No records</em>'; return; }
                const table = document.createElement('table');
                const thead = document.createElement('thead');
                const trh = document.createElement('tr');
                keys.forEach(k=>{ const th=document.createElement('th'); th.textContent=k; trh.appendChild(th); });
                thead.appendChild(trh); table.appendChild(thead);
                const tbody = document.createElement('tbody');
                docs.forEach(d=>{
                    const tr = document.createElement('tr');
                    keys.forEach(k=>{
                        const td = document.createElement('td'); td.textContent = (d[k]!==undefined?String(d[k]):''); tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody); container.innerHTML=''; container.appendChild(table);
            }

            // Vlogs
            fetchJson('/export/vlogs').then(docs => {
                const el = document.getElementById('vlogsList');
                if(!docs || docs.length===0){ el.innerHTML='<em>No vlogs</em>'; return; }
                const list = document.createElement('div');
                docs.forEach((doc, i) => {
                    const div = document.createElement('div'); div.style.padding='8px'; div.style.borderBottom='1px solid #eee';
                    const title = document.createElement('div'); title.innerHTML = '<strong>Record '+(i+1)+'</strong>';
                    div.appendChild(title);
                    const mediaUrl = doc.media_url || doc.video_url || doc.audio_url || doc.url;
                    if(mediaUrl){
                        try{
                            const lower = String(mediaUrl).toLowerCase();
                            if(lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.includes('video')){
                                const vid = document.createElement('video'); vid.controls = true; vid.src = mediaUrl; vid.style.maxWidth='100%'; vid.style.display='block'; vid.style.marginTop='6px'; div.appendChild(vid);
                            } else if(lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.includes('audio')){
                                const aud = document.createElement('audio'); aud.controls = true; aud.src = mediaUrl; aud.style.display='block'; aud.style.marginTop='6px'; div.appendChild(aud);
                            } else {
                                const a = document.createElement('a'); a.href = mediaUrl; a.target = '_blank'; a.textContent = 'Open media'; a.style.display='inline-block'; a.style.marginTop='6px'; div.appendChild(a);
                            }
                            const zipLink = document.createElement('a'); zipLink.href = '/export/vlogs/zip'; zipLink.style.marginLeft='12px'; zipLink.textContent = 'Download media ZIP'; div.appendChild(zipLink);
                        }catch(e){ }
                    }
                    const body = document.createElement('pre'); body.className='raw'; body.textContent = JSON.stringify(doc, null, 2);
                    div.appendChild(body); list.appendChild(div);
                });
                el.innerHTML=''; el.appendChild(list);
            }).catch(e=>{ document.getElementById('vlogsList').textContent = 'Error: ' + e.message; });

            // Sentiments
            fetchJson('/export/sentiments').then(docs => {
                const ct = document.getElementById('sentimentsTable');
                if(!docs || docs.length===0){ 
                    ct.innerHTML='<em>No sentiments</em>'; 
                    document.getElementById('sentimentChart').style.display = 'none';
                    return; 
                }
                const scoreKeyCandidates = ['score','sentiment','value','polarity'];
                let key = null;
                for(const k of scoreKeyCandidates){ if(docs[0] && docs[0][k]!==undefined){ key=k; break; } }
                if(!key){ for(const k of Object.keys(docs[0])){ if(typeof docs[0][k] === 'number'){ key=k; break; } } }
                if(!key){ renderRawList(ct, docs); return; }
                const labels = docs.map((d, i)=> d.timestamp || d.time || i+1);
                const data = docs.map(d=> Number(d[key] || 0));
                const ctx = document.getElementById('sentimentChart').getContext('2d');
                new Chart(ctx, { type: 'line', data: { labels, datasets:[{label: key, data, borderColor:'#1976d2', fill:false}] }, options:{responsive:true} });
                const keys = ['timestamp', key, 'userId'];
                renderTable(ct, docs, keys);
            }).catch(e=>{ document.getElementById('sentimentsTable').textContent = 'Error: ' + e.message; });

            // GPS
            fetchJson('/export/gps').then(docs => {
                const ct = document.getElementById('gpsTable');
                if(!docs || docs.length===0){ 
                    ct.innerHTML='<em>No GPS records</em>'; 
                    document.getElementById('map').innerHTML = '<p>No GPS data available</p>';
                    return; 
                }
                const coords = [];
                docs.forEach(d=>{
                    let lat=null, lng=null;
                    if(d.latitude!==undefined && d.longitude!==undefined){ lat=d.latitude; lng=d.longitude; }
                    else if(d.lat!==undefined && d.lon!==undefined){ lat=d.lat; lng=d.lon; }
                    else if(d.lat!==undefined && d.lng!==undefined){ lat=d.lat; lng=d.lng; }
                    else if(d.coords && Array.isArray(d.coords)){ lat = d.coords[0]; lng = d.coords[1]; }
                    else if(d.location && d.location.latitude!==undefined){ lat=d.location.latitude; lng=d.location.longitude; }
                    if(lat!==null && lng!==null){ coords.push({lat:Number(lat), lng:Number(lng), raw:d}); }
                });
                renderRawList(ct, docs);
                if(coords.length>0){
                    const map = L.map('map').setView([coords[0].lat, coords[0].lng], 12);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
                    coords.forEach(c => L.marker([c.lat, c.lng]).addTo(map).bindPopup('<pre>'+JSON.stringify(c.raw,null,2)+'</pre>'));
                } else {
                    document.getElementById('map').innerHTML = '<p>No valid lat/lng fields found in GPS records.</p>';
                }
            }).catch(e=>{ 
                document.getElementById('gpsTable').textContent = 'Error: ' + e.message; 
                document.getElementById('map').innerHTML = '<p>Error loading GPS data</p>';
            });
        </script>
    </body>
</html>
    """
    return HTMLResponse(content=html)


@app.get("/export/vlogs/zip")
async def export_vlogs_zip():
    """Download a ZIP archive containing media files referenced by vlogs and a manifest."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    docs = await db['vlogs'].find({}).to_list(length=None)

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        try:
            zf.writestr('manifest.json', json.dumps(docs, default=str))
        except Exception:
            zf.writestr('manifest.json', '[]')

        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, doc in enumerate(docs, start=1):
                url = None
                for k in ('media_url', 'video_url', 'audio_url', 'url'):
                    if isinstance(doc.get(k), str) and doc.get(k).strip():
                        url = doc.get(k).strip()
                        break
                if not url:
                    continue
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        parts = url.split('?')[0].split('/')
                        fname = parts[-1] or f'media_{idx}'
                        fname = fname.replace('\n', '_').replace('\r', '_')
                        zf.writestr(fname, resp.content)
                except Exception:
                    continue

    buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="vlogs_media.zip"'}
    return StreamingResponse(buf, media_type='application/zip', headers=headers)


def _make_serializable(doc: dict) -> dict:
    """Convert ObjectId and other non-serializable types to strings"""
    out = {}
    for k, v in doc.items():
        try:
            json.dumps(v)
            out[k] = v
        except Exception:
            out[k] = str(v)
    return out


@app.get("/export/{kind}")
async def export_kind(kind: str):
    """Return all documents from the named collection as a downloadable JSON file."""
    if kind not in ALLOWED_EXPORTS:
        raise HTTPException(status_code=404, detail="Unknown export kind")
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        cursor = db[kind].find({})
        docs = await cursor.to_list(length=None)
        docs = [_make_serializable(d) for d in docs]
        content = json.dumps(docs, default=str)
        filename = f"{kind}.json"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export {kind}: {str(e)}")
