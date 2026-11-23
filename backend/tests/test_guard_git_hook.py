"""El guardarraíl de git evalúa la rama del directorio al que apunta el comando.

`.claude/hooks/guard_git.py` decidía con `git rev-parse` en el directorio de la **sesión**.
Con git worktrees eso daba falsos positivos (la sesión en `develop`, el comando operando en
un worktree con rama `feat/…`) y también falsos negativos (la sesión en una rama con prefijo
y el comando entrando con `cd` en el repo que está en `develop`). Estos tests ejecutan el
hook real, por stdin, contra repositorios y worktrees reales.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard_git.py"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


def _git(cwd, *args):
    subprocess.run(GIT + list(args), cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def repos(tmp_path):
    """`principal` en develop y `wt` (worktree) en feat/x."""
    principal = tmp_path / "principal"
    principal.mkdir()
    _git(principal, "init", "-q", "-b", "develop")
    (principal / "a.txt").write_text("a")
    _git(principal, "add", "a.txt")
    _git(principal, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt"
    _git(principal, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    return principal, wt


def _decision(command, cwd):
    """'deny' | 'ask' | 'allow' para `command` lanzado desde la sesión `cwd`."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
    out = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, cwd=cwd, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    if not out.stdout.strip():
        return "allow"
    return json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_commit_en_rama_protegida_de_la_sesion_sigue_denegado(repos):
    principal, _ = repos
    assert _decision("git commit -m x", principal) == "deny"
    assert _decision("git push origin develop", principal) == "deny"


def test_cd_a_un_worktree_con_rama_con_prefijo_se_permite(repos):
    principal, wt = repos
    assert _decision(f"cd {wt.as_posix()} && git commit -m x", principal) == "allow"
    assert _decision(f"cd {wt.as_posix()} && git push -u origin feat/x", principal) == "allow"


def test_git_C_a_un_worktree_con_rama_con_prefijo_se_permite(repos):
    principal, wt = repos
    assert _decision(f"git -C {wt.as_posix()} commit -m x", principal) == "allow"
    assert _decision(f"git -C {wt.as_posix()} push -u origin feat/x", principal) == "allow"


def test_sesion_en_rama_con_prefijo_que_entra_con_cd_en_develop_se_deniega(repos):
    principal, wt = repos
    assert _decision(f"cd {principal.as_posix()} && git commit -m x", wt) == "deny"
    assert _decision(f"cd {principal.as_posix()}; git commit -m x", wt) == "deny"
    assert _decision(f"git -C {principal.as_posix()} commit -m x", wt) == "deny"


def test_si_algun_destino_esta_protegido_se_deniega(repos):
    principal, wt = repos
    mixto = f"cd {wt.as_posix()} && git add . && git commit -m a && cd {principal.as_posix()} && git commit -m b"
    assert _decision(mixto, principal) == "deny"


def test_sin_cd_ni_C_manda_la_rama_de_la_sesion(repos):
    principal, wt = repos
    assert _decision("git commit -m x", wt) == "allow"
    assert _decision("git commit -m x", principal) == "deny"


def test_destino_irresoluble_cae_a_la_rama_de_la_sesion(repos):
    principal, wt = repos
    # El directorio no existe: no se sabe dónde va el commit; manda la sesión (como antes).
    assert _decision("git -C /no/existe/jamas commit -m x", principal) == "deny"
    assert _decision("git -C /no/existe/jamas commit -m x", wt) == "allow"


def test_el_texto_del_mensaje_no_se_interpreta_como_comando(repos):
    principal, wt = repos
    mensaje = 'fix: a && git push origin develop; cd /tmp'
    assert _decision(f'git -C {wt.as_posix()} commit -m "{mensaje}"', principal) == "allow"


def test_comandos_sin_commit_ni_push_no_se_tocan(repos):
    principal, _ = repos
    assert _decision("git status", principal) == "allow"
    assert _decision("ls -la", principal) == "allow"
    assert _decision(f"cd {principal.as_posix()} && git log --oneline", principal) == "allow"


def test_force_push_a_rama_protegida_sigue_denegado(repos):
    principal, wt = repos
    assert _decision("git push --force origin develop", wt) == "deny"
    assert _decision(f"git -C {principal.as_posix()} push --force origin x", wt) == "deny"


def test_no_verify_sigue_denegado_en_cualquier_rama(repos):
    _, wt = repos
    assert _decision(f"git -C {wt.as_posix()} commit --no-verify -m x", wt) == "deny"
