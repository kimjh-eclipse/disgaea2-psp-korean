# 디스가이아 2P 한국어화

> **📦 v20260823 내려받기: [Disgaea2Portable_Korean_v20260823.zip](https://github.com/kimjh-eclipse/disgaea2-psp-korean/releases/download/v20260823/Disgaea2Portable_Korean_v20260823.zip)**
> — ISO 빠른패처 + xdelta 패치 + 검증 해시 동봉. 원본 게임 데이터는 포함되지 않습니다.
>
> 최신판은 [Releases](https://github.com/kimjh-eclipse/disgaea2-psp-korean/releases/latest) 에서 받으세요.
>
> **💾 저장소: [disgaea2-psp-korean](https://github.com/kimjh-eclipse/disgaea2-psp-korean)**

받으신 파일이 배포본과 같은지 확인하실 수 있습니다.

```
Disgaea2Portable_Korean_v20260823.zip   8,032,051 바이트
SHA-256: F9D388EBF4B121FF152F56F0924E4520F7EB9FD41CEA596D22F9F9C731AD0F9C
```

```powershell
Get-FileHash .\Disgaea2Portable_Korean_v20260823.zip -Algorithm SHA256
```

PSP판 『魔界戦記ディスガイア2 PORTABLE』(일본판 `ULJS00183`) 한국어화 프로젝트입니다.
번역 결과물과 함께 **포맷 규명 과정·겪은 함정**을 기록으로 남겼습니다.

> **v20260827부터 EBOOT을 재암호화합니다.**
> v20260826까지는 게임 실행 파일(EBOOT)을 평문 ELF로 교체해 실기(PSP 개조본)의
> 서명 검사를 통과하지 못했습니다(PPSSPP 전용). 시놀부님께서 주신 type-1(`~PSP`,
> tag `C0CB167C`) 재암호화 스크립트로 원본 헤더를 재사용해 다시 봉인하면서
> 이 제약이 사라졌습니다.
> 다만 실기에서 실제로 부팅되는지는 아직 검증하지 못했습니다 — 제보 환영합니다.

## 번역 분량

| 영역 | 건수 | 글자수 |
|---|---:|---:|
| 대사 (talk ×17) | 9,822 | 161,740 |
| 재판소·시스템 (InProgramTxtDB) | 2,911 | 45,727 |
| 기술·무기·마법·이노센트 등 6종 | 2,044 | 27,857 |
| 메뉴·UI (script00) | 1,102 | 9,360 |
| 유닛 기본 이름 풀 | 906 | 3,214 |
| 캐릭터·클래스명 | 578 | 2,394 |
| 오프닝·엔딩 나레이션 | 23 | 348 |
| **합계** | **17,386** | **약 25만 자** |

이미지 작업: 타이틀 로고, 대사창 이름표, 오프닝 나레이션.

## 문서 구성

- [설치](install.md) — 패처 사용법
- [렌더러 제약](renderer.md) — 이 프로젝트에서 가장 어려웠던 부분
- [포맷](formats.md) — 규명한 파일 구조
- [빌드](pipeline.md) — 파이프라인 8단계
- [번역 규칙](translation.md) — 용어집과 표기 원칙
- [문제 해결](troubleshooting.md)

## 저장소에 게임 데이터는 없습니다

ISO, 추출 아카이브, 폰트·텍스처, 복호 EBOOT, 패처 리소스는 저작물이므로 포함하지 않았습니다.
빌드에는 일본판 원본 ISO가 필요합니다.
