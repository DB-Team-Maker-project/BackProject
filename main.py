from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Base, engine, get_db
from models import User, Competition, Participation, Team, Member, Application
from schemas import UserCreate, UserLogin, CompetitionCreate, CompetitionOut
from passlib.context import CryptContext
from typing import List
from datetime import date
from fastapi.middleware.cors import CORSMiddleware # CORS 임포트

app = FastAPI()

# CORS 미들웨어 설정
origins = [
    "http://localhost:3000", # React 개발 서버 주소
    # 필요한 경우 여기에 다른 origin들을 추가 (예: 배포된 프론트엔드 주소)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine) # DB 테이블 생성

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

@app.get("/")
def read_root():
    return {"message": "TEAMGETHER FastAPI 백엔드"}

@app.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.student_id == user.student_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 존재하는 학번입니다.")
    hashed_pw = get_password_hash(user.password)
    db_user = User(
        student_id=user.student_id,
        password=hashed_pw,
        name=user.name,
        phone_number=user.phone_number,
        main_language=user.main_language,
        mbti=user.mbti,
        career=user.career,
        gender=user.gender,
        intro=user.intro
    )
    db.add(db_user)
    db.commit()
    return {"message": "회원가입 성공"}

@app.post("/login")
def login(user_credentials: UserLogin, db: Session = Depends(get_db)): # 변수명 변경 UserLogin -> user_credentials
    db_user = db.query(User).filter(User.student_id == user_credentials.student_id).first()
    if not db_user or not verify_password(user_credentials.password, db_user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="잘못된 학번 또는 비밀번호입니다.")
    # "11111111" 학번을 관리자로 간주 (요청사항 기반)
    is_admin = user_credentials.student_id == "11111111"
    # 로그인 시 사용자 전체 정보 반환하도록 수정 (프론트엔드에서 활용)
    return {
        "message": "로그인 성공",
        "user": {
            "id": db_user.student_id, # 프론트엔드 호환성을 위해 id 필드 추가
            "student_id": db_user.student_id,
            "name": db_user.name,
            "phone_number": db_user.phone_number,
            "main_language": db_user.main_language,
            "mbti": db_user.mbti,
            "career": db_user.career,
            "gender": db_user.gender,
            "intro": db_user.intro,
            "isAdmin": is_admin # 관리자 여부 플래그
        }
    }


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 대회를 찾을 수 없습니다.")
    # 관련된 참가, 팀, 지원 정보도 삭제하는 로직 추가 (선택적이지만 권장)
    db.query(Participation).filter_by(pid=pid).delete()
    # 팀 삭제 시 Member, Application도 연쇄적으로 삭제되도록 관계 설정 또는 직접 삭제 로직 필요
    teams_to_delete = db.query(Team).filter_by(pid=pid).all()
    for team in teams_to_delete:
        db.query(Member).filter_by(tid=team.tid).delete()
        db.query(Application).filter_by(tid=team.tid).delete()
        db.delete(team)
    db.delete(comp)
    db.commit()
    return {"message": "대회 삭제 완료"}

@app.get("/competitions", response_model=List[CompetitionOut])
def list_competitions(db: Session = Depends(get_db)):
    return db.query(Competition).all()

# 대회 수정 API (추가)
@app.put("/competitions/{pid}", response_model=CompetitionOut)
def update_competition(pid: int, comp_update: CompetitionCreate, db: Session = Depends(get_db)):
    db_comp = db.query(Competition).filter_by(pid=pid).first()
    if not db_comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 대회를 찾을 수 없습니다.")

    for key, value in comp_update.dict().items():
        setattr(db_comp, key, value)

    db.commit()
    db.refresh(db_comp)
    return db_comp


@app.post("/participate/{student_id}/{pid}")
def participate(student_id: str, pid: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(student_id=student_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대회를 찾을 수 없습니다.")
    if date.today() > comp.match_start: # 매칭 시작일 이후에는 참가 신청 불가
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 매칭이 시작되어 참가 신청을 할 수 없습니다.")
    if db.query(Participation).filter_by(student_id=student_id, pid=pid).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 해당 대회에 참가 신청했습니다.")
    db_participation = Participation(student_id=student_id, pid=pid)
    db.add(db_participation)
    db.commit()
    return {"message": "대회 참가 신청 완료"}

@app.delete("/participate/{student_id}/{pid}")
def cancel_participation(student_id: str, pid: int, db: Session = Depends(get_db)):
    part = db.query(Participation).filter_by(student_id=student_id, pid=pid).first()
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="참가 신청 내역이 없습니다.")
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not comp: # 혹시 모를 경우
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대회 정보를 찾을 수 없습니다.")
    if date.today() >= comp.match_start: # 매칭 시작일 이후에는 참가 취소 불가
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="매칭이 시작되어 참가를 취소할 수 없습니다.")
    db.delete(part)
    db.commit()
    return {"message": "참가 신청 취소 완료"}

# 내가 참가한 대회 목록 가져오기 (추가)
@app.get("/participations/{student_id}", response_model=List[CompetitionOut])
def get_my_participated_competitions(student_id: str, db: Session = Depends(get_db)):
    participations = db.query(Participation).filter_by(student_id=student_id).all()
    if not participations:
        return []
    competition_pids = [p.pid for p in participations]
    competitions = db.query(Competition).filter(Competition.pid.in_(competition_pids)).all()
    return competitions


@app.post("/team/create/{student_id}/{pid}")
def create_team(student_id: str, pid: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(student_id=student_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    comp = db.query(Competition).filter_by(pid=pid).first()
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대회를 찾을 수 없습니다.")

    # 이미 해당 대회에 팀이 있는지 (팀장 또는 팀원) 확인
    existing_member = db.query(Member).join(Team).filter(Team.pid == pid, Member.student_id == student_id).first()
    if existing_member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 이 대회의 다른 팀에 소속되어 있습니다.")


    # 팀 개설 조건: (프로젝트A 참가 인원수 / 프로젝트A 최소 인원수) < 프로젝트A 팀장 수 (즉, 팀 수가 부족할 때만 개설 가능)
    # 또는 요청사항: (참가인원수/최소인원수) 가 팀장수와 같거나 클 때 개설 불가
    # 여기서는 후자로 구현
    part_count = db.query(Participation).filter_by(pid=pid).count()
    team_count = db.query(Team).filter_by(pid=pid).count()
    if comp.min_members > 0 : # 0으로 나누기 방지
      if (part_count // comp.min_members <= team_count) and team_count > 0 : # 팀이 하나라도 있을 때 이 조건 적용
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="팀 개설 조건(참가 인원 대비 팀 수)을 만족하지 못합니다.")


    team = Team(leader_id=student_id, pid=pid, completed=False)
    db.add(team)
    db.commit()
    db.refresh(team) # team.tid를 얻기 위해 refresh
    # 팀 생성 시 팀장을 멤버로 자동 추가
    db_member = Member(tid=team.tid, student_id=student_id)
    db.add(db_member)
    db.commit()
    return {"message": "팀 생성 완료", "team_id": team.tid} # tid -> team_id로 변경 (일관성)

# 특정 대회의 팀 목록 가져오기 (팀원 정보 포함 - 상세)
@app.get("/teams/{pid}", response_model=List[dict]) # 스키마 정의가 복잡하므로 dict로 임시 처리
def list_teams_for_competition(pid: int, db: Session = Depends(get_db)):
    teams = db.query(Team).filter_by(pid=pid).all()
    result = []
    for team_db in teams:
        leader_user = db.query(User).filter_by(student_id=team_db.leader_id).first()
        members_db = db.query(Member).filter_by(tid=team_db.tid).all()
        member_users_info = []
        for member_entry in members_db:
            user_info = db.query(User).filter_by(student_id=member_entry.student_id).first()
            if user_info:
                member_users_info.append({
                    "id": user_info.student_id,
                    "student_id": user_info.student_id,
                    "name": user_info.name,
                    "gender": user_info.gender,
                    "intro": user_info.intro,
                    "contact": user_info.phone_number,
                    # 필요시 다른 필드 추가
                })
        result.append({
            "id": team_db.tid,
            "team_id": team_db.tid, # 프론트엔드 호환성
            "project_id": team_db.pid, # 프론트엔드 호환성
            "leader_id": team_db.leader_id,
            "leader_info": { # 팀장 정보도 함께 반환
                "id": leader_user.student_id,
                "student_id": leader_user.student_id,
                "name": leader_user.name,
                "gender": leader_user.gender,
                "intro": leader_user.intro,
                "contact": leader_user.phone_number,
            } if leader_user else None,
            "members": member_users_info,
            "is_complete": team_db.completed
        })
    return result


@app.post("/apply/{student_id}/{tid}")
def apply_to_team(student_id: str, tid: int, db: Session = Depends(get_db)): # 함수명 변경
    user = db.query(User).filter_by(student_id=student_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    team = db.query(Team).filter_by(tid=tid).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="팀을 찾을 수 없습니다.")
    if team.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 확정된 팀에는 지원할 수 없습니다.")

    # 이미 해당 대회(team.pid)의 다른 팀에 멤버로 있는지 확인
    existing_member = db.query(Member).join(Team).filter(Team.pid == team.pid, Member.student_id == student_id).first()
    if existing_member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 이 대회의 다른 팀에 소속되어 있습니다. 지원할 수 없습니다.")


    if db.query(Application).filter_by(student_id=student_id, tid=tid).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 해당 팀에 지원했습니다.")

    # 팀 최대 인원수 체크
    comp = db.query(Competition).filter_by(pid=team.pid).first()
    current_members_count = db.query(Member).filter_by(tid=tid).count()
    if current_members_count >= comp.max_members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="팀 인원이 이미 가득 찼습니다.")


    db_application = Application(student_id=student_id, tid=tid, status=0) # 0: 대기
    db.add(db_application)
    db.commit()
    return {"message": "팀 지원 완료"}

@app.get("/team/applications/{leader_id}", response_model=List[dict]) # 팀장이 자기 팀들의 지원자 목록 확인
def get_applications_for_leader_teams(leader_id: str, db: Session = Depends(get_db)):
    # 해당 리더가 팀장인 모든 팀을 조회
    leader_teams = db.query(Team).filter_by(leader_id=leader_id, completed=False).all() # 미확정 팀만
    if not leader_teams:
        return []

    all_applications_info = []
    for team in leader_teams:
        # 해당 팀에 들어온 '대기 상태(0)' 신청서만 조회
        applications_for_team = db.query(Application).filter_by(tid=team.tid, status=0).all()
        for app in applications_for_team:
            applicant_user = db.query(User).filter_by(student_id=app.student_id).first()
            if applicant_user:
                all_applications_info.append({
                    "application_id": f"{app.tid}-{app.student_id}", # 프론트엔드에서 사용할 고유 ID
                    "team_id": team.tid,
                    "project_id": team.pid, # 어느 대회의 팀인지
                    "status": app.status, # 항상 0 (대기)
                    "applicant_info": { # 지원자 정보
                        "id": applicant_user.student_id,
                        "student_id": applicant_user.student_id,
                        "name": applicant_user.name,
                        "phone_number": applicant_user.phone_number,
                        "main_language": applicant_user.main_language,
                        "mbti": applicant_user.mbti,
                        "career": applicant_user.career,
                        "gender": applicant_user.gender,
                        "intro": applicant_user.intro
                    }
                })
    return all_applications_info


@app.post("/accept/{tid}/{applicant_student_id}") # applicant_student_id로 명확히
def accept_team_member(tid: int, applicant_student_id: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter_by(tid=tid).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="팀을 찾을 수 없습니다.")
    if team.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 확정된 팀입니다.")

    applicant = db.query(User).filter_by(student_id=applicant_student_id).first()
    if not applicant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="지원자 정보를 찾을 수 없습니다.")

    application = db.query(Application).filter_by(tid=tid, student_id=applicant_student_id, status=0).first() # 대기중인 신청만
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 지원자의 대기 중인 신청 내역이 없습니다.")

    # 팀 최대 인원수 체크
    comp = db.query(Competition).filter_by(pid=team.pid).first()
    current_members_count = db.query(Member).filter_by(tid=tid).count()
    if current_members_count >= comp.max_members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="팀 인원이 이미 가득 찼습니다. 수락할 수 없습니다.")

    # 이미 해당 대회(team.pid)의 다른 팀에 멤버로 있는지 확인 (중복 수락 방지)
    existing_member_in_competition = db.query(Member).join(Team).filter(Team.pid == team.pid, Member.student_id == applicant_student_id).first()
    if existing_member_in_competition:
        # 만약 이전에 다른 팀 지원이 거절되었거나, 본인이 탈퇴했다면 수락 가능할 수도 있음.
        # 여기서는 엄격하게, 해당 대회에 어떤 팀이든 멤버로 있으면 중복 수락 불가로 처리.
        # 또는, Application 테이블의 status를 보고, 다른 팀에서 이미 status=1(수락) 상태라면 여기서 막아야 함.
        # FastAPI의 /accept 엔드포인트의 기존 로직(accepted_app) 참고 및 통합 필요.
        # 현재 로직은 신청서(Application) 기준이므로, Member 테이블에 추가하기 전에 Application 상태 변경.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="해당 지원자는 이미 이 대회의 다른 팀에 소속되어 있습니다.")


    db_member = Member(tid=tid, student_id=applicant_student_id)
    db.add(db_member)
    application.status = 1  # 1: 수락
    db.commit()
    return {"message": "팀원 수락 완료"}


@app.post("/reject/{tid}/{applicant_student_id}") # POST로 변경 (상태 업데이트) 또는 DELETE 유지 시 의미 명확화
def reject_team_member(tid: int, applicant_student_id: str, db: Session = Depends(get_db)):
    application = db.query(Application).filter_by(tid=tid, student_id=applicant_student_id, status=0).first() # 대기중인 신청만
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 지원자의 대기 중인 신청 내역이 없습니다.")
    application.status = 2  # 2: 거절
    db.commit()
    return {"message": "팀원 지원 거절 완료"}

# 내가 지원한 신청서 목록 (상태 포함)
@app.get("/applications/my/{student_id}", response_model=List[dict])
def get_my_sent_applications(student_id: str, db: Session = Depends(get_db)):
    apps = db.query(Application).filter_by(student_id=student_id).all()
    result = []
    for app in apps:
        team = db.query(Team).filter_by(tid=app.tid).first()
        if not team: continue
        competition = db.query(Competition).filter_by(pid=team.pid).first()
        leader = db.query(User).filter_by(student_id=team.leader_id).first()
        result.append({
            "application_id": f"{app.tid}-{app.student_id}",
            "team_id": app.tid,
            "project_id": team.pid,
            "project_name": competition.title if competition else "N/A",
            "team_leader_name": leader.name if leader else "N/A",
            "status": app.status  # 0: 대기, 1: 수락, 2: 거절
        })
    return result


@app.post("/team/confirm/{tid}") # URL 변경 team/confirm
def confirm_project_team(tid: int, db: Session = Depends(get_db)): # 함수명 변경
    team = db.query(Team).filter_by(tid=tid).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="팀을 찾을 수 없습니다.")
    if team.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 확정된 팀입니다.")

    comp = db.query(Competition).filter_by(pid=team.pid).first()
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="관련 대회 정보를 찾을 수 없습니다.")

    member_count = db.query(Member).filter_by(tid=tid).count()
    if member_count < comp.min_members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"팀 확정을 위해 최소 {comp.min_members}명의 팀원이 필요합니다. (현재 {member_count}명)")

    team.completed = True
    db.commit()
    # 팀 확정 시, 해당 팀에 대기 중이던 다른 지원서들은 자동으로 거절 처리 (선택적)
    db.query(Application).filter(Application.tid == tid, Application.status == 0).update({"status": 2}) # 대기 중인 것들을 거절로
    db.commit()

    return {"message": "팀 확정 완료"}

@app.delete("/team/leave/{tid}/{student_id}") # URL 변경 team/leave
def leave_project_team(tid: int, student_id: str, db: Session = Depends(get_db)): # 함수명 변경
    team = db.query(Team).filter_by(tid=tid).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="팀을 찾을 수 없습니다.")
    if team.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 확정된 팀에서는 탈퇴할 수 없습니다.")
    if team.leader_id == student_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="팀장은 팀을 탈퇴할 수 없습니다. 팀 해체 기능을 이용해주세요.") # 팀 해체 기능은 별도 구현 필요

    member_to_delete = db.query(Member).filter_by(tid=tid, student_id=student_id).first()
    if not member_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="팀 소속 멤버가 아닙니다.")

    db.delete(member_to_delete)
    # 관련된 Application 정보도 삭제 또는 상태 변경 (선택적)
    # db.query(Application).filter_by(tid=tid, student_id=student_id).delete()
    db.commit()
    return {"message": "팀 탈퇴 완료"}

# 사용자 정보 조회 API (추가 - MemberInfoPopup 등에서 사용)
@app.get("/users/{student_id}", response_model=dict) # 간단히 dict로 처리, UserOut 스키마 정의 권장
def get_user_details(student_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(student_id=student_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    return {
        "id": user.student_id,
        "student_id": user.student_id,
        "name": user.name,
        "phone_number": user.phone_number,
        "main_language": user.main_language,
        "mbti": user.mbti,
        "career": user.career,
        "gender": user.gender,
        "intro": user.intro,
        "isAdmin": user.student_id == "11111111" # 관리자 여부 (임시)
    }
