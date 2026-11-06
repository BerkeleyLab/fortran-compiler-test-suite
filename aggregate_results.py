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
import sys
from pathlib import Path
from typing import Dict, List
from framework.test_result import TestResult


def collect_results(result_dirs: List[str]) -> Dict[str, List[TestResult]]:
    """
    Collect results from one or more compiler result directories.
    Returns a dict mapping compiler name -> list of test results.
    """
    compiler_results: Dict[str, List[TestResult]] = {}

    for result_dir in result_dirs:
        path = Path(result_dir)
        compiler_name = path.name

        compiler_results[compiler_name] = []

        # Find all outcome.yml files and parse them using TestResult
        for outcome_path in path.rglob('outcome.yml'):
            result = TestResult.from_yaml(outcome_path.read_text())
            # Calculate relative path components
            rel_path = outcome_path.parent.relative_to(path)
            result.directory = rel_path.parts[0]
            result.full_path = str(rel_path)
            compiler_results[compiler_name].append(result)

    return compiler_results


def group_results(
    results_by_compiler: Dict[str, List[TestResult]],
    key_func: callable
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Group results by a key derived from each result.

    Args:
        results_by_compiler: Dict mapping compiler name to list of results
        key_func: Function that extracts the grouping key from a TestResult

    Returns:
        Dict mapping group key -> compiler -> {pass, total counts}
    """
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            key = key_func(result)

            if key not in groups:
                groups[key] = {}

            if compiler not in groups[key]:
                groups[key][compiler] = {'pass': 0, 'total': 0}

            groups[key][compiler]['total'] += 1
            if not result.failed():
                groups[key][compiler]['pass'] += 1

    return groups


def _group_by_feature(
    results_by_compiler: Dict[str, List[TestResult]]
) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Special grouping for features - each test counts for each feature it has."""
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            for feature in result.features or ['none']:
                if feature not in groups:
                    groups[feature] = {}

                if compiler not in groups[feature]:
                    groups[feature][compiler] = {'pass': 0, 'total': 0}

                groups[feature][compiler]['total'] += 1
                if not result.failed():
                    groups[feature][compiler]['pass'] += 1

    return groups


def calculate_actual_totals(
    results_by_compiler: Dict[str, List[TestResult]]
) -> Dict[str, Dict[str, int]]:
    """Calculate totals from actual unique test cases per compiler."""
    return {
        compiler: {
            'total': len(results),
            'pass': sum(1 for r in results if not r.failed())
        }
        for compiler, results in results_by_compiler.items()
    }


def output_table(
    groups: Dict[str, Dict[str, Dict[str, int]]],
    compilers: List[str],
    actual_totals: Dict[str, Dict[str, int]],
    format_type: str = 'table'
) -> str:
    """Generate output in the specified format."""
    from tabulate import tabulate

    categories = sorted(groups.keys())

    if not categories:
        return ''

    # Build table data
    table_data = []
    for cat in categories:
        row = {'Category': cat}
        for compiler in compilers:
            counts = groups[cat][compiler]
            percent = counts['pass'] / counts['total']
            row[compiler] = f"{counts['pass']:<3} / {counts['total']:<3} ({percent:6.1%})"
        table_data.append(row)

    # Add totals row
    totals_row = {'Category': 'Total'}
    for compiler in compilers:
        percent = actual_totals[compiler]['pass'] / actual_totals[compiler]['total']
        totals_row[compiler] = f"{actual_totals[compiler]['pass']:<3} / {actual_totals[compiler]['total']:<3} ({percent:6.1%})"
    table_data.append(totals_row)

    # Convert to list of lists for tabulate
    headers = ['Category'] + compilers
    rows = [[d['Category']] + [d[c] for c in compilers] for d in table_data]

    if format_type == 'csv':
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().strip()

    elif format_type == 'json':
        import json
        output = {'groups': {}, 'totals': actual_totals}
        for cat, compilers_data in groups.items():
            output['groups'][cat] = {}
            for compiler in compilers:
                output['groups'][cat][compiler] = compilers_data[compiler]
        return json.dumps(output, indent=2)

    else:
        # table or markdown format
        table = tabulate(rows, headers=headers, tablefmt=format_type)
        return table


def main():
    parser = argparse.ArgumentParser(
        description='Aggregate test results from multiple compiler result directories.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        'result_dirs',
        nargs='+',
        help='Result directories (e.g., results/gfortran results/intel)'
    )
    parser.add_argument(
        '--group-by',
        choices=['directory', 'feature', 'revision'],
        default='directory',
        help='How to group the results'
    )
    parser.add_argument(
        '--format',
        choices=['table', 'markdown', 'csv', 'json'],
        default='table',
        help='Output format'
    )

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
        groups = group_results(results_by_compiler, lambda r: r.directory or 'unknown')
    elif args.group_by == 'feature':
        groups = _group_by_feature(results_by_compiler)
    elif args.group_by == 'revision':
        groups = group_results(results_by_compiler, lambda r: r.requires_revision or 'unknown')

    # Calculate actual totals from unique test cases
    actual_totals = calculate_actual_totals(results_by_compiler)

    # Generate output
    output = output_table(groups, compilers, actual_totals, args.format)
    print(output)


if __name__ == '__main__':
    main()
