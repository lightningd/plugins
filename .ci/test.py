from pathlib import Path
import subprocess
from pprint import pprint
from collections import namedtuple
from typing import Generator

import logging
import shutil
import sys
import tempfile
import shlex
import os

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Directories that are not plugins
exclude = [
    '.ci',
    '.git',
    '.github',
    'lightning',
    'feeadjuster'
]

global_dependencies = [
    'pytest',
    'pytest-xdist',
    'pytest-timeout',
    'grpcio',
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


def enumerate_plugins(basedir: Path) -> Generator[Plugin, None, None]:
    plugins = list([
        x for x in basedir.iterdir() \
        if x.is_dir() and x.name not in exclude
    ])
    pip_pytest = [
        x for x in plugins if (x / Path('requirements.txt')).exists()
    ]

    poetry_pytest = [
        x for x in plugins if (x / Path("pyproject.toml")).exists()
    ]
    print(poetry_pytest)

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
    else:
        raise ValueError(f"Unknown framework {p.framework}")

def prepare_env_poetry(p: Plugin, directory: Path) -> bool:
    logging.info(f"Installing a new poetry virtualenv")

    pip3 = directory / 'bin' / 'pip3'
    poetry = directory / 'bin' / 'poetry'
    python3 = directory / 'bin' / 'python3'

    subprocess.check_call(['which', 'python3'])

    subprocess.check_call([
        pip3, 'install', '-U', *pip_opts, 'pip', 'wheel', 'poetry'
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

def run_one(p: Plugin) -> bool:
    print("Running tests on plugin {p.name}".format(p=p))

    testfiles = [
        x for x in p.path.iterdir()
        if (x.is_dir() and x.name == 'tests')
        or (x.name.startswith("test_") and x.name.endswith('.py'))
    ]

    if len(testfiles) == 0:
        print("No test files found, skipping plugin {p.name}".format(p=p))
        return True

    print("Found {ctestfiles} test files, creating virtualenv and running tests".format(ctestfiles=len(testfiles)))
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


def run_all(args):
    root_path = subprocess.check_output([
        'git',
        'rev-parse',
        '--show-toplevel'
    ]).decode('ASCII').strip()

    root = Path(root_path)

    plugins = list(enumerate_plugins(root))
    if args != []:
        plugins = [p for p in plugins if p.name in args]
        print("Testing the following plugins: {names}".format(names=[p.name for p in plugins]))
    else:
        print("Testing all plugins in {root}".format(root=root))

    results = [(p, run_one(p)) for p in plugins]
    success = all([t[1] for t in results])

    if not success:
        print("The following tests failed:")
        for t in filter(lambda t: not t[1], results):
            print(" - {p.name} ({p.path})".format(p=t[0]))
        sys.exit(1)

if __name__ == "__main__":
    run_all(sys.argv[1:])
