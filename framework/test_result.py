"""
Classes to hold and format the results of a test case
"""

class Check:
    def __init__(self, description: str, passed: bool):
        self.description = description
        self.passed = passed

    def __repr__(self):
        return "\"{d}: {p}\"".format(d = self.description, p = "passed" if self.passed else "failed")

class TestResult:
    def __init__(self, title : str, features : [str], checks : [Check], commands : [str], stdout : str, stderr : str, allowed_failure : bool, requires_revision : str = "", feature_sections : [str] = None):
        self.title = title
        self.features = features
        self.checks = checks
        self.commands = commands
        self.stdout = stdout
        self.stderr = stderr
        self.allowed_failure = allowed_failure
        self.requires_revision = requires_revision
        self.feature_sections = feature_sections if feature_sections is not None else []

    def failed(self):
        return not all([c.passed for c in self.checks])

    def failing_checks(self):
        return filter(lambda c: not c.passed, self.checks)

    def __repr__(self):
        lines = [
            "Case: {title}".format(title=self.title),
            "Features: {features}".format(features=self.features),
            "Passed: {passed}".format(passed=not self.failed()),
            "Failure Acceptable? {accept}".format(accept="yes" if self.allowed_failure else "no"),
        ]
        if self.requires_revision:
            lines.append("Requires Revision: {rev}".format(rev=self.requires_revision))
        if self.feature_sections:
            lines.append("Feature Sections: {sections}".format(sections=self.feature_sections))
        lines.append("Checks: {checks}".format(checks=self.checks))
        lines.append("commands:\n{commands}".format(commands="\n".join(self.commands)))
        lines.append("")
        lines.append("stdout:\n{stdout}".format(stdout=self.stdout))
        lines.append("")
        lines.append("stderr:\n{stderr}".format(stderr=self.stderr))
        lines.append("")
        return "\n".join(lines)