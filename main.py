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
    """Interactive HTML page with download buttons for all data types."""
    html = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>EmoGo Data Export</title>
        <style>
            * { box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                margin: 0; 
                padding: 20px; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                padding: 32px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }
            h1 {
                color: #333;
                margin: 0 0 12px 0;
                font-size: 32px;
            }
            .subtitle {
                color: #666;
                margin-bottom: 32px;
                font-size: 16px;
            }
            .status { 
                padding: 16px; 
                margin-bottom: 24px; 
                border-radius: 8px; 
                border-left: 4px solid;
            }
            .status.ok { 
                background: #d4edda; 
                color: #155724; 
                border-color: #28a745;
            }
            .status.error { 
                background: #f8d7da; 
                color: #721c24; 
                border-color: #dc3545;
            }
            .card {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 24px;
                margin-bottom: 20px;
                border: 1px solid #e0e0e0;
            }
            .card h2 {
                margin: 0 0 12px 0;
                color: #333;
                font-size: 22px;
                display: flex;
                align-items: center;
            }
            .card-icon {
                width: 40px;
                height: 40px;
                margin-right: 12px;
                background: white;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
            }
            .card-desc {
                color: #666;
                margin-bottom: 20px;
                font-size: 14px;
            }
            .download-btn {
                display: inline-block;
                padding: 12px 24px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 600;
                transition: all 0.3s;
                margin-right: 12px;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }
            .download-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(102, 126, 234, 0.6);
            }
            .download-btn.secondary {
                background: #6c757d;
                box-shadow: 0 4px 12px rgba(108, 117, 125, 0.3);
            }
            .download-btn.secondary:hover {
                box-shadow: 0 6px 16px rgba(108, 117, 125, 0.5);
            }
            .stats {
                display: flex;
                gap: 16px;
                margin-top: 16px;
            }
            .stat-box {
                flex: 1;
                background: white;
                padding: 12px;
                border-radius: 6px;
                text-align: center;
            }
            .stat-number {
                font-size: 24px;
                font-weight: 700;
                color: #667eea;
            }
            .stat-label {
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                margin-top: 4px;
            }
            .footer {
                text-align: center;
                color: #666;
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #e0e0e0;
                font-size: 14px;
            }
            .loading {
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid #f3f3f3;
                border-top: 2px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-left: 8px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎥 EmoGo Data Export</h1>
            <div class="subtitle">下載您收集的所有 vlogs、情緒分析和 GPS 資料</div>
            
            <div id="status" class="status">
                <span>正在檢查連線狀態...</span>
                <div class="loading"></div>
            </div>

            <div class="card">
                <h2>
                    <div class="card-icon">🎬</div>
                    Vlogs (影片檔案)
                </h2>
                <div class="card-desc">下載所有錄製的影片檔案，包含完整的 metadata 和媒體內容</div>
                <div id="vlogStats" class="stats" style="display:none;">
                    <div class="stat-box">
                        <div class="stat-number" id="vlogCount">-</div>
                        <div class="stat-label">影片數量</div>
                    </div>
                </div>
                <div style="margin-top: 16px;">
                    <a href="/export/vlogs/zip" class="download-btn" download>
                        📦 下載 MP4 影片壓縮檔 (.zip)
                    </a>
                    <a href="/export/vlogs" class="download-btn secondary" download>
                        📄 下載 JSON 資料
                    </a>
                </div>
            </div>

            <div class="card">
                <h2>
                    <div class="card-icon">😊</div>
                    Sentiments (情緒分析)
                </h2>
                <div class="card-desc">下載情緒分析結果，包含分數、情緒類型和時間戳記</div>
                <div id="sentimentStats" class="stats" style="display:none;">
                    <div class="stat-box">
                        <div class="stat-number" id="sentimentCount">-</div>
                        <div class="stat-label">記錄數量</div>
                    </div>
                </div>
                <div style="margin-top: 16px;">
                    <a href="/export/sentiments" class="download-btn" download>
                        📊 下載情緒資料 (.json)
                    </a>
                </div>
            </div>

            <div class="card">
                <h2>
                    <div class="card-icon">📍</div>
                    GPS (位置座標)
                </h2>
                <div class="card-desc">下載所有 GPS 位置記錄，包含經緯度和準確度資訊</div>
                <div id="gpsStats" class="stats" style="display:none;">
                    <div class="stat-box">
                        <div class="stat-number" id="gpsCount">-</div>
                        <div class="stat-label">位置點數</div>
                    </div>
                </div>
                <div style="margin-top: 16px;">
                    <a href="/export/gps" class="download-btn" download>
                        🗺️ 下載 GPS 資料 (.json)
                    </a>
                </div>
            </div>

            <div class="footer">
                <p>💡 提示：ZIP 檔案包含所有影片和完整的 manifest.json</p>
                <p>如有問題，請聯繫系統管理員</p>
            </div>
        </div>

        <script>
            // Check backend status and display stats
            fetch('/').then(r => r.json()).then(data => {
                const statusDiv = document.getElementById('status');
                if (data.status === 'ok') {
                    statusDiv.className = 'status ok';
                    statusDiv.innerHTML = '✅ 後端已連接到資料庫';
                    
                    // Show stats
                    if (data.collections) {
                        if (data.collections.vlogs !== undefined) {
                            document.getElementById('vlogStats').style.display = 'flex';
                            document.getElementById('vlogCount').textContent = data.collections.vlogs;
                        }
                        if (data.collections.sentiments !== undefined) {
                            document.getElementById('sentimentStats').style.display = 'flex';
                            document.getElementById('sentimentCount').textContent = data.collections.sentiments;
                        }
                        if (data.collections.gps !== undefined) {
                            document.getElementById('gpsStats').style.display = 'flex';
                            document.getElementById('gpsCount').textContent = data.collections.gps;
                        }
                    }
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.innerHTML = '❌ 資料庫未連接<br>' + 
                        '<small>錯誤: ' + (data.error || data.note || '未知錯誤') + '</small>';
                }
            }).catch(e => {
                const statusDiv = document.getElementById('status');
                statusDiv.innerHTML = '❌ 無法連接到後端: ' + e.message;
                statusDiv.className = 'status error';
            });
        </script>
    </body>
</html>
    """
    return HTMLResponse(content=html)


@app.get("/export/vlogs/zip")
async def export_vlogs_zip():
    """Download a ZIP archive containing all media files and a manifest."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    docs = await db['vlogs'].find({}).to_list(length=None)

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Write manifest
        try:
            manifest_data = json.dumps(docs, default=str, indent=2)
            zf.writestr('manifest.json', manifest_data)
        except Exception as e:
            zf.writestr('manifest.json', f'{{"error": "Failed to create manifest", "details": "{str(e)}"}}')

        # Download and add media files
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for idx, doc in enumerate(docs, start=1):
                # Try to find media URL
                url = None
                for k in ('media_url', 'video_url', 'audio_url', 'url'):
                    if isinstance(doc.get(k), str) and doc.get(k).strip():
                        url = doc.get(k).strip()
                        break
                
                if not url:
                    continue
                
                try:
                    print(f"Downloading media {idx}/{len(docs)}: {url}")
                    resp = await client.get(url)
                    
                    if resp.status_code == 200:
                        # Generate filename
                        parts = url.split('?')[0].split('/')
                        fname = parts[-1] if parts[-1] else f'media_{idx}'
                        
                        # Ensure extension
                        if '.' not in fname:
                            fname += '.mp4'
                        
                        # Clean filename
                        fname = fname.replace('\n', '_').replace('\r', '_').replace('/', '_').replace('\\', '_')
                        
                        # Add timestamp to avoid duplicates
                        timestamp = doc.get('timestamp', '').replace(':', '-').replace('.', '-')[:19]
                        if timestamp:
                            name_parts = fname.rsplit('.', 1)
                            fname = f"{name_parts[0]}_{timestamp}.{name_parts[1]}" if len(name_parts) == 2 else f"{fname}_{timestamp}"
                        
                        zf.writestr(f"videos/{fname}", resp.content)
                        print(f"✓ Added {fname} ({len(resp.content)} bytes)")
                    else:
                        print(f"✗ Failed to download {url}: HTTP {resp.status_code}")
                        
                except Exception as e:
                    print(f"✗ Error downloading {url}: {str(e)}")
                    continue

    buf.seek(0)
    headers = {
        "Content-Disposition": 'attachment; filename="emogo_vlogs.zip"',
        "Content-Type": "application/zip"
    }
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
        content = json.dumps(docs, default=str, indent=2)
        filename = f"emogo_{kind}.json"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/json"
        }
        return Response(content, media_type="application/json", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export {kind}: {str(e)}")
