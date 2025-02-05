from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, EmailStr

from database import engine, get_db, Base, SessionLocal
from models import User, Post, Tag, Rating

app = FastAPI()

Base.metadata.create_all(bind=engine)

# pydantic schemas
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
    user_id: int

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
    author_id: int
    tag_ids: List[int]

class PostResponse(PostBase):
    id: int
    author_id: int
    tags: List[TagResponse] = []
    ratings: List[RatingResponse] = []
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int
    posts: List[PostResponse] = []
    class Config:
        from_attributes = True

# endpoints

# create a user
@app.post("/users/create/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# get a specific user using id
@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# get all users
@app.get("/users/", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all() 
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users

# create a post
@app.post("/posts/create/", response_model=PostResponse)
def create_post(post: PostCreate, db: Session = Depends(get_db)):
    db_post = Post(title=post.title, content=post.content, author_id=post.author_id)

    tags = db.query(Tag).filter(Tag.id.in_(post.tag_ids)).all()
    db_post.tags.extend(tags)

    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

#get a specific post using post id
@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

#get a specific post using user id
@app.get("/users/{author_id}/posts", response_model=List[PostResponse])
def get_users_posts(author_id: int, db: Session = Depends(get_db)):
    posts = db.query(Post).filter(Post.author_id == author_id).all()
    if not posts:
        raise HTTPException(status_code=404, detail="No posts found")
    return posts


# get all posts
@app.get("/posts/", response_model=List[PostResponse])
def get_posts(db: Session = Depends(get_db)):
    posts = db.query(Post).all() 
    if not posts:
        raise HTTPException(status_code=404, detail="No posts found")
    return posts

# create a tag
@app.post("/tags/create/", response_model=TagResponse)
def create_tag(tag: TagCreate, db: Session = Depends(get_db)):
    db_tag = Tag(name=tag.name)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

# get all tags
@app.get("/tags/", response_model=List[TagResponse])
def get_tags(db: Session = Depends(get_db)):
    return db.query(Tag).all()

#create a rating
@app.post("/ratings/create/", response_model=RatingResponse)
def rate_post(rating: RatingCreate, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == rating.post_id).first()
    user = db.query(User).filter(User.id == rating.user_id).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db_rating = Rating(score=rating.score, post_id=rating.post_id, user_id=rating.user_id)
    db.add(db_rating)
    db.commit()
    db.refresh(db_rating)
    return db_rating

# egt the ratings to a post using post id
@app.get("/posts/{post_id}/ratings", response_model=List[RatingResponse])
def get_post_ratings(post_id: int, db: Session = Depends(get_db)):
    return db.query(Rating).filter(Rating.post_id == post_id).all()
