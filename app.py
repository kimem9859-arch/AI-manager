import json
import time
from typing import Any, Dict, List, Optional

import gspread
import pandas as pd
import streamlit as st
from google.generativeai import GenerativeModel, configure
from oauth2client.service_account import ServiceAccountCredentials


# ==========================================================
# 1. 기본 설정 및 공통 상수/유틸
# ==========================================================

PAGE_TITLE = "내 AI 프로젝트 매니저"
PAGE_ICON = "🤖"
SPREADSHEET_NAME = "Safety_Project"
NOTICE_SHEET_NAME = "공지"

# 금액/비용 관련 컬럼을 감지할 키워드
COST_KEYWORDS = ["금액", "가격", "비용"]

# Streamlit 페이지 설정
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = []


# ----------------------------------------------------------
# 1-1. 공통 유틸 함수
# ----------------------------------------------------------
def toast(message: str, icon: Optional[str] = None) -> None:
    """간단 토스트 래퍼."""
    if icon:
        st.toast(message, icon=icon)
    else:
        st.toast(message)


def rerun(delay: float = 0.0) -> None:
    """필요하다면 잠깐 대기 후 rerun."""
    if delay > 0:
        time.sleep(delay)
    st.rerun()


# ----------------------------------------------------------
# 1-2. 채팅 관련 유틸
# ----------------------------------------------------------
def undo_last_chat() -> None:
    """방금 AI 응답 + 내 질문 1쌍을 되돌리는 함수."""
    if len(st.session_state.messages) >= 2:
        st.session_state.messages.pop()  # AI 답변 삭제
        st.session_state.messages.pop()  # 내 질문 삭제
        toast("↩️ 방금 대화를 취소했습니다!", icon="🗑️")
        rerun(0.5)
    else:
        toast("⚠️ 취소할 대화 내역이 없습니다.")


# ----------------------------------------------------------
# 1-3. 사용 설명서 다이얼로그
# ----------------------------------------------------------
@st.dialog("📖 사용 설명서")
def show_guide() -> None:
    st.markdown(
        """
        ### 👋 환영합니다!
        **1. 💬 채팅 명령**
        - "라즈베리파이 추가해줘" (추가)
        - "3D 모델링 진행률 50%로 바꿔줘" (수정)
        
        **2. 📊 시트 관리**
        - **작업 탭:** 진행률에 따라 색상이 변합니다.
        - **물품 탭:** 총 비용 계산 & 구매 링크 버튼이 제공됩니다.
        
        **3. ↩️ 되돌리기**
        - 채팅창 오른쪽 위 빨간 버튼으로 실행 취소가 가능합니다.
        """
    )


# ----------------------------------------------------------
# 1-4. 구글 시트 연결/유틸
# ----------------------------------------------------------
def _get_credentials(scope: List[str]) -> ServiceAccountCredentials:
    """환경에 따라 적절한 서비스 계정을 가져온다."""
    try:
        # Streamlit Secrets 사용 (배포 환경)
        creds_dict = dict(st.secrets["gcp_service_account"])
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception:
        # 로컬 JSON 파일 사용
        return ServiceAccountCredentials.from_json_keyfile_name(
            "service_account.json", scope
        )


def get_spreadsheet() -> gspread.Spreadsheet:
    """프로젝트 스프레드시트 객체 반환."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _get_credentials(scope)
    client = gspread.authorize(creds)
    return client.open(SPREADSHEET_NAME)


def load_data_safe(sheet_name: str) -> pd.DataFrame:
    """
    시트 데이터를 DataFrame으로 안전하게 로드한다.
    - 상단 5행에서 헤더 후보를 찾고, 이후를 데이터로 간주.
    """
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(sheet_name)

        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame()

        # 헤더 후보 찾기 (최초로 유효 값이 2개 이상인 행)
        header_idx = 0
        for i, row in enumerate(all_values[:5]):
            if len([x for x in row if x.strip()]) >= 2:
                header_idx = i
                break

        headers = all_values[header_idx]
        data = all_values[header_idx + 1 :]

        if not data:
            return pd.DataFrame(columns=headers)

        df = pd.DataFrame(data, columns=headers)
        return df

    except Exception as e:
        st.error(f"❌ '{sheet_name}' 시트 로딩 실패: {e}")
        return pd.DataFrame()


def append_row(sheet_name: str, row_data: List[Any]) -> bool:
    """지정 시트에 행 추가."""
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        ws.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"❌ '{sheet_name}' 시트 행 추가 실패: {e}")
        return False


# ----------------------------------------------------------
# 1-5. 공지 관련 유틸
# ----------------------------------------------------------
def _get_or_create_notice_sheet(client: gspread.Client) -> gspread.Worksheet:
    """공지 시트를 가져오거나, 없으면 생성."""
    try:
        return client.worksheet(NOTICE_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = client.add_worksheet(NOTICE_SHEET_NAME, rows=5, cols=2)
        ws.update_cell(1, 1, "공지없음")
        return ws


def get_notice() -> str:
    """공지 시트의 1행 1열 값을 반환."""
    try:
        client = get_spreadsheet()
        ws = _get_or_create_notice_sheet(client)
        val = ws.cell(1, 1).value
        return val if val else "공지없음"
    except Exception:
        return "공지 연결 실패"


def update_notice(text: str) -> bool:
    """공지 내용을 업데이트."""
    try:
        client = get_spreadsheet()
        ws = _get_or_create_notice_sheet(client)
        ws.update_cell(1, 1, text)
        return True
    except Exception as e:
        st.error(f"❌ 공지사항 업데이트 실패: {e}")
        return False


# ----------------------------------------------------------
# 1-6. Gemini 설정
# ----------------------------------------------------------
if "GOOGLE_API_KEY" in st.secrets:
    configure(api_key=st.secrets["GOOGLE_API_KEY"])

model: GenerativeModel = GenerativeModel("gemini-2.5-pro")


# ==========================================================
# 2. 데이터 로딩 및 전처리
# ==========================================================
# 작업 데이터
df_task = load_data_safe("작업")

if not df_task.empty and "상태" in df_task.columns:
    total_tasks = len(df_task)
    done_tasks = len(df_task[df_task["상태"] == "완료"])
    pending_tasks = len(df_task[df_task["상태"] == "대기"])
else:
    total_tasks, done_tasks, pending_tasks = 0, 0, 0

# 물품 데이터
df_items = load_data_safe("물품")

if not df_items.empty:
    # 빈칸 채우기
    df_items = df_items.fillna("-")

    # 금액/가격/비용 관련 컬럼 숫자화
    for col in df_items.columns:
        if any(keyword in col for keyword in COST_KEYWORDS):
            df_items[col] = (
                df_items[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("원", "")
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
            )


# ==========================================================
# 3. UI 레이아웃 구성
# ==========================================================
st.title("🤖 든든한 프로젝트 매니저")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()

    if st.button("🔄 데이터 새로고침", use_container_width=True):
        rerun()

    if st.button("❓ 도움말"):
        show_guide()

# 상단 통계 카드
st.markdown(
    f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:15px; border-radius:10px; margin-bottom:20px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center;">📌 전체 작업<br><b style="font-size:20px;">{total_tasks}</b></div>
        <div style="text-align:center;">✅ 완료됨<br><b style="font-size:20px; color:#4CAF50;">{done_tasks}</b></div>
        <div style="text-align:center;">⏳ 대기중<br><b style="font-size:20px; color:#FF9800;">{pending_tasks}</b></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 탭/컬럼 구성
if is_mobile:
    tab_chat, tab_task, tab_items = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat = tab_chat
    c_sheet = tab_task
    c_items = tab_items
else:
    col_left, col_right = st.columns([1, 1.3])
    c_chat = col_left
    with col_right:
        sub_task, sub_items = st.tabs(["📊 작업 현황", "📦 물품 견적"])
        c_sheet = sub_task
        c_items = sub_items


# ==========================================================
# 4. 작업 리스트 탭
# ==========================================================
with c_sheet:
    if not df_task.empty:
        col_search, col_filter = st.columns([1, 1])

        with col_search:
            search_query = st.text_input("🔍 작업 검색", placeholder="작업명을 입력하세요...")

        with col_filter:
            all_statuses = df_task["상태"].unique() if "상태" in df_task.columns else []
            selected_status = st.multiselect(
                "🏷️ 상태 필터", all_statuses, default=list(all_statuses)
            )

        df_view = df_task.copy()

        # 상태 필터
        if "상태" in df_view.columns and selected_status:
            df_view = df_view[df_view["상태"].isin(selected_status)]

        # 검색어 필터(첫 컬럼 기준)
        if search_query:
            df_view = df_view[
                df_view.iloc[:, 0]
                .astype(str)
                .str.contains(search_query, case=False, na=False)
            ]

        # 진행률 색상 함수
        def color_progress(val: Any) -> Optional[str]:
            if pd.isna(val) or str(val) in ["", "-"]:
                return None
            try:
                num = float(str(val).replace("%", "").strip())
                num = max(0, min(100, num))
                if num < 50:
                    ratio = num / 50
                    red, green, blue = 255, int(255 * ratio), 0
                else:
                    ratio = (num - 50) / 50
                    red, green, blue = int(255 * (1 - ratio)), 255, 0

                style = f"background-color: rgb({red}, {green}, {blue}); color: black;"
                if num >= 100:
                    style += " font-weight: bold;"
                return style
            except Exception:
                return None

        if not df_view.empty:
            if "진행률" in df_view.columns:
                st.dataframe(
                    df_view.style.map(color_progress, subset=["진행률"]),
                    use_container_width=True,
                    height=500,
                )
            else:
                st.dataframe(df_view, use_container_width=True, height=500)
        else:
            st.warning("검색 결과가 없습니다.")
    else:
        st.info("작업 리스트가 비어있습니다.")


# ==========================================================
# 5. 물품 리스트 탭
# ==========================================================
with c_items:
    if not df_items.empty:
        col_search, col_filter = st.columns([2, 1])

        with col_search:
            search_item = st.text_input(
                "📦 물품 검색",
                placeholder="품목명, 비고 등을 입력하세요...",
                key="item_search_input",
            )

        with col_filter:
            filter_col = next(
                (
                    c
                    for c in ["상태", "구분", "구매상태", "Status"]
                    if c in df_items.columns
                ),
                None,
            )
            if filter_col:
                all_opts = df_items[filter_col].unique()
                selected_opts = st.multiselect(
                    f"🏷️ {filter_col} 필터",
                    all_opts,
                    default=list(all_opts),
                    key="item_filter_unique",
                )
            else:
                selected_opts = []
                st.empty()

        df_display = df_items.copy()

        # 필터 적용
        if filter_col and selected_opts:
            df_display = df_display[df_display[filter_col].isin(selected_opts)]

        # 검색 적용
        if search_item:
            first_col = df_display.iloc[:, 0].astype(str)
            remark_col = df_display.get("비고", pd.Series([""] * len(df_display))).astype(
                str
            )
            mask = first_col.str.contains(search_item, case=False, na=False) | remark_col.str.contains(
                search_item, case=False, na=False
            )
            df_display = df_display[mask]

        # 링크 컬럼 처리
        if "구매 링크" not in df_display.columns:
            df_display["구매 링크"] = None

        if "비고" in df_display.columns:
            for i, row in df_display.iterrows():
                val = str(row["비고"])
                if val.startswith("http"):
                    df_display.at[i, "구매 링크"] = val
                    df_display.at[i, "비고"] = "-"

        # 표 출력
        if not df_display.empty:
            st.dataframe(
                df_display,
                use_container_width=True,
                height=400,
                column_config={
                    "구매 링크": st.column_config.LinkColumn(
                        "링크", display_text="🔗 구매"
                    )
                },
            )
        else:
            st.warning("조건에 맞는 물품이 없습니다.")

        # 총 비용 계산
        cost_cols = [
            c for c in df_items.columns if any(k in c for k in COST_KEYWORDS)
        ]
        if cost_cols:
            current_cost = int(df_display[cost_cols[0]].sum())
            st.markdown(
                f"""
                <div style="
                    text-align: center; 
                    padding: 20px; 
                    background-color: rgba(0, 200, 100, 0.1); 
                    border: 1px solid rgba(0, 200, 100, 0.3);
                    border-radius: 15px; 
                    margin-top: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <span style="font-size: 1.3em; font-weight: bold; color: #555; margin-right: 10px;">💰 견적 합계:</span>
                    <span style="font-size: 2.0em; color: #2ecc71; font-weight: bold;">{current_cost:,}원</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("물품 리스트가 비어있습니다.")


# ==========================================================
# 6. 채팅 탭 및 AI 처리
# ==========================================================
with c_chat:
    current_notice = get_notice()
    if current_notice not in ["-", "공지없음", "공지 연결 실패"]:
        st.info(f" **공지:** {current_notice}", icon="📢")

    h_col1, h_col2 = st.columns([1, 0.4])
    h_col1.subheader("💬 AI 매니저")
    if h_col2.button("↩️ 되돌리기", type="primary", use_container_width=True):
        undo_last_chat()

    chat_box = st.container(height=500, border=True)
    with chat_box:
        for m in st.session_state.messages:
            st.chat_message(m["role"]).write(m["content"])


def build_system_prompt(task_summary: Any) -> str:
    """Gemini에게 줄 시스템 프롬프트 문자열 생성."""
    return f"""
    당신은 구글 시트 데이터베이스 관리자입니다.
    
    [절대 규칙]
    1. 당신은 사용자의 말을 듣고 **JSON 데이터만** 출력해야 합니다.
    2. 절대로 대화하거나, 설명을 덧붙이거나, 문장을 교정하지 마십시오.
    3. 사용자가 숫자(%)와 함께 "변경", "수정" 등을 말하면 'update' 명령입니다.
    4. "공지", "공지사항"을 변경하라고 하면 'notice' 명령입니다.

    [현재 작업 목록]
    {task_summary}

    [출력 가능한 JSON 포맷]
    - 추가: {{"action": "add", "sheet": "작업/물품", "row": ["내용", "대기", "", "", "", "0%"]}}
    - 수정: {{"action": "update", "sheet": "작업", "target": "작업명", "value": "50%"}}
    - 공지: {{"action": "notice", "content": "새로운 공지 내용"}}
    - 삭제: {{"action": "delete", "target": "..."}}
    - 대화: {{"action": "chat", "response": "할말"}}

    [예시]
    Q: "공지사항 '내일 3시 회의'로 바꿔줘"
    A: {{"action": "notice", "content": "내일 3시 회의"}}
    """


def handle_ai_command(cmd: Dict[str, Any]) -> str:
    """Gemini에서 받은 JSON 명령을 실제 동작으로 연결."""
    action = cmd.get("action")

    # 1) 추가
    if action == "add":
        sheet_name = cmd.get("sheet", "작업")
        row_vals = cmd.get("row") or []
        if append_row(sheet_name, row_vals):
            return f"✅ **{sheet_name}** 시트에 추가되었습니다."
        return f"❌ **{sheet_name}** 시트에 추가하지 못했습니다."

    # 2) 진행률 수정
    if action == "update":
        target = cmd.get("target")
        val = cmd.get("value", "")
        if not target:
            return "❌ 수정할 작업명을 찾지 못했습니다."

        if "%" not in val:
            val = f"{val}%"

        try:
            client = get_spreadsheet()
            ws = client.worksheet("작업")

            cell = ws.find(target)
            headers = ws.row_values(1)

            # 기본 6번째 열, '진행' 포함된 헤더가 있으면 그 열로
            col_idx = 6
            for i, h in enumerate(headers):
                if "진행" in h:
                    col_idx = i + 1
                    break

            ws.update_cell(cell.row, col_idx, val)
            msg = f"📈 **'{target}'** 진행률을 **{val}**로 변경했습니다."
            rerun()  # 반영 후 새로고침
            return msg
        except Exception:
            return f"😅 **'{target}'** 작업을 찾을 수 없거나 수정에 실패했습니다."

    # 3) 공지 수정
    if action == "notice":
        content = cmd.get("content", "")
        if update_notice(content):
            rerun()
            return f"📢 공지사항이 업데이트 되었습니다: **{content}**"
        return "❌ 공지사항 업데이트에 실패했습니다."

    # 4) 일반 대화/기타
    return cmd.get("response", "명령을 이해하지 못했습니다.")


# 사용자 입력 처리
if prompt := st.chat_input("명령을 입력하세요 (예: 공지사항 '내일 회식'으로 변경해줘)"):
    # 1. 사용자 메시지 기록
    st.session_state.messages.append({"role": "user", "content": prompt})
    chat_box.chat_message("user").write(prompt)

    # 2. 현재 작업 요약
    task_summary = df_task.iloc[:, 0].tolist() if not df_task.empty else "없음"

    # 3. 시스템 프롬프트 생성
    sys_msg = build_system_prompt(task_summary)

    try:
        # 4. Gemini 호출
        response = model.generate_content(sys_msg + f"\n사용자 요청: {prompt}")
        text_res = (
    response.text.strip()
    .replace("", "")
    .replace("```", "")
)
        st.write("🔍 AI RAW 응답:", text_res)

        # 5. JSON 파싱
        cmd = json.loads(text_res)

        # 6. 명령 실행
        msg = handle_ai_command(cmd)

    except json.JSONDecodeError:
        msg = "❌ AI 응답을 JSON으로 해석하지 못했습니다."
    except Exception as e:
        msg = f"오류가 발생했습니다: {e}"

    # 7. 결과 메시지 저장 및 출력
    st.session_state.messages.append({"role": "assistant", "content": msg})
    chat_box.chat_message("assistant").write(msg)