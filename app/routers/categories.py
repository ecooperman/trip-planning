from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=List[schemas.Category])
def list_categories(db: Session = Depends(get_db)):
    return crud.get_categories(db)


@router.post("", response_model=schemas.Category)
def create_category(category: schemas.CategoryCreate, db: Session = Depends(get_db)):
    return crud.create_category(db, category)


@router.post("/reorder", response_model=List[schemas.Category])
def reorder_categories(payload: schemas.CategoryReorderRequest, db: Session = Depends(get_db)):
    return crud.reorder_categories(db, payload.ordered_ids)


@router.patch("/{category_id}", response_model=schemas.Category)
def update_category(category_id: int, updates: schemas.CategoryUpdate, db: Session = Depends(get_db)):
    category = crud.update_category(db, category_id, updates)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    result = crud.delete_category(db, category_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Category not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Category still has activities assigned to it")
    return {"ok": True}
