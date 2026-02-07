"""AI command handler: load prompt from file, call Gemini, parse JSON, execute actions."""
import json
import os
import time
import streamlit as st
from .config import STATUS_OPTIONS
from .spreadsheet import (
    update_sheet_any,
    get_notice,
    update_notice,
    delete_row_by_target,
    update_cell_by_target,
    clear_cell_by_target,
)


PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "prompts", "ai_system_prompt.txt"
)


def load_system_prompt(task_headers, task_full_data, items_full_data):
    """Load prompt template and fill placeholders."""
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    return template.format(
        task_headers=task_headers,
        task_full_data=task_full_data,
        items_full_data=items_full_data,
    )


def handle_ai_command(prompt, model, df_task, df_items):
    """
    Process user prompt: build system message, call model, parse JSON, execute action.
    Updates st.session_state and may call st.rerun(). Returns None.
    """
    task_headers = (
        df_task.columns.tolist()
        if not df_task.empty
        else ["상위 작업", "하위 작업", "상태", "비고", "진행률"]
    )
    task_full_data = df_task.to_string(index=False) if not df_task.empty else "작업 데이터 없음"
    items_full_data = df_items.to_string(index=False) if not df_items.empty else "물품 데이터 없음"

    sys_msg = load_system_prompt(task_headers, task_full_data, items_full_data)
    full_request = sys_msg + f"\n사용자 요청: {prompt}"

    try:
        response = model.generate_content(full_request)
        text_res = response.text.strip().replace("```json", "").replace("```", "")
        cmd = json.loads(text_res)
        action = cmd.get("action")

        # [1] Add task
        if action == "add":
            sheet_name = cmd.get("sheet", "작업")
            row_vals = cmd.get("row") or []
            if not isinstance(row_vals, list):
                row_vals = [str(row_vals)]
            if sheet_name == "작업" and not df_task.empty:
                n_cols = len(df_task.columns)
                row_vals = [str(v) if v is not None else "" for v in row_vals[:n_cols]]
                row_vals += [""] * (n_cols - len(row_vals))
            update_sheet_any(sheet_name, row_vals)
            upper_name = row_vals[0] if len(row_vals) > 0 else ""
            lower_name = row_vals[1] if len(row_vals) > 1 else ""
            msg = f"✅ '{upper_name} > {lower_name}' 작업이 추가되었습니다."
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.toast(msg, icon="✅")
            time.sleep(1)
            st.rerun()

        # [2] Update progress (and update_status for first time from 0%)
        elif action in ("update", "update_progress"):
            target = cmd.get("target")
            val = cmd.get("value", "0%")
            if "%" not in str(val):
                val = str(val) + "%"
            try:
                progress_num = float(str(val).replace("%", "").strip())
            except Exception:
                progress_num = 0

            current_progress = 0
            if (
                not df_task.empty
                and "진행률" in df_task.columns
                and "하위 작업" in df_task.columns
            ):
                task_row = df_task[df_task["하위 작업"] == target]
                if not task_row.empty:
                    try:
                        current_val = (
                            str(task_row["진행률"].values[0]).replace("%", "").strip()
                        )
                        current_progress = float(current_val) if current_val else 0
                    except Exception:
                        current_progress = 0

            ok, err = update_cell_by_target("작업", target, "진행", val)
            if ok:
                msg = f"📈 '{target}' 진행률을 {val}로 변경했습니다."
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

        # [3] Update status
        elif action == "update_status":
            target = cmd.get("target")
            val = cmd.get("value", "대기/보류")
            status_map = {
                "대기": "대기/보류",
                "보류": "대기/보류",
                "대기/보류": "대기/보류",
                "진행": "진행",
                "진행중": "진행",
                "수정": "수정/검토",
                "검토": "수정/검토",
                "수정/검토": "수정/검토",
                "완료": "완료",
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
                st.toast(f"😅 '{target}' 작업을 찾을 수 없습니다.", icon="😅")

        # [4] Update remark
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
                st.toast(f"😅 '{target}' 작업을 찾을 수 없습니다.", icon="😅")

        # [5] Clear cell (e.g. remark)
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
                st.toast(
                    f"😅 '{target}' 작업 또는 '{column}' 열을 찾을 수 없습니다.",
                    icon="😅",
                )

        # [6] Notice
        elif action == "notice":
            content = cmd.get("content")
            if update_notice(content):
                msg = f"📢 공지사항이 업데이트 되었습니다: {content}"
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.toast(msg, icon="📢")
                time.sleep(1)
                st.rerun()
            else:
                st.toast("❌ 공지사항 업데이트에 실패했습니다.", icon="❌")

        # [7] Delete
        elif action == "delete":
            sheet_name = cmd.get("sheet", "작업")
            target = cmd.get("target")
            if not target:
                st.toast("❌ 삭제할 항목 이름이 없습니다.", icon="❌")
            else:
                ok, err = delete_row_by_target(sheet_name, target)
                if ok:
                    msg = f"🗑️ '{target}' 항목을 삭제했습니다."
                    st.session_state.messages.append(
                        {"role": "assistant", "content": msg}
                    )
                    st.toast(msg, icon="🗑️")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.toast(
                        f"😅 '{target}' 항목을 찾을 수 없거나 삭제에 실패했습니다.",
                        icon="😅",
                    )

        # [8] Summary (show in dialog)
        elif action == "summary":
            msg = cmd.get("response", "요약 정보를 가져올 수 없습니다.")
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.session_state.last_ai_response = f"📊 {msg}"
            st.rerun()

        # [9] Chat / other
        else:
            msg = cmd.get("response", "명령을 이해하지 못했습니다.")
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.toast(f"🤖 {msg}", icon="💬")

    except Exception as e:
        msg = f"오류가 발생했습니다: {e}"
        st.session_state.messages.append({"role": "assistant", "content": msg})
        st.toast(msg, icon="❌")
