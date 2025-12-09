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
        "testfiles",
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


def get_testfiles(p: Path) -> List[PosixPath]:
    test_files = []
    for x in p.iterdir():
        if x.is_dir() and x.name == "tests":
            test_files.extend(
                [
                    y
                    for y in x.iterdir()
                    if y.is_file()
                    and y.name.startswith("test_")
                    and y.name.endswith(".py")
                ]
            )
        elif x.is_file() and x.name.startswith("test_") and x.name.endswith(".py"):
            test_files.append(x)
    return test_files


def list_plugins(plugins: list) -> str:
    return ", ".join([p.name for p in sorted(plugins)])


def get_test_framework(p: Path, filename: str):
    if p is None:
        return None
    for candidate in [p / filename, p / "tests" / filename]:
        if candidate.exists():
            return candidate
    return None


def get_framework_working_dir(p: Plugin) -> Path:
    if p.framework == "uv":
        return p.details["pyproject"].parent.resolve()
    elif p.framework == "poetry":
        return p.details["pyproject"].parent.resolve()
    elif p.framework == "pip":
        if "requirements" in p.details:
            return p.details["requirements"].parent.resolve()
        elif "devrequirements" in p.details:
            return p.details["devrequirements"].parent.resolve()
    elif p.framework == "generic":
        if "requirements" in p.details:
            return p.details["requirements"].parent.resolve()
        return p.path.resolve()
    return p.path.resolve()


def enumerate_plugins(basedir: Path) -> Generator[Plugin, None, None]:
    plugins = list(
        [x for x in basedir.iterdir() if x.is_dir() and x.name not in exclude]
    )

    pip_pytest = [
        x for x in plugins if get_test_framework(x, "requirements.txt") is not None
    ]
    print(f"Pip plugins: {list_plugins(pip_pytest)}")

    uv_pytest = [x for x in plugins if get_test_framework(x, "uv.lock") is not None]
    print(f"Uv plugins: {list_plugins(uv_pytest)}")

    # Don't double detect plugins migrating to uv
    poetry_pytest = [
        x
        for x in plugins
        if (get_test_framework(x, "poetry.lock") is not None) and x not in uv_pytest
    ]
    print(f"Poetry plugins: {list_plugins(poetry_pytest)}")

    generic_plugins = [
        x
        for x in plugins
        if x not in pip_pytest and x not in poetry_pytest and x not in uv_pytest
    ]
    print(f"Generic plugins: {list_plugins(generic_plugins)}")

    for p in sorted(pip_pytest):
        details = {}

        req = get_test_framework(p, "requirements.txt")
        if req:
            details["requirements"] = req

        devreq = get_test_framework(p, "requirements-dev.txt")
        if devreq:
            details["devrequirements"] = devreq

        if details == {}:
            print(f"Could not find requirements in {p}")
            continue

        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="pip",
            testfiles=get_testfiles(p),
            details=details,
        )

    for p in sorted(poetry_pytest):
        details = {}

        req = get_test_framework(p, "pyproject.toml")
        if req:
            details["pyproject"] = req
        else:
            print(f"Could not find pyproject.toml in {p}")
            continue

        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="poetry",
            testfiles=get_testfiles(p),
            details=details,
        )

    for p in sorted(uv_pytest):
        details = {}

        req = get_test_framework(p, "pyproject.toml")
        if req:
            details["pyproject"] = req
        else:
            print(f"Could not find pyproject.toml in {p}")
            continue

        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="uv",
            testfiles=get_testfiles(p),
            details=details,
        )

    for p in sorted(generic_plugins):
        details = {}

        req = get_test_framework(p, "requirements.txt")
        if req:
            details["requirements"] = req

        yield Plugin(
            name=p.name,
            path=p,
            language="other",
            framework="generic",
            testfiles=get_testfiles(p),
            details=details,
        )
