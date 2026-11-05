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
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_outcome_file(outcome_path: str) -> Dict[str, Any]:
    """Parse an outcome.yml file and extract relevant fields."""
    with open(outcome_path, 'r') as f:
        data = yaml.safe_load(f)

    return {
        'passed': data.get('passed'),
        'allowed_failure': data.get('allowed_failure'),
        'features': data.get('features'),
        'requires_revision': data.get('requires_revision'),
        'feature_sections': data.get('feature_sections'),
        'title': data.get('title'),
        'commands': data.get('commands'),
        'stdout': data.get('stdout'),
        'stderr': data.get('stderr'),
    }


def collect_results(result_dirs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect results from one or more compiler result directories.
    Returns a dict mapping compiler name -> list of test results.

    Assumes format: results/<compiler_name>/test_category/.../outcome.yml
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

        # Find all outcome.yml files
        for root, dirs, files in os.walk(result_dir):
            if 'outcome.yml' in files:
                outcome_path = os.path.join(root, 'outcome.yml')
                result = parse_outcome_file(outcome_path)
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
                 results_by_compiler: Dict[str, List[Dict[str, Any]]],
                 format_type: str = 'table') -> str:
    """Generate output in the specified format."""

    # Collect all categories and sort them
    categories = sorted(groups.keys())

    # Calculate totals
    totals = calculate_totals(groups, compilers)

    if format_type == 'csv':
        lines = []
        lines.append(['Category'] + compilers)

        for cat in categories:
            row = [cat]
            for compiler in compilers:
                counts = groups[cat].get(compiler, {'pass': 0, 'total': 0})
                row.append(f"{counts['pass']}/{counts['total']}")
            lines.append(row)

        # Totals row - calculate from actual unique test cases, not sum of cells
        actual_totals = {compiler: {'pass': 0, 'total': 0} for compiler in compilers}
        for compiler, results in results_by_compiler.items():
            actual_totals[compiler]['total'] = len(results)
            actual_totals[compiler]['pass'] = sum(1 for r in results if r['passed'])

        totals_row = ['Total']
        for compiler in compilers:
            totals_row.append(f"{actual_totals[compiler]['pass']}/{actual_totals[compiler]['total']}")
        lines.append(totals_row)

        return '\n'.join(','.join(str(x) for x in row) for row in lines)

    elif format_type == 'markdown':
        lines = []

        # Calculate max category width based on actual categories
        max_cat_width = max(len('Category'), *(len(cat) for cat in categories))
        # Calculate max total for padding (assume max 3 digits)
        max_total = max(
            (counts['total'] for cat_data in groups.values()
             for counts in cat_data.values()),
            default=100
        )
        num_digits = max(3, len(str(max_total)))
        # Cell content is "123 / 456" = digits + space + slash + space + digits = 2*num_digits + 3
        cell_content_width = 2 * num_digits + 3

        # Header
        header = f'| {"Category":<{max_cat_width}} | ' + ' | '.join(f'{c:>{cell_content_width}}' for c in compilers) + ' |'
        lines.append(header)

        # Separator - aligns with header column widths
        sep = f'|:{ "-" * max_cat_width }:-|' + ':'.join(f'{"-" * cell_content_width}' for _ in compilers) + ':|'
        lines.append(sep)

        # Data rows
        for cat in categories:
            row = f'| {cat:<{max_cat_width}} |'
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    # Format like "123 / 456" with consistent spacing
                    cell = f'{counts["pass"]:>{num_digits}} / {counts["total"]:>{num_digits}}'
                    row += f' {cell:>{cell_content_width}} |'
                else:
                    row += f' {"-":^{cell_content_width}} |'
            lines.append(row)

        # Separator before totals
        lines.append(sep)

        # Totals row - calculate from actual unique test cases, not sum of cells
        actual_totals = {compiler: {'pass': 0, 'total': 0} for compiler in compilers}
        for compiler, results in results_by_compiler.items():
            actual_totals[compiler]['total'] = len(results)
            actual_totals[compiler]['pass'] = sum(1 for r in results if r['passed'])

        totals_row = f'| {"Total":<{max_cat_width}} |'
        for compiler in compilers:
            totals_row += f' {actual_totals[compiler]["pass"]:>{num_digits}} / {actual_totals[compiler]["total"]:>{num_digits}} |'
        lines.append(totals_row)

        return '\n'.join(lines)

    elif format_type == 'json':
        # Calculate actual totals from unique test cases, not sum of cells
        actual_totals = {compiler: {'pass': 0, 'total': 0} for compiler in compilers}
        for compiler, results in results_by_compiler.items():
            actual_totals[compiler]['total'] = len(results)
            actual_totals[compiler]['pass'] = sum(1 for r in results if r['passed'])

        output = {'groups': {}, 'totals': actual_totals}
        for cat, compilers_data in groups.items():
            output['groups'][cat] = {}
            for compiler in compilers:
                output['groups'][cat][compiler] = compilers_data.get(compiler, {'pass': 0, 'total': 0})
        return json.dumps(output, indent=2)

    else:  # 'table' format (human-readable)
        lines = []

        # Calculate max category width based on actual categories
        max_cat_width = max(len('Category'), *(len(cat) for cat in categories))
        # Calculate max total for padding (assume max 3 digits)
        max_total = max(
            (counts['total'] for cat_data in groups.values()
             for counts in cat_data.values()),
            default=100
        )
        num_digits = max(3, len(str(max_total)))
        # Cell content is " 123 / 456 " = space + digits + space + slash + space + digits + space
        # = 1 + num_digits + 1 + 1 + 1 + num_digits + 1 = 2*num_digits + 6
        # But we want " 123 / 456" without trailing space = 2*num_digits + 5
        cell_content_width = 2 * num_digits + 5

        # Header
        header = f"{'Category':<{max_cat_width}} | " + ' | '.join(f'{c:>{cell_content_width}}' for c in compilers)
        lines.append(header)
        lines.append('-' * (max_cat_width + 3 + (cell_content_width + 2) * len(compilers)))

        # Data rows
        for cat in categories:
            row = f"{cat:<{max_cat_width}} |"
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    # Format like "123 / 456" with consistent spacing
                    cell = f'{counts["pass"]:>{num_digits}} / {counts["total"]:>{num_digits}}'
                    # Pad cell to cell_content_width (same width as header column)
                    row += f'{cell:>{cell_content_width}} |'
                else:
                    # Pad dash to cell_content_width
                    row += f'{"-":^{cell_content_width}} |'
            lines.append(row)

        # Separator before totals
        lines.append('-' * (max_cat_width + 3 + (cell_content_width + 2) * len(compilers)))

        # Totals row - calculate from actual unique test cases, not sum of cells
        actual_totals = {compiler: {'pass': 0, 'total': 0} for compiler in compilers}
        for compiler, results in results_by_compiler.items():
            actual_totals[compiler]['total'] = len(results)
            actual_totals[compiler]['pass'] = sum(1 for r in results if r['passed'])

        totals_row = f"{'Total':<{max_cat_width}} |"
        for compiler in compilers:
            totals_row += f' {actual_totals[compiler]["pass"]:>{num_digits}} / {actual_totals[compiler]["total"]:>{num_digits}} |'
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
    output = output_table(groups, compilers, results_by_compiler, args.format)
    print(output)


if __name__ == '__main__':
    main()
