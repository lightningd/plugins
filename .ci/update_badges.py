import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path, PosixPath
from typing import Generator, List

Plugin = namedtuple(
    "Plugin",
    [
        "name",
        "path",
        "language",
        "framework",
        "details",
    ],
)

exclude = [
    ".ci",
    ".git",
    ".github",
    "archived",
    "lightning",
]


def configure_git():
    # Git needs some user and email to be configured in order to work in the context of GitHub Actions.
    subprocess.run(
        ["git", "config", "--global", "user.email", '"lightningd@github.plugins.repo"']
    )
    subprocess.run(["git", "config", "--global", "user.name", '"lightningd"'])


def get_testfiles(p: Plugin) -> List[PosixPath]:
    return [
        x
        for x in p.path.iterdir()
        if (x.is_dir() and x.name == "tests")
        or (x.name.startswith("test_") and x.name.endswith(".py"))
    ]


def has_testfiles(p: Plugin) -> bool:
    return len(get_testfiles(p)) > 0


def list_plugins(plugins):
    return ", ".join([p.name for p in sorted(plugins)])


def enumerate_plugins(basedir: Path) -> Generator[Plugin, None, None]:
    plugins = list(
        [x for x in basedir.iterdir() if x.is_dir() and x.name not in exclude]
    )
    pip_pytest = [x for x in plugins if (x / Path("requirements.txt")).exists()]
    print(f"Pip plugins: {list_plugins(pip_pytest)}")

    poetry_pytest = [x for x in plugins if (x / Path("pyproject.toml")).exists()]
    print(f"Poetry plugins: {list_plugins(poetry_pytest)}")

    other_plugins = [
        x for x in plugins if x not in pip_pytest and x not in poetry_pytest
    ]
    print(f"Other plugins: {list_plugins(other_plugins)}")

    for p in sorted(pip_pytest):
        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="pip",
            details={
                "requirements": p / Path("requirements.txt"),
                "devrequirements": p / Path("requirements-dev.txt"),
            },
        )

    for p in sorted(poetry_pytest):
        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="poetry",
            details={
                "pyproject": p / Path("pyproject.toml"),
            },
        )

    for p in sorted(other_plugins):
        yield Plugin(
            name=p.name,
            path=p,
            language="other",
            framework="generic",
            details={
                "requirements": p / Path("tests/requirements.txt"),
                "setup": p / Path("tests/setup.sh"),
            },
        )


def update_and_commit_badge(plugin_name, passed, workflow):
    json_data = { "schemaVersion": 1, "label": "", "message": " ✔ ", "color": "green" }
    if not passed:
        json_data.update({"message": "✗", "color": "red"})

    filename = os.path.join(".badges", f"{plugin_name}_{workflow}.json")
    with open(filename, "w") as file:
        file.write(json.dumps(json_data))

    output = subprocess.check_output(["git", "add", "-v", filename]).decode("utf-8")
    if output != "":
        subprocess.run(["git", "commit", "-m", f'Update {plugin_name} badge to {"passed" if passed else "failed"} ({workflow})'])
        return True
    return False


def push_badges_data(workflow, num_of_python_versions):
    print("Pushing badges data...")
    configure_git()
    subprocess.run(["git", "fetch"])
    subprocess.run(["git", "checkout", "badges"])
    subprocess.run(["git", "pull"])

    root_path = (
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode("ASCII")
        .strip()
    )
    plugins = list(enumerate_plugins(Path(root_path)))

    any_changes = False
    for plugin in plugins:
        results = []
        _dir = f".badges/gather_data/{workflow}/{plugin.name}"
        if os.path.exists(_dir):
            for child in Path(_dir).iterdir():
                result = child.read_text().strip()
                results.append(result)
                print(f"Results for {child}: {result}")

            passed = False
            if (
                len(set(results)) == 1
                and results[0] == "passed"
                # and len(results) == num_of_python_versions  # TODO: Disabled as gather data for python versions is missing sporadingly.
            ):
                passed = True
            any_changes |= update_and_commit_badge(plugin.name, passed, workflow)

    if any_changes:
        subprocess.run(["git", "push", "origin", "badges"])
    print("Done.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plugins completion script")
    parser.add_argument("workflow", type=str, help="Name of the GitHub workflow")
    parser.add_argument(
        "num_of_python_versions", type=str, help="Number of Python versions"
    )
    args = parser.parse_args()

    push_badges_data(args.workflow, int(args.num_of_python_versions))
