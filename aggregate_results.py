#!/usr/bin/env python3
"""
Aggregate test results from multiple compiler result directories into comparison tables.

Results are expected to be in the format: results/<compiler_name>/...

Usage:
    python aggregate_results.py [--group-by {directory,feature,revision}]
                                [--format {table,markdown,csv,json}]
                                RESULT_DIR [RESULT_DIR ...]

Example:
    python aggregate_results.py results/gfortran results/intel --group-by directory --format markdown

Grouping options:
  - directory: Group by top-level directory (basic, io, control, etc.)
  - feature: Group by feature (each test counts for each feature it has)
  - revision: Group by Fortran revision (requires_revision field)
"""

import argparse
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_outcome_file(outcome_path: str) -> Optional[Dict[str, Any]]:
    """Parse an outcome.txt file and extract relevant fields."""
    try:
        with open(outcome_path, 'r') as f:
            content = f.read()

        result = {
            'passed': False,
            'allowed_failure': False,
            'features': [],
            'requires_revision': '',
            'feature_sections': [],
            'title': ''
        }

        for line in content.split('\n'):
            if line.startswith('Case:'):
                result['title'] = line.split(':', 1)[1].strip()
            elif line.startswith('Passed:'):
                result['passed'] = line.split(':', 1)[1].strip().lower() == 'true'
            elif line.startswith('Failure Acceptable?'):
                if ':' in line:
                    result['allowed_failure'] = line.split(':', 1)[1].strip().lower() == 'yes'
                else:
                    result['allowed_failure'] = line.split('?', 1)[1].strip().lower() == 'yes'
            elif line.startswith('Features:'):
                features_str = line.split(':', 1)[1].strip()
                if features_str and features_str != '[]':
                    features = features_str.strip('[]').replace("'", '').replace('"', '').split(', ')
                    result['features'] = [f.strip() for f in features if f.strip()]
            elif line.startswith('Requires Revision:'):
                result['requires_revision'] = line.split(':', 1)[1].strip()
            elif line.startswith('Feature Sections:'):
                sections_str = line.split(':', 1)[1].strip()
                if sections_str and sections_str != '[]':
                    sections = sections_str.strip('[]').replace("'", '').replace('"', '').split(', ')
                    result['feature_sections'] = [s.strip() for s in sections if s.strip()]

        return result
    except Exception:
        return None


def collect_results(result_dirs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect results from one or more compiler result directories.
    Returns a dict mapping compiler name -> list of test results.

    Assumes format: results/<compiler_name>/test_category/.../outcome.txt
    The compiler name is extracted from the directory path.
    """
    compiler_results: Dict[str, List[Dict[str, Any]]] = {}

    for result_dir in result_dirs:
        # Extract compiler name from path (second-to-last component)
        path = Path(result_dir)
        parts = list(path.parts)

        # Get compiler name from the directory name
        compiler_name = path.name

        compiler_results[compiler_name] = []

        # Find all outcome.txt files
        for root, dirs, files in os.walk(result_dir):
            if 'outcome.txt' in files:
                outcome_path = os.path.join(root, 'outcome.txt')
                result = parse_outcome_file(outcome_path)
                if result:
                    # Extract directory path relative to result_dir
                    rel_path = os.path.relpath(root, result_dir)
                    # Get top-level category (first component of path)
                    parts = rel_path.split(os.sep)
                    result['directory'] = parts[0] if parts and parts[0] else ''
                    result['full_path'] = rel_path
                    compiler_results[compiler_name].append(result)

    return compiler_results


def group_by_directory(results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Group results by directory (top-level category like 'basic', 'io', etc.)."""
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            directory = result.get('directory', '') or 'unknown'

            if directory not in groups:
                groups[directory] = {}

            if compiler not in groups[directory]:
                groups[directory][compiler] = {'pass': 0, 'total': 0}

            groups[directory][compiler]['total'] += 1
            if result['passed']:
                groups[directory][compiler]['pass'] += 1

    return groups


def group_by_feature(results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Group results by feature (each test counts for each feature it has)."""
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            features = result.get('features', []) or ['none']

            for feature in features:
                if feature not in groups:
                    groups[feature] = {}

                if compiler not in groups[feature]:
                    groups[feature][compiler] = {'pass': 0, 'total': 0}

                groups[feature][compiler]['total'] += 1
                if result['passed']:
                    groups[feature][compiler]['pass'] += 1

    return groups


def group_by_revision(results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Group results by revision (requires_revision field)."""
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            revision = result.get('requires_revision', '') or 'unknown'

            if revision not in groups:
                groups[revision] = {}

            if compiler not in groups[revision]:
                groups[revision][compiler] = {'pass': 0, 'total': 0}

            groups[revision][compiler]['total'] += 1
            if result['passed']:
                groups[revision][compiler]['pass'] += 1

    return groups


def calculate_totals(groups: Dict[str, Dict[str, Dict[str, int]]],
                     compilers: List[str]) -> Dict[str, Dict[str, int]]:
    """Calculate total counts across all groups for each compiler."""
    totals = {compiler: {'pass': 0, 'total': 0} for compiler in compilers}

    for directory, compiler_counts in groups.items():
        for compiler in compilers:
            if compiler in compiler_counts:
                totals[compiler]['pass'] += compiler_counts[compiler]['pass']
                totals[compiler]['total'] += compiler_counts[compiler]['total']

    return totals


def output_table(groups: Dict[str, Dict[str, Dict[str, int]]],
                 compilers: List[str],
                 format_type: str = 'table') -> str:
    """Generate output in the specified format."""

    # Collect all categories and sort them
    categories = sorted(groups.keys())

    # Calculate totals
    totals = calculate_totals(groups, compilers)

    if format_type == 'csv':
        lines = []
        lines.append(['Category'] + compilers + ['Total'])

        for cat in categories:
            row = [cat]
            cat_pass = sum(groups[cat].get(c, {}).get('pass', 0) for c in compilers)
            cat_total = sum(groups[cat].get(c, {}).get('total', 0) for c in compilers)
            for compiler in compilers:
                counts = groups[cat].get(compiler, {'pass': 0, 'total': 0})
                row.append(f"{counts['pass']}/{counts['total']}")
            row.append(f"{cat_pass}/{cat_total}")
            lines.append(row)

        totals_row = ['Total']
        for compiler in compilers:
            totals_row.append(f"{totals[compiler]['pass']}/{totals[compiler]['total']}")
        totals_row.append(f"{sum(t['pass'] for t in totals.values())}/{sum(t['total'] for t in totals.values())}")
        lines.append(totals_row)

        return '\n'.join(','.join(str(x) for x in row) for row in lines)

    elif format_type == 'markdown':
        lines = []

        # Header
        header = '| Category | ' + ' | '.join(f'{c:^12}' for c in compilers) + ' |'
        lines.append(header)

        # Separator
        sep = '|-' + '-' * 10 + '|-' + '-|-'.join('-' * 12 for _ in compilers) + '-|'
        lines.append(sep)

        # Data rows
        for cat in categories:
            row = f'| {cat:<10} |'
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    row += f' {counts["pass"]}/{counts["total"]:^10} |'
                else:
                    row += f' {"-":^10} |'
            lines.append(row)

        # Separator before totals
        lines.append(sep)

        # Totals row
        totals_row = '| Total |'
        for compiler in compilers:
            count_str = f"{totals[compiler]['pass']}/{totals[compiler]['total']}"
            totals_row += f' {count_str:^10} |'
        lines.append(totals_row)

        return '\n'.join(lines)

    elif format_type == 'json':
        output = {'groups': {}, 'totals': totals}
        for cat, compilers_data in groups.items():
            output['groups'][cat] = {}
            for compiler in compilers:
                output['groups'][cat][compiler] = compilers_data.get(compiler, {'pass': 0, 'total': 0})
        return json.dumps(output, indent=2)

    else:  # 'table' format (human-readable)
        lines = []

        # Header
        header = f"{'Category':<12} | " + ' | '.join(f'{c:>12}' for c in compilers)
        lines.append(header)
        lines.append('-' * (12 + 3 + 13 * len(compilers)))

        # Data rows
        for cat in categories:
            row = f"{cat:<12} |"
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    row += f' {counts["pass"]}/{counts["total"]:>10} |'
                else:
                    row += f' {"-":>12} |'
            lines.append(row)

        # Separator before totals
        lines.append('-' * (12 + 3 + 13 * len(compilers)))

        # Totals row
        totals_row = f"{'Total':<12} |"
        for compiler in compilers:
            count_str = f"{totals[compiler]['pass']}/{totals[compiler]['total']}"
            totals_row += f' {count_str:>10} |'
        lines.append(totals_row)

        return '\n'.join(lines)

    return ''


def main():
    parser = argparse.ArgumentParser(
        description='Aggregate test results from multiple compiler result directories.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('result_dirs', nargs='+', help='Result directories (e.g., results/gfortran results/intel)')
    parser.add_argument('--group-by', choices=['directory', 'feature', 'revision'],
                        default='directory',
                        help='How to group the results')
    parser.add_argument('--format', choices=['table', 'markdown', 'csv', 'json'],
                        default='table',
                        help='Output format')

    args = parser.parse_args()

    # Collect results from all directories
    results_by_compiler = collect_results(args.result_dirs)

    if not results_by_compiler:
        print("No results found in the specified directories.")
        sys.exit(1)

    # Get sorted list of compilers
    compilers = sorted(results_by_compiler.keys())

    # Group results
    if args.group_by == 'directory':
        groups = group_by_directory(results_by_compiler)
    elif args.group_by == 'feature':
        groups = group_by_feature(results_by_compiler)
    elif args.group_by == 'revision':
        groups = group_by_revision(results_by_compiler)

    # Output in requested format
    output = output_table(groups, compilers, args.format)
    print(output)


if __name__ == '__main__':
    main()
