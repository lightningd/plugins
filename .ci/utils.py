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


def list_plugins(plugins: list) -> str:
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
