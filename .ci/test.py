import logging
import os
import subprocess
import sys
import tempfile
import time
import json
from itertools import chain
from pathlib import Path

from utils import Plugin, configure_git, enumerate_plugins

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

global_dependencies = [
    "pytest",
    "pytest-xdist",
    "pytest-timeout",
]

pip_opts = ["-qq"]


def prepare_env(p: Plugin, directory: Path, env: dict, workflow: str) -> bool:
    """Returns whether we can run at all. Raises error if preparing failed."""
    subprocess.check_call(["python3", "-m", "venv", "--clear", directory])
    os.environ["PATH"] += f":{directory}"

    if p.framework == "pip":
        return prepare_env_pip(p, directory, workflow)
    elif p.framework == "poetry":
        return prepare_env_poetry(p, directory)
    elif p.framework == "generic":
        return prepare_generic(p, directory, env, workflow)
    else:
        raise ValueError(f"Unknown framework {p.framework}")


def prepare_env_poetry(p: Plugin, directory: Path) -> bool:
    logging.info("Installing a new poetry virtualenv")

    pip3 = directory / "bin" / "pip3"
    poetry = directory / "bin" / "poetry"
    python3 = directory / "bin" / "python3"

    subprocess.check_call(["which", "python3"])

    subprocess.check_call(
        [pip3, "install", "-U", *pip_opts, "pip", "wheel", "poetry"], cwd=p.path.parent
    )

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_call(
        [pip3, "install", "-U", "-qq", *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    # We run all commands in the plugin directory so poetry remembers its settings
    workdir = p.path.resolve()

    logging.info(f"Using poetry at {poetry} ({python3}) to run tests in {workdir}")

    # Now we can proceed with the actual implementation
    logging.info(
        f"Exporting poetry {poetry} dependencies from {p.details['pyproject']}"
    )
    subprocess.check_call(
        [
            poetry,
            "export",
            "--with=dev",
            "--without-hashes",
            "-f",
            "requirements.txt",
            "--output",
            "requirements.txt",
        ],
        cwd=workdir,
    )

    subprocess.check_call(
        [
            pip3,
            "install",
            *pip_opts,
            "-r",
            str(workdir) + "/requirements.txt",
        ],
        stderr=subprocess.STDOUT,
    )

    subprocess.check_call([pip3, "freeze"])
    return True


def prepare_env_pip(p: Plugin, directory: Path, workflow: str) -> bool:
    print("Installing a new pip virtualenv")
    pip_path = directory / "bin" / "pip3"

    if workflow == "nightly":
        install_dev_pyln_testing(pip_path)
    else:
        install_pyln_testing(pip_path)

    # Now install all the requirements
    print(f"Installing requirements from {p.details['requirements']}")
    subprocess.check_call(
        [pip_path, "install", *pip_opts, "-r", p.details["requirements"]],
        stderr=subprocess.STDOUT,
    )

    if p.details["devrequirements"].exists():
        print(f"Installing requirements from {p.details['devrequirements']}")
        subprocess.check_call(
            [pip_path, "install", *pip_opts, "-r", p.details["devrequirements"]],
            stderr=subprocess.STDOUT,
        )

    subprocess.check_call([pip_path, "freeze"])
    return True


def prepare_generic(p: Plugin, directory: Path, env: dict, workflow: str) -> bool:
    print("Installing a new generic virtualenv")
    pip_path = directory / "bin" / "pip3"

    if workflow == "nightly":
        install_dev_pyln_testing(pip_path)
    else:
        install_pyln_testing(pip_path)

    # Now install all the requirements
    if p.details["requirements"].exists():
        print(f"Installing requirements from {p.details['requirements']}")
        subprocess.check_call(
            [pip_path, "install", "-U", *pip_opts, "-r", p.details["requirements"]],
            stderr=subprocess.STDOUT,
        )

    if p.details["setup"].exists():
        print(f"Running setup script from {p.details['setup']}")
        subprocess.check_call(
            ["bash", p.details["setup"], f"TEST_DIR={directory}"],
            env=env,
            stderr=subprocess.STDOUT,
        )

    subprocess.check_call([pip_path, "freeze"])
    return True


def install_pyln_testing(pip_path):
    # Many plugins only implicitly depend on pyln-testing, so let's help them
    cln_path = os.environ["CLN_PATH"]

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_call(
        [pip_path, "install", *pip_opts, *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    subprocess.check_call(
        [pip_path, "install", "-U", *pip_opts, "pip", "wheel"],
        stderr=subprocess.STDOUT,
    )

    subprocess.check_call(
        [
            pip_path,
            "install",
            *pip_opts,
            cln_path + "/contrib/pyln-client",
            cln_path + "/contrib/pyln-testing",
            "MarkupSafe>=2.0",
            "itsdangerous>=2.0",
        ],
        stderr=subprocess.STDOUT,
    )


def install_dev_pyln_testing(pip_path):
    # Many plugins only implicitly depend on pyln-testing, so let's help them
    cln_path = os.environ["CLN_PATH"]

    subprocess.check_call(
        [
            pip_path,
            "install",
            *pip_opts,
            "-r",
            cln_path + "/requirements.txt",
        ],
        stderr=subprocess.STDOUT,
    )


def run_one(p: Plugin, workflow: str) -> bool:
    print("Running tests on plugin {p.name}".format(p=p))

    if not p.testfiles:
        print("No test files found, skipping plugin {p.name}".format(p=p))
        return True

    print(
        "Found {ctestfiles} test files, creating virtualenv and running tests".format(
            ctestfiles=len(p.testfiles)
        )
    )
    print("::group::{p.name}".format(p=p))

    # Create a virtual env
    vdir = tempfile.TemporaryDirectory()
    vpath = Path(vdir.name)

    bin_path = vpath / "bin"
    pytest_path = vpath / "bin" / "pytest"

    env = os.environ.copy()
    env.update(
        {
            # Need to customize PATH so lightningd can find the correct python3
            "PATH": "{}:{}".format(bin_path, os.environ["PATH"]),
            # Some plugins require a valid locale to be set
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
    )

    try:
        if not prepare_env(p, vpath, env, workflow):
            # Skipping is counted as a success
            return True
    except Exception as e:
        print(f"Error creating test environment: {e}")
        print("::endgroup::")
        return False

    logging.info(f"Virtualenv at {vpath}")

    cmd = [
        str(pytest_path),
        "-vvv",
        "--timeout=600",
        "--timeout-method=thread",
        "--color=yes",
        "-n=5",
    ]

    logging.info(f"Running `{' '.join(cmd)}` in directory {p.path.resolve()}")
    try:
        subprocess.check_call(
            cmd,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=p.path.resolve(),
        )
        return True
    except Exception as e:
        logging.warning(f"Error while executing: {e}")
        return False
    finally:
        print("::endgroup::")


# gather data
def collect_gather_data(results: list, success: bool) -> dict:
    gather_data = {}
    for t in results:
        p = t[0]
        if p.testfiles:
            if success or t[1]:
                gather_data[p.name] = "passed"
            else:
                gather_data[p.name] = "failed"
    return gather_data


def push_gather_data(data: dict, workflow: str, python_version: str):
    print("Pushing gather data...")
    configure_git()
    subprocess.run(["git", "fetch"])
    subprocess.run(["git", "checkout", "badges"])
    filenames_to_add = []
    for plugin_name, result in data.items():
        filename = write_gather_data_file(plugin_name, result, workflow, python_version)
        filenames_to_add.append(filename)
    output = subprocess.check_output(
        list(chain(["git", "add", "-v"], filenames_to_add))
    ).decode("utf-8")
    print(f"output from git add: {output}")
    if output != "":
        output = subprocess.check_output(
            [
                "git",
                "commit",
                "-m",
                f"Update test result for Python{python_version} to ({workflow} workflow)",
            ]
        ).decode("utf-8")
        print(f"output from git commit: {output}")
        for _ in range(10):
            subprocess.run(["git", "pull", "--rebase"])
            output = subprocess.run(
                ["git", "push", "origin", "badges"], capture_output=True, text=True
            )
            if output.returncode == 0:
                print("Push successful")
                break
            else:
                print(
                    f"Push failed with return code {output.returncode}, retrying in 2 seconds..."
                )
                print(f"Push failure message: {output.stderr}")
                time.sleep(2)
    print("Done.")


def write_gather_data_file(
    plugin_name: str, result, workflow: str, python_version: str
) -> str:
    _dir = f".badges/gather_data/{workflow}/{plugin_name}"
    filename = os.path.join(_dir, f"python{python_version}.txt")
    os.makedirs(_dir, exist_ok=True)
    with open(filename, "w") as file:
        print(f"Writing {filename}")
        file.write(result)

    return filename


def gather_old_failures(old_failures: list, workflow: str):
    print("Gather old failures...")
    configure_git()
    subprocess.run(["git", "fetch"])
    subprocess.run(["git", "checkout", "badges"])

    directory = ".badges"

    for filename in os.listdir(directory):
        if filename.endswith(f"_{workflow}.json"):
            file_path = os.path.join(directory, filename)
            plugin_name = filename.rsplit(f"_{workflow}.json", 1)[0]

            with open(file_path, "r") as file:
                data = json.load(file)
                if data["color"] == "red":
                    old_failures.append(plugin_name)

    print(f"Old failures: {old_failures}")
    print("Done.")


def run_all(
    workflow: str, python_version: str, update_badges: bool, plugin_names: list
):
    root_path = (
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode("ASCII")
        .strip()
    )

    root = Path(root_path)

    plugins = list(enumerate_plugins(root))
    if plugin_names != []:
        plugins = [p for p in plugins if p.name in plugin_names]
        print(
            "Testing the following plugins: {names}".format(
                names=[p.name for p in plugins]
            )
        )
    else:
        print("Testing all plugins in {root}".format(root=root))

    results = [(p, run_one(p, workflow)) for p in plugins]
    success = all([t[1] for t in results])

    old_failures = []
    if not success and plugin_names == []:
        gather_old_failures(old_failures, workflow)

    if update_badges:
        push_gather_data(
            collect_gather_data(results, success), workflow, python_version
        )

    if not success:
        print("The following tests failed:")
        has_new_failure = False
        for t in filter(lambda t: not t[1], results):
            if t[0].name not in old_failures:
                has_new_failure = True
            print(" - {p.name} ({p.path})".format(p=t[0]))
        if has_new_failure:
            sys.exit(1)
    else:
        print("All tests passed.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plugins test script")
    parser.add_argument("workflow", type=str, help="Name of the GitHub workflow")
    parser.add_argument("python_version", type=str, help="Python version")
    parser.add_argument(
        "--update-badges",
        action="store_true",
        help="Whether badges data should be updated",
    )
    parser.add_argument("plugins", nargs="*", default=[], help="List of plugins")
    args = parser.parse_args()

    run_all(args.workflow, args.python_version, args.update_badges, args.plugins)
