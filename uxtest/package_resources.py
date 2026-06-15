from __future__ import annotations

import difflib
from importlib import resources
from pathlib import Path
from typing import Any

from .store import StoreError


DOC_ALIASES = {
    "root": "README.md",
    "readme": "README.md",
    "report-writer-agent": "report_writer_agent.md",
    "report_writer_agent": "report_writer_agent.md",
    "research-report-agent": "report_writer_agent.md",
    "research_report_agent": "report_writer_agent.md",
    "spec": "SPEC.md",
    "study-types": "study_types/README.md",
    "study_types": "study_types/README.md",
    "accessibility-inclusive-ux": "study_types/accessibility_inclusive_ux/README.md",
    "accessibility_inclusive_ux": "study_types/accessibility_inclusive_ux/README.md",
    "competitive-benchmark-studies": "study_types/competitive_benchmark_studies/README.md",
    "competitive_benchmark_studies": "study_types/competitive_benchmark_studies/README.md",
    "content-comprehension": "study_types/content_comprehension/README.md",
    "content_comprehension": "study_types/content_comprehension/README.md",
    "conversion-path-testing": "study_types/conversion_path_testing/README.md",
    "conversion_path_testing": "study_types/conversion_path_testing/README.md",
    "enterprise-buying-research": "study_types/enterprise_buying_research/README.md",
    "enterprise_buying_research": "study_types/enterprise_buying_research/README.md",
    "feature-findability": "study_types/feature_findability/README.md",
    "feature_findability": "study_types/feature_findability/README.md",
    "information-architecture": "study_types/information_architecture/README.md",
    "information_architecture": "study_types/information_architecture/README.md",
    "longitudinal-regression": "study_types/longitudinal_regression/README.md",
    "longitudinal_regression": "study_types/longitudinal_regression/README.md",
    "onboarding-activation": "study_types/onboarding_activation/README.md",
    "onboarding_activation": "study_types/onboarding_activation/README.md",
    "post-login-workflow-testing": "study_types/post_login_workflow_testing/README.md",
    "post_login_workflow_testing": "study_types/post_login_workflow_testing/README.md",
    "task-discovery": "study_types/task_discovery/README.md",
    "task_discovery": "study_types/task_discovery/README.md",
}

EXAMPLE_ALIASES = {
    "all": "",
    "expectedparrot": "expectedparrot_site",
    "expectedparrot-batch": "expectedparrot_site/batch.yaml",
    "expectedparrot-content-comprehension": "expectedparrot_site/content-comprehension.yaml",
    "expectedparrot-conversion-path": "expectedparrot_site/conversion-path.yaml",
    "expectedparrot-enterprise-demo": "expectedparrot_site/enterprise-demo.yaml",
    "expectedparrot-credibility": "expectedparrot_site/credibility.yaml",
    "expectedparrot-feature-findability": "expectedparrot_site/feature-findability.yaml",
    "expectedparrot-information-architecture": "expectedparrot_site/information-architecture.yaml",
    "expectedparrot-task-discovery": "expectedparrot_site/task-discovery.yaml",
    "jjh": "jjh_site",
    "jjh-discovery": "jjh_site/discovery.yaml",
    "jjh-targeted": "jjh_site/targeted.yaml",
    "saas": "saas_site",
    "saas-regression": "saas_site/regression.yaml",
    "saas-regression-edsl": "saas_site/regression-edsl.yaml",
    "task-discovery": "study_types/task_discovery/README.md",
}

_RESOURCE_CONTEXTS: list[Any] = []


def resource_root(kind: str) -> Any:
    root = resources.files("uxtest").joinpath("resources", kind)
    if not root.is_dir():
        raise StoreError(f"Bundled {kind} resources are unavailable.", exit_code=1)
    return root


def resource_files(kind: str, *, suffixes: tuple[str, ...] | None = None) -> list[str]:
    root = resource_root(kind)
    output: list[str] = []

    def walk(node: Any, prefix: str = "") -> None:
        for child in sorted(node.iterdir(), key=lambda item: item.name):
            child_path = f"{prefix}{child.name}"
            if child.is_dir():
                walk(child, f"{child_path}/")
            elif suffixes is None or child.name.endswith(suffixes):
                output.append(child_path)

    walk(root)
    return output


def doc_resource(name: str) -> Any:
    requested = DOC_ALIASES.get(name, name)
    return resolve_resource("docs", requested)


def example_resource(name: str) -> Any:
    requested = EXAMPLE_ALIASES.get(name, name)
    return resolve_resource("examples", requested)


def example_resource_path(relative_path: str) -> Path:
    resource = example_resource(relative_path)
    context = resources.as_file(resource)
    path = context.__enter__()
    _RESOURCE_CONTEXTS.append(context)
    return path


def resource_as_file(resource: Any) -> Any:
    return resources.as_file(resource)


def resolve_resource(kind: str, requested: str) -> Any:
    root = resource_root(kind)
    normalized = requested.strip("/")
    if kind == "docs":
        normalized = normalize_doc_request(normalized)
    resource = root if not normalized else root.joinpath(*Path(normalized).parts)
    if not resource.exists():
        available_files = resource_files(kind)
        suggestions = difflib.get_close_matches(normalized or requested, available_files, n=5, cutoff=0.35)
        suffix_matches = [path for path in available_files if path.endswith(normalized) or normalized in path]
        hints = suggestions or suffix_matches[:5]
        available = ", ".join(available_files[:20])
        hint_text = f" Did you mean: {', '.join(hints)}?" if hints else ""
        raise StoreError(f"Bundled {kind} resource {requested!r} not found.{hint_text} Available: {available}", exit_code=2)
    return resource


def normalize_doc_request(value: str) -> str:
    if not value:
        return value
    if value in DOC_ALIASES:
        return DOC_ALIASES[value]
    path = Path(value)
    if len(path.parts) == 2 and path.parts[1] == "README.md":
        return f"study_types/{path.parts[0]}/README.md"
    if len(path.parts) == 1 and not value.endswith(".md"):
        underscored = value.replace("-", "_")
        return DOC_ALIASES.get(underscored, value)
    return value


def copy_resource_tree(resource: Any, dest: Path) -> None:
    for child in resource.iterdir():
        target = dest / child.name
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            copy_resource_tree(child, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(child.read_bytes())
