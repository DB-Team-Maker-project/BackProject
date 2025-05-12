from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Base, engine, get_db
from models import User, Competition, Participation, Team, Member, Application
from schemas import UserCreate, UserLogin, CompetitionCreate, CompetitionOut
from passlib.context import CryptContext
from typing import List
from datetime import date

app = FastAPI()
Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.student_id == user.student_id).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 학번입니다.")
    hashed_pw = get_password_hash(user.password)
    db_user = User(**user.dict(exclude={"password"}), password=hashed_pw)
    db.add(db_user)
    db.commit()
    return {"message": "회원가입 성공"}

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.student_id == user.student_id).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=400, detail="잘못된 학번 또는 비밀번호입니다.")
    return {"message": "로그인 성공", "admin": user.student_id == "11111111"}

@app.post("/competitions", response_model=CompetitionOut)
def create_competition(comp: CompetitionCreate, db: Session = Depends(get_db)):
    db_comp = Competition(**comp.dict())
    db.add(db_comp)
    db.commit()
    db.refresh(db_comp)
    return db_comp

@app.delete("/competitions/{pid}")
def delete_competition(pid: int, db: Session = Depends(get_db)):
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not comp:
        raise HTTPException(status_code=404, detail="대회 없음")
    db.delete(comp)
    db.commit()
    return {"message": "삭제 완료"}

@app.get("/competitions", response_model=List[CompetitionOut])
def list_competitions(db: Session = Depends(get_db)):
    return db.query(Competition).all()

@app.post("/participate/{student_id}/{pid}")
def participate(student_id: str, pid: int, db: Session = Depends(get_db)):
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not comp or date.today() > comp.match_start:
        raise HTTPException(status_code=400, detail="신청 마감")
    if db.query(Participation).filter_by(student_id=student_id, pid=pid).first():
        raise HTTPException(status_code=400, detail="이미 신청함")
    db.add(Participation(student_id=student_id, pid=pid))
    db.commit()
    return {"message": "신청 완료"}

@app.delete("/participate/{student_id}/{pid}")
def cancel_participation(student_id: str, pid: int, db: Session = Depends(get_db)):
    part = db.query(Participation).filter_by(student_id=student_id, pid=pid).first()
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not part:
        raise HTTPException(status_code=404, detail="신청 내역 없음")
    if date.today() > comp.match_start:
        raise HTTPException(status_code=400, detail="취소 불가")
    db.delete(part)
    db.commit()
    return {"message": "취소 완료"}

@app.post("/team/create/{student_id}/{pid}")
def create_team(student_id: str, pid: int, db: Session = Depends(get_db)):
    part_count = db.query(Participation).filter_by(pid=pid).count()
    team_count = db.query(Team).filter_by(pid=pid).count()
    comp = db.query(Competition).filter_by(pid=pid).first()
    if part_count // comp.min_members <= team_count:
        raise HTTPException(status_code=400, detail="팀장 수 초과")
    team = Team(leader_id=student_id, pid=pid, completed=False)
    db.add(team)
    db.commit()
    db.refresh(team)
    db.add(Member(tid=team.tid, student_id=student_id))
    db.commit()
    return {"message": "팀 생성 완료", "tid": team.tid}

@app.get("/teams/{pid}")
def list_teams(pid: int, db: Session = Depends(get_db)):
    teams = db.query(Team).filter_by(pid=pid).all()
    result = []
    for team in teams:
        members = db.query(Member).filter_by(tid=team.tid).all()
        users = [db.query(User).filter_by(student_id=m.student_id).first() for m in members]
        result.append({"tid": team.tid, "leader_id": team.leader_id, "completed": team.completed, "members": users})
    return result

@app.post("/apply/{student_id}/{tid}")
def apply_team(student_id: str, tid: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter_by(tid=tid).first()
    if team.completed:
        raise HTTPException(status_code=400, detail="이미 확정된 팀에는 신청할 수 없습니다.")
    if db.query(Application).filter_by(student_id=student_id, tid=tid).first():
        raise HTTPException(status_code=400, detail="이미 지원함")
    db.add(Application(student_id=student_id, tid=tid, status=0))
    db.commit()
    return {"message": "지원 완료"}


@app.post("/accept/{tid}/{student_id}")
def accept_member(tid: int, student_id: str, db: Session = Depends(get_db)):
    # 팀 정보 불러오기
    team = db.query(Team).filter_by(tid=tid).first()
    if not team:
        raise HTTPException(status_code=404, detail="팀 없음")

    # 같은 대회에서 이미 수락된 상태인지 확인
    accepted_app = (
        db.query(Application)
        .join(Team, Application.tid == Team.tid)
        .filter(
            Application.student_id == student_id,
            Application.status == 1,
            Team.pid == team.pid  # 같은 대회 내에서만 확인
        )
        .first()
    )
    if accepted_app:
        raise HTTPException(status_code=400, detail="이미 이 대회에서 다른 팀에 수락된 상태입니다.")

    # 수락 처리
    db.add(Member(tid=tid, student_id=student_id))
    application = db.query(Application).filter_by(tid=tid, student_id=student_id).first()
    if application:
        application.status = 1  # 수락
        db.commit()
        return {"message": "수락 완료"}
    else:
        raise HTTPException(status_code=404, detail="신청 내역 없음")


@app.delete("/reject/{tid}/{student_id}")
def reject_member(tid: int, student_id: str, db: Session = Depends(get_db)):
    application = db.query(Application).filter_by(tid=tid, student_id=student_id).first()
    if application:
        application.status = 2  # 거절
        db.commit()
        return {"message": "거절 완료"}
    raise HTTPException(status_code=404, detail="신청 내역 없음")

@app.get("/applications/{student_id}")
def get_my_applications(student_id: str, db: Session = Depends(get_db)):
    apps = db.query(Application).filter_by(student_id=student_id).all()
    result = []

    for app in apps:
        team = db.query(Team).filter_by(tid=app.tid).first()
        if not team:
            continue
        competition = db.query(Competition).filter_by(pid=team.pid).first()
        leader = db.query(User).filter_by(student_id=team.leader_id).first()
        result.append({
            "tid": app.tid,
            "competition_title": competition.title if competition else None,
            "team_leader_name": leader.name if leader else None,
            "status": app.status  # 0: 대기, 1: 수락, 2: 거절
        })

    return result


@app.post("/confirm/{tid}")
def confirm_team(tid: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter_by(tid=tid).first()
    comp = db.query(Competition).filter_by(pid=team.pid).first()
    member_count = db.query(Member).filter_by(tid=tid).count()
    if member_count < comp.min_members:
        raise HTTPException(status_code=400, detail="인원 부족")
    team.completed = True
    db.commit()
    return {"message": "팀 확정 완료"}

@app.delete("/leave/{tid}/{student_id}")
def leave_team(tid: int, student_id: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter_by(tid=tid).first()
    if team.completed:
        raise HTTPException(status_code=400, detail="완료된 팀은 탈퇴 불가")
    db.query(Member).filter_by(tid=tid, student_id=student_id).delete()
    db.commit()
    return {"message": "팀 탈퇴 완료"}
