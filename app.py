import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import time
import os

# ----------------------------------------------------------
# 1. 초기 설정 & 필수 함수(백업)
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
    
    **1. 💬 채팅 명령어**
    - **추가:** "라즈베리파이 추가해줘" → 진행률 0%, 상태 대기/보류로 추가
    - **삭제:** "라즈베리파이 삭제해줘" → 작업 전체 삭제
    - **진행률:** "라즈베리파이 진행률 50%로 변경해줘"
    - **상태:** "라즈베리파이 상태 진행으로 바꿔줘"
    - **세부내용:** "라즈베리파이 세부내용 '설계 진행 중'으로 변경해줘"
    - **세부내용 삭제:** "라즈베리파이 세부내용 삭제해줘"
    - **비고:** "라즈베리파이 비고에 '담당자: 홍길동' 넣어줘"
    - **비고 삭제:** "라즈베리파이 비고 삭제해줘"
    - **공지:** "내일 회의로 공지 변경해줘"
    
    **2. 📊 작업 현황**
    - **상태 빠른 변경:** 상태 셀을 클릭하면 드롭다운으로 빠르게 변경!
    - **상태 옵션:** 대기/보류, 진행, 수정/검토, 완료
    - **진행률 바:** 진행률이 프로그레스 바로 표시됩니다.
    
    **3. 📦 물품 견적**
    - 총 비용 자동 계산
    - 구매 링크 버튼 제공
    
    **4. ↩️ 되돌리기**
    - 채팅창 오른쪽 위 빨간 버튼으로 실행 취소 가능
    
    **5. 🔄 자동 새로고침**
    - 데이터 변경 시 자동으로 시트가 새로고침됩니다.
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

# [기능] 시트에서 target(작업명/품목명)이 있는 행 삭제
def delete_row_by_target(sheet_name, target):
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        cell = ws.find(target)
        # gspread v5: delete_rows(행번호) — end_index 없으면 해당 행 1줄만 삭제
        ws.delete_rows(cell.row)
        return True, None
    except Exception as e:
        return False, str(e)

# [기능] 특정 셀 값 업데이트 (작업명 기준으로 열 찾아서 변경)
def update_cell_by_target(sheet_name, target, column_keyword, new_value):
    """
    target: 작업명/품목명
    column_keyword: 찾을 열 이름 키워드 (예: '진행', '상태', '세부', '비고')
    new_value: 새로운 값
    """
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        
        # 작업명/품목명으로 행 찾기
        cell = ws.find(target)
        if not cell:
            return False, f"'{target}'을(를) 찾을 수 없습니다."
        
        # 헤더에서 해당 열 찾기
        headers = ws.row_values(1)
        col_idx = None
        for i, h in enumerate(headers):
            if column_keyword in h:
                col_idx = i + 1
                break
        
        if col_idx is None:
            return False, f"'{column_keyword}' 열을 찾을 수 없습니다."
        
        # 셀 업데이트
        ws.update_cell(cell.row, col_idx, new_value)
        return True, None
    except Exception as e:
        return False, str(e)

# [기능] 특정 셀 내용 삭제 (빈칸으로 변경)
def clear_cell_by_target(sheet_name, target, column_keyword):
    """특정 작업의 특정 열 내용을 빈칸으로 삭제"""
    return update_cell_by_target(sheet_name, target, column_keyword, "")

# [기능] 상태 빠른 변경
def update_status_quick(sheet_name, target, new_status):
    """상태를 빠르게 변경"""
    return update_cell_by_target(sheet_name, target, "상태", new_status)

# Gemini 모델 설정 (Secrets → 환경변수 fallback)
_api_key = None
if "GOOGLE_API_KEY" in st.secrets:
    _api_key = st.secrets["GOOGLE_API_KEY"]
if not _api_key:
    _api_key = os.environ.get("GOOGLE_API_KEY")
if _api_key:
    genai.configure(api_key=_api_key)
    model = genai.GenerativeModel('gemini-2.5-pro')
else:
    model = None

# ----------------------------------------------------------
# 2. 데이터 로딩 (화면 그리기 전 준비)
# ----------------------------------------------------------
# 상태 옵션 정의 (전역)
STATUS_OPTIONS = ["대기/보류", "진행", "수정/검토", "완료"]

# 작업 데이터 로드
df_task = load_data_safe("작업")
if not df_task.empty and '상태' in df_task.columns:
    total = len(df_task)
    pending = len(df_task[df_task['상태'].isin(['대기', '대기/보류', '보류'])])
    in_progress = len(df_task[df_task['상태'].isin(['진행', '진행중'])])
    reviewing = len(df_task[df_task['상태'].isin(['수정', '검토', '수정/검토'])])
    done = len(df_task[df_task['상태']=='완료'])
else:
    total, pending, in_progress, reviewing, done = 0, 0, 0, 0, 0

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
    if model is None:
        st.warning("⚠️ **GOOGLE_API_KEY**가 설정되지 않았습니다. 채팅 기능을 쓰려면 Secrets 또는 환경변수에 API 키를 넣어주세요.")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.rerun()
    if st.button("❓ 도움말"): show_guide()

# 상단 통계 카드
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:15px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center;">📌 전체 작업<br><b style="font-size:20px;">{total}</b></div>
        <div style="text-align:center;">⏳ 대기/보류<br><b style="font-size:20px; color:#FF9800;">{pending}</b></div>
        <div style="text-align:center;">🔄 진행<br><b style="font-size:20px; color:#2196F3;">{in_progress}</b></div>
        <div style="text-align:center;">🔍 수정/검토<br><b style="font-size:20px; color:#9C27B0;">{reviewing}</b></div>
        <div style="text-align:center;">✅ 완료<br><b style="font-size:20px; color:#4CAF50;">{done}</b></div>
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

# --- [탭 1] 작업 리스트 (검색 & 필터 & 3색 신호등 & 상태 빠른 변경) ---
with c_sheet:
    if not df_task.empty:
        # 1. 필터 UI 구성 (검색창과 상태선택을 나란히 배치)
        col_search, col_filter = st.columns([1, 1])
        
        with col_search:
            search_query = st.text_input("🔍 작업 검색", placeholder="작업명을 입력하세요...")
        
        with col_filter:
            # 상태 컬럼이 있으면 필터 생성, 없으면 빈 리스트
            all_statuses = df_task['상태'].unique() if '상태' in df_task.columns else []
            selected_status = st.multiselect("🏷️ 상태 필터", all_statuses, default=list(all_statuses))

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

        # 4. 결과 출력 (상태 빠른 변경 기능 포함)
        if not df_view.empty:
            # 원본 인덱스 저장 (수정 추적용)
            df_view = df_view.reset_index(drop=True)
            
            # 진행률 숫자 변환 (ProgressColumn용)
            if '진행률' in df_view.columns:
                df_view['진행률_숫자'] = df_view['진행률'].apply(
                    lambda x: float(str(x).replace('%', '').strip()) / 100 
                    if pd.notna(x) and str(x).replace('%', '').strip().replace('.', '').isdigit() 
                    else 0
                )
            
            # 상태 열에 대한 column_config 설정
            col_config = {}
            if '상태' in df_view.columns:
                col_config['상태'] = st.column_config.SelectboxColumn(
                    "상태",
                    help="클릭하여 상태를 빠르게 변경하세요",
                    options=STATUS_OPTIONS,
                    required=True
                )
            
            # 진행률 프로그레스 바 표시 (조건부 서식 대체)
            if '진행률_숫자' in df_view.columns:
                col_config['진행률_숫자'] = st.column_config.ProgressColumn(
                    "진행률",
                    help="진행률 바 (0% ~ 100%)",
                    min_value=0,
                    max_value=1,
                    format="%.0f%%"
                )
                # 원래 진행률 열 숨기기
                col_config['진행률'] = None
            
            # data_editor로 표시 (상태 변경 가능)
            edited_df = st.data_editor(
                df_view,
                use_container_width=True,
                height=500,
                column_config=col_config,
                disabled=[col for col in df_view.columns if col != '상태'],  # 상태 열만 편집 가능
                hide_index=True,
                key="task_editor"
            )
            
            # 상태 변경 감지 및 적용
            if '상태' in df_view.columns:
                for idx in range(len(df_view)):
                    old_status = df_view.at[idx, '상태']
                    new_status = edited_df.at[idx, '상태']
                    if old_status != new_status:
                        # 작업명 가져오기 (첫 번째 열)
                        task_name = df_view.iloc[idx, 0]
                        ok, err = update_cell_by_target("작업", task_name, "상태", new_status)
                        if ok:
                            st.toast(f"✅ '{task_name}' 상태가 '{new_status}'로 변경되었습니다!", icon="🔄")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"상태 변경 실패: {err}")
            
            # 진행률 색상 표시 안내
            st.caption("💡 상태를 클릭하면 드롭다운으로 빠르게 변경할 수 있습니다!")
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

        # (2) 검색어 적용 (비고 컬럼이 있을 때만 비고 포함)
        if search_item:
            mask = df_display.iloc[:, 0].astype(str).str.contains(search_item, case=False, na=False)
            if "비고" in df_display.columns:
                mask = mask | df_display["비고"].astype(str).str.contains(search_item, case=False, na=False)
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

# 4. 사용자 입력 처리 (공지 수정 기능 추가됨)   
if prompt := st.chat_input("명령을 입력하세요 (예: 공지사항 '내일 회식'으로 변경해줘)"):
    # 1. 사용자 메시지 기록
    st.session_state.messages.append({"role": "user", "content": prompt})
    chat_box.chat_message("user").write(prompt)

    if model is None:
        msg = "⚠️ API 키가 설정되지 않아 AI 명령을 처리할 수 없습니다. 사이드바 안내를 확인해주세요."
        st.session_state.messages.append({"role": "assistant", "content": msg})
        chat_box.chat_message("assistant").write(msg)
    else:
        # 2. 현재 데이터 요약 + 작업 시트 컬럼 순서 (추가 시 행 순서 맞추기용)
        task_summary = df_task.iloc[:, 0].tolist() if not df_task.empty else "없음"
        task_headers = df_task.columns.tolist() if not df_task.empty else ["작업명", "진행률", "세부내용", "상태", "비고"]
        # 새 작업 한 행 예시: 시트 컬럼 순서에 맞게 [작업명, 진행률, 세부내용, 상태, 비고] 등 배치
        def _example_row_for_new_task(headers):
            row = [""] * len(headers)
            for i, h in enumerate(headers):
                if "작업" in h or "명" in h or h == "제목":
                    row[i] = "프로젝트 기획"
                    break
            for i, h in enumerate(headers):
                if "진행" in h:
                    row[i] = "0%"
                    break
            for i, h in enumerate(headers):
                if "상태" in h:
                    row[i] = "대기"
                    break
            return row
        example_add_row = _example_row_for_new_task(task_headers)
        
        # 3. AI 시스템 프롬프트 (확장된 기능)
        sys_msg = f"""
        당신은 구글 시트 데이터베이스 관리자입니다.
        
        [절대 규칙]
        1. 당신은 사용자의 말을 듣고 **JSON 데이터만** 출력해야 합니다.
        2. 절대로 대화하거나, 설명을 덧붙이거나, 문장을 교정하지 마십시오.
        3. 명령어 종류: add(추가), delete(삭제), update_progress(진행률변경), update_status(상태변경), update_detail(세부내용변경), update_remark(비고변경), clear_cell(셀내용삭제), notice(공지변경), chat(대화)

        [작업 시트 컬럼 순서] (추가 시 row는 이 순서와 반드시 동일하게)
        {task_headers}
        - 새 작업 추가 시: 진행률 "0%", 세부내용 "", 상태 "대기/보류", 비고 "" 로 채우세요.

        [현재 작업 목록]
        {task_summary}

        [상태 옵션] (반드시 이 4가지만 사용!)
        대기/보류, 진행, 수정/검토, 완료

        [출력 가능한 JSON 포맷]
        1. 작업 추가 (~ 추가해줘):
           {{"action": "add", "sheet": "작업", "row": ["작업명", "0%", "", "대기/보류", ""]}}
           
        2. 작업 삭제 - 행 전체 삭제 (~ 삭제해줘, ~ 작업 삭제):
           {{"action": "delete", "sheet": "작업", "target": "작업명"}}
           
        3. 진행률 변경 (~ 진행률 50%로 변경, ~ 50%로 바꿔줘):
           {{"action": "update_progress", "target": "작업명", "value": "50%"}}
           
        4. 상태 변경 (~ 상태 진행으로 변경, ~ 완료로 바꿔줘):
           {{"action": "update_status", "target": "작업명", "value": "진행"}}
           (상태는 반드시 대기/보류, 진행, 수정/검토, 완료 중 하나)
           
        5. 세부내용 변경 (~ 세부내용 "내용"으로 변경):
           {{"action": "update_detail", "target": "작업명", "value": "새로운 세부내용"}}
           
        6. 세부내용 삭제 (~ 세부내용 삭제해줘):
           {{"action": "clear_cell", "target": "작업명", "column": "세부"}}
           
        7. 비고 변경 (~ 비고 "내용"으로 변경):
           {{"action": "update_remark", "target": "작업명", "value": "새로운 비고"}}
           
        8. 비고 삭제 (~ 비고 삭제해줘):
           {{"action": "clear_cell", "target": "작업명", "column": "비고"}}
           
        9. 공지 변경 (~로 공지 변경):
           {{"action": "notice", "content": "새로운 공지 내용"}}
           
        10. 일반 대화:
            {{"action": "chat", "response": "할말"}}
        
        [예시]
        Q: "프로젝트 기획 추가해줘"
        A: {{"action": "add", "sheet": "작업", "row": ["프로젝트 기획", "0%", "", "대기/보류", ""]}}
        
        Q: "프로젝트 기획 삭제해줘"
        A: {{"action": "delete", "sheet": "작업", "target": "프로젝트 기획"}}
        
        Q: "프로젝트 기획 진행률 50%로 변경해줘"
        A: {{"action": "update_progress", "target": "프로젝트 기획", "value": "50%"}}
        
        Q: "프로젝트 기획 상태를 진행으로 바꿔줘"
        A: {{"action": "update_status", "target": "프로젝트 기획", "value": "진행"}}
        
        Q: "프로젝트 기획 세부내용을 '기초 설계 진행 중'으로 변경해줘"
        A: {{"action": "update_detail", "target": "프로젝트 기획", "value": "기초 설계 진행 중"}}
        
        Q: "프로젝트 기획 세부내용 삭제해줘"
        A: {{"action": "clear_cell", "target": "프로젝트 기획", "column": "세부"}}
        
        Q: "프로젝트 기획 비고에 '담당자: 홍길동' 넣어줘"
        A: {{"action": "update_remark", "target": "프로젝트 기획", "value": "담당자: 홍길동"}}
        
        Q: "프로젝트 기획 비고 삭제해줘"
        A: {{"action": "clear_cell", "target": "프로젝트 기획", "column": "비고"}}
        
        Q: "내일 회의로 공지 변경해줘"
        A: {{"action": "notice", "content": "내일 회의"}}
        """

        try:
            # AI에게 요청
            response = model.generate_content(sys_msg + f"\n사용자 요청: {prompt}")
            text_res = response.text.strip().replace("```json", "").replace("```", "")
            
            # JSON 파싱
            cmd = json.loads(text_res)
            action = cmd.get("action")

            # [동작 1] 추가 (Add) — 행이 시트 컬럼 수와 맞도록 보정
            if action == "add":
                sheet_name = cmd.get("sheet", "작업")
                row_vals = cmd.get("row") or []
                if not isinstance(row_vals, list):
                    row_vals = [str(row_vals)]
                # 작업 시트면 컬럼 수에 맞춤 (앞에서 맞고, 부족하면 "", 많으면 자름)
                if sheet_name == "작업" and not df_task.empty:
                    n_cols = len(df_task.columns)
                    row_vals = [str(v) if v is not None else "" for v in row_vals[:n_cols]]
                    row_vals += [""] * (n_cols - len(row_vals))
                update_sheet_any(sheet_name, row_vals)
                task_name = row_vals[0] if row_vals else "새 작업"
                msg = f"✅ **'{task_name}'** 작업이 추가되었습니다. (진행률: 0%, 상태: 대기/보류)"
                st.session_state.messages.append({"role": "assistant", "content": msg})
                chat_box.chat_message("assistant").write(msg)
                st.rerun()

            # [동작 2] 진행률 변경 (Update Progress)
            elif action == "update" or action == "update_progress":
                target = cmd.get("target")
                val = cmd.get("value", "0%")
                if "%" not in str(val): val = str(val) + "%"
                
                ok, err = update_cell_by_target("작업", target, "진행", val)
                if ok:
                    msg = f"📈 **'{target}'** 진행률을 **{val}**로 변경했습니다."
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = f"😅 **'{target}'** 작업을 찾을 수 없습니다. ({err})"

            # [동작 3] 상태 변경 (Update Status)
            elif action == "update_status":
                target = cmd.get("target")
                val = cmd.get("value", "대기/보류")
                
                # 상태 값 검증 및 매핑
                status_map = {
                    "대기": "대기/보류", "보류": "대기/보류", "대기/보류": "대기/보류",
                    "진행": "진행", "진행중": "진행",
                    "수정": "수정/검토", "검토": "수정/검토", "수정/검토": "수정/검토",
                    "완료": "완료"
                }
                val = status_map.get(val, val)
                
                ok, err = update_cell_by_target("작업", target, "상태", val)
                if ok:
                    msg = f"🔄 **'{target}'** 상태를 **{val}**(으)로 변경했습니다."
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = f"😅 **'{target}'** 작업을 찾을 수 없습니다. ({err})"

            # [동작 4] 세부내용 변경 (Update Detail)
            elif action == "update_detail":
                target = cmd.get("target")
                val = cmd.get("value", "")
                
                ok, err = update_cell_by_target("작업", target, "세부", val)
                if ok:
                    msg = f"📝 **'{target}'** 세부내용을 변경했습니다: **{val}**"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = f"😅 **'{target}'** 작업을 찾을 수 없습니다. ({err})"

            # [동작 5] 비고 변경 (Update Remark)
            elif action == "update_remark":
                target = cmd.get("target")
                val = cmd.get("value", "")
                
                ok, err = update_cell_by_target("작업", target, "비고", val)
                if ok:
                    msg = f"📋 **'{target}'** 비고를 변경했습니다: **{val}**"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = f"😅 **'{target}'** 작업을 찾을 수 없습니다. ({err})"

            # [동작 6] 셀 내용 삭제 (Clear Cell) - 세부내용/비고 삭제
            elif action == "clear_cell":
                target = cmd.get("target")
                column = cmd.get("column", "")
                
                ok, err = clear_cell_by_target("작업", target, column)
                if ok:
                    msg = f"🗑️ **'{target}'** 의 **{column}** 내용을 삭제했습니다."
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = f"😅 **'{target}'** 작업 또는 '{column}' 열을 찾을 수 없습니다. ({err})"

            # [동작 7] ★ 공지 수정
            elif action == "notice":
                content = cmd.get("content")
                if update_notice(content):
                    msg = f"📢 공지사항이 업데이트 되었습니다: **{content}**"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    chat_box.chat_message("assistant").write(msg)
                    st.rerun()
                else:
                    msg = "❌ 공지사항 업데이트에 실패했습니다."

            # [동작 8] 삭제 (Delete) - 행 전체 삭제
            elif action == "delete":
                sheet_name = cmd.get("sheet", "작업")
                target = cmd.get("target")
                if not target:
                    msg = "❌ 삭제할 항목 이름(target)이 없습니다."
                else:
                    ok, err = delete_row_by_target(sheet_name, target)
                    if ok:
                        msg = f"🗑️ **{sheet_name}** 시트에서 **'{target}'** 항목을 삭제했습니다."
                        st.session_state.messages.append({"role": "assistant", "content": msg})
                        chat_box.chat_message("assistant").write(msg)
                        st.rerun()
                    else:
                        msg = f"😅 **'{target}'** 항목을 찾을 수 없거나 삭제에 실패했습니다. ({err})"

            # [동작 9] 그 외 (대화 등)
            else:
                msg = cmd.get("response", "명령을 이해하지 못했습니다.")

        except Exception as e:
            msg = f"오류가 발생했습니다: {e}"

        # 4. 결과 출력 및 저장 (update/notice 성공 시에는 위에서 이미 append 후 rerun)
        st.session_state.messages.append({"role": "assistant", "content": msg})
        chat_box.chat_message("assistant").write(msg)