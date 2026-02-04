import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re 
import time

# ----------------------------------------------------------
# 1. 초기 설정 & 함수
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

# 세션 상태 초기화
if "first_visit" not in st.session_state:
    st.session_state.first_visit = True
if "messages" not in st.session_state:
    st.session_state.messages = []

# ★ [핵심 기능] 방금 대화 취소 함수
def undo_last_chat():
    if len(st.session_state.messages) >= 2:
        st.session_state.messages.pop() # AI 답변 삭제
        st.session_state.messages.pop() # 내 질문 삭제
        st.toast("↩️ 방금 대화를 취소했습니다!", icon="🗑️")
        time.sleep(0.5)
        st.rerun()
    else:
        st.toast("⚠️ 취소할 대화 내역이 없습니다.")

# 사용 설명서 팝업
@st.dialog("📖 사용 설명서")
def show_guide():
    st.markdown("""
    ### 👋 환영합니다!
    
    **1. 💬 채팅 비서**
    작업 관리 & 물품 검색을 도와줍니다.
    
    **2. 📊 작업 리스트**
    할 일 목록을 관리합니다. ('작업' 시트)
    
    **3. 📦 물품 리스트**
    구매 목록을 확인합니다. ('물품' 시트)
    
    **4. ↩️ 되돌리기 버튼**
    채팅창 오른쪽 위의 빨간 버튼을 누르면 마지막 대화를 취소합니다.
    """)
    if st.button("닫기", use_container_width=True):
        st.rerun()

if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("API 키 설정 필요")

# 모델 설정
model = genai.GenerativeModel('gemini-2.5-pro')

def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client.open("Safety_Project")

def connect_to_task_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("작업")
    except: return sh.sheet1 

def connect_to_notice_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("공지")
    except:
        new = sh.add_worksheet("공지", 10, 2)
        new.update_cell(1,1,"공지없음")
        return new

def connect_to_item_sheet():
    sh = get_spreadsheet()
    try: return sh.worksheet("물품")
    except:
        new_sheet = sh.add_worksheet(title="물품", rows="100", cols="6")
        new_sheet.append_row(["품목명", "수량", "가격", "구매처", "링크", "비고"])
        return new_sheet

def get_notice():
    try:
        sh = connect_to_notice_sheet()
        val = sh.cell(1,1).value
        return val if val else "공지없음"
    except: return "-"

def update_notice(txt):
    try:
        connect_to_notice_sheet().update_cell(1,1,txt)
        return True
    except: return False

def update_sheet_any(task, col, val):
    try:
        sh = connect_to_task_sheet()
        cell = sh.find(task)
        col_map = {"상태":3, "비고":4, "세부내용":2}
        idx = col_map.get(col)
        if idx: sh.update_cell(cell.row, idx, val)
        return True
    except: return False

def add_new_task(task):
    try:
        connect_to_task_sheet().append_row([task, "설정필요", "대기", "-"])
        return True
    except: return False

def delete_task(task):
    try:
        sh = connect_to_task_sheet()
        cell = sh.find(task)
        sh.delete_rows(cell.row)
        return True
    except: return False

# ----------------------------------------------------------
# 2. 데이터 로딩
# ----------------------------------------------------------
if st.session_state.first_visit:
    show_guide()
    st.session_state.first_visit = False

try:
    task_sheet = connect_to_task_sheet()
    data = task_sheet.get_all_records()
    df = pd.DataFrame(data)
    total = len(df)
    done = len(df[df['상태']=='완료']) if not df.empty else 0
    pending = len(df[df['상태']=='대기']) if not df.empty else 0
except:
    df = pd.DataFrame()
    total, done, pending = 0,0,0

try:
    item_sheet = connect_to_item_sheet()
    item_data = item_sheet.get_all_records()
    df_items = pd.DataFrame(item_data)
    if not df_items.empty:
        df_items = df_items.replace("", pd.NA)
        df_items.iloc[:, 0] = df_items.iloc[:, 0].ffill()
        df_items = df_items.dropna(subset=[df_items.columns[1]])
        df_items = df_items.fillna("-")
except:
    df_items = pd.DataFrame()

current_notice = get_notice()

# ----------------------------------------------------------
# 3. 화면 구성
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.rerun()
    if st.button("❓ 도움말"): show_guide()
    st.link_button("📂 구글시트 바로가기", "https://docs.google.com/spreadsheets/")

# 통계 UI
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(255,255,255,0.1); padding:10px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.2);">
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">📌 전체</p><p style="margin:0; font-size:20px; font-weight:bold;">{total}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">✅ 완료</p><p style="margin:0; font-size:20px; font-weight:bold;">{done}</p></div>
        <div style="text-align:center;"><p style="margin:0; font-size:14px; opacity:0.8;">⏳ 대기</p><p style="margin:0; font-size:20px; font-weight:bold;">{pending}</p></div>
    </div>
""", unsafe_allow_html=True)

if is_mobile:
    tab1, tab2, tab3 = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat, c_sheet, c_items = tab1, tab2, tab3
else:
    col1, col2 = st.columns([1, 1.2])
    c_chat = col1
    with col2:
        sub_tab1, sub_tab2 = st.tabs(["📊 작업 리스트", "📦 물품 리스트"])
        c_sheet = sub_tab1
        c_items = sub_tab2

# [탭 2] 작업
with c_sheet:
    if not df.empty:
        # 1. 색상 스타일 함수 정의 (그라데이션 로직)
        def color_progress(val):
            # 값이 없거나 에러나면 투명하게
            if pd.isna(val) or val == "" or val == "-":
                return None
            
            # 문자열(10%)을 숫자(10)로 변환
            try:
                numeric_val = float(str(val).replace('%', '').strip())
            except:
                return None

            # 100% 이상이면 파란색 (완료)
            if numeric_val >= 100:
                return 'background-color: #2E86C1; color: white; font-weight: bold;'
            
            # 0~99% 그라데이션 (빨강 -> 초록)
            # 숫자가 낮을수록 빨강(Red), 높을수록 초록(Green) 비율을 높임
            red = int(255 * (100 - numeric_val) / 100)
            green = int(255 * numeric_val / 100)
            # 글자색은 검정으로 통일하여 가독성 확보
            return f'background-color: rgb({red}, {green}, 100); color: black;'

        # 2. 스타일 적용 (진행률 컬럼이 있을 때만)
        if '진행률' in df.columns:
            # Pandas의 Style 기능을 사용하여 색 입히기
            st.dataframe(
                df.style.map(color_progress, subset=['진행률']), 
                use_container_width=True, 
                height=500
            )
        else:
            # 진행률 컬럼이 아직 없으면 그냥 보여주기
            st.dataframe(df, use_container_width=True, height=500)
            st.caption("※ 구글 시트에 '진행률' 열을 추가하면 색상이 표시됩니다.")
            
    else: st.info("작업 데이터가 없습니다.")

# [탭 3] 물품 (수정됨: 비용 계산 기능 강화 + 디버깅)
with c_items:
    if not df_items.empty:
        df_display = df_items.copy()
        
        # --- (1) 링크 처리 로직 (기존 유지) ---
        if "구매 링크" not in df_display.columns:
            df_display["구매 링크"] = None

        if "비고" in df_display.columns:
            for i, row in df_display.iterrows():
                val = str(row["비고"])
                if val.startswith("http"):
                    df_display.at[i, "구매 링크"] = val
                    df_display.at[i, "비고"] = "-"

        cols_to_clean = ["구매 링크"]
        for col in cols_to_clean:
            df_display[col] = df_display[col].replace({"-": None, "": None, "nan": None})
            df_display[col] = df_display[col].where(pd.notnull(df_display[col]), None)
        # ------------------------------------

        # --- (2) 표 출력 ---
        st.dataframe(
            df_display, 
            use_container_width=True, 
            height=500,
            column_config={
                "구매 링크": st.column_config.LinkColumn("구매 링크", display_text="🔗 바로가기")
            }
        )

        # --- (3) ★ 핵심 수정: 총 비용 계산 로직 ---
        # '금액'이랑 비슷한 단어가 들어간 열을 다 찾아봅니다. (예: '금액', '총금액', '가격', '비용')
        possible_cols = [col for col in df_items.columns if any(keyword in col for keyword in ['금액', '가격', '비용'])]
        
        if possible_cols:
            target_col = possible_cols[0] # 찾은 것 중 첫 번째를 사용 (예: '금액')
            try:
                # 1. 문자열로 변환 -> 2. 콤마(,) 제거 -> 3. '원' 글자 제거 -> 4. 숫자로 변환
                # (숫자 변환이 안 되는 글자는 0으로 처리)
                total_cost = (
                    df_items[target_col]
                    .astype(str)
                    .str.replace(',', '')
                    .str.replace('원', '')
                    .apply(pd.to_numeric, errors='coerce')
                    .fillna(0)
                    .sum()
                )
                
                # 멋진 UI 표시
                st.markdown(f"""
                    <div style="
                        text-align: right; 
                        padding: 15px; 
                        background-color: rgba(40, 167, 69, 0.1); 
                        border: 1px solid rgba(40, 167, 69, 0.3);
                        border-radius: 10px; 
                        margin-top: 10px;">
                        <span style="font-size: 1.1em; font-weight: bold; margin-right: 10px; color: #555;">💰 총 예상 비용 ({target_col}):</span>
                        <span style="font-size: 1.8em; color: #28a745; font-weight: bold;">{int(total_cost):,}원</span>
                    </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"계산 중 오류 발생: {e}")
        else:
            # 못 찾았으면 왜 못 찾았는지 알려줌 (이게 뜨면 시트 열 이름을 확인하세요!)
            st.warning(f"⚠️ 비용 계산 불가: 시트에 '금액'이나 '가격'이라고 적힌 열이 없습니다.\n(현재 인식된 열 이름: {list(df_items.columns)})")

    else:
        st.info("📦 물품 리스트가 비어있습니다.")

with c_chat:
    if current_notice not in ["-", "공지없음"]:
        st.info(f"📢 **공지:** {current_notice}")
    
    # ★ [UI 변경] 채팅창 헤더에 '되돌리기' 버튼 배치
    # 컬럼을 나누어 왼쪽엔 제목, 오른쪽엔 버튼을 둡니다.
    chat_header_col1, chat_header_col2 = st.columns([1, 0.4])
    
    with chat_header_col1:
        st.subheader("💬 AI 비서")
    
    with chat_header_col2:
        # 빨간색(primary) 버튼으로 눈에 띄게 만듭니다.
        if st.button("↩️ 되돌리기", type="primary", use_container_width=True, help="방금 한 질문과 답변을 삭제합니다."):
            undo_last_chat()

    chat_con = st.container(height=400 if is_mobile else 550, border=True)
    
    with chat_con:
        for m in st.session_state.messages: st.chat_message(m["role"]).write(m["content"])

# ------------------------------------------------------------------
# 4. AI 답변 및 액션 처리 (수정됨: 진행률 변경 기능 추가)
# ------------------------------------------------------------------
if prompt := st.chat_input("AI 매니저에게 명령하세요 (예: 3D 모델링 진행률 50%로 변경해줘)"):
    # 1. 사용자 메시지 표시
    st.chat_message("user").write(prompt)
    
    # 2. AI에게 보낼 시스템 명령 (뇌 개조: update 기능 교육)
    # AI가 상황을 파악하고 JSON으로 명령을 내리도록 유도합니다.
    system_instruction = f"""
    너는 이 프로젝트의 AI 매니저야. 사용자의 말을 듣고 구글 시트를 관리해야 해.
    사용자의 의도를 파악해서 반드시 아래 **JSON 형식**으로만 대답해. (다른 사족 붙이지 마)
    
    [현재 데이터 현황]
    - 작업 리스트: {df['작업 내용'].tolist() if not df.empty else '없음'}
    - 물품 리스트: {df_items['품목명'].tolist() if not df_items.empty else '없음'}

    [명령어 규칙]
    1. 추가: {{"action": "add", "type": "task/item", "content": "내용", "note": "비고(옵션)"}}
    2. 삭제: {{"action": "delete", "type": "task/item", "target": "지울항목명"}}
    3. 수정(진행률): {{"action": "update", "target": "작업명", "value": "50%"}} 
    4. 일반대화: {{"action": "chat", "response": "답변내용"}}

    [예시]
    - "라즈베리파이 구매 추가해줘" -> {{"action": "add", "type": "item", "content": "라즈베리파이"}}
    - "3D 모델링 완료했어(100%)" -> {{"action": "update", "target": "3D 모델링", "value": "100%"}}
    """
    
    # 3. AI 생각 시키기
    full_prompt = system_instruction + f"\n사용자: {prompt}"
    
    try:
        response = model.generate_content(full_prompt)
        text_res = response.text.strip()
        
        # JSON 부분만 억지로 뜯어내기 (가끔 AI가 백틱 ```json ... ``` 을 붙일 때가 있어서)
        if "```" in text_res:
            text_res = text_res.replace("```json", "").replace("```", "").strip()
            
        import json
        ai_data = json.loads(text_res) # JSON으로 변환 시도
        
        # 4. AI의 명령 수행 (손 움직이기)
        action = ai_data.get("action")
        
        # [A] 추가 (Add)
        if action == "add":
            if ai_data["type"] == "task":
                update_sheet_any(conn, "작업", [ai_data["content"], "대기", "", "", "", "0%"]) # 진행률 0% 기본값
                msg = f"✅ 작업 시트에 **'{ai_data['content']}'** 추가 완료!"
            else:
                update_sheet_any(conn, "물품", ["", ai_data["content"], "1", "", ""])
                msg = f"📦 물품 시트에 **'{ai_data['content']}'** 추가 완료!"
            st.chat_message("assistant").write(msg)
            st.rerun()

        # [B] 삭제 (Delete)
        elif action == "delete":
            # (삭제 로직은 기존과 동일하거나, 필요하면 구현)
            st.chat_message("assistant").write(f"🗑️ **{ai_data['target']}** 삭제 기능은 아직 안전을 위해 막아뒀어요. 시트에서 직접 지워주세요!")

        # [C] ★ 수정 (Update) - 진행률 변경 기능!
        elif action == "update":
            target_task = ai_data.get("target")
            new_value = ai_data.get("value")
            
            # 1. 시트 연결
            sh = conn.open("Project_Manager") # 시트 이름 확인하세요!
            ws = sh.worksheet("작업")
            
            # 2. 해당 작업이 몇 번째 줄에 있는지 찾기
            try:
                cell = ws.find(target_task) # 작업 이름을 찾음
                
                # 3. '진행률' 컬럼이 몇 번째인지 찾기 (보통 6번째 열이지만, 확실하게 하기 위해)
                # (만약 헤더를 못 찾으면 F열(6번)이라고 가정)
                header = ws.row_values(1)
                try:
                    col_idx = header.index("진행률") + 1
                except:
                    col_idx = 6 
                
                # 4. 값 업데이트 (퍼센트 기호 없으면 붙여주기)
                if "%" not in new_value: new_value += "%"
                
                ws.update_cell(cell.row, col_idx, new_value)
                
                st.chat_message("assistant").write(f"📈 **'{target_task}'**의 진행률을 **{new_value}**로 업데이트했습니다!")
                st.rerun() # 새로고침해서 색깔 바뀐거 보여줌
                
            except Exception as e:
                st.error(f"작업을 찾을 수 없거나 수정 실패: {e}")
                st.chat_message("assistant").write(f"😅 **'{target_task}'**라는 작업을 못 찾겠어요. 정확한 이름을 말씀해 주세요.")

        # [D] 일반 대화
        else:
            st.chat_message("assistant").write(ai_data.get("response"))

    except Exception as e:
        # JSON 파싱 실패하거나 에러나면 그냥 일반 대화로 처리
        # st.error(f"에러 로그: {e}") # 디버깅용 (필요하면 주석 해제)
        response = model.generate_content(prompt) # 그냥 일반 질문으로 다시 던짐
        st.chat_message("assistant").write(response.text)