import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re 

# ----------------------------------------------------------
# 1. 초기 설정
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키가 아직 설정되지 않았습니다. Streamlit 설정을 확인해주세요.")

try:
    genai.configure(api_key=GOOGLE_API_KEY.strip())
    model = genai.GenerativeModel('gemini-2.5-pro')
except Exception as e:
    st.error(f"API 키 오류: {e}")

# 기존의 connect_to_sheet 함수를 지우고 이걸로 덮어쓰세요!
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # [수정된 부분] 파일이 아니라, Streamlit의 비밀 금고(Secrets)에서 정보를 가져옵니다.
    try:
        # 1. 스트림릿 클라우드에 저장된 비밀정보(gcp_service_account)를 사용
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        # (혹시 로컬에서 실행할 때를 대비해 기존 방식도 남겨둠)
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        
    client = gspread.authorize(creds)
    return client.open("Safety_Project").sheet1

def update_sheet_any(task_name, target_col, new_value):
    try:
        sheet = connect_to_sheet()
        cell = sheet.find(task_name)
        col_map = {"상태": 3, "비고": 4, "세부내용": 2}
        target_col_idx = col_map.get(target_col)
        
        if target_col_idx:
            sheet.update_cell(cell.row, target_col_idx, new_value)
            return True
        else:
            return False
    except:
        return False

def add_new_task(task_name):
    try:
        sheet = connect_to_sheet()
        sheet.append_row([task_name, "설정필요", "대기", "-"])
        return True
    except:
        return False

def delete_task(task_name):
    """★ [신규 기능] 작업을 시트에서 삭제하는 함수"""
    try:
        sheet = connect_to_sheet()
        cell = sheet.find(task_name)
        sheet.delete_rows(cell.row) # 해당 줄을 아예 삭제
        return True
    except:
        return False

# ----------------------------------------------------------
# 3. 화면 구성 (대시보드 추가)
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

# 데이터 불러오기
try:
    sheet = connect_to_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    task_list = [str(row['작업명']) for row in data]
    
    # ★ [신규 기능] 대시보드 지표 계산
    total_tasks = len(df)
    completed_tasks = len(df[df['상태'] == '완료'])
    pending_tasks = len(df[df['상태'] == '대기'])
    
    # 화면 상단에 멋진 통계 박스 3개 배치
    m1, m2, m3 = st.columns(3)
    m1.metric("📌 전체 작업", f"{total_tasks}개")
    m2.metric("✅ 완료됨", f"{completed_tasks}개")
    m3.metric("⏳ 대기중", f"{pending_tasks}개")
    
    st.divider() # 구분선

except:
    st.error("시트 연결 대기중...")
    df = pd.DataFrame()
    task_list = []

col1, col2 = st.columns([1, 1.2])

# [오른쪽] 시트 현황판
with col2:
    st.subheader("📊 실시간 프로젝트 리스트")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=500)

# [왼쪽] 채팅창
with col1:
    st.subheader("💬 AI 작업 비서")
    chat_container = st.container(height=500, border=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input("명령을 입력하세요... (예: 라즈베리파이 작업 삭제해줘)")

    if prompt:
        with chat_container:
            with st.chat_message("user"):
                st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # --- AI 프롬프트 (삭제 기능 교육 추가) ---
        system_prompt = f"""
        너는 프로젝트 매니저야. 현재 작업 목록: {task_list}
        
        사용자의 명령을 분석해서 반드시 아래 JSON 형식으로 답해.
        
        1. [수정] {{"action": "update", "task": "작업명", "target": "상태/비고/세부내용", "value": "변경할내용"}}
        2. [추가] {{"action": "add", "task": "새로운작업명"}}
        3. [삭제] {{"action": "delete", "task": "삭제할작업명"}}
        
        [규칙]
        - '지워줘', '삭제해줘', '없애줘'는 delete 명령이야.
        - target은 '상태', '비고', '세부내용' 중 하나.
        
        사족 금지. 오직 JSON만 출력해.
        """
        
        full_prompt = system_prompt + "\n사용자: " + prompt
        
        try:
            response = model.generate_content(full_prompt)
            ai_text = response.text.strip()
            
            clean_text = ai_text.replace("```json", "").replace("```", "").strip()
            json_objects = re.findall(r'\{.*?\}', clean_text, re.DOTALL)
            
            processed_count = 0
            
            if json_objects:
                for json_str in json_objects:
                    try:
                        command = json.loads(json_str)
                        
                        # 1. 수정
                        if command.get("action") == "update":
                            if update_sheet_any(command['task'], command['target'], command['value']):
                                result_msg = f"✅ **'{command['task']}'**의 **{command['target']}** ➔ **'{command['value']}'** 변경!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                        
                        # 2. 추가
                        elif command.get("action") == "add":
                            if add_new_task(command['task']):
                                result_msg = f"🆕 **'{command['task']}'** 추가 완료!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1

                        # 3. ★ 삭제 (NEW!)
                        elif command.get("action") == "delete":
                            if delete_task(command['task']):
                                result_msg = f"🗑️ **'{command['task']}'** 작업을 삭제했습니다."
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                                
                    except json.JSONDecodeError:
                        continue 

                if processed_count > 0:
                    st.rerun()
                else:
                    with chat_container:
                        st.warning("명령을 실행하지 못했어요. 작업명을 정확히 확인해주세요.")
            else:
                with chat_container:
                    with st.chat_message("assistant"):
                        st.write(ai_text)
                st.session_state.messages.append({"role": "assistant", "content": ai_text})
                
        except Exception as e:

            st.error(f"에러 발생: {e}")
