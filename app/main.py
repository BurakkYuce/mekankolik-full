
from fastapi import FastAPI
from app import models
from .routers import admin
from .routers import business
from app.routers import comment
from .database import engine
from .routers import  user
from .config import settings
from app.routers import auth
from .routers import campaign
from .routers import reservation
app = FastAPI()
@app.get("/")
async def root():
    return {"message": "Hello World"}
models.Base.metadata.create_all(bind=engine)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(business.router)    
app.include_router(reservation.router)
app.include_router(comment.router)
app.include_router(admin.router)
app.include_router(campaign.router) 