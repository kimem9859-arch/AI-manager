"""Main entry: page config, data load, UI layout, AI chat input."""
import time
import streamlit as st
import pandas as pd

from utils.config import (
    init_page_config,
    init_session_state,
    STATUS_OPTIONS,
    get_gemini_model,
)
from utils.spreadsheet import load_data_safe, get_notice, update_cell_by_target
from utils.ui_guide import show_guide
from utils.ai_handler import handle_ai_command

# ----------------------------------------------------------
# 1. Initial setup
# ----------------------------------------------------------
init_page_config()
init_session_state()
model = get_gemini_model()

# ----------------------------------------------------------
# 2. Data loading
# ----------------------------------------------------------
df_task = load_data_safe("작업")
if not df_task.empty and "상태" in df_task.columns:
    total = len(df_task)
    pending = len(df_task[df_task["상태"].isin(["대기", "대기/보류", "보류"])])
    in_progress = len(df_task[df_task["상태"].isin(["진행", "진행중"])])
    reviewing = len(df_task[df_task["상태"].isin(["수정", "검토", "수정/검토"])])
    done = len(df_task[df_task["상태"] == "완료"])
else:
    total = pending = in_progress = reviewing = done = 0

upper_task_progress = {}
if (
    not df_task.empty
    and "상위 작업" in df_task.columns
    and "진행률" in df_task.columns
):
    for upper in df_task["상위 작업"].unique():
        if upper and str(upper).strip():
            subset = df_task[df_task["상위 작업"] == upper]
            progress_values = []
            for val in subset["진행률"]:
                try:
                    num = float(str(val).replace("%", "").strip())
                    progress_values.append(num)
                except Exception:
                    progress_values.append(0)
            if progress_values:
                upper_task_progress[upper] = sum(progress_values) / len(
                    progress_values
                )

df_items = load_data_safe("물품")
if not df_items.empty:
    df_items = df_items.fillna("-")
    for col in df_items.columns:
        if any(k in col for k in ["금액", "가격", "비용"]):
            df_items[col] = (
                df_items[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("원", "")
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
            )

# ----------------------------------------------------------
# 3. UI layout
# ----------------------------------------------------------
st.markdown(
    """
<style>
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

current_notice = get_notice()
notice_html = ""
if current_notice not in ["-", "공지없음", "공지 연결 실패", ""]:
    notice_html = f'<div style="background-color:rgba(30,136,229,0.15); padding:8px 15px; border-radius:8px; border-left:4px solid #1E88E5; font-size:0.9em;"><b>📢 공지:</b> {current_notice}</div>'

st.markdown(
    f"""
<div style="display:flex; justify-content:space-between; align-items:center; margin-top:0px; margin-bottom:10px; flex-wrap:wrap; gap:10px;">
    <h1 style="font-family: 'Segoe UI', 'Arial', sans-serif; font-weight: 700; letter-spacing: -1px; margin:0;">Project Manager</h1>
    {notice_html}
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ 설정")
    if model is None:
        st.warning(
            "⚠️ **GOOGLE_API_KEY**가 설정되지 않았습니다. 채팅 기능을 쓰려면 Secrets 또는 환경변수에 API 키를 넣어주세요."
        )
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()
    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.rerun()
    if st.button("❓ 도움말"):
        show_guide()

if is_mobile:
    label_size, number_size, padding = "0.7em", "14px", "10px"
else:
    label_size, number_size, padding = "1em", "20px", "15px"

st.markdown(
    f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:{padding}; border-radius:10px; margin-bottom:10px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center; font-size:{label_size};">📌 전체 작업<br><b style="font-size:{number_size};">{total}</b></div>
        <div style="text-align:center; font-size:{label_size};">⏳ 대기/보류<br><b style="font-size:{number_size}; color:#FF9800;">{pending}</b></div>
        <div style="text-align:center; font-size:{label_size};">▶️ 진행<br><b style="font-size:{number_size}; color:#2196F3;">{in_progress}</b></div>
        <div style="text-align:center; font-size:{label_size};">🔍 수정/검토<br><b style="font-size:{number_size}; color:#9C27B0;">{reviewing}</b></div>
        <div style="text-align:center; font-size:{label_size};">✅ 완료<br><b style="font-size:{number_size}; color:#4CAF50;">{done}</b></div>
    </div>
""",
    unsafe_allow_html=True,
)

if upper_task_progress:
    avg_progress = int(sum(upper_task_progress.values()) / len(upper_task_progress))
    with st.expander(f"📊 상위 작업 진행률 (평균: {avg_progress}%)", expanded=False):
        gauge_cols = st.columns(min(len(upper_task_progress), 4))
        for idx, (upper_name, progress) in enumerate(upper_task_progress.items()):
            progress_int = int(progress)
            col_idx = idx % len(gauge_cols)
            with gauge_cols[col_idx]:
                st.caption(f"📂 {upper_name}")
                st.progress(progress_int / 100, text=f"{progress_int}%")

tab_sheet, tab_items = st.tabs(["📊 작업 현황", "📦 물품 견적"])

# --- Tab 1: Task list ---
with tab_sheet:
    if not df_task.empty:
        if is_mobile:
            st.markdown(
                """
            <style>
            [data-testid="stExpander"] [data-testid="stTextInput"] { margin-top: 0px; margin-bottom: 10px; }
            [data-testid="stTextInput"] > div > div > input { font-size: 0.9em; padding: 0.35rem 0.5rem; }
            [data-testid="stTextInput"] > label { font-size: 0.9em; }
            [data-testid="stMultiSelect"] > div, [data-testid="stMultiSelect"] > label, [data-testid="stMultiSelect"] span { font-size: 0.9em; }
            </style>
            """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
            <style>
            [data-testid="stTextInput"] { margin-top: -20px; margin-bottom: -10px; }
            [data-testid="stTextInput"] > div > div > input { font-size: 0.9em; padding: 0.35rem 0.5rem; }
            [data-testid="stTextInput"] > label { font-size: 0.9em; }
            [data-testid="stMultiSelect"] > div, [data-testid="stMultiSelect"] > label, [data-testid="stMultiSelect"] span { font-size: 0.9em; }
            </style>
            """,
                unsafe_allow_html=True,
            )

        if "상위 작업" in df_task.columns:
            all_upper = [
                s
                for s in df_task["상위 작업"].unique()
                if s and str(s).strip() not in ["", "None", "nan", "없음"]
            ]
        else:
            all_upper = []
        if "상태" in df_task.columns:
            all_statuses = [
                s
                for s in df_task["상태"].unique()
                if s and str(s).strip() not in ["", "None", "nan", "없음"]
            ]
        else:
            all_statuses = []

        if is_mobile:
            with st.expander("🔍 검색 및 필터", expanded=False):
                search_query = st.text_input(
                    "🔍 작업 검색", placeholder="작업명을 입력하세요...", key="task_search"
                )
                selected_upper = st.multiselect(
                    "📂 상위 작업", all_upper, default=list(all_upper), key="filter_upper", placeholder="필터 선택"
                )
                selected_status = st.multiselect(
                    "🏷️ 상태", all_statuses, default=list(all_statuses), key="filter_status", placeholder="필터 선택"
                )
        else:
            col_search, _ = st.columns([1, 1])
            with col_search:
                search_query = st.text_input(
                    "🔍 작업 검색", placeholder="작업명을 입력하세요...", key="task_search"
                )
            col_upper, col_status = st.columns([1, 1])
            with col_upper:
                selected_upper = st.multiselect(
                    "📂 상위 작업", all_upper, default=list(all_upper), key="filter_upper", placeholder="필터 선택"
                )
            with col_status:
                selected_status = st.multiselect(
                    "🏷️ 상태", all_statuses, default=list(all_statuses), key="filter_status", placeholder="필터 선택"
                )

        df_view = df_task.copy()
        if "상위 작업" in df_view.columns and selected_upper:
            df_view = df_view[df_view["상위 작업"].isin(selected_upper)]
        if "상태" in df_view.columns and selected_status:
            df_view = df_view[df_view["상태"].isin(selected_status)]
        if search_query:
            mask = (
                df_view["하위 작업"].astype(str).str.contains(search_query, case=False, na=False)
                if "하위 작업" in df_view.columns
                else pd.Series([False] * len(df_view))
            )
            if "상위 작업" in df_view.columns:
                mask = mask | df_view["상위 작업"].astype(str).str.contains(
                    search_query, case=False, na=False
                )
            if "비고" in df_view.columns:
                mask = mask | df_view["비고"].astype(str).str.contains(
                    search_query, case=False, na=False
                )
            df_view = df_view[mask]

        if not df_view.empty:
            df_view = df_view.reset_index(drop=True)
            if "진행률" in df_view.columns:
                df_view["진행률_바"] = df_view["진행률"].apply(
                    lambda x: float(str(x).replace("%", "").strip())
                    if pd.notna(x)
                    and str(x).replace("%", "").strip().replace(".", "").isdigit()
                    else 0
                )
            col_config = {}
            if "상태" in df_view.columns:
                col_config["상태"] = st.column_config.SelectboxColumn(
                    "상태",
                    help="클릭하여 상태를 빠르게 변경하세요",
                    options=STATUS_OPTIONS,
                    required=True,
                )
            if "진행률_바" in df_view.columns:
                col_config["진행률_바"] = st.column_config.ProgressColumn(
                    "진행률", help="진행률 바 (0% ~ 100%)", min_value=0, max_value=100, format="%d%%"
                )
                col_config["진행률"] = None
            edited_df = st.data_editor(
                df_view,
                use_container_width=True,
                height=600,
                column_config=col_config,
                disabled=[c for c in df_view.columns if c != "상태"],
                hide_index=True,
                key="task_editor",
            )
            if "상태" in df_view.columns and "하위 작업" in df_view.columns:
                for idx in range(len(df_view)):
                    old_status = df_view.at[idx, "상태"]
                    new_status = edited_df.at[idx, "상태"]
                    if old_status != new_status:
                        task_name = df_view.at[idx, "하위 작업"]
                        ok, err = update_cell_by_target("작업", task_name, "상태", new_status)
                        if ok:
                            st.toast(f"✅ '{task_name}' 상태가 '{new_status}'로 변경되었습니다!", icon="🔄")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"상태 변경 실패: {err}")
            st.caption("💡 상태를 클릭하면 드롭다운으로 빠르게 변경할 수 있습니다!")
        else:
            st.warning("검색 결과가 없습니다.")
    else:
        st.info("작업 리스트가 비어있습니다.")

# --- Tab 2: Items ---
with tab_items:
    if not df_items.empty:
        st.markdown(
            """
        <style>
        [data-testid="stTextInput"] { margin-top: -20px; margin-bottom: -10px; }
        [data-testid="stTextInput"] > div > div > input { font-size: 0.9em; padding: 0.35rem 0.5rem; }
        [data-testid="stTextInput"] > label { font-size: 0.9em; }
        [data-testid="stMultiSelect"] > div, [data-testid="stMultiSelect"] > label, [data-testid="stMultiSelect"] span { font-size: 0.9em; }
        </style>
        """,
            unsafe_allow_html=True,
        )
        search_item = st.text_input(
            "📦 물품 검색", placeholder="품목명, 비고 등을 입력하세요...", key="item_search_input"
        )
        filter_col = next(
            (c for c in ["상태", "구분", "구매상태", "Status"] if c in df_items.columns),
            None,
        )
        if filter_col:
            all_opts = [
                s
                for s in df_items[filter_col].unique()
                if s and str(s).strip() not in ["", "None", "nan", "없음", "-"]
            ]
            selected_opts = st.multiselect(
                f"🏷️ {filter_col} 필터",
                all_opts,
                default=all_opts,
                key="item_filter_unique",
                placeholder="필터 선택",
            )
        else:
            selected_opts = []
        df_display = df_items.copy()
        if filter_col and selected_opts:
            df_display = df_display[df_display[filter_col].isin(selected_opts)]
        if search_item:
            mask = df_display.iloc[:, 0].astype(str).str.contains(
                search_item, case=False, na=False
            )
            if "비고" in df_display.columns:
                mask = mask | df_display["비고"].astype(str).str.contains(
                    search_item, case=False, na=False
                )
            df_display = df_display[mask]
        if "구매 링크" not in df_display.columns:
            df_display["구매 링크"] = None
        if "비고" in df_display.columns:
            for i, row in df_display.iterrows():
                val = str(row["비고"])
                if val.startswith("http"):
                    df_display.at[i, "구매 링크"] = val
                    df_display.at[i, "비고"] = "-"
        if not df_display.empty:
            st.dataframe(
                df_display,
                use_container_width=True,
                height=400,
                column_config={
                    "구매 링크": st.column_config.LinkColumn("링크", display_text="🔗 구매")
                },
            )
        else:
            st.warning("조건에 맞는 물품이 없습니다.")
        cost_cols = [
            c for c in df_items.columns if any(k in c for k in ["금액", "가격", "비용"])
        ]
        if cost_cols:
            current_cost = df_display[cost_cols[0]].sum()
            st.markdown(
                f"""
                <div style="text-align: center; padding: 20px; background-color: rgba(0, 200, 100, 0.1); border: 1px solid rgba(0, 200, 100, 0.3); border-radius: 15px; margin-top: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <span style="font-size: 1.3em; font-weight: bold; color: #555; margin-right: 10px;">💰 견적 합계:</span>
                    <span style="font-size: 2.0em; color: #2ecc71; font-weight: bold;">{int(current_cost):,}원</span>
                </div>
            """,
                unsafe_allow_html=True,
            )
    else:
        st.info("물품 리스트가 비어있습니다.")

# --- AI response dialog ---
@st.dialog("📊 AI 응답", width="large")
def show_ai_response(response_text):
    st.markdown(response_text)
    if st.button("닫기", use_container_width=True):
        st.session_state.last_ai_response = None
        st.rerun()

if st.session_state.last_ai_response:
    show_ai_response(st.session_state.last_ai_response)
    st.session_state.last_ai_response = None

# --- Chat input ---
if prompt := st.chat_input(
    "💬 AI에게 명령하기 (예: '소프트웨어 개발 진행률 50%로 변경해줘')"
):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.toast(f"📝 {prompt}", icon="👤")
    if model is None:
        msg = "⚠️ API 키가 설정되지 않아 AI 명령을 처리할 수 없습니다."
        st.session_state.messages.append({"role": "assistant", "content": msg})
        st.toast(msg, icon="⚠️")
    else:
        handle_ai_command(prompt, model, df_task, df_items)
