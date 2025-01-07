from itertools import groupby
import logging


__virtualname__ = "snap"

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def __virtual__():
    return __virtualname__


def _snapd_is_installed():
    return __salt__["pkg.info_installed"]("snapd", failhard=False)


def _cleanup_stdout(raw_stdout):
    """Remove duplicate lines from the output of "snap remove"."""
    # `raw_stdout` looks like "\rRemoving snap abc     /\rRemoving snap abc     -".
    log.debug(f"raw stdout: {raw_stdout}")
    # Split this on '\r' into a list of lines.
    stdout_lines = raw_stdout.splitlines()
    log.debug(f"stdout as lines: {stdout_lines}")
    # Remove the "spinning character" at the end of each line.
    stdout_lines = [l.rstrip('/-\\|') for l in stdout_lines]
    log.debug(f"stripped 1: {stdout_lines}")
    # Remove the remaining trailing whitespace in each line.
    stdout_lines = [l.rstrip() for l in stdout_lines]
    log.debug(f"stripped 2: {stdout_lines}")
    # Remove duplicate consecutive lines.
    stdout_lines = [l for l, _ in groupby(stdout_lines)]
    log.debug(f"without duplicates: {stdout_lines}")
    return '\n'.join(stdout_lines)


def purged(name):
    """Purge the snap from the system."""
    ret = {
        "name": name,
        "result": None,
        "changes": {},
        "comment": "",
    }

    # Check if snapd is installed. If not, then we cannot do anything.
    if not _snapd_is_installed():
        ret["result"] = True
        ret["comment"] = f'Cannot purge snap "{name}" because snapd is not installed.'
        return ret

    if __opts__["test"]:
        ret["result"] = None
        ret["comment"] = "Test mode is not supported."
        return ret

    # Attempt to purge the snap. `cmd_output` is a dict looking like this:
    # `{"pid": 123, "retcode": 0, "stdout": "abc", "stderr": "abc"}`
    cmd_output = __salt__["cmd.run_all"](cmd=f"snap remove --purge {name}")

    if cmd_output["stderr"] == f'snap "{name}" is not installed':
        ret["result"] = True
        ret["comment"] = f'Snap "{name}" is already removed.'
        return ret

    stdout = _cleanup_stdout(cmd_output["stdout"])
    stderr = cmd_output["stderr"]

    if cmd_output["retcode"] != 0:
        ret["result"] = False
        ret["comment"] = f'Non-zero return code when purging snap "{name}".'
        ret["changes"] = {
            "stdout": stdout,
            "stderr": stderr,
        }
        return ret

    # The return code of "snap remove" is 0 and stderr is != "... not installed".
    # So it's very likely that the removal was successful. We verify this by
    # asking snapd now if the snap is still present.
    # (`ignore_retcode` is needed to suppress Salt's error log in case of a non-zero
    # return code -- a non-zero return code is a good thing and is what we expect)
    is_still_installed = __salt__["cmd.retcode"](cmd=f"snap list {name}", ignore_retcode=True) == 0
    if is_still_installed:
        ret["result"] = False
        ret["comment"] = f'Purging snap "{name}" was unsuccessful.'
        ret["changes"] = {
            "stdout": stdout,
            "stderr": stderr,
        }
        return ret

    # Checks were passed; the removal was successful.
    ret["result"] = True
    ret["comment"] = f'Snap "{name}" was successfully purged.'
    ret["changes"] = {
        "old": "installed",
        "new": "removed",
        "stdout": stdout,
        "stderr": stderr,
    }
    return ret


def assert_all_removed(name="assert_all_removed"):
    """Succeeds if no snaps are installed, fails otherwise."""
    ret = {
        "name": name,
        "result": None,
        "changes": {},
        "comment": "",
    }

    # Check if snapd is installed. If not, then we cannot do anything.
    if not _snapd_is_installed():
        ret["result"] = True
        ret["comment"] = "Cannot check for installed snaps because snapd is not installed. Assuming that all snaps are removed."
        return ret

    # List installed snaps. `cmd_output` is a dict looking like this:
    # `{"pid": 123, "retcode": 0, "stdout": "abc", "stderr": "abc"}`
    cmd_output = __salt__["cmd.run_all"](cmd="snap list")

    # stdout should be blank if no snaps are installed. A non-blank stdout means
    # that snaps are installed.
    if cmd_output["stdout"]:
        ret["result"] = False
        ret["comment"] = '\n'.join([
            "It seems like at least one snap is still installed.",
            "Output:",
            cmd_output["stdout"],
            "Errors:",
            cmd_output["stderr"] or "(no errors)",
        ])
        return ret

    # If no snaps are installed, then we expect stdout to be blank and stderr to
    # be this string: "No snaps are installed yet. Try 'snap install hello-world'."
    if cmd_output["stderr"].startswith("No snaps are installed"):
        ret["result"] = True
        ret["comment"] = "No snaps are installed."
        return ret

    # At this point stdout is blank and stderr is not the expected string. So
    # something probably went wrong.
    ret["result"] = False
    ret["comment"] = '\n'.join([
        "Listing all installed snaps failed due to error.",
        cmd_output["stderr"],
    ])
    return ret
