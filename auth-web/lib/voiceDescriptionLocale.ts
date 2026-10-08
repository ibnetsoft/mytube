import type { SupportedLocale } from './i18n'

type VoiceDescription = {
    description?: string
    description_i18n?: Partial<Record<SupportedLocale, string>>
}

// Match the description, not a voice ID: providers and administrators can change
// the copy without accidentally showing a translation of an older description.
const normalize = (text: string) => text.trim().replace(/\s+/g, ' ')
type DescriptionEntry = [source: string, ko: string, vi: string, th: string, en?: string]
const descriptions: DescriptionEntry[] = [
    [
        '무료 Google 한국어 TTS입니다. 긴 대본은 자동 분할 초고속 생성됩니다.',
        '무료 Google 한국어 음성 합성입니다. 긴 대본은 자동으로 나누어 매우 빠르게 생성합니다.',
        'Dịch vụ chuyển văn bản tiếng Hàn thành giọng nói miễn phí của Google. Kịch bản dài được tự động chia nhỏ và tạo giọng nói với tốc độ rất nhanh.',
        'บริการแปลงข้อความภาษาเกาหลีเป็นเสียงพูดฟรีจากกูเกิล บทยาวจะถูกแบ่งโดยอัตโนมัติเพื่อสร้างเสียงได้อย่างรวดเร็วมาก',
        'Free Google Korean text-to-speech. Long scripts are automatically split and generated very quickly.',
    ],
    [
        'Easy going and perfect for casual conversations.',
        '느긋하고 편안하며 일상적인 대화에 잘 어울립니다.',
        'Thoải mái, dễ gần và rất phù hợp với những cuộc trò chuyện thường ngày.',
        'สบาย ๆ เป็นกันเอง เหมาะอย่างยิ่งสำหรับการสนทนาในชีวิตประจำวัน',
    ],
    [
        'Young adult woman with a confident and warm, mature quality and a reassuring, professional tone.',
        '자신감과 따뜻함, 성숙함을 갖춘 젊은 성인 여성의 목소리로, 안심을 주는 전문적인 어조가 특징입니다.',
        'Giọng nữ trưởng thành trẻ tuổi, tự tin, ấm áp và chín chắn, với sắc thái chuyên nghiệp mang lại cảm giác yên tâm.',
        'เสียงหญิงวัยผู้ใหญ่ตอนต้นที่มั่นใจ อบอุ่น และสุขุม พร้อมน้ำเสียงที่ทำให้รู้สึกอุ่นใจและเป็นมืออาชีพ',
    ],
    [
        'This young adult female voice delivers sunny enthusiasm with a quirky attitude.',
        '밝은 열정과 개성 넘치는 태도가 돋보이는 젊은 성인 여성의 목소리입니다.',
        'Giọng nữ trưởng thành trẻ tuổi thể hiện sự nhiệt tình tươi sáng cùng nét cá tính khác biệt.',
        'เสียงหญิงวัยผู้ใหญ่ตอนต้นที่ถ่ายทอดความกระตือรือร้นสดใส พร้อมบุคลิกแปลกใหม่มีเสน่ห์',
    ],
    [
        'A young Australian male with a confident and energetic voice.',
        '자신감 있고 활기찬 젊은 호주 남성의 목소리입니다.',
        'Giọng nam người Úc trẻ tuổi, tự tin và tràn đầy năng lượng.',
        'เสียงชายชาวออสเตรเลียวัยหนุ่มที่มั่นใจและเปี่ยมพลัง',
    ],
    [
        'Warm resonance that instantly captivates listeners.',
        '따뜻한 울림으로 듣는 사람을 단번에 사로잡습니다.',
        'Âm vang ấm áp cuốn hút người nghe ngay lập tức.',
        'เสียงกังวานอบอุ่นที่ดึงดูดผู้ฟังได้ทันที',
    ],
    [
        'Deceptively gravelly, yet unsettling edge.',
        '예상 밖으로 거친 질감에 불안감을 자아내는 날카로움이 담긴 목소리입니다.',
        'Chất giọng khàn sạn đầy bất ngờ, mang nét sắc lạnh gây bất an.',
        'เสียงแหบพร่าที่คาดไม่ถึง พร้อมความคมเข้มที่ชวนให้รู้สึกไม่สบายใจ',
    ],
    [
        'A relaxed, neutral voice ready for narrations or conversational projects.',
        '차분하고 중립적인 목소리로, 내레이션이나 대화형 콘텐츠에 적합합니다.',
        'Giọng nói thư thái, trung tính, phù hợp với thuyết minh hoặc các dự án hội thoại.',
        'เสียงผ่อนคลายและเป็นกลาง เหมาะสำหรับงานบรรยายหรือเนื้อหาการสนทนา',
    ],
    [
        'An animated warrior ready to charge forward.',
        '금방이라도 돌진할 듯 생동감 넘치는 전사의 목소리입니다.',
        'Giọng chiến binh đầy sức sống, sẵn sàng lao về phía trước.',
        'เสียงนักรบที่มีชีวิตชีวา พร้อมพุ่งทะยานไปข้างหน้า',
    ],
    [
        'A young adult with energy and warmth - suitable for reels and shorts.',
        '활력과 따뜻함을 갖춘 젊은 성인의 목소리로, 릴스와 쇼츠에 적합합니다.',
        'Giọng người trưởng thành trẻ tuổi, đầy năng lượng và ấm áp, phù hợp với các video ngắn trên mạng xã hội.',
        'เสียงวัยผู้ใหญ่ตอนต้นที่เปี่ยมพลังและอบอุ่น เหมาะสำหรับวิดีโอสั้นบนสื่อสังคมออนไลน์',
    ],
    [
        'Clear and engaging, friendly woman with a British accent suitable for e-learning.',
        '명료하고 몰입감을 주는 친근한 여성의 영국식 억양으로, 온라인 교육에 적합합니다.',
        'Giọng nữ thân thiện với giọng Anh, rõ ràng và cuốn hút, phù hợp với học trực tuyến.',
        'เสียงหญิงเป็นมิตรสำเนียงอังกฤษ ชัดเจนและน่าติดตาม เหมาะสำหรับการเรียนรู้ออนไลน์',
    ],
    [
        'A professional woman with a pleasing alto pitch. Suitable for many use cases.',
        '듣기 좋은 알토 음역의 전문적인 여성 목소리로, 다양한 용도에 적합합니다.',
        'Giọng nữ chuyên nghiệp với âm vực trầm dễ nghe, phù hợp với nhiều mục đích sử dụng.',
        'เสียงหญิงมืออาชีพในช่วงเสียงต่ำที่ฟังสบาย เหมาะกับการใช้งานหลากหลายรูปแบบ',
    ],
    [
        'Conversational and laid back.',
        '대화하듯 자연스럽고 편안한 목소리입니다.',
        'Tự nhiên như đang trò chuyện và rất thoải mái.',
        'เป็นธรรมชาติเหมือนกำลังสนทนาและให้ความรู้สึกผ่อนคลาย',
    ],
    [
        'Young and popular, this playful American female voice is perfect for trendy content.',
        '젊고 인기 있는 장난기 넘치는 미국 여성의 목소리로, 유행하는 콘텐츠에 잘 어울립니다.',
        'Giọng nữ Mỹ trẻ trung, được yêu thích và tinh nghịch, rất phù hợp với nội dung theo xu hướng.',
        'เสียงหญิงอเมริกันวัยสาวที่เป็นที่นิยมและมีความขี้เล่น เหมาะอย่างยิ่งกับเนื้อหาตามกระแส',
    ],
    [
        'A smooth tenor pitch from a man in his 40s - perfect for agentic use cases.',
        '40대 남성의 부드러운 테너 음색으로, 대화형 에이전트에 적합합니다.',
        'Giọng nam cao mượt mà của người đàn ông ở độ tuổi 40, rất phù hợp với các ứng dụng trợ lý tự động.',
        'เสียงชายสูงที่นุ่มนวลของชายวัยสี่สิบ เหมาะอย่างยิ่งสำหรับผู้ช่วยอัตโนมัติ',
    ],
    [
        'This voice is warm, bright, and professional, characterized by a Standard American accent and a polished, narrative quality. It features a medium-high pitch with crisp diction and a deliberate, rhythmic pace that makes it highly intelligible and engaging for long-form listening.',
        '따뜻하고 밝으며 전문적인 목소리로, 표준 미국식 억양과 세련된 내레이션이 특징입니다. 중고음의 높이, 또렷한 발음, 신중하고 리듬감 있는 속도 덕분에 긴 콘텐츠도 쉽게 이해하며 몰입해서 들을 수 있습니다.',
        'Giọng nói ấm áp, tươi sáng và chuyên nghiệp, với giọng Mỹ chuẩn và phong cách kể chuyện trau chuốt. Âm vực trung cao, phát âm rõ nét cùng nhịp đọc có chủ ý, đều đặn giúp nội dung dễ hiểu và cuốn hút ngay cả khi nghe trong thời gian dài.',
        'เสียงอบอุ่น สดใส และเป็นมืออาชีพ โดดเด่นด้วยสำเนียงอเมริกันมาตรฐานและการบรรยายที่ประณีต มีระดับเสียงกลางค่อนข้างสูง ออกเสียงชัดถ้อยชัดคำ และเว้นจังหวะอย่างตั้งใจเป็นจังหวะสม่ำเสมอ ทำให้เข้าใจง่ายและน่าติดตามแม้ฟังเนื้อหายาว',
    ],
    [
        'Natural and real, this down-to-earth voice is great across many use-cases.',
        '자연스럽고 진솔하며 꾸밈없는 목소리로, 다양한 용도에 잘 어울립니다.',
        'Tự nhiên, chân thật và mộc mạc, giọng nói này phù hợp với nhiều mục đích sử dụng.',
        'เสียงเป็นธรรมชาติ จริงใจ และเรียบง่าย เหมาะกับการใช้งานหลากหลายรูปแบบ',
    ],
    [
        'Middle-aged man with a resonant and comforting tone. Great for narrations and advertisements.',
        '울림 있고 편안함을 주는 중년 남성의 목소리로, 내레이션과 광고에 적합합니다.',
        'Giọng nam trung niên vang ấm và mang lại cảm giác an tâm, phù hợp với thuyết minh và quảng cáo.',
        'เสียงชายวัยกลางคนที่กังวานและให้ความรู้สึกอุ่นใจ เหมาะสำหรับงานบรรยายและโฆษณา',
    ],
    [
        'A strong voice perfect for delivering a professional broadcast or news story.',
        '전문적인 방송이나 뉴스 전달에 적합한 힘 있는 목소리입니다.',
        'Giọng nói mạnh mẽ, rất phù hợp để dẫn chương trình phát thanh, truyền hình hoặc bản tin chuyên nghiệp.',
        'เสียงทรงพลังที่เหมาะอย่างยิ่งสำหรับการออกอากาศหรือนำเสนอข่าวอย่างมืออาชีพ',
    ],
    [
        'Velvety British female voice delivers news and narrations with warmth and clarity.',
        '벨벳처럼 부드러운 영국 여성의 목소리로, 뉴스와 내레이션을 따뜻하고 명료하게 전달합니다.',
        'Giọng nữ Anh mượt như nhung, truyền tải bản tin và lời thuyết minh một cách ấm áp, rõ ràng.',
        'เสียงหญิงอังกฤษนุ่มละมุนดุจกำมะหยี่ ถ่ายทอดข่าวและคำบรรยายอย่างอบอุ่นและชัดเจน',
    ],
    [
        'A bright tenor pitch that immediately cuts through. The delivery is brash and openly confident, speaking with unwavering certainty and a slightly aggressive self-assurance.',
        '단번에 귀에 들어오는 밝은 테너 음색입니다. 거침없고 자신감 넘치는 표현으로, 흔들림 없는 확신과 약간 공격적인 당당함을 담아 말합니다.',
        'Giọng nam cao sáng nổi bật ngay lập tức. Cách thể hiện táo bạo, tự tin rõ rệt, nói với sự chắc chắn không dao động và nét tự tin hơi mạnh mẽ, lấn át.',
        'เสียงชายสูงที่สดใสและโดดเด่นจนได้ยินชัดทันที ถ่ายทอดอย่างกล้าแสดงออกและมั่นใจอย่างเปิดเผย พูดด้วยความแน่วแน่ไม่หวั่นไหวและความมั่นใจที่แข็งกร้าวเล็กน้อย',
    ],
    [
        'Friendly and comforting voice ready to narrate your stories.',
        '이야기를 들려주기에 좋은 친근하고 편안한 목소리입니다.',
        'Giọng nói thân thiện và ấm áp, sẵn sàng kể những câu chuyện của bạn.',
        'เสียงเป็นมิตรและให้ความรู้สึกอุ่นใจ พร้อมบรรยายเรื่องราวของคุณ',
    ],
    [
        '한국의 여성노인 목소리 입니다.',
        '한국의 여성노인 목소리 입니다.',
        'Giọng phụ nữ cao tuổi người Hàn Quốc.',
        'เสียงหญิงสูงวัยชาวเกาหลี',
        'The voice of an elderly Korean woman.',
    ],
    [
        'Warm, intelligent, and versatile, her voice brings authenticity and connection to every project. Her voice is perfect for Narrations, eLearning, Training, IVR, Call Agent and Customer Interaction.',
        '따뜻하고 지적이며 다재다능한 목소리로, 모든 프로젝트에 진정성과 유대감을 더합니다. 내레이션, 온라인 교육, 훈련, 자동 음성 응답, 전화 상담, 고객 응대에 적합합니다.',
        'Ấm áp, thông minh và linh hoạt, giọng nói của cô mang đến sự chân thật và gắn kết cho mọi dự án. Rất phù hợp với thuyết minh, học trực tuyến, đào tạo, trả lời tự động qua điện thoại, tổng đài viên và tương tác với khách hàng.',
        'เสียงของเธออบอุ่น ชาญฉลาด และปรับใช้ได้หลากหลาย ช่วยเพิ่มความจริงใจและความเชื่อมโยงให้ทุกโครงการ เหมาะอย่างยิ่งสำหรับงานบรรยาย การเรียนรู้ออนไลน์ การฝึกอบรม ระบบตอบรับอัตโนมัติทางโทรศัพท์ เจ้าหน้าที่รับสาย และการโต้ตอบกับลูกค้า',
    ],
    [
        'This is the voice of a middle-aged to elderly Japanese speaker. It is intended for use in calm narration and similar applications.',
        '중년에서 노년 사이의 일본인 화자 목소리입니다. 차분한 내레이션과 이와 유사한 용도에 적합합니다.',
        'Giọng người Nhật từ trung niên đến cao tuổi, dành cho lời thuyết minh điềm tĩnh và các ứng dụng tương tự.',
        'เสียงผู้พูดชาวญี่ปุ่นวัยกลางคนถึงสูงวัย ออกแบบมาสำหรับการบรรยายที่สงบและงานลักษณะใกล้เคียงกัน',
    ],
    [
        'A warm, smooth, and expressive voice with a trustworthy, narrative tone. Versatile enough for younger to mature characters, perfect for audiobooks and storytelling.',
        '따뜻하고 부드러우며 표현력이 풍부한 목소리로, 신뢰감을 주는 이야기체 어조가 특징입니다. 젊은 인물부터 성숙한 인물까지 폭넓게 표현할 수 있어 오디오북과 이야기 낭독에 적합합니다.',
        'Giọng nói ấm áp, mượt mà và giàu biểu cảm với sắc thái kể chuyện đáng tin cậy. Linh hoạt cho cả nhân vật trẻ lẫn trưởng thành, rất phù hợp với sách nói và kể chuyện.',
        'เสียงอบอุ่น นุ่มนวล และถ่ายทอดอารมณ์ได้ดี พร้อมน้ำเสียงเล่าเรื่องที่น่าเชื่อถือ ปรับใช้ได้กับตัวละครตั้งแต่วัยเยาว์จนถึงวัยผู้ใหญ่ เหมาะอย่างยิ่งกับหนังสือเสียงและการเล่าเรื่อง',
    ],
    [
        'Calm, middle-aged female voice.',
        '차분한 중년 여성의 목소리입니다.',
        'Giọng nữ trung niên điềm tĩnh.',
        'เสียงหญิงวัยกลางคนที่สงบ',
    ],
    [
        'Female conversational voice.',
        '대화체의 여성 목소리입니다.',
        'Giọng nữ tự nhiên như đang trò chuyện.',
        'เสียงหญิงในลักษณะการสนทนา',
    ],
    [
        'A soft, middle-aged male voice with a professional Korean voice actor feel (mid-to-low tone), suitable for commercial dubbing/narration and professional research narration.',
        '한국 전문 성우 같은 느낌의 부드러운 중년 남성 목소리로, 중저음이 특징입니다. 상업용 더빙·내레이션과 전문적인 연구 내레이션에 적합합니다.',
        'Giọng nam trung niên nhẹ nhàng, mang phong cách diễn viên lồng tiếng Hàn Quốc chuyên nghiệp, ở âm vực trung trầm. Phù hợp với lồng tiếng và thuyết minh thương mại cũng như thuyết minh nghiên cứu chuyên môn.',
        'เสียงชายวัยกลางคนที่นุ่มนวล ให้ความรู้สึกเหมือนนักพากย์เกาหลีมืออาชีพในโทนเสียงกลางถึงต่ำ เหมาะสำหรับงานพากย์หรือบรรยายเชิงพาณิชย์ และการบรรยายงานวิจัยเฉพาะทาง',
    ],
    [
        'Korean female voice with a bright, crisp, and highly articulate tone.',
        '밝고 또렷하며 발음이 매우 명확한 한국 여성의 목소리입니다.',
        'Giọng nữ Hàn Quốc tươi sáng, rõ nét và phát âm rất rành mạch.',
        'เสียงหญิงเกาหลีที่สดใส คมชัด และออกเสียงได้ชัดถ้อยชัดคำอย่างยิ่ง',
    ],
    [
        'Calm, gentle, and thoughtful the perfect voice for literary fiction audiobook narration, documentary commentary, and meditative content.',
        '차분하고 부드러우며 사려 깊은 목소리로, 문학 소설 오디오북 낭독, 다큐멘터리 해설, 명상 콘텐츠에 적합합니다.',
        'Điềm tĩnh, dịu dàng và sâu lắng, đây là giọng nói lý tưởng để đọc sách nói văn học hư cấu, bình luận phim tài liệu và nội dung thiền định.',
        'เสียงสงบ อ่อนโยน และใคร่ครวญ เหมาะอย่างยิ่งสำหรับการอ่านหนังสือเสียงวรรณกรรมเรื่องแต่ง การบรรยายสารคดี และเนื้อหาเพื่อการทำสมาธิ',
    ],
    [
        'A clear and warm Korean female voice with a calm, friendly, and trustworthy feel. Ideal for explainer videos, tutorials, educational content, product introductions, lifestyle narration, and social media voiceovers. The tone is natural and conversational, helping information sound easy, approachable, and reliable.',
        '맑고 따뜻한 한국 여성의 목소리로, 차분하고 친근하며 신뢰감을 줍니다. 설명 영상, 사용법 안내, 교육 콘텐츠, 제품 소개, 생활 정보 내레이션, 소셜 미디어 더빙에 적합합니다. 자연스럽고 대화하는 듯한 어조로 정보를 쉽고 친근하며 믿음직하게 전달합니다.',
        'Giọng nữ Hàn Quốc rõ ràng và ấm áp, tạo cảm giác điềm tĩnh, thân thiện và đáng tin cậy. Lý tưởng cho video giải thích, hướng dẫn, nội dung giáo dục, giới thiệu sản phẩm, thuyết minh về lối sống và lồng tiếng trên mạng xã hội. Giọng điệu tự nhiên như trò chuyện giúp thông tin dễ hiểu, dễ tiếp cận và đáng tin.',
        'เสียงหญิงเกาหลีที่ชัดเจนและอบอุ่น ให้ความรู้สึกสงบ เป็นมิตร และน่าเชื่อถือ เหมาะสำหรับวิดีโออธิบาย บทสอน เนื้อหาการศึกษา การแนะนำสินค้า การบรรยายเรื่องวิถีชีวิต และเสียงพากย์บนสื่อสังคมออนไลน์ น้ำเสียงเป็นธรรมชาติราวกับกำลังสนทนา ช่วยให้ข้อมูลฟังง่าย เข้าถึงได้ และน่าเชื่อถือ',
    ],
    [
        "This is a voice of a Japanese woman suitable for narration. Speaking in standard Japanese, it's ideal for a wide range of uses, including educational and explanatory videos, and company introductions.",
        '내레이션에 적합한 일본 여성의 목소리입니다. 표준 일본어를 구사하며, 교육 영상, 설명 영상, 회사 소개를 비롯한 다양한 용도에 적합합니다.',
        'Giọng nữ Nhật Bản phù hợp với thuyết minh. Sử dụng tiếng Nhật chuẩn, giọng nói này lý tưởng cho nhiều mục đích, bao gồm video giáo dục, video giải thích và giới thiệu công ty.',
        'เสียงหญิงญี่ปุ่นที่เหมาะกับงานบรรยาย พูดภาษาญี่ปุ่นมาตรฐาน เหมาะกับการใช้งานหลากหลาย ทั้งวิดีโอการศึกษา วิดีโออธิบาย และการแนะนำบริษัท',
    ],
    [
        'Conversational male voice.',
        '대화체의 남성 목소리입니다.',
        'Giọng nam tự nhiên như đang trò chuyện.',
        'เสียงชายในลักษณะการสนทนา',
    ],
    [
        'Saori - Japanese female - Calm Japanese female narrator. Clear standard Japanese, suitable for audiobooks, meditation, and educational content.',
        'Saori - 일본 여성 - 차분한 일본 여성 내레이터입니다. 명료한 표준 일본어로, 오디오북, 명상, 교육 콘텐츠에 적합합니다.',
        'Saori - Nữ Nhật Bản - Giọng nữ kể chuyện người Nhật điềm tĩnh. Tiếng Nhật chuẩn, rõ ràng, phù hợp với sách nói, thiền định và nội dung giáo dục.',
        'Saori - หญิงญี่ปุ่น - เสียงบรรยายหญิงญี่ปุ่นที่สงบ ใช้ภาษาญี่ปุ่นมาตรฐานชัดเจน เหมาะกับหนังสือเสียง การทำสมาธิ และเนื้อหาการศึกษา',
    ],
    [
        'A wise, comforting & human narrator’s voice, filled with warmth, wisdom, and quiet wonder. Grandpa Everett speaks with the calm rhythm of bedtime stories and the heart of lived experience. Gentle, steady, timeless – perfect for fairytales, audiobooks, narration, commercials, explainer videos, apps, and educational content. Also great as Santa Claus or Weihnachtsmann. Loved this voice? Discover more character voices by Alex Vox.',
        '따뜻함과 지혜, 잔잔한 경이로움이 담긴 현명하고 편안하며 인간적인 내레이터 목소리입니다. 할아버지 Everett는 잠자리 이야기의 차분한 리듬과 오랜 삶에서 우러나오는 진심으로 말합니다. 부드럽고 안정적이며 시대를 타지 않아 동화, 오디오북, 내레이션, 광고, 설명 영상, 앱, 교육 콘텐츠에 적합합니다. 산타클로스나 독일의 산타 역할에도 잘 어울립니다. 이 목소리가 마음에 드셨나요? Alex Vox의 다른 캐릭터 목소리도 만나 보세요.',
        'Giọng kể chuyện thông thái, an ủi và đầy tính người, chứa đựng sự ấm áp, trí tuệ và niềm ngạc nhiên lặng lẽ. Ông Everett nói với nhịp điệu bình thản của truyện kể trước giờ ngủ và tấm lòng từ trải nghiệm cuộc đời. Dịu dàng, vững vàng và vượt thời gian, lý tưởng cho truyện cổ tích, sách nói, thuyết minh, quảng cáo, video giải thích, ứng dụng và nội dung giáo dục. Cũng rất phù hợp để đóng vai ông già Noel hoặc ông già Giáng sinh của Đức. Bạn yêu thích giọng nói này? Hãy khám phá thêm các giọng nhân vật của Alex Vox.',
        'เสียงผู้บรรยายที่เปี่ยมปัญญา ให้ความอุ่นใจ และมีความเป็นมนุษย์ เต็มไปด้วยความอบอุ่น ความรอบรู้ และความพิศวงอย่างสงบ คุณปู่ Everett พูดด้วยจังหวะนุ่มนวลแบบนิทานก่อนนอนและหัวใจที่ผ่านประสบการณ์ชีวิต อ่อนโยน มั่นคง และงดงามเหนือกาลเวลา เหมาะอย่างยิ่งกับนิทาน หนังสือเสียง งานบรรยาย โฆษณา วิดีโออธิบาย แอปพลิเคชัน และเนื้อหาการศึกษา อีกทั้งเหมาะกับบทซานตาคลอสหรือซานตาตามธรรมเนียมเยอรมัน ชอบเสียงนี้หรือไม่ ลองค้นพบเสียงตัวละครอื่น ๆ ของ Alex Vox',
    ],
    [
        'Julian - deep rich mature British voice - A mature British male voice with a hint of roughness - yet soothing enough to melt butter. Works well for Narrations.',
        'Julian - 깊고 풍성하며 성숙한 영국식 목소리 - 약간 거친 질감이 있으면서도 사르르 녹아들 만큼 편안한 성숙한 영국 남성의 목소리입니다. 내레이션에 잘 어울립니다.',
        'Julian - Giọng Anh trầm, dày và chín chắn - Giọng nam Anh trưởng thành hơi khàn, nhưng vẫn êm dịu đến mức khiến người nghe tan chảy. Rất phù hợp với thuyết minh.',
        'Julian - เสียงอังกฤษทุ้มลึก หนักแน่น และสุขุม - เสียงชายอังกฤษวัยผู้ใหญ่ที่มีความสากเล็กน้อย แต่ผ่อนคลายชวนเคลิบเคลิ้มจนนุ่มละลาย เหมาะกับงานบรรยาย',
    ],
    [
        'YohanKoo - The voice of a confident, authoritative man in his 30s.',
        'YohanKoo - 자신감 있고 권위 있는 30대 남성의 목소리입니다.',
        'YohanKoo - Giọng người đàn ông ở độ tuổi 30, tự tin và có uy quyền.',
        'YohanKoo - เสียงชายวัยสามสิบที่มั่นใจและมีอำนาจน่าเชื่อถือ',
    ],
    [
        'Young Korean female voice. Great for Narrations.',
        '젊은 한국 여성의 목소리로, 내레이션에 적합합니다.',
        'Giọng nữ Hàn Quốc trẻ tuổi, rất phù hợp với thuyết minh.',
        'เสียงหญิงเกาหลีวัยสาว เหมาะกับงานบรรยาย',
    ],
    [
        'An old male voice, speaking Japanese, with a trending, distinguished tone.',
        '일본어를 구사하는 노년 남성의 목소리로, 세련되고 품격 있는 어조가 특징입니다.',
        'Giọng nam cao tuổi nói tiếng Nhật, với sắc thái thời thượng và trang trọng.',
        'เสียงชายสูงวัยที่พูดภาษาญี่ปุ่น ด้วยน้ำเสียงร่วมสมัยและมีสง่าราศี',
    ],
    [
        'Flint - Commanding Presence - Ignite your content with Flint, a voice that strikes with precision and leaves a lasting impression. Its deep, raspy resonance embodies strength and determination, while maintaining a smooth undertone that captivates listeners. Perfect for narrations, trailers, or authoritative characters, Flint balances grit and clarity to deliver messages with power and finesse. Forge unforgettable moments with the voice of Flint.',
        'Flint - 압도적인 존재감 - 정확하게 전달하고 오래 남는 인상을 주는 Flint의 목소리로 콘텐츠에 활력을 더해 보세요. 깊고 거친 울림은 힘과 결단력을 나타내면서도, 듣는 사람을 사로잡는 부드러운 바탕 음색을 유지합니다. 내레이션, 예고편, 권위 있는 캐릭터에 적합한 Flint는 거친 질감과 명료함의 균형을 통해 메시지를 힘 있고 섬세하게 전달합니다. Flint의 목소리로 잊지 못할 순간을 만들어 보세요.',
        'Flint - Sự hiện diện đầy uy lực - Thổi bùng sức sống cho nội dung của bạn với Flint, giọng nói truyền tải chính xác và để lại ấn tượng lâu dài. Âm vang trầm, khàn thể hiện sức mạnh và quyết tâm, đồng thời giữ lớp âm nền mượt mà cuốn hút người nghe. Lý tưởng cho thuyết minh, đoạn giới thiệu phim hoặc nhân vật có uy quyền, Flint cân bằng sự gai góc và rõ ràng để truyền tải thông điệp mạnh mẽ mà tinh tế. Tạo nên những khoảnh khắc khó quên với giọng nói của Flint.',
        'Flint - บุคลิกอันทรงพลัง - เติมประกายให้เนื้อหาของคุณด้วย Flint เสียงที่สื่อสารอย่างแม่นยำและสร้างความประทับใจยาวนาน เสียงกังวานทุ้มลึกและแหบพร่าถ่ายทอดพลังและความมุ่งมั่น พร้อมคงความนุ่มนวลในน้ำเสียงที่ดึงดูดผู้ฟัง เหมาะอย่างยิ่งกับงานบรรยาย ตัวอย่างภาพยนตร์ หรือตัวละครที่มีอำนาจ Flint สร้างสมดุลระหว่างความดุดันและความชัดเจนเพื่อส่งสารอย่างทรงพลังและประณีต สร้างช่วงเวลาที่ไม่อาจลืมด้วยเสียงของ Flint',
    ],
    [
        'Casual and Friendly Mio - Casual and Friendly',
        '편안하고 친근한 Mio - 편안하고 친근합니다.',
        'Mio thoải mái và thân thiện - Thoải mái và thân thiện.',
        'Mio ที่สบาย ๆ และเป็นมิตร - สบาย ๆ และเป็นมิตร',
    ],
    [
        '낭독하는 목소리',
        '낭독하는 목소리',
        'Giọng đọc thành tiếng.',
        'เสียงสำหรับการอ่านออกเสียง',
        'A voice for reading aloud.',
    ],
    [
        '따뜻하고 신뢰감있는 목소리',
        '따뜻하고 신뢰감있는 목소리',
        'Giọng nói ấm áp và đáng tin cậy.',
        'เสียงอบอุ่นและน่าเชื่อถือ',
        'A warm and trustworthy voice.',
    ],
]

const translated = new Map(descriptions.map(([source, ko, vi, th, en]) => [
    normalize(source), { ko, en: en || source, vi, th },
]))

const unavailable: Record<SupportedLocale, string> = {
    ko: '아직 이 설명의 번역이 준비되지 않았습니다.',
    en: 'Description translation is not available yet.',
    vi: 'Bản dịch mô tả này chưa có sẵn.',
    th: 'ยังไม่มีคำแปลสำหรับคำอธิบายนี้',
}

export function localizedVoiceDescription(voice: VoiceDescription, locale: SupportedLocale): string {
    const source = String(voice.description || '').trim()
    if (!source) return ''
    const provided = voice.description_i18n?.[locale]?.trim()
    if (provided) return provided
    const known = translated.get(normalize(source))
    if (known) return locale === 'en' && /[A-Za-z]/.test(source) && !/[가-힣]/.test(source) ? source : known[locale]

    // Unknown catalog additions remain readable when already in the selected
    // language; otherwise show localized status instead of leaking source copy.
    if (locale === 'en' && /^[\x20-\x7e\s\u2010-\u2026]+$/.test(source)
        && /\b(a|an|the|and|or|with|for|this|that|voice|narration|warm|clear|soft|calm)\b/i.test(source)) return source
    if (locale === 'ko' && /[가-힣]/.test(source)
        && /^[가-힣ㄱ-ㅎㅏ-ㅣ\s\p{N}\p{P}\p{S}]+$/u.test(source)) return source
    return unavailable[locale]
}
