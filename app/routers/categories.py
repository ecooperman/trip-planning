from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import current_user
from ..deps import get_db

# Your own categories - how *you* label your activities and places. Someone a
# trip is shared with sees the owner's labels only on what they can see.
router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=List[schemas.Category])
def list_categories(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return crud.get_categories(db, user.id)


@router.post("", response_model=schemas.Category)
def create_category(category: schemas.CategoryCreate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    if crud.category_name_taken(db, user.id, category.name):
        raise HTTPException(status_code=409, detail="A category with that name already exists")
    return crud.create_category(db, user.id, category)


@router.post("/reorder", response_model=List[schemas.Category])
def reorder_categories(
    payload: schemas.CategoryReorderRequest, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    return crud.reorder_categories(db, user.id, payload.ordered_ids)


@router.patch("/{category_id}", response_model=schemas.Category)
def update_category(
    category_id: int,
    updates: schemas.CategoryUpdate,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if updates.name is not None and crud.category_name_taken(db, user.id, updates.name, exclude_id=category_id):
        raise HTTPException(status_code=409, detail="A category with that name already exists")
    category = crud.update_category(db, user.id, category_id, updates)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.delete("/{category_id}")
def delete_category(category_id: int, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    result = crud.delete_category(db, user.id, category_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Category not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Category still has activities assigned to it")
    return {"ok": True}
