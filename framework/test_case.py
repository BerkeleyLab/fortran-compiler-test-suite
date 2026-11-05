import os
import re
import shutil
import yaml
from framework.test_result import TestResult
from framework.checkers import create_checker, CompileOnly, FailToCompile
from framework.processor import Processor

class TestCase:
    """
    The base/default implementation for a test case
    """
    def __init__(self, location : str) -> None:
        config = yaml.safe_load(open(os.path.join(location, "config.yml"), 'r'))
        self.description = config.get("description")
        self.features = config.get("features", [])
        self.files = config.get("source_files")
        self.location = location
        self.other_files_on_disk = config.get("other_files", [])
        self.cmd_line_args = config.get("command_line_arguments", [])
        self.std_in_string = config.get("standard_input", "")
        self.env_vars = config.get("environment_variables", {})
        self.num_images = config.get("num_images", 1)
        self.allowed_not_to_detect = config.get("allowed_not_to_detect", False) # Is the processor allowed to not detect the error in this test case?
        self.uses_optional_feature = config.get("uses_optional_feature", False) # Does this case use a feature not required to be supported?
        self.uses_extension = config.get("uses_extension", False) # Does this case use an extension to the standard?
        self.expected_outcome = create_checker(config.get("expected"))
        self.requires_revision = config.get("requires_revision")
        self.feature_sections = config.get("feature_sections", [])

    def execute_with(self, processor : Processor, tests_path : str, results_path: str) -> None:
        result_location = self.location.replace(tests_path, results_path)
        shutil.copytree(self.location, result_location)
        outcome = processor.execute(
            self.files,
            result_location,
            self.features,
            self.other_files_on_disk,
            self.cmd_line_args,
            self.std_in_string,
            self.env_vars,
            self.num_images,
            not (isinstance(self.expected_outcome, CompileOnly) or isinstance(self.expected_outcome, FailToCompile))
            )
        result = TestResult(
            self.description,
            self.features,
            self.expected_outcome.check(outcome, result_location),
            outcome.commands,
            outcome.stdout,
            outcome.stderr,
            self.allowed_not_to_detect or self.uses_optional_feature or self.uses_extension,
            self.requires_revision,
            self.feature_sections)
        with open(os.path.join(result_location, "outcome.yml"), 'w') as output:
            output.write(result.to_yaml())
        return result

def create_test_case(location : str):
    """
    This is where we figure out if we're constructing just the default behavior
    test case, or if we should pick up some special test case class.
    This should be based on whether there is a custom test case class in this
    directory, or if based on the metadata in ??? we should select
    one of our specialized test cases.
    """
    case = make_case_specific_class(location)
    if not case is None: return case
    case = make_special_class(location)
    if not case is None: return case
    return TestCase(location)

def make_case_specific_class(location : str):
    """
    See if there is a python file (name?) that we should import and instantiate
    a TestCase from it
    """
    # TODO
    return None

def make_special_class(location : str):
    """
    Look at the "features" of the test case and see if there is some aspect
    of it that falls into a "special" case that we have a different implementation for.
    """
    # TODO
    return None

def is_test_case(location : str):
    """
    Look at the contents of this directory to determine if it is a test case
    """
    return "config.yml" in os.listdir(location)
    # TODO: should we support having a single Fortran file with no config?
