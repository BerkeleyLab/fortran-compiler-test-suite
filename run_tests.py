#!/usr/bin/env python3
"""
This is the entry point for running the compiler test framework.
"""

import argparse
import os
import re
import shutil
import sys
from framework.processor import Processor
from framework.test_case import create_test_case, is_test_case

# We handle the flags option manually
# because argparse yells about values with leading -
if '-f' in sys.argv:
    flag_start = sys.argv.index('-f')
elif '--flag' in sys.argv:
    flag_start = sys.argv.index('--flag')
else:
    flag_start = 0
# If there's nothing after the option, we'll let argparse yell about it
if flag_start == len(sys.argv)-1: flag_start = 0
flags = [] if flag_start == 0 else sys.argv[flag_start+1:]

parser = argparse.ArgumentParser(
    prog="run_tests.py",
    description="Run the Fortran compiler test suite",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument('-i', '--input', default="tests", help="Directory to search for the tests")
parser.add_argument('-o', '--output', default="results", help="Where to put the test results")
parser.add_argument('-c', '--compiler', default="gfortran", help="The compiler to test")
parser.add_argument('-C', '--c-compiler', default="", help="The companion C processor")
parser.add_argument('-v', '--verbose', action='count', default=0, help="""
Print additional details about each test case to the screen.
Passing once prints the pass/fail status of each test case.
Passing twice includes any failing checks for each test case.
Passing a third time includes all checks for a test case.
Passing a fourth time outputs the full detailed report for each test case.
""")
parser.add_argument('-f', '--flags', nargs='+', help="The default flags to use for compilation")
args = parser.parse_args(sys.argv[1:] if flag_start == 0 else sys.argv[1:flag_start])
args.flags = flags

processor = Processor(args.compiler, args.c_compiler, args.flags)
if (os.path.exists(args.output)): shutil.rmtree(args.output)
os.mkdir(args.output)

# TODO: filter test cases in some
test_cases = [create_test_case(root) for root, dirs, files in os.walk(args.input) if is_test_case(root)]
# TODO: run test cases in parallel
results = [case.execute_with(processor, args.input, args.output) for case in test_cases]

num_failed = 0
num_allowed_to_fail = 0
num_cases = 0
for result in results:
    num_cases += 1
    if result.failed():
        case_summary = "Failed: " + result.title
        num_failed += 1
        if result.allowed_failure:
            num_allowed_to_fail += 1
    else:
        case_summary = "Passed: " + result.title
    if 0 < args.verbose < 4:
        print(case_summary)
    if args.verbose == 2:
        for failure in result.failing_checks():
            print("  {0}".format(failure))
    if args.verbose == 3:
        for check in result.checks:
            print("  {0}".format(check))
    if args.verbose >= 4:
        print(result)

if num_failed <= num_allowed_to_fail:
    print("Success!")
else:
    print("Failure")
print("{0} of {1} cases failed, with {2} of them being allowed to fail".format(num_failed, num_cases, num_allowed_to_fail))
print()
print("Additional details can be found in the output folder for each test case in a file named `outcome.txt`")
