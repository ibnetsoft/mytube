# 줌/팬 효과 선택 기능 구현 계획

## 목적
자막 편집기에서 각 이미지 씬(Scene)마다 "Zoom In / Zoom Out / Pan Left / Pan Right" 효과를 선택할 수 있는 기능을 "썸네일과 시간 사이"에 추가하고, 선택한 설정을 백엔드에 저장합니다.

## 1. 프론트엔드 (`subtitle_gen.html`)

### 데이터 모델
- 전역 상태 변수 `let imageEffects = [];` 추가.
- 이 배열은 `images` 배열(타임라인 이미지)과 1:1로 대응됩니다.
- 기본값: `'zoom_in'` (확대).

### UI 변경
- `renderSubtitles()` 함수 수정:
    - `leftCol`(썸네일 영역) 생성 로직에서 이미지가 전환되는 시점(`isTransition`이 true 일 때)에 드롭다운 메뉴를 추가합니다.
    - 위치: 썸네일 아래 또는 측면 (사용자 요청: "썸네일과 시간 사이").
    - `<select>` 드롭다운 옵션:
        - `zoom_in`: 확대 (Zoom In)
        - `zoom_out`: 축소 (Zoom Out)
        - `pan_left`: 좌로 이동 (Pan Left)
        - `pan_right`: 우로 이동 (Pan Right)
        - `none`: 고정 (Static)
    - 스타일: 좁은 공간에 맞게 아주 작은 텍스트(`text-[9px]` 등) 사용.
    - 이벤트 핸들러: `onchange="updateImageEffect(actualIndex, this.value)"`

### 로직
- **초기화**: `loadProjectAndSubtitles`에서 백엔드로부터 `image_effects` 데이터를 받아 전역 변수에 설정. 없으면 기본값으로 채움.
- **업데이트**: `updateImageEffect(index, value)` 함수로 상태 업데이트.
- **저장**: `saveSubtitles()` 호출 시 `image_effects` 배열을 JSON에 포함하여 전송.
- **동기화**: `distributeImages()` 등 이미지가 재배치될 때 효과 배열도 이에 맞춰 리사이즈하거나 초기화.

## 2. 백엔드 (`main.py`)

### API 업데이트
- **`POST /api/subtitle/save`**:
    - 요청 바디에서 `image_effects` 리스트를 받습니다.
    - 이를 `config.OUTPUT_DIR` 내의 `image_effects_{project_id}.json` 파일로 저장합니다.
    - 데이터베이스의 프로젝트 설정(`image_effects_path`)을 업데이트합니다.
- **`GET /api/subtitle/{project_id}`**:
    - 저장된 JSON 파일이 있다면 읽어서 `image_effects` 필드로 반환합니다.

## 3. 저장소
- `image_effects_{project_id}.json` 파일을 생성하여 관리합니다 (기존 이미지 타임라인 저장 방식과 유사).

## 4. 추후 렌더링 지원 (참고)
- 이 계획은 **UI 선택 및 데이터 저장**까지를 다룹니다.
- 실제로 비디오 렌더링 시 이 효과를 적용하는 기능(MoviePy Ken Burns 효과 등)은 데이터 저장이 구현된 후, `video_service.py` 수정 단계에서 진행합니다.
