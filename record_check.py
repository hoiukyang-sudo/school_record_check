import streamlit as st
import pandas as pd
import re
from collections import Counter
import html 

# --- CSS 스타일 ---
st.markdown("""
<style>
.error-highlight {
    color: red;
    font-weight: bold;
    background-color: #ffe0e0;
    padding: 2px 4px;
    border-radius: 4px;
}
.sentence-error-highlight {
    color: #0056b3; /* 어두운 파란색 */
    font-weight: bold;
    background-color: #e0f0ff; /* 밝은 파란색 */
    padding: 2px 4px;
    border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)

# --- 오류 검사 함수 ---

def find_regex_errors(text, patterns):
    """정규식 패턴에 맞는 오류를 찾아 (start, end) 인덱스와 오류 메시지를 반환"""
    errors_found = []
    all_matches = [] # (start, end) 튜플 저장

    # 1. 원본 텍스트에서 모든 오류 위치 찾기
    for error_type, pattern, message in patterns:
        # re.IGNORECASE: 영어 대소문자 구분 없이 검사
        for match in re.finditer(pattern, text, re.IGNORECASE):
            all_matches.append((match.start(), match.end()))
            if message not in errors_found:
                errors_found.append(message)
    
    return all_matches, list(set(errors_found)) # 중복 제거

def apply_merged_highlights(text, red_matches, blue_matches):
    """
    빨간색(단어)과 파란색(문장) 하이라이트 위치를 받아 HTML 태그를 적용합니다.
    겹치는 구간은 빨간색을 우선으로 하고, 나머지 오류 문장 구간은 파란색으로 표시합니다.
    """
    # 1. 모든 경계 지점 수집 (0, 끝, 각 매칭의 시작/끝)
    boundaries = {0, len(text)}
    for s, e in red_matches:
        boundaries.add(s)
        boundaries.add(e)
    for s, e in blue_matches:
        boundaries.add(s)
        boundaries.add(e)
    
    # 경계 지점 정렬
    sorted_boundaries = sorted(list(boundaries))
    
    final_html_parts = []
    
    # 2. 각 구간별로 스타일 적용 (Atomic Segments)
    for i in range(len(sorted_boundaries) - 1):
        start = sorted_boundaries[i]
        end = sorted_boundaries[i+1]
        segment_text = text[start:end]
        
        if not segment_text: continue
        
        # 현재 구간이 빨간색 범위에 포함되는지 확인
        is_red = False
        for s, e in red_matches:
            if s <= start and end <= e:
                is_red = True
                break
        
        # 현재 구간이 파란색 범위에 포함되는지 확인
        is_blue = False
        for s, e in blue_matches:
            if s <= start and end <= e:
                is_blue = True
                break
        
        escaped_text = html.escape(segment_text)
        
        if is_red:
            # 빨간색과 파란색이 겹치면 빨간색 우선
            final_html_parts.append(f'<span class="error-highlight">{escaped_text}</span>')
        elif is_blue:
            # 파란색만 있는 구간
            final_html_parts.append(f'<span class="sentence-error-highlight">{escaped_text}</span>')
        else:
            # 아무것도 없는 구간
            final_html_parts.append(escaped_text)
            
    return "".join(final_html_parts)

def check_duplicate_sentences(text):
    """셀 내 중복 문장을 검사하고, 중복된 문장의 (start, end) 인덱스 리스트를 반환"""
    if not text or pd.isna(text):
        return False, "", []
        
    # 마침표, 물음표, 느낌표로 문장 구분 (구분자도 포함하여 위치 찾기)
    sentence_matches = list(re.finditer(r'([^.!?]+[.!?])', text))
    
    # 정규식으로 나눠지지 않는 나머지 텍스트 처리
    last_match_end = 0
    if sentence_matches:
        last_match_end = sentence_matches[-1].end()
        
    remaining_text = text[last_match_end:].strip()
    if remaining_text:
        # 문장으로 취급할 수 있도록 가상의 (텍스트, 시작, 끝) 튜플 생성
        sentence_tuples = [(m.group(0).strip(), m.start(), m.end()) for m in sentence_matches]
        sentence_tuples.append((remaining_text, last_match_end, len(text)))
    else:
        sentence_tuples = [(m.group(0).strip(), m.start(), m.end()) for m in sentence_matches]

    clean_sentences = [s[0] for s in sentence_tuples if s[0]]

    if not clean_sentences or len(clean_sentences) < 2:
        return False, "", []

    sentence_counts = Counter(clean_sentences)
    dup_sentences_text = [s for s, c in sentence_counts.items() if c > 1]
    
    if not dup_sentences_text:
        return False, "", []
        
    matches = []
    # 원본 튜플 리스트에서 중복된 텍스트를 가진 항목의 (start, end)를 찾음
    for s_text, start, end in sentence_tuples:
        if s_text in dup_sentences_text:
            matches.append((start, end))
    
    if not matches:
         return False, "", []

    return True, "중복 문장 존재", matches

# --- Streamlit UI ---

def main():
    st.title("🏫 학교생활기록부 특기사항 검사기")
    st.info("엑셀 파일을 업로드하면 '특기사항'의 내용을 분석하여 오류를 검사합니다.")

    # 오류 검사 항목 정의 (유형, 정규식, 오류 메시지)
    ERROR_PATTERNS = [
        ("띄어쓰기 두번", r'  +', "띄어쓰기 두번"),
        ("특수 기호", r'[!@#$%^&*_=+[\]{};\'":\\|<>/?~`()·]', "특수 기호"),
        ("영어", r'[a-zA-Z]', "영어 포함"),
        ("1인칭", r'\b(나의|나만의|내( |가|는)|저의|저만의|제( |가|는))\b', "1인칭 표현"),
        ("과거형", r'(었|았|였)(다|습니다|어요|음)\b', "과거형 종결 어미")
    ]

    uploaded_file = st.file_uploader("엑셀 파일(.xlsx, .xls)을 업로드하세요.", type=["xlsx", "xls"])

    if uploaded_file:
        try:
            # 헤더 없이 일단 읽어와서 탐색
            raw_df = pd.read_excel(uploaded_file, sheet_name=0, header=None)
            
            header_row_idx = None
            
            # [수정] 0번 행부터 19번 행까지(엑셀 1행~20행) 탐색 (범위 확대)
            for i in range(min(20, len(raw_df))):
                # 행의 값들을 문자열로 변환하고, 줄바꿈 등을 제거하여 검사
                row_values = [str(val).replace('\n', ' ').replace('\r', '') for val in raw_df.iloc[i].values]
                if any("특기사항" in val for val in row_values):
                    header_row_idx = i
                    break
            
            if header_row_idx is None:
                st.error("상위 20개 행에서 '특기사항'이 포함된 행(헤더)을 찾을 수 없습니다. 파일 형식을 확인해주세요.")
                return

            # 찾은 행(header_row_idx)을 컬럼 이름으로 설정하여 데이터프레임 재구성
            sheet_df = raw_df.iloc[header_row_idx+1:].reset_index(drop=True)
            
            # [수정] 컬럼 이름 정제 (줄바꿈 제거 및 공백 정리)
            cleaned_columns = []
            for col in raw_df.iloc[header_row_idx]:
                col_str = str(col).replace('\n', ' ').replace('\r', '').strip()
                cleaned_columns.append(col_str)
            sheet_df.columns = cleaned_columns
            
            # 엑셀의 실제 행 번호 계산을 위한 오프셋
            excel_row_offset = header_row_idx + 2 

            columns = list(sheet_df.columns)
            
            # '특기사항'이 포함된 컬럼 자동 선택
            selected_columns = [col for col in columns if "특기사항" in str(col)]
            
            if not selected_columns:
                st.error("헤더 행은 찾았으나, '특기사항' 컬럼을 특정할 수 없습니다.")
                return
            else:
                st.success(f"검사 대상: {', '.join(selected_columns)}")

            if st.button("검사 시작", type="primary"):
                # '성명' 컬럼 자동 찾기
                id_column_name = None
                for col in columns:
                    if str(col) == "성명":
                        id_column_name = col
                        break

                with st.spinner("파일을 검사 중입니다..."):
                    
                    if id_column_name:
                        st.success(f"학생 '{id_column_name}'을 식별자로 사용합니다.")
                    else:
                        st.warning("'성명' 데이터(열)를 찾을 수 없습니다. 결과에 행 번호만 표시됩니다.")
                        
                    # 식별자 Series 생성
                    if id_column_name:
                        id_series = sheet_df[id_column_name].fillna("").astype(str)
                    else:
                        # 행 번호 계산 시 오프셋 적용
                        id_series = sheet_df.index.to_series().apply(lambda x: f"{x + excel_row_offset}번 행")

                    # '컬럼 내 중복 셀' 검사를 위한 데이터 준비
                    duplicate_masks = {}
                    duplicate_partners_map = {}
                    
                    for col_name in selected_columns:
                        all_texts = sheet_df[col_name].fillna("").astype(str)
                        # 중복 마스크
                        duplicate_masks[col_name] = all_texts.duplicated(keep=False) & (all_texts != "")
                        
                        # 중복 대상 매핑
                        grouped = sheet_df.groupby(all_texts)
                        col_key = col_name 
                        duplicate_partners_map[col_key] = {}
                        
                        for text_content, group in grouped:
                            if text_content == "" or len(group) < 2:
                                continue
                            
                            partners = id_series.loc[group.index].tolist()
                            for index in group.index:
                                current_id = id_series.loc[index]
                                other_partners = [p for p in partners if p != current_id]
                                duplicate_partners_map[col_key][index] = other_partners

                    results = []

                    # 모든 행 순회
                    for index, row in sheet_df.iterrows():
                        for col_name in selected_columns:
                            text = str(row[col_name]) if pd.notna(row[col_name]) else ""
                            if not text.strip():
                                continue

                            errors_found = []
                            red_matches = []  # 단어 오류 (빨강)
                            blue_matches = [] # 문장/셀 오류 (파랑)
                            
                            # 1. 정규식 오류 (빨강)
                            red_matches, regex_errors = find_regex_errors(text, ERROR_PATTERNS)
                            errors_found.extend(regex_errors)

                            # 2. 셀 내 중복 문장 (파랑)
                            has_dup_sentence, dup_sentence_msg, sentence_blue_matches = check_duplicate_sentences(text)
                            if has_dup_sentence:
                                errors_found.append(dup_sentence_msg)
                                blue_matches.extend(sentence_blue_matches)

                            # 3. 컬럼 내 중복 셀 (파랑)
                            is_dup_cell = duplicate_masks[col_name][index]
                            if is_dup_cell:
                                col_key = col_name
                                partners = duplicate_partners_map.get(col_key, {}).get(index, [])
                                partner_string = ", ".join(partners) if partners else "알 수 없음"
                                errors_found.append(f"'{col_name}' 전체 내용 중복 (중복 대상: {partner_string})")
                                
                                # 전체 중복이면서, 문장 중복이 아닐 때만 전체를 파란색으로 표시
                                if not has_dup_sentence:
                                    blue_matches.append((0, len(text)))

                            # 결과 저장
                            if errors_found:
                                id_value = ""
                                if id_column_name and id_column_name in row:
                                    id_value = str(row[id_column_name]) if pd.notna(row[id_column_name]) else ""
                                
                                # 하이라이트 적용
                                final_highlighted_text = apply_merged_highlights(text, red_matches, blue_matches)
                                
                                # 행 번호 저장 시 오프셋 적용
                                results.append({
                                    "index": index + excel_row_offset,
                                    "id_value": id_value,
                                    "column": col_name,
                                    "original_text": text,
                                    "highlighted_text": final_highlighted_text,
                                    "errors": list(set(errors_found)),
                                })

                st.success(f"검사 완료! 총 {len(sheet_df)}명, 특기사항 검사 결과 {len(results)}개의 수정 권장 사항을 발견했습니다.")

                if results:
                    st.markdown("---")
                    st.subheader("검사 결과 상세")
                    
                    for res in results:
                        id_display_string = f"({res['id_value']}) " if res['id_value'] else ""
                        st.markdown(f"**📌 {res['index']}번 행 {id_display_string}, '{res['column']}' 컬럼**")
                        st.markdown(f"> {res['highlighted_text']}", unsafe_allow_html=True)
                        
                        if res['errors']:
                            # 오류 내용 간격을 넓게 조정 (쉼표 + 공백 4칸)
                            formatted_errors = ',    '.join(res['errors'])
                            st.error(f"**[발견된 오류]** {formatted_errors}")
                        st.markdown("---")
                else:
                    st.balloons()
                    st.success("모든 항목을 확인했습니다. 발견된 오류가 없습니다! 🎉")

        except Exception as e:
            st.error(f"파일을 읽거나 처리하는 중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()