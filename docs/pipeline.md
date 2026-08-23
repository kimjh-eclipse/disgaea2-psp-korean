# 빌드 파이프라인

일본판 원본 ISO를 상위 폴더에 두고 **순서대로** 실행합니다.

```bash
python tools/bake_font.py            # 폰트 (한글 1,625자 + 전각 영숫자 62자 복원)
python tools/merge_tr.py             # script00 번역 병합·검증
python tools/build_jp.py  --iso      # START 아카이브 + EBOOT 주입
python tools/build_talk.py --iso     # SCRIPTPACK (대사 + 나레이션)
python tools/build_char.py --iso     # 대사창 이름표
python tools/build_nameplate.py --iso  # name.txp 아틀라스
python tools/build_title.py --iso    # 타이틀 로고
python tools/build_names.py --iso    # 루트 NAME.DAT
python tools/build_vmnames.py --iso  # 유닛 이름 풀 (실제 사용처)
python tools/verify_iso.py           # 정적 검증
```

## 순서가 중요한 이유

- `bake_font` 가 먼저여야 합니다. `krtext` 가 `build_jp/hangul_codes.tsv` 를 읽습니다.
- `build_nameplate` → `build_title` 순서를 지켜야 합니다. 둘 다 TXPPACK을 건드리며,
  `build_title` 은 기존 `build_jp/TXPPACK.DAT` 를 기반으로 삼아 이름표 작업을 보존합니다.
- `build_char` 를 생략하면 대사창 이름표가 일본어로 남습니다.

## 안전장치

빌드 도구가 스스로 막는 것들입니다.

- `build_jp` — 패치된 EBOOT(`EBOOT_KR.BIN`)가 없으면 중단. 무패치 EBOOT + 전량 전각화 조합 방지
- `build_talk` — talk 멤버가 `0x36000`(221,184B)을 넘으면 중단
- `build_talk` — SCRIPTPACK이 슬롯을 넘으면 재배치 대신 중단
- `recdat.put` — 고정 필드 폭 초과 시 예외
- `krtext.validate` — 인코딩 불가 문자와 **글리프가 비어 있는 ASCII** 거부
- `bake_font` — `work/tr_*.py` 전부를 읽어 사용 음절을 강제 포함(self-healing)

> `bake_font` 의 음절 수집은 패턴을 열거하지 않고 `work/tr_*.py` 전부를 읽습니다.
> 열거 방식이었을 때 새 파일 계열(`tr_char` `tr_iptxt` `tr_rec`)이 추가될 때마다
> 누락 사고가 났습니다.

## 검증

```bash
python tools/verify_iso.py     # 무손상·구조·내용 확인
python tools/scan_kanji.py     # 글리프 지운 한자 잔존 전수 검사
python tools/qa_tr.py talk     # 번역 QA (키·인코딩·서식·용어)
python tools/qa_rec.py         # 고정 필드 바이트 예산
```

`scan_kanji.py` 가 중요합니다. 번역률이 100%여도 인벤토리가 문자열을 놓쳤거나 다른 포맷에
있으면 원문이 남고, 글리프를 지웠으니 화면에서 빈칸이 됩니다. 실제로 이것으로
메모리스틱 관련 시스템 메시지 8건 누락을 찾았습니다(`textio.dump` 가 strict `shift_jis` 로
디코드해 cp932 전용 문자 `⑪ ④ ㍉` 가 든 문자열이 조용히 탈락).

## 패처 생성

```bash
python iso_quickpatch/build_range_pack.py

csc /target:winexe /optimize+ \
  /out:iso_quickpatch/D2_ISO_QuickPatch.exe \
  /resource:iso_quickpatch/D2_ISO_ranges.bin,D2_ISO_ranges.bin \
  iso_quickpatch/D2IsoQuickPatch.cs
```

해시가 원본·패치본에 고정되므로 **빌드가 바뀌면 리소스 재생성 + 재컴파일 + 왕복 재검증**
이 필요합니다.
