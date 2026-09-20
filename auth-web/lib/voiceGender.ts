export function detectVoiceGender(
    rawGender?: string | null,
    name?: string | null,
    description?: string | null
): 'female' | 'male' {
    const raw = String(rawGender || '').trim().toLowerCase()
    if (raw === 'female' || raw === '여성' || raw === '여자' || raw === 'f' || raw === 'woman' || raw === 'girl') {
        return 'female'
    }
    if (raw === 'male' || raw === '남성' || raw === '남자' || raw === 'm' || raw === 'man' || raw === 'boy') {
        return 'male'
    }

    const text = `${name || ''} ${description || ''}`.toLowerCase()

    // 1. 한국어 여성 키워드 (부분 일치 검사)
    const koreanFemale = [
        '여성', '여자', '어머니', '엄마', '할머니', '할멈', '이모', '고모', '숙모',
        '누나', '언니', '소녀', '아내', '며느리', '딸', '여사', '마님', '공주', '아가씨',
        '선녀', '왕비', '황후', '황태자비', '수녀', '마녀', '여신', '여학생', '여동생', '신내린',
        '여성노인'
    ]
    for (const kw of koreanFemale) {
        if (text.includes(kw)) {
            return 'female'
        }
    }

    // 2. 영어 여성 키워드 (단어 경계 \b 검사로 오탐 방지: moments->mom, dominant->mina 방지)
    const englishFemale = [
        'female', 'woman', 'women', 'girl', 'girls', 'mother', 'mom', 'grandma', 'grandmother',
        'aunt', 'sister', 'wife', 'daughter', 'lady', 'queen', 'princess', 'mrs', 'ms', 'miss', 'actress',
        'mina', 'sian', 'yooni', 'sarah', 'bella', 'alice', 'lily', 'laura', 'jessica', 'selly', 'saori',
        'matilda', 'charlotte', 'dorothy', 'freya', 'gigi', 'grace', 'helena', 'ivy', 'jenny', 'karen',
        'nicole', 'olivia', 'paula', 'rachel', 'sophia', 'zoe', 'aria', 'emma', 'ava', 'mia', 'amelia',
        'yukari', 'elise', 'maria', 'jane'
    ]
    for (const kw of englishFemale) {
        if (new RegExp('\\b' + kw + '\\b', 'i').test(text)) {
            return 'female'
        }
    }

    // 3. 한국어 남성 키워드 (부분 일치 검사)
    const koreanMale = [
        '남성', '남자', '아버지', '아빠', '할아버지', '할아범', '삼촌', '외삼촌',
        '형', '오빠', '소년', '남편', '사위', '아들', '아저씨', '총각', '왕자', '왕', '황제',
        '남학생', '남동생', '신사', '타다오키', '진우', '요한'
    ]
    for (const kw of koreanMale) {
        if (text.includes(kw)) {
            return 'male'
        }
    }

    // 4. 영어 남성 키워드 (단어 경계 \b 검사)
    const englishMale = [
        'male', 'man', 'men', 'boy', 'boys', 'father', 'dad', 'grandpa', 'grandfather',
        'uncle', 'brother', 'husband', 'son', 'prince', 'king', 'mr', 'actor',
        'adam', 'antoni', 'arnold', 'bill', 'brian', 'callum', 'charlie', 'chris',
        'daniel', 'dave', 'drew', 'eric', 'ethan', 'fin', 'george', 'harry',
        'james', 'jeremy', 'josh', 'liam', 'marcus', 'michael', 'paul', 'river',
        'roger', 'sam', 'theo', 'thomas', 'will', 'flint', 'julian', 'everett', 'jun'
    ]
    for (const kw of englishMale) {
        if (new RegExp('\\b' + kw + '\\b', 'i').test(text)) {
            return 'male'
        }
    }

    return 'male'
}
