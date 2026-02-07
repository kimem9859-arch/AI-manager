"""User guide dialog."""
import streamlit as st


@st.dialog("📖 사용 설명서", width="large")
def show_guide():
    st.markdown("## 👋 AI 프로젝트 매니저 사용법")
    st.divider()

    tab1, tab2, tab3 = st.tabs(["💬 채팅 명령어", "📊 작업 관리", "📦 기타 기능"])

    with tab1:
        st.markdown("### 🗣️ AI에게 명령하기")
        st.info("하단 입력창에 명령을 입력하세요! 결과는 팝업으로 표시됩니다.")

        st.markdown("#### ➕ 작업 추가/삭제 (상위/하위 작업 계층 지원)")
        st.code(
            '"프로젝트 개발에 UI 설계 추가해줘"  →  상위: 프로젝트 개발, 하위: UI 설계',
            language=None,
        )
        st.code('"인프라 구축에 DB 설정 추가해줘"', language=None)
        st.code('"소프트웨어 개발 삭제해줘"  →  하위 작업 기준으로 삭제', language=None)

        st.markdown("#### 📈 진행률/상태 변경")
        st.code('"소프트웨어 개발 진행률 50%로 변경해줘"', language=None)
        st.code('"하드웨어 개발 상태 진행으로 바꿔줘"', language=None)

        st.markdown("#### 📝 비고 변경")
        st.code("'서버 구축 비고에 \\'담당자: 홍길동\\' 넣어줘'", language=None)
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
        st.markdown(
            """
        - **상위 작업 필터**: 프로젝트 개발, 인프라 구축 등 대분류 선택
        - **하위 작업 필터**: 선택된 상위 작업에 속한 하위 작업만 표시 (종속형)
        - **상태 필터**: 대기/보류, 진행, 수정/검토, 완료
        """
        )
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 🔄 상태 빠른 변경")
            st.success("상태 셀 클릭 → 드롭다운 선택")
        with col2:
            st.markdown("#### 📊 상태 옵션")
            st.markdown(
                """
            - ⏳ 대기/보류
            - 🔄 진행
            - 🔍 수정/검토
            - ✅ 완료
            """
            )
        st.divider()
        st.markdown("#### 📈 진행률 게이지 바")
        st.markdown("상단에 상위 작업별 평균 진행률이 표시됩니다.")

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 📦 물품 견적")
            st.markdown(
                """
            - 💰 총 비용 자동 계산
            - 🔗 구매 링크 버튼
            """
            )
        with col2:
            st.markdown("### ⚡ 편의 기능")
            st.markdown(
                """
            - 🔄 **자동 새로고침**: 데이터 변경 시 즉시 반영
            - 💬 **AI 응답**: 팝업(Toast)으로 빠르게 확인
            """
            )
