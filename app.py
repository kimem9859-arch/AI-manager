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
if "last_ai_response" not in st.session_state:
    st.session_state.last_ai_response = None

# [기능] 사용 설명서
@st.dialog("📖 사용 설명서", width="large")
def show_guide():
    st.markdown("## 👋 AI 프로젝트 매니저 사용법")
    st.divider()
    
    # 탭으로 구분
    tab1, tab2, tab3 = st.tabs(["💬 채팅 명령어", "📊 작업 관리", "📦 기타 기능"])
    
    with tab1:
        st.markdown("### 🗣️ AI에게 명령하기")
        st.info("하단 입력창에 명령을 입력하세요! 결과는 팝업으로 표시됩니다.")
        
        st.markdown("#### ➕ 작업 추가/삭제 (상위/하위 작업 계층 지원)")
        st.code('"프로젝트 개발에 UI 설계 추가해줘"  →  상위: 프로젝트 개발, 하위: UI 설계', language=None)
        st.code('"인프라 구축에 DB 설정 추가해줘"', language=None)
        st.code('"소프트웨어 개발 삭제해줘"  →  하위 작업 기준으로 삭제', language=None)
        
        st.markdown("#### 📈 진행률/상태 변경")
        st.code('"소프트웨어 개발 진행률 50%로 변경해줘"', language=None)
        st.code('"하드웨어 개발 상태 진행으로 바꿔줘"', language=None)
        
        st.markdown("#### 📝 비고 변경")
        st.code('"서버 구축 비고에 \'담당자: 홍길동\' 넣어줘"', language=None)
        st.code('"서버 구축 비고 삭제해줘"', language=None)
        
        st.markdown("#### 📢 공지 변경")
        st.code('"내일 회의로 공지 변경해줘"', language=None)
        
        st.markdown("#### 📊 데이터 요약/조회 (상위 작업별 조회 지원)")
        st.code('"프로젝트 개발 진행률 알려줘"  →  상위 작업의 평균 진행률', language=None)
        st.code('"인프라 구축 작업들 알려줘"  →  해당 상위 작업의 하위 작업 목록', language=None)
        st.code('"진행 중인 작업 알려줘"', language=None)
        st.code('"아직 배송되지 않은 물품 알려줘"', language=None)
    
    with tab2:
        st.markdown("### 📋 작업 현황 탭")
        
        st.markdown("#### 🔍 필터 기능")
        st.markdown("""
        - **상위 작업 필터**: 프로젝트 개발, 인프라 구축 등 대분류 선택
        - **하위 작업 필터**: 선택된 상위 작업에 속한 하위 작업만 표시 (종속형)
        - **상태 필터**: 대기/보류, 진행, 수정/검토, 완료
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 🔄 상태 빠른 변경")
            st.success("상태 셀 클릭 → 드롭다운 선택")
        with col2:
            st.markdown("#### 📊 상태 옵션")
            st.markdown("""
            - ⏳ 대기/보류
            - 🔄 진행  
            - 🔍 수정/검토
            - ✅ 완료
            """)
        
        st.divider()
        st.markdown("#### 📈 진행률 게이지 바")
        st.markdown("상단에 상위 작업별 평균 진행률이 표시됩니다.")
    
    with tab3:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📦 물품 견적")
            st.markdown("""
            - 💰 총 비용 자동 계산
            - 🔗 구매 링크 버튼
            """)
        
        with col2:
            st.markdown("### ⚡ 편의 기능")
            st.markdown("""
            - 🔄 **자동 새로고침**: 데이터 변경 시 즉시 반영
            - 💬 **AI 응답**: 팝업(Toast)으로 빠르게 확인
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

# 상위 작업별 진행률 계산
upper_task_progress = {}
if not df_task.empty and '상위 작업' in df_task.columns and '진행률' in df_task.columns:
    for upper in df_task['상위 작업'].unique():
        if upper and str(upper).strip():
            subset = df_task[df_task['상위 작업'] == upper]
            progress_values = []
            for val in subset['진행률']:
                try:
                    num = float(str(val).replace('%', '').strip())
                    progress_values.append(num)
                except:
                    progress_values.append(0)
            if progress_values:
                upper_task_progress[upper] = sum(progress_values) / len(progress_values)

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
# 상단 여백 적절히 조정
st.markdown("""
<style>
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# 제목 + 공지사항 (같은 행에 배치)
current_notice = get_notice()
notice_html = ""
if current_notice not in ["-", "공지없음", "공지 연결 실패", ""]:
    notice_html = f'<div style="background-color:rgba(30,136,229,0.15); padding:8px 15px; border-radius:8px; border-left:4px solid #1E88E5; font-size:0.9em;">📢 {current_notice}</div>'

st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; margin-top:0px; margin-bottom:10px; flex-wrap:wrap; gap:10px;">
    <h1 style="font-family: 'Segoe UI', 'Arial', sans-serif; font-weight: 700; letter-spacing: -1px; margin:0;">Project Manager</h1>
    {notice_html}
</div>
""", unsafe_allow_html=True)

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
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:15px; border-radius:10px; margin-bottom:10px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center;">📌 전체 작업<br><b style="font-size:20px;">{total}</b></div>
        <div style="text-align:center;">⏳ 대기/보류<br><b style="font-size:20px; color:#FF9800;">{pending}</b></div>
        <div style="text-align:center;">▶️ 진행<br><b style="font-size:20px; color:#2196F3;">{in_progress}</b></div>
        <div style="text-align:center;">🔍 수정/검토<br><b style="font-size:20px; color:#9C27B0;">{reviewing}</b></div>
        <div style="text-align:center;">✅ 완료<br><b style="font-size:20px; color:#4CAF50;">{done}</b></div>
    </div>
""", unsafe_allow_html=True)

# 상위 작업별 진행률 게이지 바 (접기/펼치기 가능)
if upper_task_progress:
    # 전체 평균 진행률 계산
    avg_progress = int(sum(upper_task_progress.values()) / len(upper_task_progress))
    
    with st.expander(f"📊 상위 작업 진행률 (평균: {avg_progress}%)", expanded=False):
        gauge_cols = st.columns(min(len(upper_task_progress), 4))
        
        for idx, (upper_name, progress) in enumerate(upper_task_progress.items()):
            progress_int = int(progress)
            col_idx = idx % len(gauge_cols)
            
            with gauge_cols[col_idx]:
                st.caption(f"📂 {upper_name}")
                st.progress(progress_int / 100, text=f"{progress_int}%")

# 탭 구성 (채팅창 제거, 전체 너비 사용)
tab_sheet, tab_items = st.tabs(["📊 작업 현황", "📦 물품 견적"])

# --- [탭 1] 작업 리스트 (검색 & 필터 & 3색 신호등 & 상태 빠른 변경) ---
with tab_sheet:
    if not df_task.empty:
        # 필터 UI 크기 축소 및 위치 조정 스타일
        st.markdown("""
        <style>
        [data-testid="stTextInput"] {
            margin-top: -20px;
            margin-bottom: -10px;
        }
        [data-testid="stTextInput"] > div > div > input {
            font-size: 0.9em;
            padding: 0.35rem 0.5rem;
        }
        [data-testid="stTextInput"] > label {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] > div {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] > label {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] span {
            font-size: 0.9em;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 1. 필터 UI 구성 (가로 배치)
        # 검색창: 절반 너비
        col_search, col_empty = st.columns([1, 1])
        with col_search:
            search_query = st.text_input("🔍 작업 검색", placeholder="작업명을 입력하세요...", key="task_search")
        
        # 상위 작업 / 상태 필터 (가로 배치)
        col_upper, col_status = st.columns([1, 1])
        
        # 상위 작업 필터
        with col_upper:
            if '상위 작업' in df_task.columns:
                all_upper = [s for s in df_task['상위 작업'].unique() if s and str(s).strip() not in ['', 'None', 'nan', '없음']]
            else:
                all_upper = []
            selected_upper = st.multiselect("📂 상위 작업", all_upper, default=list(all_upper), key="filter_upper")
        
        # 상태 필터
        with col_status:
            if '상태' in df_task.columns:
                all_statuses = [s for s in df_task['상태'].unique() if s and str(s).strip() not in ['', 'None', 'nan', '없음']]
            else:
                all_statuses = []
            selected_status = st.multiselect("🏷️ 상태", all_statuses, default=list(all_statuses), key="filter_status")

        # 2. 데이터 필터링 로직
        df_view = df_task.copy()
        
        # (1) 상위 작업 필터 적용
        if '상위 작업' in df_view.columns and selected_upper:
            df_view = df_view[df_view['상위 작업'].isin(selected_upper)]
        
        # (2) 상태 필터 적용
        if '상태' in df_view.columns and selected_status:
            df_view = df_view[df_view['상태'].isin(selected_status)]
            
        # (3) 검색어 적용 (하위 작업명 기준)
        if search_query:
            # 상위 작업, 하위 작업, 비고 모두에서 검색
            mask = df_view['하위 작업'].astype(str).str.contains(search_query, case=False, na=False) if '하위 작업' in df_view.columns else pd.Series([False]*len(df_view))
            if '상위 작업' in df_view.columns:
                mask = mask | df_view['상위 작업'].astype(str).str.contains(search_query, case=False, na=False)
            if '비고' in df_view.columns:
                mask = mask | df_view['비고'].astype(str).str.contains(search_query, case=False, na=False)
            df_view = df_view[mask]

        # 3. 결과 출력 (상태 빠른 변경 기능 + ProgressColumn 게이지 바)
        if not df_view.empty:
            # 원본 인덱스 저장 (수정 추적용)
            df_view = df_view.reset_index(drop=True)
            
            # 진행률 숫자 변환 (ProgressColumn용 - 0~100 범위)
            if '진행률' in df_view.columns:
                df_view['진행률_바'] = df_view['진행률'].apply(
                    lambda x: float(str(x).replace('%', '').strip()) 
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
            
            # 진행률 프로그레스 바 표시
            if '진행률_바' in df_view.columns:
                col_config['진행률_바'] = st.column_config.ProgressColumn(
                    "진행률",
                    help="진행률 바 (0% ~ 100%)",
                    min_value=0,
                    max_value=100,
                    format="%d%%"
                )
                # 원래 진행률 열 숨기기
                col_config['진행률'] = None
            
            # data_editor로 표시 (상태 변경 가능)
            edited_df = st.data_editor(
                df_view,
                use_container_width=True,
                height=600,
                column_config=col_config,
                disabled=[col for col in df_view.columns if col != '상태'],  # 상태 열만 편집 가능
                hide_index=True,
                key="task_editor"
            )
            
            # 상태 변경 감지 및 적용
            if '상태' in df_view.columns and '하위 작업' in df_view.columns:
                for idx in range(len(df_view)):
                    old_status = df_view.at[idx, '상태']
                    new_status = edited_df.at[idx, '상태']
                    if old_status != new_status:
                        # 하위 작업명 가져오기
                        task_name = df_view.at[idx, '하위 작업']
                        ok, err = update_cell_by_target("작업", task_name, "상태", new_status)
                        if ok:
                            st.toast(f"✅ '{task_name}' 상태가 '{new_status}'로 변경되었습니다!", icon="🔄")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"상태 변경 실패: {err}")
            
            # 안내 문구
            st.caption("💡 상태를 클릭하면 드롭다운으로 빠르게 변경할 수 있습니다!")
        else:
            st.warning("검색 결과가 없습니다.")
            
    else:
        st.info("작업 리스트가 비어있습니다.")

# --- [탭 2] 물품 리스트 (검색 & 필터 & 링크 & 비용) ---
with tab_items:
    if not df_items.empty:
        # 필터 UI 크기 축소 및 위치 조정 스타일
        st.markdown("""
        <style>
        [data-testid="stTextInput"] {
            margin-top: -20px;
            margin-bottom: -10px;
        }
        [data-testid="stTextInput"] > div > div > input {
            font-size: 0.9em;
            padding: 0.35rem 0.5rem;
        }
        [data-testid="stTextInput"] > label {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] > div {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] > label {
            font-size: 0.9em;
        }
        [data-testid="stMultiSelect"] span {
            font-size: 0.9em;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 1. 상단 UI 구성 (검색창 위, 상태필터 아래)
        search_item = st.text_input("📦 물품 검색", placeholder="품목명, 비고 등을 입력하세요...", key="item_search_input")
        
        # 필터링할 열 자동 감지 ('상태', '구분', '구매상태' 등)
        filter_col = next((c for c in ['상태', '구분', '구매상태', 'Status'] if c in df_items.columns), None)
        
        if filter_col:
            # None, 빈칸 제외
            all_opts = [s for s in df_items[filter_col].unique() if s and str(s).strip() not in ['', 'None', 'nan', '없음', '-']]
            selected_opts = st.multiselect(
                f"🏷️ {filter_col} 필터", 
                all_opts, 
                default=all_opts,
                key="item_filter_unique"
            )
        else:
            selected_opts = [] 

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

# --- AI 채팅 입력 (하단 고정, Toast 팝업 형식) ---
# AI 긴 응답(요약 등)이 있으면 Dialog로 표시
@st.dialog("📊 AI 응답", width="large")
def show_ai_response(response_text):
    st.markdown(response_text)
    if st.button("닫기", use_container_width=True):
        st.session_state.last_ai_response = None
        st.rerun()

if st.session_state.last_ai_response:
    show_ai_response(st.session_state.last_ai_response)
    st.session_state.last_ai_response = None

# 4. 사용자 입력 처리 (Toast 팝업 형식)   
if prompt := st.chat_input("💬 AI에게 명령하기 (예: '소프트웨어 개발 진행률 50%로 변경해줘')"):
    # 1. 사용자 메시지 기록
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.toast(f"📝 {prompt}", icon="👤")

    if model is None:
        msg = "⚠️ API 키가 설정되지 않아 AI 명령을 처리할 수 없습니다."
        st.session_state.messages.append({"role": "assistant", "content": msg})
        st.toast(msg, icon="⚠️")
    else:
        # 2. 현재 데이터 요약 + 작업 시트 컬럼 순서 (추가 시 행 순서 맞추기용)
        # 새 컬럼 순서: 상위 작업, 하위 작업, 상태, 비고, 진행률
        task_headers = df_task.columns.tolist() if not df_task.empty else ["상위 작업", "하위 작업", "상태", "비고", "진행률"]
        
        # 전체 작업 데이터 (요약용)
        task_full_data = df_task.to_string(index=False) if not df_task.empty else "작업 데이터 없음"
        
        # 전체 물품 데이터 (요약용)
        items_full_data = df_items.to_string(index=False) if not df_items.empty else "물품 데이터 없음"
        
        # 3. AI 시스템 프롬프트 (확장된 기능 - 계층 구조 지원)
        sys_msg = f"""
        당신은 구글 시트 데이터베이스 관리자입니다.
        
        [절대 규칙]
        1. 당신은 사용자의 말을 듣고 **JSON 데이터만** 출력해야 합니다.
        2. 절대로 대화하거나, 설명을 덧붙이거나, 문장을 교정하지 마십시오.
        3. 명령어 종류: add(추가), delete(삭제), update_progress(진행률변경), update_status(상태변경), update_remark(비고변경), clear_cell(셀내용삭제), notice(공지변경), summary(데이터요약), chat(대화)

        [작업 시트 컬럼 순서] (추가 시 row는 이 순서와 반드시 동일하게!)
        {task_headers}
        - 순서: 상위 작업, 하위 작업, 상태, 비고, 진행률
        - 새 작업 추가 시: 상태 "대기/보류", 비고 "", 진행률 "0%" 로 채우세요.

        [현재 작업 데이터 전체]
        {task_full_data}

        [현재 물품 데이터 전체]
        {items_full_data}

        [상태 옵션] (반드시 이 4가지만 사용!)
        대기/보류, 진행, 수정/검토, 완료

        [출력 가능한 JSON 포맷]
        1. 작업 추가 (~ 추가해줘, ~에 ~ 추가해줘):
           - "프로젝트 개발에 UI 설계 추가해줘" → 상위: 프로젝트 개발, 하위: UI 설계
           - "소프트웨어 개발 추가해줘" → 문맥상 적절한 상위 작업 선택 또는 사용자에게 질문
           {{"action": "add", "sheet": "작업", "row": ["상위 작업명", "하위 작업명", "대기/보류", "", "0%"]}}
           
        2. 작업 삭제 - 행 전체 삭제 (~ 삭제해줘, ~ 작업 삭제):
           - target은 "하위 작업명"으로 지정
           {{"action": "delete", "sheet": "작업", "target": "하위 작업명"}}
           
        3. 진행률 변경 (~ 진행률 50%로 변경, ~ 50%로 바꿔줘):
           - target은 "하위 작업명"으로 지정
           {{"action": "update_progress", "target": "하위 작업명", "value": "50%"}}
           
        4. 상태 변경 (~ 상태 진행으로 변경, ~ 완료로 바꿔줘):
           - target은 "하위 작업명"으로 지정
           {{"action": "update_status", "target": "하위 작업명", "value": "진행"}}
           (상태는 반드시 대기/보류, 진행, 수정/검토, 완료 중 하나)
           
        5. 비고 변경 (~ 비고 "내용"으로 변경):
           {{"action": "update_remark", "target": "하위 작업명", "value": "새로운 비고"}}
           
        6. 비고 삭제 (~ 비고 삭제해줘):
           {{"action": "clear_cell", "target": "하위 작업명", "column": "비고"}}
           
        7. 공지 변경 (~로 공지 변경, 공지사항 ~로 변경):
           {{"action": "notice", "content": "새로운 공지 내용"}}
           
        8. 데이터 요약/조회 (~ 알려줘, ~ 요약해줘, ~ 있어?, ~ 뭐야?):
            {{"action": "summary", "response": "요약 내용을 자연스러운 문장으로 작성"}}
            - 작업 데이터나 물품 데이터를 분석하여 사용자 질문에 답변
            - 상위 작업별 진행률, 상태별 작업, 물품 배송상태 등을 요약
            - "프로젝트 개발 진행률 알려줘" → 해당 상위 작업의 평균 진행률 계산
            - "인프라 구축 작업들 알려줘" → 해당 상위 작업에 속한 하위 작업 목록
            - 한국어로 친절하게 답변
           
        9. 일반 대화:
            {{"action": "chat", "response": "할말"}}
        
        [예시]
        Q: "프로젝트 개발에 UI 설계 추가해줘"
        A: {{"action": "add", "sheet": "작업", "row": ["프로젝트 개발", "UI 설계", "대기/보류", "", "0%"]}}
        
        Q: "인프라 구축에 DB 설정 추가해줘"
        A: {{"action": "add", "sheet": "작업", "row": ["인프라 구축", "DB 설정", "대기/보류", "", "0%"]}}
        
        Q: "소프트웨어 개발 삭제해줘"
        A: {{"action": "delete", "sheet": "작업", "target": "소프트웨어 개발"}}
        
        Q: "소프트웨어 개발 진행률 50%로 변경해줘"
        A: {{"action": "update_progress", "target": "소프트웨어 개발", "value": "50%"}}
        
        Q: "하드웨어 개발 상태를 진행으로 바꿔줘"
        A: {{"action": "update_status", "target": "하드웨어 개발", "value": "진행"}}
        
        Q: "서버 구축 비고에 '담당자: 홍길동' 넣어줘"
        A: {{"action": "update_remark", "target": "서버 구축", "value": "담당자: 홍길동"}}
        
        Q: "내일 회의로 공지 변경해줘"
        A: {{"action": "notice", "content": "내일 회의"}}
        
        Q: "프로젝트 개발 진행률 알려줘"
        A: {{"action": "summary", "response": "프로젝트 개발의 평균 진행률은 45%입니다.\\n- 소프트웨어 개발: 50%\\n- 하드웨어 개발: 40%"}}
        
        Q: "인프라 구축 작업들 알려줘"
        A: {{"action": "summary", "response": "인프라 구축에 속한 작업 목록입니다:\\n1. 서버 구축 (진행률: 70%, 상태: 진행)\\n2. 네트워크 설정 (진행률: 100%, 상태: 완료)"}}
        
        Q: "진행 중인 작업 알려줘"
        A: {{"action": "summary", "response": "현재 진행 중인 작업은 다음과 같습니다:\\n1. 소프트웨어 개발 (프로젝트 개발) - 50%\\n2. 서버 구축 (인프라 구축) - 70%"}}
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
                # 상위 작업, 하위 작업 표시
                upper_name = row_vals[0] if len(row_vals) > 0 else ""
                lower_name = row_vals[1] if len(row_vals) > 1 else ""
                msg = f"✅ '{upper_name} > {lower_name}' 작업이 추가되었습니다."
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.toast(msg, icon="✅")
                time.sleep(1)
                st.rerun()

            # [동작 2] 진행률 변경 (Update Progress)
            elif action == "update" or action == "update_progress":
                target = cmd.get("target")
                val = cmd.get("value", "0%")
                if "%" not in str(val): val = str(val) + "%"
                
                # 진행률 숫자 추출
                try:
                    progress_num = float(str(val).replace('%', '').strip())
                except:
                    progress_num = 0
                
                # 현재 진행률 확인 (0%에서 최초 변경인지 체크)
                current_progress = 0
                if not df_task.empty and '진행률' in df_task.columns and '하위 작업' in df_task.columns:
                    task_row = df_task[df_task['하위 작업'] == target]
                    if not task_row.empty:
                        try:
                            current_val = str(task_row['진행률'].values[0]).replace('%', '').strip()
                            current_progress = float(current_val) if current_val else 0
                        except:
                            current_progress = 0
                
                ok, err = update_cell_by_target("작업", target, "진행", val)
                if ok:
                    msg = f"📈 '{target}' 진행률을 {val}로 변경했습니다."
                    
                    # 0%에서 최초 변경 시에만 상태를 자동으로 '진행'으로 변경
                    if current_progress == 0 and progress_num > 0:
                        status_ok, _ = update_cell_by_target("작업", target, "상태", "진행")
                        if status_ok:
                            msg += " (상태: 진행으로 자동 변경)"
                    
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.toast(msg, icon="📈")
                    time.sleep(1)
                    st.rerun()
                else:
                    msg = f"😅 '{target}' 작업을 찾을 수 없습니다."
                    st.toast(msg, icon="😅")

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
                    msg = f"🔄 '{target}' 상태를 {val}(으)로 변경했습니다."
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.toast(msg, icon="🔄")
                    time.sleep(1)
                    st.rerun()
                else:
                    msg = f"😅 '{target}' 작업을 찾을 수 없습니다."
                    st.toast(msg, icon="😅")

            # [동작 4] 비고 변경 (Update Remark)
            elif action == "update_remark":
                target = cmd.get("target")
                val = cmd.get("value", "")
                
                ok, err = update_cell_by_target("작업", target, "비고", val)
                if ok:
                    msg = f"📋 '{target}' 비고를 변경했습니다: {val}"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.toast(msg, icon="📋")
                    time.sleep(1)
                    st.rerun()
                else:
                    msg = f"😅 '{target}' 작업을 찾을 수 없습니다."
                    st.toast(msg, icon="😅")

            # [동작 5] 셀 내용 삭제 (Clear Cell) - 비고 삭제
            elif action == "clear_cell":
                target = cmd.get("target")
                column = cmd.get("column", "")
                
                ok, err = clear_cell_by_target("작업", target, column)
                if ok:
                    msg = f"🗑️ '{target}'의 {column} 내용을 삭제했습니다."
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.toast(msg, icon="🗑️")
                    time.sleep(1)
                    st.rerun()
                else:
                    msg = f"😅 '{target}' 작업 또는 '{column}' 열을 찾을 수 없습니다."
                    st.toast(msg, icon="😅")

            # [동작 6] ★ 공지 수정
            elif action == "notice":
                content = cmd.get("content")
                if update_notice(content):
                    msg = f"📢 공지사항이 업데이트 되었습니다: {content}"
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.toast(msg, icon="📢")
                    time.sleep(1)
                    st.rerun()
                else:
                    msg = "❌ 공지사항 업데이트에 실패했습니다."
                    st.toast(msg, icon="❌")

            # [동작 7] 삭제 (Delete) - 행 전체 삭제
            elif action == "delete":
                sheet_name = cmd.get("sheet", "작업")
                target = cmd.get("target")
                if not target:
                    msg = "❌ 삭제할 항목 이름이 없습니다."
                    st.toast(msg, icon="❌")
                else:
                    ok, err = delete_row_by_target(sheet_name, target)
                    if ok:
                        msg = f"🗑️ '{target}' 항목을 삭제했습니다."
                        st.session_state.messages.append({"role": "assistant", "content": msg})
                        st.toast(msg, icon="🗑️")
                        time.sleep(1)
                        st.rerun()
                    else:
                        msg = f"😅 '{target}' 항목을 찾을 수 없거나 삭제에 실패했습니다."
                        st.toast(msg, icon="😅")

            # [동작 8] 데이터 요약 (Summary)
            elif action == "summary":
                msg = cmd.get("response", "요약 정보를 가져올 수 없습니다.")
                st.session_state.messages.append({"role": "assistant", "content": msg})
                # 요약은 길 수 있으므로 dialog로 표시
                st.session_state.last_ai_response = f"📊 {msg}"
                st.rerun()

            # [동작 9] 그 외 (대화 등)
            else:
                msg = cmd.get("response", "명령을 이해하지 못했습니다.")
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.toast(f"🤖 {msg}", icon="💬")

        except Exception as e:
            msg = f"오류가 발생했습니다: {e}"
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.toast(msg, icon="❌")