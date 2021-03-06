import datetime
import os
from invoke import task

from .utils import (
    bin_name,
    get_gopath,
    get_build_flags,
    REPO_PATH,
    get_version,
    get_git_branch_name,
    get_go_version,
    get_git_commit,
)
from .build_tags import get_default_build_tags
from .go import generate

BIN_DIR = os.path.join(".", "bin", "security-agent")
BIN_PATH = os.path.join(BIN_DIR, bin_name("security-agent", android=False))
GIMME_ENV_VARS = ['GOROOT', 'PATH']


def get_go_env(ctx, go_version):
    goenv = {}
    if go_version:
        lines = ctx.run("gimme {version}".format(version=go_version)).stdout.split("\n")
        for line in lines:
            for env_var in GIMME_ENV_VARS:
                if env_var in line:
                    goenv[env_var] = line[line.find(env_var) + len(env_var) + 1 : -1].strip('\'\"')

    # extend PATH from gimme with the one from get_build_flags
    if "PATH" in os.environ and "PATH" in goenv:
        goenv["PATH"] += ":" + os.environ["PATH"]

    return goenv


@task
def build(ctx, race=False, go_version=None, incremental_build=False, major_version='7', arch="x64", go_mod="vendor"):
    """
    Build the security agent
    """
    ldflags, gcflags, env = get_build_flags(ctx, arch=arch, major_version=major_version, python_runtimes='3')

    # TODO use pkg/version for this
    main = "main."
    ld_vars = {
        "Version": get_version(ctx, major_version=major_version),
        "GoVersion": get_go_version(),
        "GitBranch": get_git_branch_name(),
        "GitCommit": get_git_commit(),
        "BuildDate": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    goenv = {}
    if go_version:
        lines = ctx.run("gimme {version}".format(version=go_version)).stdout.split("\n")
        for line in lines:
            for env_var in GIMME_ENV_VARS:
                if env_var in line:
                    goenv[env_var] = line[line.find(env_var) + len(env_var) + 1 : -1].strip('\'\"')
        ld_vars["GoVersion"] = go_version

    # Generating go source from templates by running go generate on ./pkg/status
    generate(ctx)

    # extend PATH from gimme with the one from get_build_flags
    if "PATH" in os.environ and "PATH" in goenv:
        goenv["PATH"] += ":" + os.environ["PATH"]
    env.update(goenv)

    ldflags += ' '.join(["-X '{name}={value}'".format(name=main + key, value=value) for key, value in ld_vars.items()])
    build_tags = get_default_build_tags(
        build="security-agent"
    )  # TODO/FIXME: Arch not passed to preserve build tags. Should this be fixed?

    # TODO static option
    cmd = 'go build -mod={go_mod} {race_opt} {build_type} -tags "{go_build_tags}" '
    cmd += '-o {agent_bin} -gcflags="{gcflags}" -ldflags="{ldflags}" {REPO_PATH}/cmd/security-agent'

    args = {
        "go_mod": go_mod,
        "race_opt": "-race" if race else "",
        "build_type": "" if incremental_build else "-a",
        "go_build_tags": " ".join(build_tags),
        "agent_bin": BIN_PATH,
        "gcflags": gcflags,
        "ldflags": ldflags,
        "REPO_PATH": REPO_PATH,
    }

    ctx.run(cmd.format(**args), env=env)


@task()
def gen_mocks(ctx):
    """
    Generate mocks.
    """

    gopath = get_gopath(ctx)
    if not os.path.exists(os.path.join(gopath, "bin/mockery")):
        with ctx.cd(gopath):
            ctx.run("go get -u github.com/vektra/mockery/cmd/mockery", env={'GO111MODULE': 'on'})

    with ctx.cd("./pkg/compliance"):
        ctx.run("./gen_mocks.sh")


@task
def functional_tests(
    ctx, race=False, verbose=False, go_version=None, arch="x64", major_version='7', pattern='', output=''
):
    ldflags, gcflags, env = get_build_flags(ctx, arch=arch, major_version=major_version)

    goenv = get_go_env(ctx, go_version)
    env.update(goenv)

    cmd = 'sudo -E go test -tags functionaltests,linux_bpf {output_opt} {verbose_opt} {run_opt} {REPO_PATH}/pkg/security/tests'

    args = {
        "verbose_opt": "-v" if verbose else "",
        "race_opt": "-race" if race else "",
        "output_opt": "-c -o " + output if output else "",
        "run_opt": "-run " + pattern if pattern else "",
        "REPO_PATH": REPO_PATH,
    }

    ctx.run(cmd.format(**args), env=env)
