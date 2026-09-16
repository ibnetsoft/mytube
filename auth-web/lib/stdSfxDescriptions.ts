// Descriptions inferred from filenames; these are not audio transcriptions.
const descriptions: [string, string][] = [
    ['Slow,_dry_creak_of_a_', '천천히 삐걱거리는 건조한 마찰음'],
    ['ANMLCat-short_surprised_cat_', '고양이가 놀라며 짧게 내는 소리'],
    ['ANMLFarm-Create_a_short_roost', '수탉이 짧게 우는 소리로 추정'],
    ['ANMLHors-horse_neighing_sound', '말이 울부짖는 소리'],
    ['ANMLWcat-A_tiger_growling_hur', '호랑이가 으르렁거리는 소리'],
    ['ANMLMisc-Wolf_howling', '늑대가 길게 울부짖는 소리'],
    ['ANMLDog-Barking_dog', '개가 짖는 소리'],
    ['ANMLWild-ealistic_animal_soun', '사실적인 야생동물 소리로 추정 · 동물 종류 미상'],
    ['MUSCPluck-shred_electric_guita', '일렉트릭 기타를 빠르고 화려하게 연주하는 소리'],
    ['TOONVox-Cute_cartoon_crane_b', '귀여운 만화풍 두루미 울음소리로 추정'],
    ['DSGNBram-Epic_heroic_deity_en', '영웅적인 신의 등장을 표현한 웅장한 효과음으로 추정'],
    ['UIGlitch-A_short_glitch_trans', '짧은 디지털 글리치 전환 효과음'],
    ['ANMLRept-Large_theropod_dinos', '대형 수각류 공룡 소리로 추정'],
    ['HMNKiss-kiss', '입맞춤 소리'],
    ['GOREBone-back_bone_cracking', '등뼈가 우두둑 꺾이는 소리'],
    ['SPRTField-Crisp_close_up_sound', '선명한 근접 스포츠 효과음으로 추정 · 구체적인 동작 미상'],
    ['STORM-Violent_Jurassic_rai', '쥐라기 분위기의 거센 폭우·폭풍 소리로 추정'],
    ['AMBUndwtr-A_10-second_underwat', '물속 분위기를 표현한 수중 환경음'],
    ['DSGNImpt-short_impact_hit,_pu', '짧고 강하게 치는 충격 효과음'],
    ['WINDGust-Strong_cinematic_wes', '강한 영화풍 돌풍 소리로 추정'],
    ['THUN-Close_lightning_stri', '가까이서 번개가 치는 강한 천둥소리'],
    ['HMNBrth-Very_quiet_sound_of_', '아주 조용한 사람의 숨소리로 추정'],
    ['AMBSea-Very_calm_open_sea_a', '매우 잔잔한 바다의 환경음'],
    ['FEETHmn-Realistic_footsteps_', '사실적인 사람의 발걸음 소리'],
    ['ANMLInsc-Very_soft,_sparse_so', '아주 작고 드문드문 들리는 곤충 소리로 추정'],
    ['AMBMisc-Sound_of_desert_wind', '사막에 부는 바람 소리'],
    ['CRWDApls-Sound_of_an_audience', '관객들이 박수치는 소리로 추정'],
    ['DSGNBoom-Prompt_PRO_Cinematic', '영화풍의 묵직한 저음 충격 효과음으로 추정'],
    ['AMBForst-A_calm_and_peaceful_', '고요하고 평화로운 숲의 환경음으로 추정'],
    ['VOXLaff-A_man_and_a_woman_la', '남자와 여자가 함께 웃는 소리'],
    ['AMBForst-Peaceful_seamless_na', '자연스럽게 이어지는 평화로운 숲·자연 환경음으로 추정'],
    ['WHSH-A_short,_soft_and_sa', '짧고 부드러운 휙 지나가는 전환 효과음으로 추정'],
]

export function sfxDescriptionKo(asset: { file_name?: string; metadata?: { description_ko?: string } }): string {
    if (asset.metadata?.description_ko) return asset.metadata.description_ko
    const name = String(asset.file_name || '').toLowerCase()
    return descriptions.find(([prefix]) => name.startsWith(prefix.toLowerCase()))?.[1]
        || '파일명만으로 소리를 확인하기 어렵습니다. 미리듣기로 확인해 주세요.'
}
