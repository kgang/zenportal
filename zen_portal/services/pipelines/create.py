"""Create session pipeline: composable steps for session creation."""

from dataclasses import dataclass, field
from pathlib import Path

from ..pipeline import StepResult
from ..config import ConfigManager, FeatureSettings, ProxySettings
from ..session_commands import SessionCommandBuilder
from ..tmux import TmuxService
from ..worktree import WorktreeService
from ..proxy_validation import ProxyValidator
from ...models.session import Session, SessionState, SessionFeatures, SessionType


@dataclass
class CreateContext:
    """Flows through the create pipeline, accumulating state."""

    # Input parameters
    name: str
    prompt: str = ""
    session_type: SessionType = SessionType.AI
    provider: str = "claude"  # AI provider for AI sessions
    features: SessionFeatures | None = None

    # Resolved configuration
    resolved_config: FeatureSettings | None = None
    working_dir: Path | None = None
    dangerous_mode: bool = False
    uses_proxy: bool = False

    # Built artifacts
    session: Session | None = None
    command: list[str] | None = None
    env_vars: dict[str, str] | None = None
    tmux_name: str = ""

    # Proxy validation
    proxy_warning: str = ""


class ValidateLimit:
    """Step: Check session count limit."""

    def __init__(self, max_sessions: int, current_count: int):
        self.max = max_sessions
        self.current = current_count

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        if self.current >= self.max:
            return StepResult.fail(f"Maximum sessions ({self.max}) reached")
        return StepResult.success(ctx)


class ResolveConfig:
    """Step: Resolve configuration through tiers."""

    def __init__(self, config_manager: ConfigManager, fallback_dir: Path):
        self._config = config_manager
        self._fallback = fallback_dir

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        # Build session-level override
        session_override = None
        if ctx.features and ctx.features.has_overrides():
            session_override = FeatureSettings(
                working_dir=ctx.features.working_dir,
                model=ctx.features.model if ctx.session_type == SessionType.AI and ctx.provider == "claude" else None,
            )

        resolved = self._config.resolve_features(session_override)
        ctx.resolved_config = resolved
        ctx.working_dir = resolved.working_dir or self._fallback
        ctx.dangerous_mode = ctx.features.dangerously_skip_permissions if ctx.features else False

        # Check if using proxy (only for Claude AI sessions)
        ctx.uses_proxy = bool(
            ctx.session_type == SessionType.AI
            and ctx.provider == "claude"
            and resolved.openrouter_proxy
            and resolved.openrouter_proxy.enabled
        )

        return StepResult.success(ctx)


class CreateSessionModel:
    """Step: Create the Session dataclass."""

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        session = Session(
            name=ctx.name,
            prompt=ctx.prompt if ctx.session_type == SessionType.AI else "",
            session_type=ctx.session_type,
            provider=ctx.provider if ctx.session_type == SessionType.AI else "claude",
            features=ctx.features or SessionFeatures(),
            resolved_working_dir=ctx.working_dir,
            resolved_model=ctx.resolved_config.model if ctx.session_type == SessionType.AI and ctx.provider == "claude" else None,
            dangerously_skip_permissions=ctx.dangerous_mode,
            uses_proxy=ctx.uses_proxy,
        )

        if ctx.session_type == SessionType.AI and ctx.provider == "claude":
            session.claude_session_id = ""  # Discovered later

        ctx.session = session
        return StepResult.success(ctx)


class SetupWorktree:
    """Step: Set up git worktree if enabled."""

    def __init__(self, worktree_service: WorktreeService | None):
        self._worktree = worktree_service

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        if not ctx.session or not ctx.resolved_config:
            return StepResult.fail("Session or config not initialized")

        # Only setup worktree if service is available
        if self._worktree:
            ctx.working_dir = self._worktree.setup_for_session(
                ctx.session,
                ctx.features,
                ctx.resolved_config.worktree,
            )
        else:
            ctx.working_dir = ctx.session.resolved_working_dir

        return StepResult.success(ctx)


class ValidateBinary:
    """Step: Validate required binary exists."""

    def __init__(self, commands: SessionCommandBuilder):
        self._commands = commands

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        error = self._commands.validate_binary(ctx.session_type, ctx.provider)
        if error:
            return StepResult.fail(error)
        return StepResult.success(ctx)


class ValidateProxy:
    """Step: Validate proxy settings (non-blocking, just sets warning)."""

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        if not ctx.resolved_config:
            return StepResult.success(ctx)

        proxy = ctx.resolved_config.openrouter_proxy
        # Only validate proxy for Claude AI sessions
        if ctx.session_type != SessionType.AI or ctx.provider != "claude" or not proxy:
            return StepResult.success(ctx)

        validator = ProxyValidator(proxy)
        result = validator.validate_sync()
        if result and result.has_errors:
            ctx.proxy_warning = result.summary

        return StepResult.success(ctx)


class BuildCommand:
    """Step: Build the shell command to execute."""

    def __init__(self, commands: SessionCommandBuilder):
        self._commands = commands

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        if not ctx.session or not ctx.resolved_config:
            return StepResult.fail("Session or config not initialized")

        command_args = self._commands.build_create_command(
            session_type=ctx.session_type,
            working_dir=ctx.working_dir,
            provider=ctx.provider,
            model=ctx.resolved_config.model,
            prompt=ctx.prompt,
            dangerous_mode=ctx.dangerous_mode,
        )

        # Build env vars for proxy (only for Claude AI sessions)
        env_vars = None
        if ctx.session_type == SessionType.AI and ctx.provider == "claude" and ctx.resolved_config.openrouter_proxy:
            env_vars = self._commands.build_proxy_env_vars(ctx.resolved_config.openrouter_proxy)

        ctx.command = self._commands.wrap_with_banner(
            command_args, ctx.name, ctx.session.id, env_vars
        )
        ctx.env_vars = env_vars

        return StepResult.success(ctx)


class SpawnTmux:
    """Step: Create the tmux session."""

    def __init__(self, tmux: TmuxService, tmux_name_func):
        self._tmux = tmux
        self._tmux_name = tmux_name_func

    def invoke(self, ctx: CreateContext) -> StepResult[CreateContext]:
        if not ctx.session or not ctx.command:
            return StepResult.fail("Session or command not initialized")

        tmux_name = self._tmux_name(ctx.session.id)
        ctx.tmux_name = tmux_name
        ctx.session.tmux_name = tmux_name

        result = self._tmux.create_session(
            name=tmux_name,
            command=ctx.command,
            working_dir=ctx.working_dir,
        )

        if result.success:
            ctx.session.state = SessionState.RUNNING
        else:
            ctx.session.state = SessionState.FAILED
            ctx.session.error_message = result.error or "Failed to create tmux session"

        # Apply proxy warning if set
        if ctx.proxy_warning and ctx.session:
            ctx.session.proxy_warning = ctx.proxy_warning

        return StepResult.success(ctx)


class CreateSessionPipeline:
    """Orchestrates session creation as explicit steps."""

    def __init__(
        self,
        tmux: TmuxService,
        config_manager: ConfigManager,
        commands: SessionCommandBuilder,
        worktree_service: WorktreeService | None,
        tmux_name_func,
        max_sessions: int,
        current_count: int,
        fallback_dir: Path,
    ):
        self._steps = [
            ValidateLimit(max_sessions, current_count),
            ResolveConfig(config_manager, fallback_dir),
            CreateSessionModel(),
            SetupWorktree(worktree_service),
            ValidateBinary(commands),
            ValidateProxy(),
            BuildCommand(commands),
            SpawnTmux(tmux, tmux_name_func),
        ]

    def invoke(self, ctx: CreateContext) -> StepResult[Session]:
        """Run the pipeline and return the created session."""
        for step in self._steps:
            result = step.invoke(ctx)
            if not result.ok:
                # On failure, still return a failed session if one was created
                if ctx.session:
                    ctx.session.state = SessionState.FAILED
                    ctx.session.error_message = result.error
                    return StepResult.success(ctx.session)
                return StepResult.fail(result.error)
            ctx = result.value

        return StepResult.success(ctx.session)
