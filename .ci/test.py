import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import namedtuple
from pathlib import Path, PosixPath
from typing import Generator, List
from itertools import chain

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Directories that are not plugins
exclude = [
    '.ci',
    '.git',
    '.github',
    'archived',
    'lightning',
]

global_dependencies = [
    'pytest',
    'pytest-xdist',
    'pytest-timeout',
]

pip_opts = ['-qq']

Plugin = namedtuple(
    'Plugin',
    [
        'name',
        'path',
        'language',
        'framework',
        'details',
    ]
)


def list_plugins(plugins):
    return ", ".join([p.name for p in sorted(plugins)])


def enumerate_plugins(basedir: Path) -> Generator[Plugin, None, None]:
    plugins = list([
        x for x in basedir.iterdir() \
        if x.is_dir() and x.name not in exclude
    ])
    pip_pytest = [
        x for x in plugins if (x / Path('requirements.txt')).exists()
    ]
    print(f"Pip plugins: {list_plugins(pip_pytest)}")

    poetry_pytest = [
        x for x in plugins if (x / Path("pyproject.toml")).exists()
    ]
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
                "requirements": p/Path('requirements.txt'),
                "devrequirements": p/Path('requirements-dev.txt'),
            }
        )

    for p in sorted(poetry_pytest):
        yield Plugin(
            name=p.name,
            path=p,
            language="python",
            framework="poetry",
            details={
                "pyproject": p / Path("pyproject.toml"),
            }
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
            }
        )

def prepare_env(p: Plugin, directory: Path) -> bool:
    """ Returns whether we can run at all. Raises error if preparing failed.
    """
    subprocess.check_call(['python3', '-m', 'venv', '--clear', directory])
    os.environ['PATH'] += f":{directory}"
    pip_path = directory / 'bin' / 'pip3'
    python_path = directory / 'bin' / 'python'

    if p.framework == "pip":
        return prepare_env_pip(p, directory)
    elif p.framework == "poetry":
        return prepare_env_poetry(p, directory)
    elif p.framework == "generic":
        return prepare_generic(p, directory)
    else:
        raise ValueError(f"Unknown framework {p.framework}")

def prepare_env_poetry(p: Plugin, directory: Path) -> bool:
    logging.info(f"Installing a new poetry virtualenv")

    pip3 = directory / 'bin' / 'pip3'
    poetry = directory / 'bin' / 'poetry'
    python3 = directory / 'bin' / 'python3'

    subprocess.check_call(['which', 'python3'])

    subprocess.check_call([
        pip3, 'install', '-U', *pip_opts, 'pip', 'wheel', 'poetry==1.7.1'
    ], cwd=p.path.parent)

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_call(
        [pip3, 'install', '-U', '-qq', *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    # We run all commands in the plugin directory so poetry remembers its settings
    workdir = p.path.resolve()

    logging.info(f"Using poetry at {poetry} ({python3}) to run tests in {workdir}")

    # Don't let poetry create a self-managed virtualenv (paths get confusing)
    subprocess.check_call([
        poetry, 'config', 'virtualenvs.create', 'false'
    ], cwd=workdir)


    # Now we can proceed with the actual implementation
    logging.info(f"Installing poetry {poetry} dependencies from {p.details['pyproject']}")
    subprocess.check_call([
        poetry, 'install', '--with=dev', '--no-interaction',
    ], cwd=workdir)

    subprocess.check_call([pip3, 'freeze'])
    return True

def prepare_env_pip(p: Plugin, directory: Path):
    pip_path = directory / 'bin' / 'pip3'

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_call(
        [pip_path, 'install', *pip_opts, *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    # Now install all the requirements
    print(f"Installing requirements from {p.details['requirements']}")
    subprocess.check_call(
        [pip_path, 'install', '-U', *pip_opts, '-r', p.details['requirements']],
        stderr=subprocess.STDOUT,
    )

    if p.details['devrequirements'].exists():
        print(f"Installing requirements from {p.details['devrequirements']}")
        subprocess.check_call(
            [pip_path, 'install', '-U', *pip_opts, '-r', p.details['devrequirements']],
            stderr=subprocess.STDOUT,
        )
    install_pyln_testing(pip_path)
    return True

def prepare_generic(p: Plugin, directory: Path):
    pip_path = directory / 'bin' / 'pip3'

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_call(
        [pip_path, 'install', *pip_opts, *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    # Now install all the requirements
    if p.details['requirements'].exists():
        print(f"Installing requirements from {p.details['requirements']}")
        subprocess.check_call(
            [pip_path, 'install', '-U', *pip_opts, '-r', p.details['requirements']],
            stderr=subprocess.STDOUT,
        )

    if p.details['setup'].exists():
        print(f"Running setup script from {p.details['setup']}")
        subprocess.check_call(
            ['bash',  p.details['setup'], f'TEST_DIR={directory}'],
            stderr=subprocess.STDOUT,
        )
    install_pyln_testing(pip_path)
    return True


def install_pyln_testing(pip_path):
    # Many plugins only implicitly depend on pyln-testing, so let's help them
    cln_path = os.environ['CLN_PATH']
    pip_opts = ['-qq']
    subprocess.check_call(
        [pip_path, 'install', '-U', *pip_opts, 'pip', 'wheel'],
        stderr=subprocess.STDOUT,
    )

    subprocess.check_call(
        [
            pip_path, 'install', '-U', *pip_opts,
            cln_path + "/contrib/pyln-client",
            cln_path + "/contrib/pyln-testing",
            "MarkupSafe>=2.0",
            'itsdangerous>=2.0'
        ],
        stderr=subprocess.STDOUT,
    )

def get_testfiles(p: Plugin) -> List[PosixPath]:
    return [
        x for x in p.path.iterdir()
        if (x.is_dir() and x.name == 'tests')
        or (x.name.startswith("test_") and x.name.endswith('.py'))
    ]

def has_testfiles(p: Plugin) -> bool:
    return len(get_testfiles(p)) > 0

def run_one(p: Plugin) -> bool:
    print("Running tests on plugin {p.name}".format(p=p))

    if not has_testfiles(p):
        print("No test files found, skipping plugin {p.name}".format(p=p))
        return True

    print("Found {ctestfiles} test files, creating virtualenv and running tests".format(ctestfiles=len(get_testfiles(p))))
    print("##[group]{p.name}".format(p=p))

    # Create a virtual env
    vdir = tempfile.TemporaryDirectory()
    vpath = Path(vdir.name)

    if not prepare_env(p, vpath):
        # Skipping is counted as a success
        return True

    bin_path = vpath / 'bin'
    pytest_path = vpath / 'bin' / 'pytest'
    poetry_path = vpath / 'bin' / 'poetry'

    pytest = [str(pytest_path)]
    if p.framework == "poetry":
        pytest = [poetry_path, 'run', 'pytest']

    if p.framework == "poetry":
        subprocess.check_call([poetry_path, 'env', 'info'])
    else:
        logging.info(f"Virtualenv at {vpath}")

    env = os.environ.copy()
    env.update({
        # Need to customize PATH so lightningd can find the correct python3
        'PATH': "{}:{}".format(bin_path, os.environ['PATH']),
        # Some plugins require a valid locale to be set
        'LC_ALL': 'C.UTF-8',
        'LANG': 'C.UTF-8',
    })
    cmd = [str(p) for p in pytest] + [
        '-vvv',
        '--timeout=600',
        '--timeout-method=thread',
        '--color=yes',
        '-n=5',
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
        logging.warning(f"Error while executing ")
        return False
    finally:
        print("##[endgroup]")

def configure_git():
    # Git requires some user and email to be configured in order to work in the context of GitHub Actions.
    subprocess.run(
        ["git", "config", "--global", "user.email", '"lightningd@github.plugins.repo"']
    )
    subprocess.run(["git", "config", "--global", "user.name", '"lightningd"'])


# gather data
def collect_gather_data(results, success):
    gather_data = {}
    for t in results:
        p = t[0]
        if has_testfiles(p):
            if success or t[1]:
                gather_data[p.name] = "passed"
            else:
                gather_data[p.name] = "failed"
    return gather_data


def push_gather_data(data, workflow, python_version):
    print("Pushing gather data...")
    configure_git()
    subprocess.run(["git", "fetch"])
    subprocess.run(["git", "checkout", "badges"])
    filenames_to_add = []
    for plugin_name, result in data.items():
        filenames_to_add.append(git_add_gather_data(
            plugin_name, result, workflow, python_version
        ))
    output = subprocess.check_output(list(chain(["git", "add", "-v"], filenames_to_add))).decode("utf-8")
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
        subprocess.run(["git", "push", "origin", "badges"])
    print("Done.")


def git_add_gather_data(plugin_name, result, workflow, python_version):
    _dir = f".badges/gather_data/{workflow}/{plugin_name}"
    filename = os.path.join(_dir, f"python{python_version}.txt")
    os.makedirs(_dir, exist_ok=True)
    with open(filename, "w") as file:
        print(f"Writing {filename}")
        file.write(result)

    return filename


def run_all(workflow, python_version, update_badges, plugin_names):
    root_path = subprocess.check_output([
        'git',
        'rev-parse',
        '--show-toplevel'
    ]).decode('ASCII').strip()

    root = Path(root_path)

    plugins = list(enumerate_plugins(root))
    if plugin_names != []:
        plugins = [p for p in plugins if p.name in plugin_names]
        print("Testing the following plugins: {names}".format(names=[p.name for p in plugins]))
    else:
        print("Testing all plugins in {root}".format(root=root))

    results = [(p, run_one(p)) for p in plugins]
    success = all([t[1] for t in results])

    if update_badges:
        push_gather_data(collect_gather_data(results, success), workflow, python_version)

    if not success:
        print("The following tests failed:")
        for t in filter(lambda t: not t[1], results):
            print(" - {p.name} ({p.path})".format(p=t[0]))
        sys.exit(1)
    else:
        print("All tests passed.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Plugins test script')
    parser.add_argument("workflow", type=str, help="Name of the GitHub workflow")
    parser.add_argument("python_version", type=str, help="Python version")
    parser.add_argument("--update-badges", action='store_true', help="Whether badges data should be updated")
    parser.add_argument("plugins", nargs="*", default=[], help="List of plugins")
    args = parser.parse_args()

    run_all(args.workflow, args.python_version, args.update_badges, args.plugins)
