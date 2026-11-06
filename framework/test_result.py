"""
Classes to hold and format the results of a test case
"""
import yaml


class Check:
    def __init__(self, description: str, passed: bool):
        self.description = description
        self.passed = passed

    def __repr__(self):
        return "\"{d}: {p}\"".format(d = self.description, p = "passed" if self.passed else "failed")

    def to_dict(self) -> dict:
        return {"description": self.description, "passed": self.passed}


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

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "features": self.features,
            "passed": not self.failed(),
            "allowed_failure": self.allowed_failure,
            "requires_revision": self.requires_revision,
            "feature_sections": self.feature_sections,
            "checks": [c.to_dict() for c in self.checks],
            "commands": self.commands,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'TestResult':
        """Parse a TestResult from YAML string."""
        data = yaml.safe_load(yaml_str)
        checks = [Check(c['description'], c['passed']) for c in data.get('checks')]
        return cls(
            title=data.get('title'),
            features=data.get('features'),
            checks=checks,
            commands=data.get('commands'),
            stdout=data.get('stdout'),
            stderr=data.get('stderr'),
            allowed_failure=data.get('allowed_failure'),
            requires_revision=data.get('requires_revision'),
            feature_sections=data.get('feature_sections')
        )

    def __repr__(self):
        lines = [
            "Case: {title}".format(title=self.title),
            "Features: {features}".format(features=self.features),
            "Passed: {passed}".format(passed=not self.failed()),
            "Failure Acceptable? {accept}".format(accept="yes" if self.allowed_failure else "no"),
            "Requires Revision: {rev}".format(rev=self.requires_revision),
            "Feature Sections: {sections}".format(sections=self.feature_sections),
            "Checks: {checks}".format(checks=self.checks),
            "commands:\n{commands}".format(commands="\n".join(self.commands)),
            "",
            "stdout:\n{stdout}".format(stdout=self.stdout),
            "",
            "stderr:\n{stderr}".format(stderr=self.stderr),
            "",
        ]
        return "\n".join(lines)