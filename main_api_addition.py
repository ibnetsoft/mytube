

# ===========================================
# API: 대본 스타일 프리셋 관리
# ===========================================

@app.get("/api/settings/script-style-presets")
async def get_script_style_presets_api():
    """모든 대본 스타일 프리셋 조회"""
    presets = db.get_script_style_presets()
    
    # DB에 하나도 없으면 기본값으로 초기화
    if not presets:
        default_styles = {
            "news": "뉴스 스타일: 객관적이고 신뢰감 있는 톤으로 작성",
            "story": "옛날 이야기 스타일: 구연동화 방식으로 따듯하고 감성적으로 작성",
            "senior_story": "시니어 사연 스타일: 중장년층 공감 사연으로 진솔하고 깊이 있게 작성",
            "script_master": "최종 확정: '딥-다이브' 대본 빌드업 4단계 프로세스 (Ver. 4.0)"
        }
        for key, val in default_styles.items():
            db.save_script_style_preset(key, val)
        presets = default_styles
        
    return presets

@app.post("/api/settings/script-style-presets")
async def save_script_style_preset_api(preset: StylePreset):
    """대본 스타일 프리셋 저장"""
    db.save_script_style_preset(preset.style_key, preset.prompt_value)
    return {"status": "ok"}


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 피카디리스튜디오 v2.0 시작")
    print("=" * 50)

    config.validate()
    
    # Initialize & Migrate Database
    db.init_db()
    db.migrate_db()



    now_kst = config.get_kst_time()
    print(f"📍 서버 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📍 서버: http://{config.HOST}:{config.PORT}")
    print("=" * 50)

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
