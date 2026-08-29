# 마계전기 디스가이아 2 PORTABLE 한국어화

PSP판 『魔界戦記ディスガイア2 PORTABLE』(일본판, `ULJS00183`) 한국어화 프로젝트의
도구 체인과 번역 소스입니다.

> v20260827부터 EBOOT을 **원본과 같은 type-1(`~PSP`) 형식으로 재암호화**해 넣습니다
> (재암호화 스크립트는 시놀부님 제공, `tools/psp_prx_type1.py`).
> v20260826까지는 평문 ELF로 교체해 PPSSPP 전용이었습니다.
> 다만 실기(PSP CFW)에서 실제로 부팅되는지는 아직 검증하지 못했습니다.

## 번역 분량

| 영역 | 건수 | 글자수 |
|---|---|---|
| 대사 (talk ×17) | 9,822 | 161,740 |
| 재판소·시스템 (InProgramTxtDB) | 2,911 | 45,727 |
| 기술·마법·이노센트 등 6종 | 2,044 | 27,857 |
| 메뉴·UI (script00) | 1,102 | 9,360 |
| 유닛 기본 이름 풀 | 906 | 3,214 |
| 스킬(고유기) 이름·설명 (char.dat) | 721 | |
| 암흑 의회 의안·설명 (START_VM_JP) | 610 | |
| 캐릭터·클래스명 | 578 | 2,394 |
| 스테이지·지명 (DUNGEON.DAT) | 165 | |
| 오프닝·엔딩 나레이션 | 23 | 348 |
| **합계** | **18,882** | **약 26만 자** |

이미지 작업: 타이틀 로고, 대사창 이름표, 오프닝 나레이션, 지명 간판(12개).

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
python tools/build_dlc.py             # DLC 18개 (코드표 동기화 검사 포함)
python tools/verify_dlc.py            # DLC 구조·번역·비대상 데이터 검증
python tools/verify_iso.py           # 정적 검증
```

패처 생성:

```bash
python iso_quickpatch/build_range_pack.py

csc /target:winexe /optimize+ \
  /out:iso_quickpatch/D2_Korean_QuickPatch.exe \
  iso_quickpatch/D2IsoQuickPatch.cs
```

> v20260829부터 구간 데이터를 exe에 **임베드하지 않습니다**(`/resource:` 없음).
> "작은 코드 + 11MB 불투명 블롭"인 미서명 exe가 Windows Defender 클라우드 ML의
> 오탐을 유발해 다운로드가 막힌다는 제보가 있었습니다. 이제 exe는 약 24KB이고
> `D2_ISO_ranges.bin`은 **같은 폴더의 별도 파일**로 배포합니다 — 배포 시 두 파일을
> 반드시 함께 두어야 합니다.

v20260830부터 빠른패처 하나에서 본편 ISO와 DLC를 함께 처리합니다. ISO와
`PSP/GAME/ULJS00183` 폴더를 선택하면 설치된 `DL_JP_00.EDAT`~`17.EDAT`만
파일별로 검사해 패치합니다. 설치되지 않은 번호는 오류나 빈 파일 생성 없이
건너뛰며, 해시가 다른 파일도 안전을 위해 수정하지 않습니다. DLC용 5개 xdelta와
`xdelta.exe`도 실행 파일과 같은 폴더에 둬야 합니다.

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

없습니다. 마지막까지 남아 있던 지명 간판(`ホルルト村` 등)은 v20260828에서
한글화했습니다 — 텍스트가 아니라 `ANMPACK/anm7151.dat` 안의 CLUT4 이미지였습니다
(`tools/build_signatlas.py`, 규격과 실패 기록은 `HANDOFF.md` §34).
