from fastapi import APIRouter
from pymongo.errors import PyMongoError
from app.database.database import client, db

router = APIRouter(prefix="/api/database", tags=["Database Monitoring"])

@router.get("/health")
def db_health():
    try:
        client.admin.command("ping")
        return {"status": "healthy", "database": "MongoDB"}
    except PyMongoError:
        return {"status": "unhealthy", "database": "MongoDB"}

@router.get("/statistics")
def db_statistics():
    collections = db.list_collection_names()
    total_objects = sum(db[collection].count_documents({}) for collection in collections)
    stats = db.command("dbstats")
    return {
        "collections_count": len(collections),
        "total_objects": total_objects,
        "data_size_mb": round(stats.get("dataSize", 0) / 1024 / 1024, 2),
        "storage_size_mb": round(stats.get("storageSize", 0) / 1024 / 1024, 2),
    }

@router.get("/storage")
def db_storage():
    stats = db.command("dbstats")
    return {
        "data_size_mb": round(stats.get("dataSize", 0) / 1024 / 1024, 2),
        "storage_size_mb": round(stats.get("storageSize", 0) / 1024 / 1024, 2),
        "index_size_mb": round(stats.get("indexSize", 0) / 1024 / 1024, 2),
    }

@router.get("/collections")
def db_collections():
    return {"collections": db.list_collection_names()}
