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

model = genai.GenerativeModel('gemini-2.5-')

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

# ----------------------------------------------------------
# [왼쪽] 채팅창 (여기서부터 끝까지 복사해서 덮어쓰세요!)
# ----------------------------------------------------------
with col1:
    st.subheader("💬 AI 작업 비서")
    chat_container = st.container(height=500, border=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input("명령을 입력하세요... (예: 진행 상황 요약해줘)")

    if prompt:
        with chat_container:
            with st.chat_message("user"):
                st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # ★★★ [업그레이드된 프롬프트] ★★★
        # AI에게 현재 시트의 모든 정보를 줍니다.
        current_data_context = df.to_csv(index=False) if not df.empty else "데이터 없음"

        system_prompt = f"""
        너는 유능한 프로젝트 매니저야.
        
        [현재 시트 데이터]
        {current_data_context}
        
        [수행 규칙]
        1. 사용자가 **'추가', '수정', '삭제'** 같은 명확한 명령을 내리면 반드시 아래 JSON 형식으로만 답해.
           - 수정: {{"action": "update", "task": "작업명", "target": "상태/비고/세부내용", "value": "변경할내용"}}
           - 추가: {{"action": "add", "task": "새로운작업명"}}
           - 삭제: {{"action": "delete", "task": "삭제할작업명"}}
           
        2. 사용자가 **'요약', '브리핑', '질문'**을 하면 JSON을 쓰지 말고, 위 [현재 시트 데이터]를 분석해서 자연스러운 한국어로 답변해.
           - 예: "현재 완료된 작업은 2개이고, 급한 건 000입니다."
        """
        
        full_prompt = system_prompt + "\n사용자: " + prompt
        
        try:
            response = model.generate_content(full_prompt)
            ai_text = response.text.strip()
            
            # JSON이 있는지 검사 (명령어인지 확인)
            clean_text = ai_text.replace("```json", "").replace("```", "").strip()
            json_objects = re.findall(r'\{.*?\}', clean_text, re.DOTALL)
            
            processed_count = 0
            
            # 1. JSON 명령어가 발견되면 실행 (기존 로직)
            if json_objects:
                for json_str in json_objects:
                    try:
                        command = json.loads(json_str)
                        
                        if command.get("action") == "update":
                            if update_sheet_any(command['task'], command['target'], command['value']):
                                result_msg = f"✅ **'{command['task']}'**의 **{command['target']}** ➔ **'{command['value']}'** 변경!"
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
                                
                    except json.JSONDecodeError:
                        continue 

                if processed_count > 0:
                    st.rerun()
                else:
                    # JSON은 있었지만 실행 실패 시 (혹은 AI가 텍스트랑 JSON을 섞어 썼을 때 텍스트 보여주기)
                     with chat_container:
                        with st.chat_message("assistant"):
                            st.write(ai_text)
                     st.session_state.messages.append({"role": "assistant", "content": ai_text})

            # 2. JSON이 없으면 그냥 일반 대화로 처리 (브리핑 기능 활성화!)
            else:
                with chat_container:
                    with st.chat_message("assistant"):
                        st.write(ai_text)
                st.session_state.messages.append({"role": "assistant", "content": ai_text})
                
        except Exception as e:
            st.error(f"에러 발생: {e}")