# 마계전기 디스가이아 2 PORTABLE 한국어화

PSP판 『魔界戦記ディスガイア2 PORTABLE』(일본판, `ULJS00183`) 한국어화 프로젝트의
도구 체인과 번역 소스입니다.

> **PPSSPP 전용입니다.** EBOOT을 평문 ELF로 교체하므로 실기(CFW)에서는 동작하지 않습니다.

## 번역 분량

| 영역 | 건수 | 글자수 |
|---|---|---|
| 대사 (talk ×17) | 9,822 | 161,740 |
| 재판소·시스템 (InProgramTxtDB) | 2,911 | 45,727 |
| 기술·마법·이노센트 등 6종 | 2,044 | 27,857 |
| 메뉴·UI (script00) | 1,102 | 9,360 |
| 유닛 기본 이름 풀 | 906 | 3,214 |
| 캐릭터·클래스명 | 578 | 2,394 |
| 오프닝·엔딩 나레이션 | 23 | 348 |
| **합계** | **17,386** | **약 25만 자** |

이미지 작업: 타이틀 로고, 대사창 이름표, 오프닝 나레이션.

## 저장소에 없는 것

게임 데이터는 저작물이므로 포함하지 않습니다. 빌드에는 일본판 원본 ISO가 필요합니다.

- ISO, 추출 아카이브(`SCRIPTPACK` `START_JP` `TXPPACK` 등), 폰트·텍스처
- 복호 EBOOT, RAM 덤프
- 패처 리소스(`D2_ISO_ranges.bin`)와 빌드된 실행 파일 — 패치된 게임 데이터를 담으므로
  저장소에 커밋하지 않고 Release 첨부로만 배포합니다

## 구성

```
tools/              도구 체인 (포맷 파서, 폰트 베이크, 빌드, 검증)
work/tr_*.py        번역 소스 (원문 → 한국어 딕셔너리)
work/GLOSSARY.md    번역 규칙·용어집
iso_quickpatch/     ISO 제자리 패처 (C# GUI + 구간 리소스 생성기)
HANDOFF.md          포맷 규명·함정·실패 기록 전체 (기술 문서)
```

## 빌드

일본판 원본 ISO를 `../` 에 두고 순서대로 실행합니다. **순서를 지켜야 합니다.**

```bash
python tools/bake_font.py            # 폰트 (한글 1,625자 + 전각 영숫자 복원)
python tools/merge_tr.py             # script00 번역 병합·검증
python tools/build_jp.py  --iso      # START 아카이브 + EBOOT 주입
python tools/build_talk.py --iso     # SCRIPTPACK (대사 + 나레이션)
python tools/build_char.py --iso     # 대사창 이름표
python tools/build_nameplate.py --iso  # name.txp 아틀라스
python tools/build_title.py --iso    # 타이틀 로고 (nameplate 뒤에)
python tools/build_names.py --iso    # 루트 NAME.DAT
python tools/build_vmnames.py --iso  # 유닛 이름 풀 (실제 사용처)
python tools/build_opening_text.py --iso  # 오프닝 나레이션 (ANMPACK/anm7101)
python tools/verify_iso.py           # 정적 검증
```

패처 생성:

```bash
python iso_quickpatch/build_range_pack.py

csc /target:winexe /optimize+ \
  /out:iso_quickpatch/D2_ISO_QuickPatch.exe \
  /resource:iso_quickpatch/D2_ISO_ranges.bin,D2_ISO_ranges.bin \
  iso_quickpatch/D2IsoQuickPatch.cs
```

## 기술 메모

규명한 포맷과 겪은 함정은 `HANDOFF.md` 에 전부 적혀 있습니다. 핵심만 옮기면:

- **대사 렌더러는 고정 바이트 오프셋으로 줄을 자른다.** 일본어는 전부 2바이트라 항상 문자
  경계에 맞지만, 1바이트 ASCII가 섞이면 그 뒤가 밀려 글자가 깨진다. 그래서 대사는 공백·
  구두점·숫자·영문까지 **모든 문자를 전각**으로 넣는다.
- **한글 코드의 후행바이트는 `0x80~0xFC` 만 쓴다.** `<0x80` 은 일부 값에서 포인터가 1바이트만
  전진해 후행바이트가 ASCII로 한 번 더 그려진다.
- **talk 공용 버퍼가 `0x318F8`(203,000B)** 이라 전량 전각화가 들어가지 않는다.
  EBOOT 9워드를 패치해 `0x36000`(221,184B)으로 확장한다.
- 원본 폰트가 `? ~ : '` 등의 글리프를 비워둔 것은 누락이 아니라 **바이트코드에 섞인 ASCII를
  화면에서 숨기는 장치**다. 채우면 대사창에 쓰레기가 드러난다.

## 알려진 미번역

- 지명 간판 (`ホルルト村` 등) — 출처 미특정
