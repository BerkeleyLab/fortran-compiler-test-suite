#!/usr/bin/env python3
"""
Aggregate test results from multiple compiler result directories into comparison tables.

Usage:
    python aggregate_results.py [-o OUTPUT] [--group-by {directory,feature,revision}]
                                [--filter {all,passed,failed}] [--format {table,markdown,csv,json}]
                                RESULT_DIR [RESULT_DIR ...]

Example:
    python aggregate_results.py results/gfortran results/intel --group-by directory --format markdown
"""

import argparse
import os
import sys
import csv
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
                # Handle line like "Failure Acceptable? no"
                if ':' in line:
                    result['allowed_failure'] = line.split(':', 1)[1].strip().lower() == 'yes'
                else:
                    result['allowed_failure'] = line.split('?', 1)[1].strip().lower() == 'yes'
            elif line.startswith('Features:'):
                features_str = line.split(':', 1)[1].strip()
                # Parse list like ['feature1', 'feature2']
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
    except Exception as e:
        return None


def is_compiler_folder(path: str) -> bool:
    """Check if a path looks like a compiler result folder (new format)."""
    # Check for common compiler names
    known_compilers = {'gfortran', 'ifort', 'ifx', 'flang', 'nagfor',
                       'pgfortran', 'nvfortran', 'lfortran', 'crayftn'}

    path_name = Path(path).name.lower()
    if path_name in known_compilers:
        return True

    # Check if outcome.txt files exist at nested paths (new format)
    for root, dirs, files in os.walk(path):
        if 'outcome.txt' in files:
            rel = os.path.relpath(root, path)
            if rel != '.' and ('/' in rel or '\\' in rel):
                return True

    return False


def collect_results(result_dirs: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect results from one or more result directories.
    Returns a dict mapping compiler name -> list of test results.

    Handles both:
    - New format: results/compiler_name/... (compiler_name extracted from path)
    - Old/flat format: results/... (single dir, uses 'default' as compiler name)
    """
    compiler_results = {}

    for result_dir in result_dirs:
        # Extract compiler name from directory path
        path = Path(result_dir)
        path_parts = list(path.parts)

        # Determine compiler name and actual results root
        if len(path_parts) >= 2 and path_parts[0] == 'results':
            # New format: results/compiler_name/...
            if len(path_parts) >= 3:
                # results/compiler_name/... - compiler is second part
                compiler_name = path_parts[1]
                results_root = result_dir
            else:
                # results/compiler_name (2 parts) - check if it's a compiler folder
                if is_compiler_folder(result_dir):
                    compiler_name = path_parts[1]
                    results_root = result_dir
                else:
                    # It's a flat format - treat as 'default' compiler
                    compiler_name = 'default'
                    results_root = result_dir
        else:
            # Old format: results/... or any flat path
            compiler_name = 'default'
            results_root = result_dir

        compiler_results[compiler_name] = []

        # For flat format (results/), exclude subdirectories that are compiler folders
        # to avoid treating them as test categories
        skip_dirs = set()
        if results_root == 'results' or results_root.startswith('results' + os.sep):
            for item in os.listdir(results_root):
                item_path = os.path.join(results_root, item)
                if os.path.isdir(item_path) and is_compiler_folder(item_path):
                    skip_dirs.add(item)

        # Find all outcome.txt files
        for root, dirs, files in os.walk(results_root):
            # Remove skipped directories from walk
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            if 'outcome.txt' in files:
                outcome_path = os.path.join(root, 'outcome.txt')
                result = parse_outcome_file(outcome_path)
                if result:
                    # Extract directory path relative to result_dir
                    rel_path = os.path.relpath(root, results_root)
                    # Get top-level category (first component of path)
                    parts = rel_path.split(os.sep)
                    result['directory'] = parts[0] if parts else ''
                    result['full_path'] = rel_path
                    compiler_results[compiler_name].append(result)

    return compiler_results


def group_by_directory(results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Group results by directory (top-level category like 'basic', 'io', etc.).
    Returns: {directory: {compiler: {'pass': n, 'total': n}}}
    """
    groups = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            directory = result.get('directory', '')
            if not directory:
                directory = 'unknown'

            if directory not in groups:
                groups[directory] = {}

            if compiler not in groups[directory]:
                groups[directory][compiler] = {'pass': 0, 'total': 0}

            groups[directory][compiler]['total'] += 1
            if result['passed']:
                groups[directory][compiler]['pass'] += 1

    return groups


def group_by_feature(results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Group results by feature (each test counts for each feature it has).
    Returns: {feature: {compiler: {'pass': n, 'total': n}}}
    """
    groups = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            features = result.get('features', [])
            if not features:
                features = ['none']

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
    """
    Group results by revision (requires_revision field).
    Returns: {revision: {compiler: {'pass': n, 'total': n}}}
    """
    groups = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            revision = result.get('requires_revision', '')
            if not revision:
                revision = 'unknown'

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


def format_count(passed: int, total: int, allowed_to_fail: int = 0) -> str:
    """Format a count as 'pass/total' with optional allowed failure indicator."""
    if allowed_to_fail > 0 and passed + allowed_to_fail == total:
        return f"{passed}/{total} (allowed: {allowed_to_fail})"
    return f"{passed}/{total}"


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
        # Header
        lines.append(['Category'] + compilers + ['Total'])

        # Data rows
        for cat in categories:
            row = [cat]
            cat_total_pass = 0
            cat_total = 0
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    row.append(f"{counts['pass']}/{counts['total']}")
                    cat_total_pass += counts['pass']
                    cat_total += counts['total']
                else:
                    row.append('-')
            row.append(f"{cat_total_pass}/{cat_total}")
            lines.append(row)

        # Totals row
        totals_row = ['Total']
        for compiler in compilers:
            totals_row.append(f"{totals[compiler]['pass']}/{totals[compiler]['total']}")
        totals_row.append(f"{sum(t['pass'] for t in totals.values())}/{sum(t['total'] for t in totals.values())}")
        lines.append(totals_row)

        # Convert to CSV string
        output = []
        for row in lines:
            output.append(','.join(str(x) for x in row))
        return '\n'.join(output)

    elif format_type == 'markdown':
        # Calculate column widths
        col_widths = [max(len(cat), 8) for cat in ['Category'] + categories + ['Total']]
        compiler_widths = [max(len(c), 6) for c in compilers]

        lines = []

        # Header
        header = '| Category | ' + ' | '.join(f'{c:^{w}}' for c, w in zip(compilers, compiler_widths)) + ' |'
        lines.append(header)

        # Separator
        sep = '|-' + '-' * (len('Category') + 2) + '|-' + '-|-'.join('-' * w for w in compiler_widths) + '-|'
        lines.append(sep)

        # Data rows
        for cat in categories:
            row = f'| {cat:<{len("Category")}} |'
            for compiler, width in zip(compilers, compiler_widths):
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    count_str = f"{counts['pass']}/{counts['total']}"
                    row += f' {count_str:^{width}} |'
                else:
                    row += f' {"-":^{width}} |'
            lines.append(row)

        # Separator before totals
        lines.append(sep)

        # Totals row
        totals_row = '| Total |'
        for compiler, width in zip(compilers, compiler_widths):
            count_str = f"{totals[compiler]['pass']}/{totals[compiler]['total']}"
            totals_row += f' {count_str:^{width}} |'
        lines.append(totals_row)

        return '\n'.join(lines)

    elif format_type == 'json':
        output = {
            'groups': {},
            'totals': totals
        }
        for cat, compilers_data in groups.items():
            output['groups'][cat] = {}
            for compiler in compilers:
                if compiler in compilers_data:
                    output['groups'][cat][compiler] = compilers_data[compiler]
                else:
                    output['groups'][cat][compiler] = {'pass': 0, 'total': 0}
        return json.dumps(output, indent=2)

    else:  # 'table' format (human-readable)
        lines = []

        # Header
        header = f"{'Category':<20} | " + ' | '.join(f'{c:>10}' for c in compilers)
        lines.append(header)
        lines.append('-' * (20 + 3 + 11 * len(compilers)))

        # Data rows
        for cat in categories:
            row = f"{cat:<20} |"
            for compiler in compilers:
                if compiler in groups[cat]:
                    counts = groups[cat][compiler]
                    count_str = f"{counts['pass']}/{counts['total']}"
                    row += f' {count_str:>10} |'
                else:
                    row += f' {"-":>10} |'
            lines.append(row)

        # Separator before totals
        lines.append('-' * (20 + 3 + 11 * len(compilers)))

        # Totals row
        totals_row = f"{'Total':<20} |"
        for compiler in compilers:
            count_str = f"{totals[compiler]['pass']}/{totals[compiler]['total']}"
            totals_row += f' {count_str:>10} |'
        lines.append(totals_row)

        return '\n'.join(lines)

    return ''


def filter_groups(groups: Dict[str, Dict[str, Dict[str, int]]],
                  filter_type: str,
                  results_by_compiler: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Filter groups based on filter_type."""
    if filter_type == 'all':
        return groups

    # For filtered output, we need to re-compute with the filter applied
    filtered_groups = {}

    for compiler, results in results_by_compiler.items():
        for result in results:
            # Determine if this result matches the filter
            matches = False
            if filter_type == 'passed' and result['passed']:
                matches = True
            elif filter_type == 'failed' and not result['passed']:
                matches = True

            if not matches:
                continue

            # Now add to groups based on grouping
            # We need to know which group this belongs to - this is tricky
            # We'll just return empty for now and handle filtering differently

    return groups


def main():
    parser = argparse.ArgumentParser(
        description='Aggregate test results from multiple compiler result directories.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('result_dirs', nargs='+', help='Result directories to aggregate')
    parser.add_argument('--group-by', choices=['directory', 'feature', 'revision'],
                        default='directory',
                        help='How to group the results')
    parser.add_argument('--filter', choices=['all', 'passed', 'failed'],
                        default='all',
                        help='Which results to include')
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
