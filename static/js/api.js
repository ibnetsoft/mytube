/**
 * wingsAIStudio API 클라이언트
 */

const API = {
    // YouTube API
    youtube: {
        async search(query, options = {}) {
            const response = await fetch('/api/youtube/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query,
                    max_results: options.maxResults || 10,
                    order: options.order || 'relevance',
                    published_after: options.publishedAfter || null
                })
            });
            return response.json();
        },

        async getVideo(videoId) {
            const response = await fetch(`/api/youtube/videos/${videoId}`);
            return response.json();
        },

        async getComments(videoId, maxResults = 100) {
            const response = await fetch(`/api/youtube/comments/${videoId}?max_results=${maxResults}`);
            return response.json();
        },

        async getChannel(channelId) {
            const response = await fetch(`/api/youtube/channel/${channelId}`);
            return response.json();
        }
    },

    // Gemini API
    gemini: {
        async generate(prompt, options = {}) {
            const response = await fetch('/api/gemini/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt,
                    temperature: options.temperature || 0.7,
                    max_tokens: options.maxTokens || 8192
                })
            });
            return response.json();
        },

        async analyzeComments(videoId, videoTitle) {
            const response = await fetch(`/api/gemini/analyze-comments?video_id=${videoId}&video_title=${encodeURIComponent(videoTitle)}`, {
                method: 'POST'
            });
            return response.json();
        }
    },

    // TTS API
    tts: {
        async generate(text, options = {}) {
            const response = await fetch('/api/tts/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text,
                    voice_id: options.voiceId || null,
                    provider: options.provider || 'elevenlabs'
                })
            });
            return response.json();
        },

        async getVoices() {
            const response = await fetch('/api/tts/voices');
            return response.json();
        }
    },

    // 이미지 API
    image: {
        async generatePrompts(script, style = 'realistic', count = 5) {
            const response = await fetch(`/api/image/generate-prompts?script=${encodeURIComponent(script)}&style=${style}&count=${count}`, {
                method: 'POST'
            });
            return response.json();
        },

        // Gemini Imagen 3로 이미지 생성 (숏폼 9:16)
        async generate(prompt, aspectRatio = '9:16') {
            const response = await fetch('/api/image/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt,
                    aspect_ratio: aspectRatio
                })
            });
            return response.json();
        },

        // 썸네일 생성 (이미지 + 텍스트)
        async generateThumbnail(prompt, text, options = {}) {
            const response = await fetch('/api/image/generate-thumbnail', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt,
                    text,
                    text_position: options.textPosition || 'center',
                    text_color: options.textColor || '#FFFFFF',
                    font_size: options.fontSize || 72
                })
            });
            return response.json();
        }
    },

    // 영상 API
    video: {
        async createSlideshow(images, audioUrl = null, durationPerImage = 5.0) {
            const response = await fetch('/api/video/create-slideshow', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    images,
                    audio_url: audioUrl,
                    duration_per_image: durationPerImage
                })
            });
            return response.json();
        }
    },

    // 프로젝트 API
    project: {
        // 프로젝트 목록
        async list() {
            const response = await fetch('/api/projects');
            return response.json();
        },

        // 프로젝트 생성
        async create(name, topic = null) {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, topic })
            });
            return response.json();
        },

        // 프로젝트 조회
        async get(projectId) {
            const response = await fetch(`/api/projects/${projectId}`);
            return response.json();
        },

        // 프로젝트 전체 데이터 조회
        async getFull(projectId) {
            const response = await fetch(`/api/projects/${projectId}/full`);
            return response.json();
        },

        // 프로젝트 업데이트
        async update(projectId, data) {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            return response.json();
        },

        // 프로젝트 삭제
        async delete(projectId) {
            const response = await fetch(`/api/projects/${projectId}`, {
                method: 'DELETE'
            });
            return response.json();
        },

        // 분석 결과 저장/조회
        async saveAnalysis(projectId, videoData, analysisResult) {
            const response = await fetch(`/api/projects/${projectId}/analysis`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_data: videoData, analysis_result: analysisResult })
            });
            return response.json();
        },

        async getAnalysis(projectId) {
            const response = await fetch(`/api/projects/${projectId}/analysis`);
            return response.json();
        },

        // 대본 구조 저장/조회
        async saveScriptStructure(projectId, structure) {
            const response = await fetch(`/api/projects/${projectId}/script-structure`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(structure)
            });
            return response.json();
        },

        async getScriptStructure(projectId) {
            const response = await fetch(`/api/projects/${projectId}/script-structure`);
            return response.json();
        },

        // 대본 저장/조회
        async saveScript(projectId, fullScript, wordCount, estimatedDuration) {
            const response = await fetch(`/api/projects/${projectId}/script`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    full_script: fullScript,
                    word_count: wordCount,
                    estimated_duration: estimatedDuration
                })
            });
            return response.json();
        },

        async getScript(projectId) {
            const response = await fetch(`/api/projects/${projectId}/script`);
            return response.json();
        },

        // 이미지 프롬프트 저장/조회
        async saveImagePrompts(projectId, prompts) {
            const response = await fetch(`/api/projects/${projectId}/image-prompts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompts })
            });
            return response.json();
        },

        async getImagePrompts(projectId) {
            const response = await fetch(`/api/projects/${projectId}/image-prompts`);
            return response.json();
        },

        // 메타데이터 저장/조회
        async saveMetadata(projectId, titles, description, tags, hashtags) {
            const response = await fetch(`/api/projects/${projectId}/metadata`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ titles, description, tags, hashtags })
            });
            return response.json();
        },

        async getMetadata(projectId) {
            const response = await fetch(`/api/projects/${projectId}/metadata`);
            return response.json();
        },

        // 썸네일 저장/조회
        async saveThumbnails(projectId, ideas, texts) {
            const response = await fetch(`/api/projects/${projectId}/thumbnails`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ideas, texts })
            });
            return response.json();
        },

        async getThumbnails(projectId) {
            const response = await fetch(`/api/projects/${projectId}/thumbnails`);
            return response.json();
        },

        // 쇼츠 저장/조회
        async saveShorts(projectId, shortsData) {
            const response = await fetch(`/api/projects/${projectId}/shorts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shorts_data: shortsData })
            });
            return response.json();
        },

        async getShorts(projectId) {
            const response = await fetch(`/api/projects/${projectId}/shorts`);
            return response.json();
        },

        // ===== 프로젝트 핵심 설정 (10가지 요소) =====
        async saveSettings(projectId, settings) {
            const response = await fetch(`/api/projects/${projectId}/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            return response.json();
        },

        async getSettings(projectId) {
            const response = await fetch(`/api/projects/${projectId}/settings`);
            return response.json();
        },

        async updateSetting(projectId, key, value) {
            const response = await fetch(`/api/projects/${projectId}/settings/${key}?value=${encodeURIComponent(value)}`, {
                method: 'PATCH'
            });
            return response.json();
        }
    },

    // 상태 확인
    async health() {
        const response = await fetch('/api/health');
        return response.json();
    },

    // API 키 관리
    apiKeys: {
        async get() {
            const response = await fetch('/api/settings/api-keys');
            return response.json();
        },

        async save(keys) {
            const response = await fetch('/api/settings/api-keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(keys)
            });
            return response.json();
        }
    }
};

// 현재 프로젝트 ID 관리
window.currentProjectId = localStorage.getItem('currentProjectId') || null;

window.setCurrentProject = function(projectId) {
    window.currentProjectId = projectId;
    localStorage.setItem('currentProjectId', projectId);
    // 프로젝트 변경 이벤트 발생
    window.dispatchEvent(new CustomEvent('projectChanged', { detail: { projectId } }));
};

window.getCurrentProject = function() {
    return window.currentProjectId;
};

// 전역 사용
window.API = API;
