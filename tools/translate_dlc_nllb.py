# -*- coding: utf-8 -*-
"""dlc_untranslated.tsv를 로컬 NLLB로 초벌 번역한다.

결과는 별도 TSV에 기록한다. 게임 제어 표식 `￥`과 괄호형 토큰은 번역기에
보내지 않고 원위치에 보존한다. 이 결과는 최종본이 아니라 사람 검수용 초벌이다.
"""
import csv
import pathlib
import re
import sys

import ctranslate2
import sentencepiece as spm

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
MODEL = ROOT.parent / 'work_ogmd' / 'models' / 'nllb-200-distilled-600M-ct2-int8'
SOURCE = ROOT / 'work' / 'dlc_untranslated.tsv'
OUTPUT = ROOT / 'work' / 'dlc_translated_nllb.tsv'

# ￥는 이 게임의 개행/페이지 관련 표식이다. 나머지는 일반적인 서식 토큰 방어용.
PROTECTED = re.compile(r'(￥|<[^>]*>|%[-+0-9.]*[A-Za-z]|\\[nrt]|@[A-Za-z0-9_]*|\[[^\]]*\]|\{[^}]*\})')


def has_japanese(text):
    return any('\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' for c in text)


class NLLB:
    def __init__(self):
        # SentencePiece의 Windows 파일 API는 경로에 한글이 있으면 Error #42를 낸다.
        # 모델 바이트를 Python으로 읽어 넘기면 같은 모델을 경로 제약 없이 쓸 수 있다.
        self.sp = spm.SentencePieceProcessor(
            model_proto=(MODEL / 'sentencepiece.bpe.model').read_bytes()
        )
        self.translator = ctranslate2.Translator(
            str(MODEL), device='cpu', inter_threads=2, intra_threads=0,
        )
        self.cache = {}

    def translate_many(self, texts):
        pending = [text for text in dict.fromkeys(texts) if text not in self.cache and has_japanese(text)]
        for start in range(0, len(pending), 24):
            batch = pending[start:start + 24]
            sources = [self.sp.encode(text, out_type=str) + ['</s>', 'jpn_Jpan'] for text in batch]
            results = self.translator.translate_batch(
                sources,
                target_prefix=[['kor_Hang']] * len(batch),
                beam_size=3,
                max_decoding_length=256,
            )
            for source, result in zip(batch, results):
                tokens = [t for t in result.hypotheses[0] if t not in ('kor_Hang', '</s>')]
                value = self.sp.decode(tokens).strip()
                value = re.sub(r'^(그리고|또한)\s+', '', value)
                self.cache[source] = value
            done = min(start + len(batch), len(pending))
            print(f'NLLB {done}/{len(pending)}', flush=True)


def pieces(text):
    return [part for part in PROTECTED.split(text) if part]


def main():
    with SOURCE.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))

    segments = []
    for row in rows:
        for part in pieces(row['jp']):
            if not PROTECTED.fullmatch(part) and has_japanese(part):
                segments.append(part)

    model = NLLB()
    model.translate_many(segments)

    for row in rows:
        out = []
        for part in pieces(row['jp']):
            if PROTECTED.fullmatch(part) or not has_japanese(part):
                out.append(part)
            else:
                out.append(model.cache.get(part, part))
        row['ko'] = ''.join(out)

    with OUTPUT.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    print(f'출력: {OUTPUT} ({len(rows):,}건)')


if __name__ == '__main__':
    main()
