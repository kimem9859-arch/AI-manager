"""Google Sheet: connect, load/update data, notice, delete/update cells."""
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials


def get_spreadsheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "service_account.json", scope
        )
    client = gspread.authorize(creds)
    return client.open("Safety_Project")


def load_data_safe(sheet_name):
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(sheet_name)
        all_values = ws.get_all_values()
        if not all_values:
            return pd.DataFrame()

        header_idx = 0
        for i, row in enumerate(all_values[:5]):
            if len([x for x in row if x.strip()]) >= 2:
                header_idx = i
                break

        headers = all_values[header_idx]
        data = all_values[header_idx + 1 :]
        return pd.DataFrame(data, columns=headers)
    except Exception as e:
        st.error(f"❌ '{sheet_name}' 시트 로딩 실패: {e}")
        return pd.DataFrame()


def update_sheet_any(sheet_name, row_data):
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        ws.append_row(row_data)
        return True
    except Exception:
        return False


def get_notice():
    try:
        client = get_spreadsheet()
        try:
            ws = client.worksheet("공지")
        except Exception:
            ws = client.add_worksheet("공지", 5, 2)
            ws.update_cell(1, 1, "공지없음")
        val = ws.cell(1, 1).value
        return val if val else "공지없음"
    except Exception:
        return "공지 연결 실패"


def update_notice(text):
    try:
        client = get_spreadsheet()
        try:
            ws = client.worksheet("공지")
        except Exception:
            ws = client.add_worksheet("공지", 5, 2)
        ws.update_cell(1, 1, text)
        return True
    except Exception:
        return False


def delete_row_by_target(sheet_name, target):
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        cell = ws.find(target)
        ws.delete_rows(cell.row)
        return True, None
    except Exception as e:
        return False, str(e)


def update_cell_by_target(sheet_name, target, column_keyword, new_value):
    """Update a cell by task/item name. column_keyword: e.g. '진행', '상태', '비고'."""
    try:
        client = get_spreadsheet()
        ws = client.worksheet(sheet_name)
        cell = ws.find(target)
        if not cell:
            return False, f"'{target}'을(를) 찾을 수 없습니다."

        headers = ws.row_values(1)
        col_idx = None
        for i, h in enumerate(headers):
            if column_keyword in h:
                col_idx = i + 1
                break
        if col_idx is None:
            return False, f"'{column_keyword}' 열을 찾을 수 없습니다."

        ws.update_cell(cell.row, col_idx, new_value)
        return True, None
    except Exception as e:
        return False, str(e)


def clear_cell_by_target(sheet_name, target, column_keyword):
    return update_cell_by_target(sheet_name, target, column_keyword, "")


def update_status_quick(sheet_name, target, new_status):
    return update_cell_by_target(sheet_name, target, "상태", new_status)
