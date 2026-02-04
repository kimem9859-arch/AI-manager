import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import time

# ----------------------------------------------------------
# 1. 초기 설정 & 필수 함수
# ----------------------------------------------------------
st.set_page_config(page_title="내 AI 프로젝트 매니저", page_icon="🤖", layout="wide")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# [기능] 방금 대화 취소 (Undo)
def undo_last_chat():
    if len(st.session_state.messages) >= 2:
        st.session_state.messages.pop() # AI 답변 삭제
        st.session_state.messages.pop() # 내 질문 삭제
        st.toast("↩️ 방금 대화를 취소했습니다!", icon="🗑️")
        time.sleep(0.5)
        st.rerun()
    else:
        st.toast("⚠️ 취소할 대화 내역이 없습니다.")

# [기능] 사용 설명서
@st.dialog("📖 사용 설명서")
def show_guide():
    st.markdown("""
    ### 👋 환영합니다!
    **1. 💬 채팅 명령**
    - "라즈베리파이 추가해줘" (추가)
    - "3D 모델링 진행률 50%로 바꿔줘" (수정)
    
    **2. 📊 시트 관리**
    - **작업 탭:** 진행률에 따라 색상이 변합니다.
    - **물품 탭:** 총 비용 계산 & 구매 링크 버튼이 제공됩니다.
    
    **3. ↩️ 되돌리기**
    - 채팅창 오른쪽 위 빨간 버튼으로 실행 취소가 가능합니다.
    """)

# [기능] 구글 시트 연결 (통합)
def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # Streamlit Cloud 배포용 (Secrets)
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        # 로컬 실행용 (json 파일)
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    
    client = gspread.authorize(creds)
    # ★ 중요: 파일 이름이 맞는지 확인하세요!
    return client.open("Safety_Project") 

# [수정된 함수] 시트 데이터 가져오기 (강제 로딩 버전)
def load_data_safe(sheet_name):
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(sheet_name)
        
        # 1. 모든 데이터를 가져옴
        all_values = ws.get_all_values()
        
        # 데이터가 없으면 빈 표 반환
        if not all_values: 
            return pd.DataFrame()

        # 2. 복잡하게 찾지 말고, 무조건 1행을 제목, 2행부터 데이터로 인식
        # (만약 1행이 병합되어 있다면 2행을 제목으로 인식하도록 인덱스 조절 가능)
        
        # 헤더 후보 찾기 (데이터가 있는 첫 번째 줄을 헤더로 간주)
        header_idx = 0
        for i, row in enumerate(all_values[:5]):
            # 행에 내용이 2개 이상 차 있으면 헤더로 봄
            if len([x for x in row if x.strip()]) >= 2:
                header_idx = i
                break
        
        headers = all_values[header_idx]
        data = all_values[header_idx+1:]
        
        df = pd.DataFrame(data, columns=headers)
        return df

    except Exception as e:
        # 에러가 나면 화면에 원인을 출력해줌 (디버깅용)
        st.error(f"❌ '{sheet_name}' 시트 로딩 실패: {e}")
        return pd.DataFrame()

# [기능] 시트 업데이트 (범용)
def update_sheet_any(sheet_name, row_data):
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        ws.append_row(row_data)
        return True
    except: return False

# [기능추가] 공지사항 읽어오기 함수
def get_notice():
    try:
        client = get_spreadsheet()
        # '공지' 시트가 없으면 만들고, 있으면 읽기
        try: ws = client.worksheet("공지")
        except: 
            ws = client.add_worksheet("공지", 5, 2)
            ws.update_cell(1, 1, "공지없음")
        
        val = ws.cell(1, 1).value
        return val if val else "공지없음"
    except: return "공지 연결 실패"

# [기능추가] 공지사항 업데이트 함수
def update_notice(text):
    try:
        client = get_spreadsheet()
        try: ws = client.worksheet("공지")
        except: ws = client.add_worksheet("공지", 5, 2)
        ws.update_cell(1, 1, text)
        return True
    except: return False

# Gemini 모델 설정
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-pro')

# ----------------------------------------------------------
# 2. 데이터 로딩 (화면 그리기 전 준비)
# ----------------------------------------------------------
# 작업 데이터 로드
df_task = load_data_safe("작업")
if not df_task.empty and '상태' in df_task.columns:
    total = len(df_task)
    done = len(df_task[df_task['상태']=='완료'])
    pending = len(df_task[df_task['상태']=='대기'])
else:
    total, done, pending = 0, 0, 0

# 물품 데이터 로드
df_items = load_data_safe("물품")
# 물품 데이터 전처리 (링크, 숫자 변환)
if not df_items.empty:
    # 1. 빈칸 채우기
    df_items = df_items.fillna("-")
    
    # 2. 금액 열 숫자로 변환 (비용 계산용)
    for col in df_items.columns:
        if any(k in col for k in ['금액', '가격', '비용']):
            df_items[col] = (
                df_items[col].astype(str)
                .str.replace(',', '')
                .str.replace('원', '')
                .apply(pd.to_numeric, errors='coerce')
                .fillna(0)
            )

# ----------------------------------------------------------
# 3. 화면 UI 구성
# ----------------------------------------------------------
st.title("🤖 든든한 프로젝트 매니저")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.rerun()
    if st.button("❓ 도움말"): show_guide()

# 상단 통계 카드
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:15px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center;">📌 전체 작업<br><b style="font-size:20px;">{total}</b></div>
        <div style="text-align:center;">✅ 완료됨<br><b style="font-size:20px; color:#4CAF50;">{done}</b></div>
        <div style="text-align:center;">⏳ 대기중<br><b style="font-size:20px; color:#FF9800;">{pending}</b></div>
    </div>
""", unsafe_allow_html=True)

# 탭 구성 (모바일/PC 분기)
if is_mobile:
    tab1, tab2, tab3 = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat, c_sheet, c_items = tab1, tab2, tab3
else:
    col1, col2 = st.columns([1, 1.3])
    c_chat = col1
    with col2:
        sub1, sub2 = st.tabs(["📊 작업 현황", "📦 물품 견적"])
        c_sheet, c_items = sub1, sub2

# --- [탭 1] 작업 리스트 (검색 & 필터 & 3색 신호등) ---
with c_sheet:
    if not df_task.empty:
        # 1. 필터 UI 구성 (검색창과 상태선택을 나란히 배치)
        col_search, col_filter = st.columns([1, 1])
        
        with col_search:
            search_query = st.text_input("🔍 작업 검색", placeholder="작업명을 입력하세요...")
        
        with col_filter:
            # 상태 컬럼이 있으면 필터 생성, 없으면 빈 리스트
            all_statuses = df_task['상태'].unique() if '상태' in df_task.columns else []
            selected_status = st.multiselect("🏷️ 상태 필터", all_statuses, default=all_statuses)

        # 2. 데이터 필터링 로직
        df_view = df_task.copy()
        
        # (1) 상태 필터 적용
        if '상태' in df_view.columns and selected_status:
            df_view = df_view[df_view['상태'].isin(selected_status)]
            
        # (2) 검색어 적용 (첫 번째 열: 작업명 기준)
        if search_query:
            # 대소문자 구분 없이 검색
            df_view = df_view[df_view.iloc[:, 0].astype(str).str.contains(search_query, case=False, na=False)]

        # 3. 색상 함수 (빨강-노랑-초록)
        def color_progress(val):
            if pd.isna(val) or str(val) in ["", "-"]: return None
            try:
                num = float(str(val).replace('%', '').strip())
                num = max(0, min(100, num))
                if num < 50:
                    ratio = num / 50
                    red, green, blue = 255, int(255 * ratio), 0
                else:
                    ratio = (num - 50) / 50
                    red, green, blue = int(255 * (1 - ratio)), 255, 0
                
                style = f'background-color: rgb({red}, {green}, {blue}); color: black;'
                if num >= 100: style += ' font-weight: bold;'
                return style
            except: return None

        # 4. 결과 출력
        if not df_view.empty:
            if '진행률' in df_view.columns:
                st.dataframe(df_view.style.map(color_progress, subset=['진행률']), use_container_width=True, height=500)
            else:
                st.dataframe(df_view, use_container_width=True, height=500)
        else:
            st.warning("검색 결과가 없습니다.")
            
    else:
        st.info("작업 리스트가 비어있습니다.")

# --- [탭 2] 물품 리스트 (검색 & 필터 & 링크 & 비용) ---
with c_items:
    if not df_items.empty:
        # 1. 상단 UI 구성 (검색창 + 상태 필터)
        col_search, col_filter = st.columns([2, 1])
        
        with col_search:
            search_item = st.text_input("📦 물품 검색", placeholder="품목명, 비고 등을 입력하세요...", key="item_search_input")
        
        with col_filter:
            # 필터링할 열 자동 감지 ('상태', '구분', '구매상태' 등)
            filter_col = next((c for c in ['상태', '구분', '구매상태', 'Status'] if c in df_items.columns), None)
            
            if filter_col:
                all_opts = df_items[filter_col].unique()
                # 👇 [핵심 수정] key="item_filter"를 추가해서 작업 탭의 필터와 구분함!
                selected_opts = st.multiselect(
                    f"🏷️ {filter_col} 필터", 
                    all_opts, 
                    default=all_opts,
                    key="item_filter_unique"
                )
            else:
                selected_opts = []
                # 공간 확보를 위해 빈 컨테이너 표시
                st.empty() 

        # 2. 데이터 가공 및 필터링
        df_display = df_items.copy()
        
        # (1) 필터 적용
        if filter_col and selected_opts:
            df_display = df_display[df_display[filter_col].isin(selected_opts)]

        # (2) 검색어 적용
        if search_item:
            mask = (
                df_display.iloc[:, 0].astype(str).str.contains(search_item, case=False, na=False) | 
                df_display["비고"].astype(str).str.contains(search_item, case=False, na=False)
            )
            df_display = df_display[mask]

        # 3. 링크 버튼 처리
        if "구매 링크" not in df_display.columns: df_display["구매 링크"] = None
        if "비고" in df_display.columns:
            for i, row in df_display.iterrows():
                val = str(row["비고"])
                if val.startswith("http"):
                    df_display.at[i, "구매 링크"] = val
                    df_display.at[i, "비고"] = "-"
        
        # 4. 표 출력
        if not df_display.empty:
            st.dataframe(
                df_display, 
                use_container_width=True, 
                height=400,
                column_config={"구매 링크": st.column_config.LinkColumn("링크", display_text="🔗 구매")}
            )
        else:
            st.warning("조건에 맞는 물품이 없습니다.")

        # 5. 총 비용 계산
        cost_cols = [c for c in df_items.columns if any(k in c for k in ['금액', '가격', '비용'])]
        if cost_cols:
            current_cost = df_display[cost_cols[0]].sum()
            
            st.markdown(f"""
                <div style="
                    text-align: center; 
                    padding: 20px; 
                    background-color: rgba(0, 200, 100, 0.1); 
                    border: 1px solid rgba(0, 200, 100, 0.3);
                    border-radius: 15px; 
                    margin-top: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <span style="font-size: 1.3em; font-weight: bold; color: #555; margin-right: 10px;">💰 견적 합계:</span>
                    <span style="font-size: 2.0em; color: #2ecc71; font-weight: bold;">{int(current_cost):,}원</span>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("물품 리스트가 비어있습니다.")

# --- [탭 3] 채팅 및 AI 처리 (여기가 핵심!) ---
with c_chat:
    # 채팅방 헤더 (제목 + 되돌리기 버튼)
    current_notice = get_notice()
    if current_notice not in ["-", "공지없음", "공지 연결 실패"]:
        st.info(f" **공지:** {current_notice}", icon="📢")
    h_col1, h_col2 = st.columns([1, 0.4])
    h_col1.subheader("💬 AI 매니저")
    if h_col2.button("↩️ 되돌리기", type="primary", use_container_width=True):
        undo_last_chat()

    # 대화 기록 표시
    chat_box = st.container(height=500, border=True)
    with chat_box:
        for m in st.session_state.messages:
            st.chat_message(m["role"]).write(m["content"])

# ------------------------------------------------------------------
# 4. AI 답변 및 액션 처리 (수정됨: 답변이 사라지는 문제 해결)
# ------------------------------------------------------------------
if prompt := st.chat_input("명령을 입력하세요 (예: 기획 삭제하고 개발 추가해줘)"):
    # 1. 사용자 메시지 기록
    st.session_state.messages.append({"role": "user", "content": prompt})
    chat_box.chat_message("user").write(prompt)

    # 2. 데이터 요약
    task_str = str(df_task.iloc[:, 0].tolist()) if not df_task.empty else "없음"
    
    # 3. AI 프롬프트 (환각 방지 & 완료 규칙 강화)
    sys_msg = f"""
    당신은 구글 시트 데이터베이스 관리자입니다.
    사용자의 말을 분석하여 **반드시 JSON 리스트([...])** 형식으로 출력하세요.
    여러 명령이 있으면 리스트 안에 여러 객체를 넣으세요.

    [현재 작업 리스트] {task_str}

    [절대 규칙]
    1. 설명이나 인사말 절대 금지. 오직 JSON만 출력.
    2. "삭제하고 추가해줘" 같은 복합 명령은 리스트에 2개를 넣을 것.
    3. 작업 추가 시 데이터 순서는 반드시 **[작업명, 0%, -, 대기, -]** 순서여야 함.
    4. **중요: "완료", "끝냈어", "했어"는 무조건 'update' (진행률 100%) 명령이다. 절대로 'delete'하지 마라.**
    5. **중요: 작업명은 위 [현재 작업 리스트]에 있는 단어만 사용해라. '라즈베리파이'를 '아두이노'로 맘대로 바꾸지 마라.**

    [출력 포맷]
    [
      {{"action": "delete", "target": "지울작업명"}},
      {{"action": "add", "sheet": "작업", "row": ["추가할작업명", "0%", "", "대기", ""]}},
      {{"action": "update", "target": "작업명", "value": "100%"}}
    ]
    """

    try:
        # AI 호출
        response = model.generate_content(sys_msg + f"\n사용자 요청: {prompt}")
        text_res = response.text.strip()
        
        # JSON 추출
        import re
        text_res = text_res.replace("```json", "").replace("```", "").strip()
        
        match = re.search(r'\[.*\]', text_res, re.DOTALL)
        if match:
            commands = json.loads(match.group())
        else:
            match_single = re.search(r'\{.*\}', text_res, re.DOTALL)
            if match_single:
                commands = [json.loads(match_single.group())]
            else:
                commands = []

        # 명령 실행
        results = []
        for cmd in commands:
            action = cmd.get("action")
            
            # [A] 추가
            if action == "add":
                sheet = cmd.get("sheet", "작업")
                row = cmd.get("row")
                update_sheet_any(sheet, row)
                results.append(f"✅ **{sheet}**에 추가됨")

            # [B] 수정
            elif action == "update":
                target = cmd.get("target")
                val = cmd.get("value")
                if "%" not in val: val += "%"
                
                client = get_spreadsheet()
                ws = client.worksheet("작업")
                try:
                    cell = ws.find(target)
                    headers = ws.row_values(1)
                    col_idx = 6
                    for i, h in enumerate(headers):
                        if "진행" in h: 
                            col_idx = i + 1; break
                    ws.update_cell(cell.row, col_idx, val)
                    results.append(f"📈 **{target}** → {val}")
                except:
                    results.append(f"⚠️ **{target}** 찾을 수 없음")

            # [C] 삭제
            elif action == "delete":
                target = cmd.get("target")
                client = get_spreadsheet()
                ws = client.worksheet("작업")
                try:
                    cell = ws.find(target)
                    ws.delete_rows(cell.row)
                    results.append(f"🗑️ **{target}** 삭제됨")
                except:
                    results.append(f"⚠️ **{target}** 삭제 실패")
            
            # [D] 공지
            elif action == "notice":
                update_notice(cmd.get("content"))
                results.append(f"📢 공지 변경됨")
            
            # [E] 대화
            elif action == "chat":
                results.append(cmd.get("response"))

        # 4. 결과 출력 및 저장 (여기가 핵심 수정!!)
        if results:
            final_msg = " / ".join(results)
            
            # 👇 [중요] 새로고침 하기 전에 세션에 기록을 먼저 남김!
            st.session_state.messages.append({"role": "assistant", "content": final_msg})
            
            # 즉시 새로고침 (화면 갱신)
            st.rerun()
        else:
            final_msg = "🤖 명령을 이해하지 못했습니다."
            st.session_state.messages.append({"role": "assistant", "content": final_msg})
            st.rerun()

    except Exception as e:
        # 에러 메시지도 저장하고 새로고침
        err_msg = f"오류 발생: {e}"
        st.session_state.messages.append({"role": "assistant", "content": err_msg})
        st.rerun()