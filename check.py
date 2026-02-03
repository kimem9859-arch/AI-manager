import google.generativeai as genai

# ★★★ 여기에 아까 그 API 키를 붙여넣으세요 ★★★
GOOGLE_API_KEY = "AIzaSyD0EhbJdDOg09Tnk18vtQgFbzFwIBRrmPM"
genai.configure(api_key=GOOGLE_API_KEY)

print("=== 내 API 키로 쓸 수 있는 모델 목록 ===")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"에러 발생: {e}")