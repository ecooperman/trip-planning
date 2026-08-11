from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db
from ..scraping.service import scrape_stay

router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.post("", response_model=schemas.Stay)
def create_stay(stay: schemas.StayCreate, db: Session = Depends(get_db)):
    db_stay = crud.create_stay(db, stay)
    if db_stay is None:
        raise HTTPException(status_code=400, detail="trip_id does not refer to an existing trip")
    return db_stay


@router.get("/{stay_id}", response_model=schemas.Stay)
def get_stay(stay_id: int, db: Session = Depends(get_db)):
    stay = crud.get_stay(db, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    return stay


@router.patch("/{stay_id}", response_model=schemas.Stay)
def update_stay(stay_id: int, updates: schemas.StayUpdate, db: Session = Depends(get_db)):
    stay = crud.update_stay(db, stay_id, updates)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    return stay


@router.delete("/{stay_id}")
def delete_stay(stay_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_stay(db, stay_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Stay not found")
    return {"ok": True}


@router.post("/{stay_id}/scrape", response_model=schemas.Stay)
def trigger_scrape(stay_id: int, db: Session = Depends(get_db)):
    stay = crud.get_stay(db, stay_id)
    if stay is None:
        raise HTTPException(status_code=404, detail="Stay not found")
    if not stay.url:
        raise HTTPException(status_code=400, detail="Stay has no URL to scrape")
    return scrape_stay(db, stay_id, stay.url)
