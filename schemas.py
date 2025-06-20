from pydantic import BaseModel
from datetime import date

class UserCreate(BaseModel):
    student_id: str
    password: str
    name: str
    phone_number: str
    main_language: str
    mbti: str
    career: str
    gender: str
    intro: str

class UserLogin(BaseModel):
    student_id: str
    password: str

class CompetitionCreate(BaseModel):
    title: str
    host: str
    apply_date: date
    match_start: date
    match_end: date
    min_members: int
    max_members: int

class CompetitionOut(CompetitionCreate):
    pid: int
    class Config:
        orm_mode = True
