import logging as log
import os
import subprocess
import sys

# Constants
encoding = "utf-8"

def run_cmd(cmd: str, print_output: bool = False, check: bool = True, timeout_seconds: int = 300, print_cmd: bool = False) -> [int, str, str]:
    log.debug('Running command "{}"'.format(cmd, check))
    if print_cmd:
        print(cmd)
    stdout = ""
    stderr = ""
    try:
        result = subprocess.run(
            [cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            check=check,
            timeout=timeout_seconds,
        )

        if result.stdout:
            stdout = result.stdout.decode(encoding).strip()

        if result.stderr:
            stderr = result.stderr.decode(encoding).strip()

        if print_output and result.returncode != 0:
            log.info("Got exit code {} to command: {}".format(result.returncode, cmd))

        if print_output:
            if stdout:
                log.info("STDOUT:\n{}".format(stdout))
            if stderr:
                log.info("STDERR:\n{}".format(stderr))
        return result.returncode, stdout, stderr
    except subprocess.CalledProcessError as e:
        if e.stdout:
            stdout = e.stdout.decode(encoding).strip()
        if e.stderr:
            stderr = e.stderr.decode(encoding).strip()
        log.error("STDOUT:\n{}".format(stdout))
        log.error("STDERR:\n{}".format(stderr))
        if check:
            sys.exit(e.returncode)
        return e.returncode, stdout, stderr

def remove_prefix(base: str, prefix: str) -> str:
    if base.startswith(prefix):
        return base[len(prefix):]
    else:
        return base[:]
