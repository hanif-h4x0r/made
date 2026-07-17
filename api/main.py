import os
import json
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import redis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# --- ATUR CORS (Supaya GitHub Pages Bisa Akses) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Nanti bisa kamu ganti spesifik ke URL GitHub Pages-mu
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- KONEKSI DATABASE (NEON POSTGRES) ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- KONEKSI CACHE (UPSTASH REDIS) ---
REDIS_URL = os.getenv("REDIS_URL")
cache = redis.from_url(REDIS_URL, decode_responses=True)

# --- MODEL DATABASE ---
class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)

# Bikin tabel otomatis di Neon kalau belum ada
Base.metadata.create_all(bind=engine)

# Dependency buat ambil session DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ENDPOINTS ---

@app.get("/notes")
def get_notes(db: Session = Depends(get_db)):
    # 1. Coba cek apakah data ada di Redis Cache
    cached_notes = cache.get("all_notes")
    if cached_notes:
        print("--- MENGAMBIL DATA DARI REDIS (CACHE HIT) ---")
        return json.loads(cached_notes)

    # 2. Kalau di Redis kosong, ambil dari Neon Postgres
    print("--- MENGAMBIL DATA DARI NEON (CACHE MISS) ---")
    notes_from_db = db.query(Note).all()
    results = [note.content for note in notes_from_db]

    # 3. Simpan hasilnya ke Redis, set kadaluarsa dalam 60 detik (optional)
    cache.setex("all_notes", 60, json.dumps(results))
    
    return results

@app.post("/notes")
def create_note(data: dict, db: Session = Depends(get_db)):
    content = data.get("note")
    if not content:
        raise HTTPException(status_code=400, detail="Catatan tidak boleh kosong")

    # 1. Simpan ke database Neon
    new_note = Note(content=content)
    db.add(new_note)
    db.commit()

    # 2. Hapus cache lama di Redis karena ada data baru
    cache.delete("all_notes")

    return {"message": "Catatan berhasil disimpan ke Postgres!"}
