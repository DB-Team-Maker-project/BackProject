from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    student_id = Column(String, primary_key=True)
    password = Column(String, nullable=False) 
    name = Column(String)
    phone_number = Column(String) 
    main_language = Column(String)
    mbti = Column(String)
    career = Column(String)
    gender = Column(String)
    intro = Column(String)

class Competition(Base):
    __tablename__ = "competitions"
    pid = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)
    host = Column(String)
    apply_date = Column(Date)
    match_start = Column(Date)
    match_end = Column(Date)
    min_members = Column(Integer)
    max_members = Column(Integer)

class Participation(Base):
    __tablename__ = "participations"
    student_id = Column(String, ForeignKey("users.student_id"), primary_key=True)
    pid = Column(Integer, ForeignKey("competitions.pid"), primary_key=True)

class Team(Base):
    __tablename__ = "teams"
    tid = Column(Integer, primary_key=True, autoincrement=True)
    leader_id = Column(String, ForeignKey("users.student_id"))
    pid = Column(Integer, ForeignKey("competitions.pid"))
    completed = Column(Boolean, default=False)

class Member(Base):
    __tablename__ = "members"
    tid = Column(Integer, ForeignKey("teams.tid"), primary_key=True)
    student_id = Column(String, ForeignKey("users.student_id"), primary_key=True)

class Application(Base):
    __tablename__ = "applications"
    tid = Column(Integer, ForeignKey("teams.tid"), primary_key=True)
    student_id = Column(String, ForeignKey("users.student_id"), primary_key=True)
    status = Column(Integer, default=0)  # 0: 대기, 1: 수락, 2: 거절
