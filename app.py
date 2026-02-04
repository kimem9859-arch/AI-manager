import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import time

# ----------------------------------------------------------
# 1. 초기 설정 & 스타일 (채팅창 고정 CSS 포함)
# ----------------------------------------------------------
st.set_page_config(page_title="AI 프로젝트 매니저", page_icon="🤖", layout="wide")

st.markdown("""
<style>
    /* 전체 레이아웃 고정 */
    .stApp { height: 100vh; overflow: hidden; }
    
    /* 선택창(Selectbox) 스타일 */
    div[data-baseweb="select"] > div {
        border-color: #ff4b4b !important;
        background-color: #262730;
    }
    
    /* 폼 버튼 너비 꽉 차게 */
    div.stButton > button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# 2. 필수 함수 (구글 시트, Gemini)
# ----------------------------------------------------------
# 세션 상태 초기화
if "messages" not in st.session_state: st.session_state.messages = []
if "cmd_mode" not in st.session_state: st.session_state.cmd_mode = None
if "selected_cmd" not in st.session_state: st.session_state.selected_cmd = None

# [기능] 되돌리기
def undo_last_chat():
    if len(st.session_state.messages) >= 2:
        st.session_state.messages.pop()
        st.session_state.messages.pop()
        st.toast("↩️ 취소 완료!", icon="🗑️")
        time.sleep(0.5)
        st.rerun()

# [기능] 구글 시트 연결
def get_spreadsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except:
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client.open("Safety_Project") 

# [기능] 데이터 로딩
@st.cache_data(ttl=5)
def load_data_safe(sheet_name):
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(sheet_name)
        all_values = ws.get_all_values()
        if not all_values: return pd.DataFrame()
        header_idx = 0
        for i, row in enumerate(all_values[:5]):
            if len([x for x in row if x.strip()]) >= 2:
                header_idx = i; break
        headers = all_values[header_idx]
        data = all_values[header_idx+1:]
        return pd.DataFrame(data, columns=headers)
    except: return pd.DataFrame()

# [기능] 시트 업데이트
def update_sheet_any(sheet_name, row_data):
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        ws.append_row(row_data)
        st.cache_data.clear()
        return True
    except: return False

# [기능] 공지 관리
def get_notice():
    try:
        client = get_spreadsheet()
        try: ws = client.worksheet("공지")
        except: 
            ws = client.add_worksheet("공지", 5, 2)
            ws.update_cell(1, 1, "공지없음")
        val = ws.cell(1, 1).value
        return val if val else "공지없음"
    except: return "-"

def update_notice(text):
    try:
        client = get_spreadsheet()
        try: ws = client.worksheet("공지")
        except: ws = client.add_worksheet("공지", 5, 2)
        ws.update_cell(1, 1, text)
        return True
    except: return False

# Gemini 설정
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-pro')

# ----------------------------------------------------------
# 3. 데이터 준비
# ----------------------------------------------------------
df_task = load_data_safe("작업")
if not df_task.empty and '상태' in df_task.columns:
    total = len(df_task)
    done = len(df_task[df_task['상태']=='완료'])
    pending = len(df_task[df_task['상태']=='대기'])
else: total, done, pending = 0, 0, 0

df_items = load_data_safe("물품")
if not df_items.empty:
    df_items = df_items.fillna("-")
    for col in df_items.columns:
        if any(k in col for k in ['금액', '가격', '비용']):
            df_items[col] = (df_items[col].astype(str).str.replace(',', '').str.replace('원', '').apply(pd.to_numeric, errors='coerce').fillna(0))

# ----------------------------------------------------------
# 4. 화면 UI 구성
# ----------------------------------------------------------
st.title("🤖 AI 프로젝트 매니저")

# [사이드바]
with st.sidebar:
    st.header("⚙️ 설정")
    is_mobile = st.checkbox("📱 모바일 모드", value=False)
    st.divider()
    if st.button("🔄 새로고침", use_container_width=True): st.rerun()

# [상단 통계]
st.markdown(f"""
    <div style="display:flex; justify-content:space-around; background-color:rgba(100,100,100,0.1); padding:10px; border-radius:10px; margin-bottom:10px; border:1px solid rgba(255,255,255,0.1);">
        <div style="text-align:center;">📌 전체<br><b>{total}</b></div>
        <div style="text-align:center;">✅ 완료<br><b style="color:#4CAF50;">{done}</b></div>
        <div style="text-align:center;">⏳ 대기<br><b style="color:#FF9800;">{pending}</b></div>
    </div>
""", unsafe_allow_html=True)

# [메인 레이아웃 분할]
if is_mobile:
    tab1, tab2, tab3 = st.tabs(["💬 채팅", "📊 작업", "📦 물품"])
    c_chat, c_sheet, c_items = tab1, tab2, tab3
else:
    col1, col2 = st.columns([1, 1.3])
    c_chat = col1
    with col2:
        sub1, sub2 = st.tabs(["📊 작업 현황", "📦 물품 견적"])
        c_sheet, c_items = sub1, sub2

# --- [탭 1] 작업 리스트 ---
with c_sheet:
    if not df_task.empty:
        col_s, col_f = st.columns([1,1])
        with col_s: search_q = st.text_input("🔍 검색", placeholder="작업명...")
        with col_f: 
            stats = df_task['상태'].unique() if '상태' in df_task.columns else []
            sel_stat = st.multiselect("🏷️ 필터", stats, default=stats)
        
        df_v = df_task.copy()
        if '상태' in df_v.columns and sel_stat: df_v = df_v[df_v['상태'].isin(sel_stat)]
        if search_q: df_v = df_v[df_v.iloc[:, 0].astype(str).str.contains(search_q, case=False, na=False)]
        
        def color_map(val):
            if pd.isna(val) or str(val) in ["", "-"]: return None
            try:
                n = float(str(val).replace('%',''))
                n = max(0, min(100, n))
                if n < 50: r,g,b = 255, int(255*(n/50)), 0
                else: r,g,b = int(255*((100-n)/50)), 255, 0
                return f'background-color: rgb({r},{g},{b}); color: black;'
            except: return None

        st.dataframe(df_v.style.map(color_map, subset=['진행률']) if '진행률' in df_v.columns else df_v, use_container_width=True, height=500)
    else: st.info("데이터 없음")

# --- [탭 2] 물품 리스트 ---
with c_items:
    if not df_items.empty:
        df_d = df_items.copy()
        if "구매 링크" not in df_d.columns: df_d["구매 링크"] = None
        if "비고" in df_d.columns:
            for i, r in df_d.iterrows():
                if str(r["비고"]).startswith("http"):
                    df_d.at[i, "구매 링크"] = r["비고"]; df_d.at[i, "비고"] = "-"
        st.dataframe(df_d, use_container_width=True, height=400, column_config={"구매 링크": st.column_config.LinkColumn("링크", display_text="🔗 구매")})
        
        cost_cols = [c for c in df_items.columns if any(k in c for k in ['금액', '가격', '비용'])]
        if cost_cols:
            st.markdown(f"<div style='text-align:center; font-size:1.5em; color:#2ecc71; font-weight:bold;'>💰 합계: {int(df_d[cost_cols[0]].sum()):,}원</div>", unsafe_allow_html=True)
    else: st.info("데이터 없음")

# --- [탭 3] 채팅 및 AI (고정형 UI 적용) ---
with c_chat:
    # 1. 공지 & 되돌리기
    notice = get_notice()
    if notice != "-": st.info(f"📢 {notice}")
    
    if st.button("↩️ 되돌리기", use_container_width=True): undo_last_chat()

    # 2. [핵심] 채팅 내역 고정창 (높이 고정으로 스크롤 생성)
    # messages_container 안에 모든 대화를 넣어서, 입력창이 밀려나지 않게 함
    messages_container = st.container(height=500)
    with messages_container:
        for m in st.session_state.messages:
            st.chat_message(m["role"]).write(m["content"])
    
    # 3. [핵심] 명령어 UI & 입력창
    # 명령어 모드일 때만 입력창 위에 '선택창'이 뜸
    if st.session_state.cmd_mode == 'select':
        with st.container():
            st.info("⬇️ 화살표(↑↓)로 명령어를 선택하고 엔터를 누르세요.")
            cmd_opts = ["➕ 작업 추가", "🗑️ 작업 삭제", "✅ 작업 완료", "📢 공지 변경", "🔙 취소"]
            # key를 주어 상태 유지
            selected = st.selectbox("명령어", cmd_opts, label_visibility="collapsed", key="cmd_selector")
            
            col_btn1, col_btn2 = st.columns([3, 1])
            if col_btn1.button("✅ 선택 (Enter)", key="btn_select", use_container_width=True):
                if "취소" in selected:
                    st.session_state.cmd_mode = None
                    st.rerun()
                else:
                    st.session_state.selected_cmd = selected
                    st.session_state.cmd_mode = 'input'
                    st.rerun()
            if col_btn2.button("취소", key="btn_cancel", use_container_width=True):
                st.session_state.cmd_mode = None
                st.rerun()

    elif st.session_state.cmd_mode == 'input':
        cmd_name = st.session_state.selected_cmd
        placeholder_map = {
            "추가": "작업명 (예: 라즈베리파이 세팅)",
            "삭제": "삭제할 작업명",
            "완료": "완료한 작업명",
            "공지": "새로운 공지 내용"
        }
        ph = next((v for k, v in placeholder_map.items() if k in cmd_name), "내용 입력")
        
        with st.container():
            st.markdown(f"**{cmd_name}** > 내용을 입력하세요:")
            # form을 사용하여 엔터로 제출 가능하게 함
            with st.form("cmd_input_form", clear_on_submit=True):
                detail_input = st.text_input("내용", placeholder=ph, label_visibility="collapsed")
                if st.form_submit_button("🚀 실행 (Enter)"):
                    if detail_input:
                        res_msg = ""
                        try:
                            if "추가" in cmd_name:
                                update_sheet_any("작업", [detail_input, "0%", "", "대기", ""])
                                res_msg = f"✅ 추가됨: {detail_input}"
                            elif "삭제" in cmd_name:
                                client = get_spreadsheet(); ws = client.worksheet("작업")
                                cell = ws.find(detail_input); ws.delete_rows(cell.row)
                                res_msg = f"🗑️ 삭제됨: {detail_input}"
                            elif "완료" in cmd_name:
                                client = get_spreadsheet(); ws = client.worksheet("작업")
                                cell = ws.find(detail_input)
                                h = ws.row_values(1)
                                c_idx = next((i+1 for i,v in enumerate(h) if "진행" in v), 6)
                                ws.update_cell(cell.row, c_idx, "100%")
                                res_msg = f"✅ 완료처리: {detail_input}"
                            elif "공지" in cmd_name:
                                update_notice(detail_input)
                                res_msg = f"📢 공지변경: {detail_input}"
                        except: res_msg = f"⚠️ 오류: '{detail_input}' 처리 실패"
                        
                        st.session_state.messages.append({"role": "assistant", "content": res_msg})
                        st.session_state.cmd_mode = None
                        st.rerun()
                    else: st.warning("내용을 입력해주세요.")

    # 4. 기본 채팅 입력창 (항상 맨 아래 고정)
    if st.session_state.cmd_mode is None:
        if prompt := st.chat_input("명령 또는 질문 (/ 입력 후 엔터로 메뉴 열기)"):
            if prompt.strip() == "/":
                st.session_state.cmd_mode = 'select'
                st.rerun()
            
            st.session_state.messages.append({"role": "user", "content": prompt})
            with messages_container:
                st.chat_message("user").write(prompt)

            # AI 처리 로직
            if not df_task.empty:
                cols = [c for c in df_task.columns if c in ['작업명', '진행률', '상태']]
                task_str = df_task[cols].to_string(index=False)
            else: task_str = "비어있음"

            sys_msg = f"""
            당신은 구글 시트 데이터베이스 관리자입니다. JSON 리스트만 출력하세요.
            [데이터] {task_str}
            [규칙] 1. 설명금지 2. "완료"는 100% update (삭제금지) 3. 시트에 있는 단어만 사용
            [포맷] [{{"action": "add", "sheet": "작업", "row": ["내용", "0%", "", "대기", ""]}}]
            """
            try:
                res = model.generate_content(sys_msg + f"\n요청: {prompt}")
                import re
                txt = res.text.replace("```json","").replace("```","").strip()
                match = re.search(r'\[.*\]', txt, re.DOTALL)
                cmds = json.loads(match.group()) if match else []
                if not cmds:
                    m2 = re.search(r'\{.*\}', txt, re.DOTALL)
                    if m2: cmds = [json.loads(m2.group())]

                log = []
                for c in cmds:
                    act = c.get("action")
                    if act == "add": 
                        update_sheet_any("작업", c.get("row"))
                        log.append("✅ 추가됨")
                    elif act == "update":
                        t, v = c.get("target"), c.get("value")
                        if "%" not in v: v+="%"
                        try:
                            cli = get_spreadsheet(); ws = cli.worksheet("작업")
                            cell = ws.find(t)
                            h = ws.row_values(1)
                            idx = next((i+1 for i,x in enumerate(h) if "진행" in x), 6)
                            ws.update_cell(cell.row, idx, v)
                            log.append(f"📈 {t}→{v}")
                        except: log.append(f"⚠️ {t} 못찾음")
                    elif act == "delete":
                        try:
                            cli = get_spreadsheet(); ws = cli.worksheet("작업")
                            cell = ws.find(c.get("target")); ws.delete_rows(cell.row)
                            log.append("🗑️ 삭제됨")
                        except: log.append("⚠️ 삭제실패")
                    elif act == "notice":
                        update_notice(c.get("content"))
                        log.append("📢 공지변경")
                
                final_msg = " / ".join(log) if log else "🤖 명령 이해 불가"
                st.session_state.messages.append({"role": "assistant", "content": final_msg})
                st.rerun()
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"오류: {e}"})
                st.rerun()