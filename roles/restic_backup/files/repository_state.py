"""Report whether the restic repository exists, opened with the settings given on standard input.

tasks/repository.yml runs this file as "python3 -c <code>" with one JSON object on standard input:
{"restic": <binary>, "repository": <repository>, "password": <password>, "env": {<name>: <value>}}.
The settings reach restic as environment variables of its process (readable by root only), never as
arguments, so they appear neither in the process list nor in the output of the task. It prints one
JSON object: {"state": "exists" | "missing" | "wrong-password" | "error", "rc": <exit code of
restic>, "stderr": <end of restic's error output>}. restic 0.17 and later exit with 10 for a missing
repository and 12 for a wrong password; 0.16 exits with 1 and prints the messages checked below.
"""

import json
import os
import subprocess
import sys

MISSING_MESSAGE = "Is there a repository at the following location?"
WRONG_PASSWORD_MESSAGE = "wrong password or no key found"

settings = json.load(sys.stdin)
env = {name: value for name, value in os.environ.items() if not name.startswith("RESTIC_")}
env.update({str(name): str(value) for name, value in settings["env"].items()})
env["RESTIC_REPOSITORY"] = settings["repository"]
env["RESTIC_PASSWORD"] = settings["password"]
try:
    result = subprocess.run(
        [settings["restic"], "--no-cache", "cat", "config"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, timeout=600, check=False)
    rc, stderr = result.returncode, result.stderr.strip()
except (OSError, subprocess.TimeoutExpired) as error:
    rc, stderr = -1, str(error)

if rc == 0:
    state = "exists"
elif rc == 10 or (rc == 1 and MISSING_MESSAGE in stderr):
    state = "missing"
elif rc == 12 or WRONG_PASSWORD_MESSAGE in stderr:
    state = "wrong-password"
else:
    state = "error"
print(json.dumps({"state": state, "rc": rc, "stderr": stderr[-2000:]}))
