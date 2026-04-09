from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDef:
    name: str
    description: str
    mode: str  # cli | mat | both
    usage: str
    aliases: tuple[str, ...] = ()


COMMANDS = [
    CommandDef('run', 'Launch the multi-agent terminal', 'cli', 'ixel', aliases=('',)),
    CommandDef('setup', 'Interactive setup — configure agents + API keys', 'cli', 'ixel setup', aliases=('configure',)),
    CommandDef('status', 'Single-screen health dashboard for providers, agents, and secrets', 'cli', 'ixel status'),
    CommandDef('models', 'Show providers, models, and auth status', 'cli', 'ixel models'),
    CommandDef('config', 'Show resolved config, tokens, validation status', 'both', 'ixel config', aliases=('cfg',)),
    CommandDef('agents', 'List agents + test connectivity', 'both', 'ixel agents'),
    CommandDef('doctor', 'Check Python deps, config, gateway reachability', 'cli', 'ixel doctor'),
    CommandDef('version', 'Show version', 'cli', 'ixel version', aliases=('v',)),
    CommandDef('help', 'Show this help', 'both', 'ixel help', aliases=('h',)),
    CommandDef('full', 'Send prompt to all agents — compare side by side', 'mat', '/full <prompt>'),
    CommandDef('consensus', 'Stream responses, then synthesize once enough valid answers arrive', 'mat', '/consensus [flags] <prompt>', aliases=('cons',)),
    CommandDef('quit', 'Exit', 'mat', '/quit', aliases=('exit', 'q')),
]


def _mode_matches(cmd: CommandDef, mode: str) -> bool:
    return cmd.mode == mode or cmd.mode == 'both'


def build_help_rows(mode: str) -> list[tuple[str, str]]:
    rows = []
    for cmd in COMMANDS:
        if _mode_matches(cmd, mode):
            rows.append((cmd.usage, cmd.description))
    return rows


def resolve_command_name(name: str, mode: str):
    raw = name.strip().lstrip('/')
    if not raw and mode == 'cli':
        return 'run'

    exact = []
    candidates = []
    for cmd in COMMANDS:
        if not _mode_matches(cmd, mode):
            continue
        names = (cmd.name, *cmd.aliases)
        if raw in names:
            exact.append(cmd.name)
        if any(n.startswith(raw) for n in names if n):
            candidates.append(cmd.name)

    if exact:
        return exact[0]
    uniq = sorted(set(candidates))
    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) > 1:
        return ('ambiguous', uniq)
    return None
