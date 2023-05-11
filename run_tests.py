#!/usr/bin/env python
"""
This is the entry point for running the compiler test framework.
"""

import argparse
import os
import re
import shutil
import sys
from framework.processor import Processor
from framework.test_case import create_test_case

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
parser.add_argument('-f', '--flags', nargs='+', help="The default flags to use for compilation")
args = parser.parse_args(sys.argv[1:] if flag_start == 0 else sys.argv[1:flag_start])
args.flags = flags

processor = Processor(args.compiler, args.flags)
if (os.path.exists(args.output)): shutil.rmtree(args.output)
os.mkdir(args.output)

# TODO: collect the test cases as a separate step from executing them
#       Will allow the possibility to filter and execute a subset of them
for root, dirs, files in os.walk(args.input):
    if any([re.match(".*\.[fF][a-zA-Z0-9]*$", f) for f in files]): # Are any files Fortran?
        test_case = create_test_case(root)
        print(test_case.execute_with(processor, args.input, args.output))
        # TODO: capture the results and figure out how to organize, display and/or save them