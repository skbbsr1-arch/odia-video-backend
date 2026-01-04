from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import uuid
import shutil
import json
import logging
import time
from typing import List

app = FastAPI(title="Odia Wedding AI Video Generator — SK Design Studio")

WORKDIR = Path("/mnt/data/renders")
WORKDIR.mkdir(parents=True, exist_ok=True)

BRAND_NAME = "SK Design Studio"
PRICE_LOCK = 999
UPI_ID = "9937286765"

MAX_FILES = 8
MAX_TOTAL_BYTES = 80 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odia-wedding-ai")

def job_meta_path(job_dir: Path) -> Path:
    return job_dir / "meta.json"

def write_meta(job_dir: Path, data: dict):
    data["updated_at"] = time.time()
    job_meta_path(job_dir).write_text(json.dumps(data, indent=2))

def read_meta(job_dir: Path) -> dict:
    return json.loads(job_meta_path(job_dir).read_text())

async def save_uploaded_files(files: List[UploadFile], job_dir: Path):
    saved, total = [], 0
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES} images allowed")
    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            await f.close()
            raise HTTPException(status_code=400, detail=f"Unsupported file type")
        fname = Path(f.filename).name
        dest = job_dir / f"{uuid.uuid4().hex}_{fname}"
        with dest.open("wb") as buf:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                buf.write(chunk)
                total += len(chunk)
                if total > MAX_TOTAL_BYTES:
                    await f.close()
                    raise HTTPException(status_code=413, detail="Upload limit exceeded")
        await f.close()
        saved.append(dest)
    return saved

def generate_odia_tts(text: str, out_dir: Path):
    p = out_dir / "voice.wav"
    p.write_bytes(b"")
    return p

def run_depth_motion(images, out_dir: Path):
    p = out_dir / "motion_frames"
    p.mkdir(exist_ok=True)
    return p

def run_lipsync(frames: Path, text: str, out_dir: Path, audio_path=None):
    p = out_dir / "lipsync_video.mp4"
    p.write_bytes(b"")
    return p

def apply_odia_theme(video: Path, out_dir: Path, mode="preview"):
    p = out_dir / ("odia_themed_preview.mp4" if mode=="preview" else "odia_themed_hd.mp4")
    p.write_bytes(b"")
    return p

def mix_sambalpuri_music(video: Path, out_dir: Path, welcome_time=2.2):
    p = out_dir / "final_60s.mp4"
    p.write_bytes(b"")
    return p

def render_hd_export(job_id: str, job_dir: Path):
    hd = apply_odia_theme(job_dir / "lipsync_video.mp4", job_dir, mode="hd")
    final_hd = mix_sambalpuri_music(hd, job_dir, welcome_time=2.2)
    meta = read_meta(job_dir)
    meta["status"] = "hd-ready"
    meta["hd_path"] = str(final_hd)
    write_meta(job_dir, meta)

def process_job_background(job_id, job_dir, groom, bride, script, images):
    meta = read_meta(job_dir); meta["status"] = "processing"; write_meta(job_dir, meta)
    frames = run_depth_motion(images, job_dir)
    voice = generate_odia_tts(script, job_dir)
    lips = run_lipsync(frames, script, job_dir, audio_path=voice)
    themed = apply_odia_theme(lips, job_dir, mode="preview")
    preview = mix_sambalpuri_music(themed, job_dir)
    meta = read_meta(job_dir)
    meta["status"] = "preview-ready"
    meta["preview_path"] = str(preview)
    write_meta(job_dir, meta)

@app.post("/api/generate")
async def generate(background_tasks: BackgroundTasks,
    groom: str = Form(...),
    bride: str = Form(...),
    script: str = Form("Welcome to our wedding ceremony"),
    photos: List[UploadFile] = File(...)
):
    job_id = str(uuid.uuid4())
    job_dir = WORKDIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    meta = {"job_id": job_id,"groom": groom,"bride": bride,"script": script,
            "status": "queued","price_lock": PRICE_LOCK,"created_at": time.time()}
    write_meta(job_dir, meta)
    image_paths = await save_uploaded_files(photos, job_dir)
    meta["images"] = [str(p) for p in image_paths]; write_meta(job_dir, meta)
    background_tasks.add_task(process_job_background, job_id, job_dir, groom, bride, script, image_paths)
    return {"job_id": job_id,"status": "queued",
            "preview": f"/api/preview/{job_id}",
            "download": f"/api/download/{job_id}",
            "hd_download": f"/api/download/{job_id}?quality=hd",
            "status_check": f"/api/status/{job_id}"}

@app.get("/api/status/{job_id}")
def status(job_id: str):
    job_dir = WORKDIR / job_id
    if not job_dir.exists(): return JSONResponse({"error":"Not found"},404)
    return read_meta(job_dir)

@app.get("/api/preview/{job_id}")
def preview(job_id: str):
    meta = read_meta(WORKDIR / job_id)
    p = Path(meta.get("preview_path",""))
    if not p.exists(): return JSONResponse({"error":"Not ready"},404)
    return FileResponse(p, media_type="video/mp4")

@app.get("/api/download/{job_id}")
def download(job_id: str, quality="sd"):
    meta = read_meta(WORKDIR / job_id)
    if quality=="hd":
        if meta.get("status")!="hd-ready":
            return JSONResponse({"error":"HD not unlocked"},403)
        p = Path(meta.get("hd_path",""))
    else:
        p = Path(meta.get("preview_path",""))
    if not p.exists(): return JSONResponse({"error":"Not ready"},404)
    return FileResponse(p, media_type="video/mp4",
        filename=f"{job_id}_odia_invitation_{quality}.mp4")
