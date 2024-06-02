import json
import os
import subprocess
from pathlib import Path

from utils import configure_git, enumerate_plugins


def update_and_commit_badge(plugin_name: str, passed: bool, workflow: str) -> bool:
    json_data = {"schemaVersion": 1, "label": "", "message": " ✔ ", "color": "green"}
    if not passed:
        json_data.update({"message": "✗", "color": "red"})

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


def push_badges_data(workflow: str, num_of_python_versions: int):
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
