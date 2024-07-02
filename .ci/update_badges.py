import json
import os
import subprocess
import time
from pathlib import Path

from utils import configure_git, enumerate_plugins


def update_and_commit_badge(
    plugin_name: str, passed: bool, workflow: str, has_tests: bool
) -> bool:
    json_data = {"schemaVersion": 1, "label": "", "message": "✔", "color": "green"}
    if not passed:
        json_data.update({"message": "✗", "color": "red"})
    if not has_tests:
        json_data.update({"message": "?", "color": "orange"})

    filename = os.path.join(".badges", f"{plugin_name}_{workflow}.json")
    with open(filename, "w") as file:
        file.write(json.dumps(json_data))

    output = subprocess.check_output(["git", "add", "-v", filename]).decode("utf-8")
    if output != "":
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f'Update {plugin_name} badge to {"passed" if passed else "failed"} ({workflow})',
            ]
        )
        return True
    return False


def cleanup_old_results(plugin_name: str, file: Path) -> bool:
    os.remove(file)
    print(
        f"Removed deprecated result {file.name} for {plugin_name}, we no longer test for this version!"
    )
    subprocess.run(["git", "add", "-v", file])
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"Remove deprecated result {file.name}",
        ]
    )
    return True


def check_wanted_result(result_file: str, python_versions_tested: list) -> bool:
    for version in python_versions_tested:
        if version in result_file:
            return True
    return False


def push_badges_data(workflow: str, python_versions_tested: list):
    print("Pushing badges data...")
    configure_git()

    root_path = (
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
        .decode("ASCII")
        .strip()
    )
    plugins = list(enumerate_plugins(Path(root_path)))

    subprocess.run(["git", "fetch"])
    subprocess.run(["git", "checkout", "badges"])
    subprocess.run(["git", "pull"])

    any_changes = False
    for plugin in plugins:
        results = []
        _dir = f".badges/gather_data/{workflow}/{plugin.name}"
        if os.path.exists(_dir):
            for child in Path(_dir).iterdir():
                if not check_wanted_result(child.name, python_versions_tested):
                    any_changes |= cleanup_old_results(plugin.name, child)
                    continue
                result = child.read_text().strip()
                results.append(result)
                print(f"Results for {child}: {result}")

            passed = False
            if (
                len(set(results)) == 1
                and results[0] == "passed"
                and len(results) == len(python_versions_tested)
            ):
                passed = True
            any_changes |= update_and_commit_badge(plugin.name, passed, workflow, True)
        else:
            any_changes |= update_and_commit_badge(plugin.name, False, workflow, False)

    if any_changes:
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plugins completion script")
    parser.add_argument("workflow", type=str, help="Name of the GitHub workflow")
    parser.add_argument(
        "python_versions_tested",
        nargs="*",
        type=str,
        default=[],
        help="Python versions tested",
    )
    args = parser.parse_args()

    push_badges_data(args.workflow, args.python_versions_tested)
