"""Static dialogue-length triage, not a proof of in-game clipping.

Groups only adjacent inline strings separated by 00 01. Reports a conservative
28-cell screening threshold; actual available width/scale is scene-dependent.
Does not alter translations. Proposals preserve words and existing line count.
"""
import ast
import collections
import csv
import json
from pathlib import Path
import textwrap

import krtext
import scriptpack
import talkfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build_dialogue_20260905'
LIMIT = 28


def main():
    translations, locations = {}, {}
    for path in sorted((ROOT / 'work').glob('tr_talk*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == 'T' for t in stmt.targets):
                continue
            if not isinstance(stmt.value, ast.Dict):
                raise ValueError(f'Nonliteral translation dictionary: {path}')
            for key, value in zip(stmt.value.keys, stmt.value.values):
                jp, ko = ast.literal_eval(key), ast.literal_eval(value)
                translations[jp] = ko
                locations[jp] = f'{path.relative_to(ROOT).as_posix()}:{key.lineno}'

    # Model the documented EBOOT advance selection after talk fullwidth mapping.
    # 420 px is a screening budget (28*15), not a measured scene boundary.
    def advance(text):
        mapped = ''.join(chr(ord(c) + 0xFEE0) if '!' <= c <= '~'
                         else '\u3000' if c == ' ' else c for c in text)
        return sum(7 if krtext.encode(c) in
                   [bytes([0x81, b]) for b in range(0x40, 0x45)]
                   else 15 for c in mapped)

    groups = {}
    occurrences = translated_occurrences = 0
    original_lengths = collections.Counter()
    archives = scriptpack.unpack((ROOT / 'jp/SCRIPTPACK.DAT').read_bytes())
    members = 0
    for entry in archives:
        if not entry['name'].startswith('talk'):
            continue
        members += 1
        data = entry['data']
        runs = []
        for off, raw in talkfile.strings(data):
            occurrences += 1
            jp = raw.decode('cp932', errors='replace')
            original_lengths[len(jp)] += 1
            if jp in translations:
                translated_occurrences += 1
            if runs and data[runs[-1][-1][0] + len(runs[-1][-1][1]):off] == b'\x00\x01':
                runs[-1].append((off, raw))
            else:
                runs.append([(off, raw)])
        for run in runs:
            keys = tuple(raw.decode('cp932', errors='replace') for _, raw in run)
            if not all(key in translations for key in keys):
                continue
            lines = [translations[key] for key in keys]
            if max(map(len, lines)) <= LIMIT:
                continue
            if keys in groups:
                groups[keys]['occurrences'] += 1
                continue
            joined = ' '.join(lines)
            proposed = textwrap.wrap(joined, width=LIMIT, break_long_words=False,
                                     break_on_hyphens=False)
            fits = len(proposed) <= len(lines) and all(len(s) <= LIMIT for s in proposed)
            assert ' '.join(proposed).split() == joined.split()
            groups[keys] = {
                'member': entry['name'], 'offset': hex(run[0][0]),
                'source': ' | '.join(locations[key] for key in keys),
                'occurrences': 1, 'line_count': len(lines),
                'max_cells': max(map(len, lines)),
                'max_estimated_px': max(advance(s) for s in lines),
                'current_lines': lines,
                'proposal': proposed if fits else [],
                'classification': 'existing_lines_fit' if fits else 'needs_layout_review',
            }
    rows = sorted(groups.values(), key=lambda r: (-r['max_estimated_px'], -r['max_cells']))
    summary = {
        'talk_members': members, 'unique_translations': len(translations),
        'string_occurrences': occurrences, 'translated_occurrences': translated_occurrences,
        'screening_cells': LIMIT, 'screening_px': LIMIT * 15,
        'candidate_unique_groups': len(rows),
        'candidate_unique_lines': len({key for keys in groups for key in keys
                                       if len(translations[key]) > LIMIT}),
        'estimated_over_420px_groups': sum(r['max_estimated_px'] > LIMIT * 15 for r in rows),
        'existing_lines_fit': sum(r['classification'] == 'existing_lines_fit' for r in rows),
        'needs_layout_review': sum(r['classification'] == 'needs_layout_review' for r in rows),
        'original_max_chars': max(original_lengths),
        'original_over_28_occurrences': sum(n for length, n in original_lengths.items() if length > LIMIT),
        'limitations': 'Static candidates only; 28 cells/420px are screening thresholds, not measured renderer limits. '
                       'Inline groups can include non-dialogue text. Excludes InProgramTxtDB and DLC EDAT. '
                       'Proposals need scene/context and source-reuse review before application.',
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'dialogue_audit.json').write_text(json.dumps({'summary': summary, 'groups': rows},
                                                        ensure_ascii=False, indent=2), encoding='utf-8')
    if rows:
        with (OUT / 'dialogue_audit.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({k: '\n'.join(v) if isinstance(v, list) else v for k, v in r.items()} for r in rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
