"""Print a coverage summary from cargo-llvm-cov's JSON, and enforce minimums.

    cargo +nightly llvm-cov --package pybars3-compiler --all-targets --branch \\
        --json --summary-only --output-path coverage.json
    python3 tools/check_coverage.py coverage.json --branches 95 --lines 98

cargo-llvm-cov can fail under a line or region percentage, but not under a
branch percentage; this does all three.
"""

import argparse
import json
from pathlib import Path
import sys

KINDS = ('lines', 'regions', 'branches')


def percent(summary, kind):
    count = summary[kind]['count']
    return 100.0 * summary[kind]['covered'] / count if count else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('report', type=Path, help='the JSON from cargo llvm-cov --json --summary-only')
    for kind in KINDS:
        parser.add_argument(f'--{kind}', type=float, default=0.0, metavar='PERCENT', help=f'minimum {kind} coverage')
    args = parser.parse_args()
    data = json.loads(args.report.read_text())['data'][0]
    root = Path.cwd().resolve()
    print(f"{'file':<48} " + ' '.join(f'{kind:>9}' for kind in KINDS))
    for file in data['files']:
        name = Path(file['filename']).resolve()
        label = str(name.relative_to(root)) if name.is_relative_to(root) else str(name)
        values = [percent(file['summary'], kind) for kind in KINDS]
        print(f'{label:<48} ' + ' '.join(f'{v:8.2f}%' if v is not None else f"{'-':>9}" for v in values))
    failed = False
    totals = [percent(data['totals'], kind) for kind in KINDS]
    print(f"{'TOTAL':<48} " + ' '.join(f'{v:8.2f}%' if v is not None else f"{'-':>9}" for v in totals))
    for kind, value in zip(KINDS, totals, strict=True):
        minimum = getattr(args, kind)
        if value is not None and value < minimum:
            print(f'{kind} coverage {value:.2f}% is below the minimum of {minimum}%', file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
