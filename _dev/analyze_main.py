import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 엔드포인트 추출
endpoints = re.findall(r'@app\.(get|post|put|delete)\([\'\"](.*?)[\'\"]', content)

# 카테고리별 분류
categories = {}
for method, path in endpoints:
    # 첫 번째 경로 세그먼트로 카테고리 분류
    parts = path.strip('/').split('/')
    category = parts[0] if parts else 'root'
    
    if category not in categories:
        categories[category] = {'GET': 0, 'POST': 0, 'PUT': 0, 'DELETE': 0, 'total': 0}
    
    categories[category][method.upper()] += 1
    categories[category]['total'] += 1

print('=' * 60)
print('main.py 모듈화 분석 리포트')
print('=' * 60)
print(f'\n📊 기본 통계')
print(f'  - 총 라인 수: 4,341줄')
print(f'  - 총 엔드포인트: {len(endpoints)}개')
print(f'  - 카테고리 수: {len(categories)}개')

print(f'\n📁 카테고리별 엔드포인트 분포')
print('-' * 60)

for cat in sorted(categories.keys(), key=lambda x: categories[x]['total'], reverse=True):
    total = categories[cat]['total']
    print(f'\n{cat}: {total}개')
    for method in ['GET', 'POST', 'PUT', 'DELETE']:
        if categories[cat][method] > 0:
            print(f'  └─ {method}: {categories[cat][method]}개')

# 모듈화 점수 계산
print(f'\n\n🎯 모듈화 평가')
print('-' * 60)

# 라우터 분리 여부 확인
with open('main.py', 'r', encoding='utf-8') as f:
    main_content = f.read()
    
has_routers = 'app.include_router' in main_content
router_count = main_content.count('app.include_router')

print(f'\n1. 라우터 분리')
if has_routers:
    print(f'   ✅ {router_count}개의 라우터가 분리되어 있음')
else:
    print(f'   ❌ 라우터가 분리되지 않음')

print(f'\n2. 파일 크기')
if len(endpoints) > 50:
    print(f'   ⚠️  main.py에 {len(endpoints)}개의 엔드포인트 (권장: <20개)')
    print(f'   → 추가 라우터 분리 필요')
else:
    print(f'   ✅ 적절한 크기')

print(f'\n3. 코드 구조')
lines_per_endpoint = 4341 / len(endpoints) if endpoints else 0
print(f'   - 엔드포인트당 평균 라인 수: {lines_per_endpoint:.1f}줄')

if lines_per_endpoint > 30:
    print(f'   ⚠️  복잡도가 높음 (권장: <30줄/엔드포인트)')
else:
    print(f'   ✅ 적절한 복잡도')

# 개선 제안
print(f'\n\n💡 개선 제안')
print('-' * 60)

suggestions = []

# API 엔드포인트가 많은 카테고리 찾기
for cat, data in categories.items():
    if data['total'] > 10 and cat not in ['api', '']:
        suggestions.append(f'  • {cat} ({data["total"]}개) → app/routers/{cat}.py로 분리')

if suggestions:
    print('\n다음 카테고리를 별도 라우터로 분리 권장:')
    for s in suggestions:
        print(s)
else:
    print('\n현재 구조가 적절합니다.')

print('\n' + '=' * 60)
