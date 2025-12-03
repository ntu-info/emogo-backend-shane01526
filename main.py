import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, Response, StreamingResponse, JSONResponse
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
    vlog: Optional[str] = None
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


@app.get("/export/vlogs")
async def export_vlogs():
    """Export all vlogs as JSON"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        cursor = db.vlogs.find({})
        vlogs = []
        async for doc in cursor:
            # Convert ObjectId to string
            doc['_id'] = str(doc['_id'])
            vlogs.append(doc)
        
        return JSONResponse(
            content=vlogs,
            headers={
                "Content-Disposition": "attachment; filename=vlogs.json"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export vlogs: {str(e)}")


@app.get("/export/sentiments")
async def export_sentiments():
    """Export all sentiments as JSON"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        cursor = db.sentiments.find({})
        sentiments = []
        async for doc in cursor:
            doc['_id'] = str(doc['_id'])
            sentiments.append(doc)
        
        return JSONResponse(
            content=sentiments,
            headers={
                "Content-Disposition": "attachment; filename=sentiments.json"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export sentiments: {str(e)}")


@app.get("/export/gps")
async def export_gps():
    """Export all GPS data as JSON"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        cursor = db.gps.find({})
        gps_data = []
        async for doc in cursor:
            doc['_id'] = str(doc['_id'])
            gps_data.append(doc)
        
        return JSONResponse(
            content=gps_data,
            headers={
                "Content-Disposition": "attachment; filename=gps.json"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export GPS data: {str(e)}")


@app.get("/export/vlogs/zip")
async def export_vlogs_zip():
    """Download all videos as a ZIP file"""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        cursor = db.vlogs.find({})
        vlogs = []
        async for doc in cursor:
            vlogs.append(doc)
        
        if not vlogs:
            raise HTTPException(status_code=404, detail="No vlogs found")
        
        # Create ZIP file in memory
        zip_buffer = BytesIO()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for idx, vlog in enumerate(vlogs):
                    # Get video URL from different possible fields
                    video_url = vlog.get('vlog') or vlog.get('media_url') or vlog.get('video_url') or vlog.get('url')
                    
                    if not video_url:
                        continue
                    
                    try:
                        # Download video
                        response = await client.get(video_url)
                        response.raise_for_status()
                        
                        # Generate filename
                        timestamp = vlog.get('timestamp', '')
                        user_id = vlog.get('userId', 'unknown')
                        filename = f"vlog_{idx+1}_{user_id}_{timestamp[:10]}.mp4"
                        
                        # Add to ZIP
                        zip_file.writestr(filename, response.content)
                        
                    except Exception as e:
                        print(f"Failed to download video {video_url}: {e}")
                        continue
        
        # Prepare ZIP for download
        zip_buffer.seek(0)
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=vlogs.zip"
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {str(e)}")


@app.get("/export", response_class=HTMLResponse)
async def export_index():
    """Interactive HTML page with data preview and download functionality."""
    html = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>EmoGo Data Export & Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
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
                max-width: 1200px;
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
            
            /* Tab Navigation */
            .tabs {
                display: flex;
                gap: 8px;
                margin-bottom: 24px;
                border-bottom: 2px solid #e0e0e0;
            }
            .tab {
                padding: 12px 24px;
                background: transparent;
                border: none;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                color: #666;
                border-bottom: 3px solid transparent;
                transition: all 0.3s;
            }
            .tab:hover {
                color: #667eea;
            }
            .tab.active {
                color: #667eea;
                border-bottom-color: #667eea;
            }
            
            .tab-content {
                display: none;
            }
            .tab-content.active {
                display: block;
            }
            
            /* Download Buttons */
            .download-section {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 24px;
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
                margin-bottom: 8px;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }
            .download-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(102, 126, 234, 0.6);
            }
            
            /* Video Grid */
            .video-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .video-card {
                background: #f8f9fa;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .video-card video {
                width: 100%;
                height: 200px;
                object-fit: cover;
                background: #000;
            }
            .video-info {
                padding: 12px;
            }
            .video-info h3 {
                margin: 0 0 8px 0;
                font-size: 14px;
                color: #333;
            }
            .video-info p {
                margin: 4px 0;
                font-size: 12px;
                color: #666;
            }
            
            /* Sentiment Chart */
            #sentimentChart {
                max-height: 300px;
                margin: 20px 0;
            }
            
            /* Table */
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                background: white;
            }
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #e0e0e0;
            }
            th {
                background: #f8f9fa;
                font-weight: 600;
                color: #333;
            }
            tr:hover {
                background: #f8f9fa;
            }
            
            /* Map */
            #map {
                height: 400px;
                border-radius: 8px;
                margin: 20px 0;
            }
            
            /* Loading & Empty States */
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
            .empty-state {
                text-align: center;
                padding: 60px 20px;
                color: #999;
            }
            .empty-state-icon {
                font-size: 64px;
                margin-bottom: 16px;
            }
            
            /* Stats */
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 16px;
                border-radius: 8px;
                text-align: center;
            }
            .stat-number {
                font-size: 32px;
                font-weight: 700;
                color: #667eea;
                margin-bottom: 4px;
            }
            .stat-label {
                font-size: 14px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎥 EmoGo Data Viewer</h1>
            <div class="subtitle">預覽和下載您收集的所有資料</div>
            
            <div id="status" class="status">
                <span>正在載入資料...</span>
                <div class="loading"></div>
            </div>

            <div class="stats-grid" id="statsGrid" style="display:none;">
                <div class="stat-card">
                    <div class="stat-number" id="vlogCount">0</div>
                    <div class="stat-label">影片</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="sentimentCount">0</div>
                    <div class="stat-label">情緒記錄</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="gpsCount">0</div>
                    <div class="stat-label">GPS 點位</div>
                </div>
            </div>

            <div class="tabs">
                <button class="tab active" onclick="switchTab('vlogs', event)">🎬 Vlogs</button>
                <button class="tab" onclick="switchTab('sentiments', event)">😊 Sentiments</button>
                <button class="tab" onclick="switchTab('gps', event)">📍 GPS</button>
            </div>

            <!-- Vlogs Tab -->
            <div id="vlogs-content" class="tab-content active">
                <div class="download-section">
                    <h3 style="margin:0 0 12px 0;">📥 下載選項</h3>
                    <a href="/export/vlogs/zip" class="download-btn">📦 下載影片 ZIP</a>
                    <a href="/export/vlogs" class="download-btn">📄 下載 JSON</a>
                </div>
                <h3>影片預覽</h3>
                <div id="vlogsGrid" class="video-grid"></div>
            </div>

            <!-- Sentiments Tab -->
            <div id="sentiments-content" class="tab-content">
                <div class="download-section">
                    <h3 style="margin:0 0 12px 0;">📥 下載選項</h3>
                    <a href="/export/sentiments" class="download-btn">📊 下載情緒資料</a>
                </div>
                <h3>情緒分析圖表</h3>
                <canvas id="sentimentChart"></canvas>
                <h3>情緒記錄</h3>
                <div id="sentimentsTable"></div>
            </div>

            <!-- GPS Tab -->
            <div id="gps-content" class="tab-content">
                <div class="download-section">
                    <h3 style="margin:0 0 12px 0;">📥 下載選項</h3>
                    <a href="/export/gps" class="download-btn">🗺️ 下載 GPS 資料</a>
                </div>
                <h3>位置地圖</h3>
                <div id="map"></div>
                <h3>GPS 記錄</h3>
                <div id="gpsTable"></div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            let currentTab = 'vlogs';
            let mapInstance = null;

            function switchTab(tabName, event) {
                currentTab = tabName;
                
                // Update tab buttons
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                event.target.classList.add('active');
                
                // Update content
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.getElementById(tabName + '-content').classList.add('active');
                
                // Initialize map if switching to GPS tab
                if (tabName === 'gps' && !mapInstance) {
                    loadGPSData();
                }
            }

            // Check backend status
            fetch('/').then(r => r.json()).then(data => {
                const statusDiv = document.getElementById('status');
                if (data.status === 'ok') {
                    statusDiv.className = 'status ok';
                    statusDiv.innerHTML = '✅ 資料庫連接成功';
                    
                    // Show stats
                    if (data.collections) {
                        document.getElementById('statsGrid').style.display = 'grid';
                        document.getElementById('vlogCount').textContent = data.collections.vlogs || 0;
                        document.getElementById('sentimentCount').textContent = data.collections.sentiments || 0;
                        document.getElementById('gpsCount').textContent = data.collections.gps || 0;
                    }
                    
                    // Load data
                    loadVlogs();
                    loadSentiments();
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.innerHTML = '❌ 資料庫連接失敗<br><small>' + (data.error || data.note || '') + '</small>';
                }
            }).catch(e => {
                document.getElementById('status').className = 'status error';
                document.getElementById('status').innerHTML = '❌ 無法連接後端';
            });

            // Load Vlogs
            function loadVlogs() {
                fetch('/export/vlogs')
                    .then(r => r.json())
                    .then(vlogs => {
                        const grid = document.getElementById('vlogsGrid');
                        if (!vlogs || vlogs.length === 0) {
                            grid.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📹</div><p>尚無影片資料</p></div>';
                            return;
                        }
                        
                        grid.innerHTML = vlogs.map((vlog, idx) => {
                            // Get video URL from different possible fields
                            const url = vlog.vlog || vlog.media_url || vlog.video_url || vlog.audio_url || vlog.url;
                            const timestamp = vlog.timestamp ? new Date(vlog.timestamp).toLocaleString('zh-TW') : '未知時間';
                            const userId = vlog.userId || '未知使用者';
                            
                            if (!url) {
                                return '';
                            }
                            
                            return `
                                <div class="video-card">
                                    <video controls>
                                        <source src="${url}" type="video/mp4">
                                        您的瀏覽器不支援影片播放
                                    </video>
                                    <div class="video-info">
                                        <h3>影片 #${idx + 1}</h3>
                                        <p>👤 ${userId}</p>
                                        <p>🕐 ${timestamp}</p>
                                        ${vlog.metadata && vlog.metadata.description ? `<p>📝 ${vlog.metadata.description}</p>` : ''}
                                    </div>
                                </div>
                            `;
                        }).join('');
                    })
                    .catch(e => {
                        document.getElementById('vlogsGrid').innerHTML = '<div class="empty-state"><p>載入失敗: ' + e.message + '</p></div>';
                    });
            }

            // Load Sentiments
            function loadSentiments() {
                fetch('/export/sentiments')
                    .then(r => r.json())
                    .then(sentiments => {
                        const table = document.getElementById('sentimentsTable');
                        
                        if (!sentiments || sentiments.length === 0) {
                            table.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😶</div><p>尚無情緒資料</p></div>';
                            return;
                        }
                        
                        // Create chart
                        const labels = sentiments.map((s, i) => {
                            if (s.timestamp) {
                                return new Date(s.timestamp).toLocaleString('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                            }
                            return '#' + (i + 1);
                        });
                        const scores = sentiments.map(s => s.score || s.value || s.polarity || 0);
                        
                        const ctx = document.getElementById('sentimentChart').getContext('2d');
                        new Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: labels,
                                datasets: [{
                                    label: '情緒分數',
                                    data: scores,
                                    borderColor: '#667eea',
                                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                                    tension: 0.4,
                                    fill: true
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: true,
                                plugins: {
                                    legend: { display: true }
                                },
                                scales: {
                                    y: {
                                        beginAtZero: false
                                    }
                                }
                            }
                        });
                        
                        // Create table
                        const tableHTML = `
                            <table>
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>情緒</th>
                                        <th>分數</th>
                                        <th>文字內容</th>
                                        <th>使用者</th>
                                        <th>時間</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${sentiments.map((s, i) => `
                                        <tr>
                                            <td>${i + 1}</td>
                                            <td>${getSentimentEmoji(s.sentiment)} ${s.sentiment || '-'}</td>
                                            <td>${(s.score || s.value || s.polarity || 0).toFixed(2)}</td>
                                            <td>${s.text || '-'}</td>
                                            <td>${s.userId || '-'}</td>
                                            <td>${s.timestamp ? new Date(s.timestamp).toLocaleString('zh-TW') : '-'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `;
                        table.innerHTML = tableHTML;
                    })
                    .catch(e => {
                        document.getElementById('sentimentsTable').innerHTML = '<div class="empty-state"><p>載入失敗: ' + e.message + '</p></div>';
                    });
            }

            function getSentimentEmoji(sentiment) {
                const s = (sentiment || '').toLowerCase();
                if (s.includes('positive') || s.includes('happy') || s.includes('joy')) return '😊';
                if (s.includes('negative') || s.includes('sad') || s.includes('angry')) return '😢';
                return '😐';
            }

            // Load GPS
            function loadGPSData() {
                fetch('/export/gps')
                    .then(r => r.json())
                    .then(gpsData => {
                        const table = document.getElementById('gpsTable');
                        const mapDiv = document.getElementById('map');
                        
                        if (!gpsData || gpsData.length === 0) {
                            table.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📍</div><p>尚無 GPS 資料</p></div>';
                            mapDiv.innerHTML = '<div class="empty-state"><p>無位置資料可顯示</p></div>';
                            return;
                        }
                        
                        // Extract coordinates
                        const coords = gpsData.map(g => {
                            let lat = g.latitude || g.lat;
                            let lng = g.longitude || g.lon || g.lng;
                            if (g.coords && Array.isArray(g.coords)) {
                                lat = g.coords[0];
                                lng = g.coords[1];
                            }
                            return { lat, lng, data: g };
                        }).filter(c => c.lat && c.lng);
                        
                        if (coords.length === 0) {
                            mapDiv.innerHTML = '<div class="empty-state"><p>GPS 資料格式不正確</p></div>';
                        } else {
                            // Initialize map
                            mapInstance = L.map('map').setView([coords[0].lat, coords[0].lng], 13);
                            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                                maxZoom: 19,
                                attribution: '© OpenStreetMap'
                            }).addTo(mapInstance);
                            
                            // Add markers
                            coords.forEach((c, i) => {
                                const marker = L.marker([c.lat, c.lng]).addTo(mapInstance);
                                const timestamp = c.data.timestamp ? new Date(c.data.timestamp).toLocaleString('zh-TW') : '未知時間';
                                marker.bindPopup(`
                                    <strong>位置 #${i + 1}</strong><br>
                                    經度: ${c.lng.toFixed(6)}<br>
                                    緯度: ${c.lat.toFixed(6)}<br>
                                    時間: ${timestamp}
                                `);
                            });
                            
                            // Fit bounds
                            if (coords.length > 1) {
                                const bounds = L.latLngBounds(coords.map(c => [c.lat, c.lng]));
                                mapInstance.fitBounds(bounds);
                            }
                        }
                        
                        // Create table
                        const tableHTML = `
                            <table>
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>緯度</th>
                                        <th>經度</th>
                                        <th>準確度</th>
                                        <th>使用者</th>
                                        <th>時間</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${gpsData.map((g, i) => {
                                        let lat = g.latitude || g.lat || '-';
                                        let lng = g.longitude || g.lon || g.lng || '-';
                                        if (g.coords && Array.isArray(g.coords)) {
                                            lat = g.coords[0];
                                            lng = g.coords[1];
                                        }
                                        return `
                                        <tr>
                                            <td>${i + 1}</td>
                                            <td>${typeof lat === 'number' ? lat.toFixed(6) : lat}</td>
                                            <td>${typeof lng === 'number' ? lng.toFixed(6) : lng}</td>
                                            <td>${g.accuracy ? g.accuracy.toFixed(2) + 'm' : '-'}</td>
                                            <td>${g.userId || '-'}</td>
                                            <td>${g.timestamp ? new Date(g.timestamp).toLocaleString('zh-TW') : '-'}</td>
                                        </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        `;
                        table.innerHTML = tableHTML;
                    })
                    .catch(e => {
                        document.getElementById('gpsTable').innerHTML = '<div class="empty-state"><p>載入失敗: ' + e.message + '</p></div>';
                    });
            }
        </script>
    </body>
</html>
    """
    return HTMLResponse(content=html)
