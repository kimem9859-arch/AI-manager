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

model = genai.GenerativeModel('gemini-2.5-pro')

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

# [함수 추가] 공지사항 읽어오기 (E2 셀)
def get_notice():
    try:
        sheet = connect_to_sheet()
        # 2행 5열(E2) 값을 가져옵니다.
        notice = sheet.cell(2, 5).value 
        return notice if notice else "등록된 공지사항이 없습니다."
    except:
        return "공지사항을 불러올 수 없습니다."

# [함수 추가] 공지사항 수정하기 (E2 셀)
def update_notice(new_text):
    try:
        sheet = connect_to_sheet()
        sheet.update_cell(2, 5, new_text) # 2행 5열(E2)에 덮어쓰기
        return True
    except:
        return False

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
# 3. 화면 구성
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

# 데이터 및 공지사항 불러오기
try:
    sheet = connect_to_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # ★ 여기서 공지사항을 가져옵니다!
    current_notice = get_notice() 
    
except:
    st.error("시트 연결 대기중...")
    df = pd.DataFrame()
    current_notice = "로딩 중..."

# --- UI 레이아웃 ---
with st.sidebar:
    st.header("⚙️ 화면 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)

# 레이아웃 나누기
if is_mobile:
    container_chat, container_sheet = st.tabs(["💬 채팅 비서", "📊 프로젝트 시트"])
else:
    col1, col2 = st.columns([1, 1.2])
    container_chat = col1
    container_sheet = col2

# [공통] 채팅창 맨 위에 공지사항 띄우기!
with container_chat:
    # 📢 공지사항을 예쁜 박스로 보여줍니다.
    st.info(f"📢 **공지사항:** {current_notice}")

    # ... (기존 채팅 UI 코드들) ...
    st.subheader("💬 AI 작업 비서")
    chat_container = st.container(height=400 if is_mobile else 600, border=True)
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input("명령을 입력하세요...")

    if prompt:
        with chat_container:
            with st.chat_message("user"):
                st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # --- AI 프롬프트 (공지사항 변경 규칙 추가!) ---
        current_data_context = df.to_csv(index=False) if not df.empty else "데이터 없음"

        system_prompt = f"""
        너는 프로젝트 매니저야.
        [현재 시트 데이터] {current_data_context}
        
        [명령 규칙]
        1. 공지사항 변경 명령: {{"action": "notice", "value": "새로운공지내용"}}
           - 예: "공지사항을 '내일 휴강'으로 바꿔줘"
           
        2. 작업 추가/수정/삭제:
           - 수정: {{"action": "update", "task": "작업명", "target": "상태/비고/세부내용", "value": "변경내용"}}
           - 추가: {{"action": "add", "task": "작업명"}}
           - 삭제: {{"action": "delete", "task": "작업명"}}
           
        3. 그 외 질문은 자연스러운 한국어로 답변.
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
                        
                        # ★ [새로운 기능] 공지사항 변경
                        if command.get("action") == "notice":
                            if update_notice(command['value']):
                                st.success(f"📢 공지사항이 **'{command['value']}'**(으)로 변경되었습니다!")
                                st.session_state.messages.append({"role": "assistant", "content": f"📢 공지사항 변경 완료: {command['value']}"})
                                processed_count += 1
                        
                        # (기존 기능들은 그대로 둠)
                        elif command.get("action") == "update":
                            if update_sheet_any(command['task'], command['target'], command['value']):
                                result_msg = f"✅ **'{command['task']}'** 수정 완료!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                        elif command.get("action") == "add":
                            if add_new_task(command['task']):
                                result_msg = f"🆕 **'{command['task']}'** 추가 완료!"
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                        elif command.get("action") == "delete":
                            if delete_task(command['task']):
                                result_msg = f"🗑️ **'{command['task']}'** 삭제 완료."
                                st.session_state.messages.append({"role": "assistant", "content": result_msg})
                                processed_count += 1
                                
                    except:
                        continue 

                if processed_count > 0:
                    st.rerun() # 새로고침해야 바뀐 공지사항이 바로 보입니다!
                else:
                     # 실행 실패 시 등
                     with chat_container:
                        st.write(ai_text)
                     st.session_state.messages.append({"role": "assistant", "content": ai_text})
            else:
                with chat_container:
                    st.write(ai_text)
                st.session_state.messages.append({"role": "assistant", "content": ai_text})
                
        except Exception as e:
            st.error(f"에러: {e}")