from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from .database import engine, get_db, Base
from .models import User, Post, Tag, Rating
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
import jwt

SECRET_KEY = "BlogSecret007"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Dependency for endpoint protection
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow these origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create all tables
Base.metadata.create_all(bind=engine)

# -------------------------
# Pydantic Schemas
# -------------------------
class TagBase(BaseModel):
    name: str

class TagCreate(TagBase):
    pass

class TagResponse(TagBase):
    id: int
    class Config:
        from_attributes = True

class RatingBase(BaseModel):
    score: int

class RatingCreate(RatingBase):
    post_id: int

class RatingResponse(RatingBase):
    id: int
    post_id: int
    user_id: int
    class Config:
        from_attributes = True

class PostBase(BaseModel):
    title: str
    content: str

class PostCreate(PostBase):
    tags: List[str]

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None 

class PostResponse(PostBase):
    id: int
    author_id: int
    author_name: str  # holds the author's name
    tags: List[TagResponse] = []
    ratings: List[RatingResponse] = []
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str 

class UserResponse(UserBase):
    id: int
    posts: List[PostResponse] = []
    class Config:
        from_attributes = True

# -------------------------
# Endpoints
# -------------------------

# Health check endpoint
@app.get("/health", tags=["Health Check"])
def health_check():
    """
    Health check endpoint to verify the application is running.
    Returns a simple JSON response with status and timestamp.
    """
    return {"status": "ok", "timestamp": datetime.utcnow()}

# Create a user
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

@app.post("/users/create/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    hashed_pw = get_password_hash(user.password)
    db_user = User(name=user.name, email=user.email, hashed_password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Login
@app.post("/token/")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Incorrect email or password"
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id
    }

# Get all users
@app.get("/users/", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all() 
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users

# Create a post
@app.post("/posts/create/", response_model=PostResponse)
def create_post(
    post: PostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_post = Post(title=post.title, content=post.content, author_id=current_user.id)
    
    for tag_name in post.tags:
        existing_tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if existing_tag:
            db_post.tags.append(existing_tag)
        else:
            new_tag = Tag(name=tag_name)
            db.add(new_tag)
            db.flush() 
            db_post.tags.append(new_tag)
    
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

# Update a post
@app.put("/posts/{post_id}/", response_model=PostResponse)
def update_post(
    post_id: int,
    post_update: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this post")
    
    if post_update.title is not None:
        post.title = post_update.title
    if post_update.content is not None:
        post.content = post_update.content
    
    if post_update.tags is not None:
        post.tags = []
        for tag_name in post_update.tags:
            existing_tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if existing_tag:
                post.tags.append(existing_tag)
            else:
                new_tag = Tag(name=tag_name)
                db.add(new_tag)
                db.flush()
                post.tags.append(new_tag)
    
    db.commit()
    db.refresh(post)
    return post

# Delete a post
@app.delete("/posts/{post_id}/")
def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")
    
    db.delete(post)
    db.commit()
    return {"detail": "Post deleted successfully"}

# Get a specific post by post id
@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

# Get posts by current user
@app.get("/users/me/posts", response_model=List[PostResponse])
def get_my_posts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    posts = db.query(Post).filter(Post.author_id == current_user.id).all()
    if not posts:
        raise HTTPException(status_code=404, detail="No posts found")
    return posts

# Get all posts
@app.get("/posts/", response_model=List[PostResponse])
def get_posts(db: Session = Depends(get_db)):
    posts = db.query(Post).all() 
    if not posts:
        raise HTTPException(status_code=404, detail="No posts found")
    return posts

# Create a tag
@app.post("/tags/create/", response_model=TagResponse)
def create_tag(tag: TagCreate, db: Session = Depends(get_db)):
    db_tag = Tag(name=tag.name)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

# Get all tags
@app.get("/tags/", response_model=List[TagResponse])
def get_tags(db: Session = Depends(get_db)):
    return db.query(Tag).all()

# Create a rating
@app.post("/ratings/create/", response_model=RatingResponse)
def rate_post(
    rating: RatingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == rating.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    existing_rating = db.query(Rating).filter(
        Rating.post_id == rating.post_id,
        Rating.user_id == current_user.id
    ).first()
    
    if existing_rating:
        existing_rating.score = rating.score
        db.commit()
        db.refresh(existing_rating)
        return existing_rating
    else:
        new_rating = Rating(score=rating.score, post_id=rating.post_id, user_id=current_user.id)
        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)
        return new_rating

# Get ratings for a post
@app.get("/posts/{post_id}/ratings", response_model=List[RatingResponse])
def get_post_ratings(post_id: int, db: Session = Depends(get_db)):
    return db.query(Rating).filter(Rating.post_id == post_id).all()

# Helper functions for authentication
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
