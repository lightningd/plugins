from pathlib import Path
import subprocess
from pprint import pprint
from collections import namedtuple
from typing import Generator
import sys
import tempfile
import shlex
import os


# Directories that are not plugins
exclude = [
    '.ci',
    '.git',
    '.github',
    'lightning',
    'feeadjuster'
]
global_dependencies = [
    'pytest==5.*',
    'pytest-xdist',
    'pytest-timeout',
    'pyln-testing',
    'pytest-rerunfailures',
]

Plugin = namedtuple('Plugin', ['name', 'path', 'requirements', 'devrequirements'])


def enumerate_plugins(basedir: Path) -> Generator[Plugin, None, None]:
    plugins = [x for x in basedir.iterdir() if x.is_dir() and x.name not in exclude]
    pytests = [x for x in plugins if (x / Path('requirements.txt')).exists()]

    for p in sorted(pytests):
        yield Plugin(
            name=p.name,
            path=p,
            requirements=p/Path('requirements.txt'),
            devrequirements=p/Path('requirements-dev.txt'),
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

    subprocess.check_output(['virtualenv', '--clear', '-q', vpath])
    bin_path = vpath / 'bin'
    pip_path = vpath / 'bin' / 'pip3'
    python_path = vpath / 'bin' / 'python'
    pytest_path = vpath / 'bin' / 'pytest'
    pip_opts = ['-qq']

    # Install pytest (eventually we'd want plugin authors to include
    # it in their requirements-dev.txt, but for now let's help them a
    # bit).
    subprocess.check_output(
        [pip_path, 'install', *pip_opts, *global_dependencies],
        stderr=subprocess.STDOUT,
    )

    # Now install all the requirements
    print("Installing requirements from {p.requirements}".format(p=p))
    subprocess.check_output(
        [pip_path, 'install', '-U', *pip_opts, '-r', p.requirements],
        stderr=subprocess.STDOUT,
    )

    if p.devrequirements.exists():
        print("Installing requirements from {p.devrequirements}".format(p=p))
        subprocess.check_output(
            [pip_path, 'install', '-U', *pip_opts, '-r', p.devrequirements],
            stderr=subprocess.STDOUT,
        )

    if os.environ.get("PYLN_MASTER", "0") == "1":
        pass

    assert pytest_path.exists()

    # Update pyln-testing to master since we're running against c-lightning master.
    install_pyln_testing(pip_path)

    print("Running tests")
    try:
        env = os.environ.copy()
        env.update({
            # Need to customize PATH so lightningd can find the correct python3
            'PATH': "{}:{}".format(bin_path, os.environ['PATH']),
            # Some plugins require a valid locale to be set
            'LC_ALL': 'C.UTF-8',
            'LANG': 'C.UTF-8',
        })
        subprocess.check_call(
            [
                pytest_path,
                p.path,
                '-vvv',
                '--timeout=600',
                '--timeout-method=thread',
                '--junitxml=report-{}.xml'.format(p.name),
                '--reruns=2',
                '--color=no',
                '-o', 'junit_family=xunit2',
                '-n=5',
            ],
            stderr=subprocess.STDOUT,
            env=env,
        )
        return True
    except:
        return False
    finally:
        print("##[endgroup]")


def install_pyln_testing(pip_path):
    # Update pyln-testing to master since we're running against c-lightning master.
    dest = Path('/tmp/lightning')
    repo = 'https://github.com/ElementsProject/lightning.git'
    if not dest.exists():
        subprocess.check_output([
            'git', 'clone', repo, dest
        ])

    subprocess.check_output([
        pip_path, 'install', '-U', f'{dest}/contrib/pyln-testing'
    ])

    subprocess.check_output([
        pip_path, 'install', '-U', f'{dest}/contrib/pyln-client'
    ])

    subprocess.check_output([
        pip_path, 'install', '-U', f'{dest}/contrib/pyln-proto'
    ])


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
