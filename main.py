import os
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
import httpx
import zipfile
from io import BytesIO

app = FastAPI()


# MongoDB client will be created at startup
mongo_client: Optional[AsyncIOMotorClient] = None
db = None


@app.on_event("startup")
async def startup_db_client():
    global mongo_client, db
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_client = AsyncIOMotorClient(mongo_uri)
    db_name = os.getenv("MONGO_DB", "emogo")
    db = mongo_client[db_name]


@app.on_event("shutdown")
async def shutdown_db_client():
    global mongo_client
    if mongo_client:
        mongo_client.close()


@app.get("/")
async def root():
    return {"message": "EmoGo backend is running"}


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

        <p style="margin-top:18px; font-size:0.9em; color:#666">If you deploy to a custom domain, just visit <code>/export</code> on that host.</p>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
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
                                        // render media players if media URL present
                                        const mediaUrl = doc.media_url || doc.video_url || doc.audio_url || doc.url;
                                        if(mediaUrl){
                                            try{
                                                const lower = String(mediaUrl).toLowerCase();
                                                if(lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.includes('video')){
                                                    const vid = document.createElement('video'); vid.controls = true; vid.src = mediaUrl; vid.style.maxWidth='100%'; vid.style.display='block'; vid.style.marginTop='6px'; div.appendChild(vid);
                                                } else if(lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.includes('audio')){
                                                    const aud = document.createElement('audio'); aud.controls = true; aud.src = mediaUrl; aud.style.display='block'; aud.style.marginTop='6px'; div.appendChild(aud);
                                                } else {
                                                    // unknown type: render link and show raw JSON below
                                                    const a = document.createElement('a'); a.href = mediaUrl; a.target = '_blank'; a.textContent = 'Open media'; a.style.display='inline-block'; a.style.marginTop='6px'; div.appendChild(a);
                                                }
                                                // link to zip download for convenience
                                                const zipLink = document.createElement('a'); zipLink.href = '/export/vlogs/zip'; zipLink.style.marginLeft='12px'; zipLink.textContent = 'Download media ZIP'; div.appendChild(zipLink);
                                            }catch(e){ /* ignore */ }
                                        }
                                        const body = document.createElement('pre'); body.className='raw'; body.textContent = JSON.stringify(doc, null, 2);
                                        div.appendChild(body); list.appendChild(div);
                });
                el.innerHTML=''; el.appendChild(list);
            }).catch(e=>{ document.getElementById('vlogsList').textContent = e.message; });

            // Sentiments
            fetchJson('/export/sentiments').then(docs => {
                const ct = document.getElementById('sentimentsTable');
                if(!docs || docs.length===0){ ct.innerHTML='<em>No sentiments</em>'; return; }
                // try to find numeric score field
                const scoreKeyCandidates = ['score','sentiment','value','polarity'];
                let key = null;
                for(const k of scoreKeyCandidates){ if(docs[0] && docs[0][k]!==undefined){ key=k; break; } }
                if(!key){ // pick first numeric field
                    for(const k of Object.keys(docs[0])){ if(typeof docs[0][k] === 'number'){ key=k; break; } }
                }
                if(!key){ renderRawList(ct, docs); return; }
                // build chart
                const labels = docs.map((d, i)=> d.timestamp || d.time || i+1);
                const data = docs.map(d=> Number(d[key] || 0));
                const ctx = document.getElementById('sentimentChart').getContext('2d');
                new Chart(ctx, { type: 'line', data: { labels, datasets:[{label: key, data, borderColor:'#1976d2', fill:false}] }, options:{responsive:true} });
                // table
                const keys = ['timestamp', key, 'userId'];
                renderTable(ct, docs, keys);
            }).catch(e=>{ document.getElementById('sentimentsTable').textContent = e.message; });

            // GPS
            fetchJson('/export/gps').then(docs => {
                const ct = document.getElementById('gpsTable');
                if(!docs || docs.length===0){ ct.innerHTML='<em>No GPS records</em>'; return; }
                // attempt to extract lat/lng pairs
                const coords = [];
                docs.forEach(d=>{
                    let lat=null, lng=null;
                    if(d.latitude!==undefined && d.longitude!==undefined){ lat=d.latitude; lng=d.longitude; }
                    else if(d.lat!==undefined && d.lon!==undefined){ lat=d.lat; lng=d.lon; }
                    else if(d.coords && Array.isArray(d.coords)){
                        lat = d.coords[0]; lng = d.coords[1];
                    } else if(d.location && d.location.latitude!==undefined){ lat=d.location.latitude; lng=d.location.longitude; }
                    if(lat!==null && lng!==null){ coords.push({lat:Number(lat), lng:Number(lng), raw:d}); }
                });
                // render table of all JSON as fallback
                renderRawList(ct, docs);
                // init map if coords found
                if(coords.length>0){
                    const map = L.map('map').setView([coords[0].lat, coords[0].lng], 12);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
                    coords.forEach(c => L.marker([c.lat, c.lng]).addTo(map).bindPopup('<pre>'+JSON.stringify(c.raw,null,2)+'</pre>'));
                } else {
                    document.getElementById('map').innerHTML = '<p>No valid lat/lng fields found in GPS records.</p>';
                }
            }).catch(e=>{ document.getElementById('gpsTable').textContent = e.message; document.getElementById('map').textContent = ''; });
        </script>
    </body>
</html>
    """
    return HTMLResponse(content=html)


@app.get("/export/vlogs/zip")
async def export_vlogs_zip():
    """Download a ZIP archive containing media files referenced by vlogs and a manifest.

    The endpoint will attempt to fetch media URLs found in each vlog document
    (fields commonly named `media_url`, `video_url`, `audio_url`, or `url`) and
    include them in a ZIP along with `manifest.json` containing the records.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    docs = await db['vlogs'].find({}).to_list(length=None)

    buf = BytesIO()
    # create zip in memory
    with zipfile.ZipFile(buf, 'w') as zf:
        # manifest
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
                        # sanitize filename
                        fname = fname.replace('\n', '_').replace('\r', '_')
                        zf.writestr(fname, resp.content)
                except Exception:
                    # skip failures to fetch
                    continue

    buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="vlogs_media.zip"'}
    return StreamingResponse(buf, media_type='application/zip', headers=headers)


def _make_serializable(doc: dict) -> dict:
    # Convert ObjectId and other non-serializable types to strings
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
    """Return all documents from the named collection as a downloadable JSON file.

    Allowed kinds: `vlogs`, `sentiments`, `gps`.
    """
    if kind not in ALLOWED_EXPORTS:
        raise HTTPException(status_code=404, detail="Unknown export kind")
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    cursor = db[kind].find({})
    docs = await cursor.to_list(length=None)
    # make serializable
    docs = [_make_serializable(d) for d in docs]
    content = json.dumps(docs, default=str)
    filename = f"{kind}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content, media_type="application/json", headers=headers)
