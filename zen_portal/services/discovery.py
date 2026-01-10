"""DiscoveryService: Discover existing Claude sessions and git worktrees."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


@dataclass
class ClaudeSessionInfo:
    """Information about an existing Claude Code session."""

    session_id: str
    project_path: Path  # The working directory this session was in
    modified_at: datetime
    file_path: Path  # Path to the session file
    created_at: datetime | None = None  # File creation time (macOS st_birthtime)


@dataclass
class DiscoveredWorktree:
    """Information about a discovered worktree."""

    path: Path
    branch: str
    has_claude_sessions: bool = False
    recent_session_id: str | None = None


@dataclass
class ExternalTmuxSession:
    """Information about an external tmux session."""

    name: str
    command: str | None  # Running command (claude, zsh, vim, etc.)
    cwd: Path | None  # Current working directory
    is_dead: bool
    has_claude: bool  # Whether Claude Code appears to be running
    claude_session_id: str | None = None  # Detected Claude session ID if available


class DiscoveryService:
    """Discovers existing Claude sessions and git worktrees."""

    CLAUDE_DIR = Path.home() / ".claude"
    PROJECTS_DIR = CLAUDE_DIR / "projects"

    def __init__(self, working_dir: Path | None = None):
        """Initialize discovery service.

        Args:
            working_dir: Current working directory to find relevant sessions
        """
        self._working_dir = working_dir or Path.cwd()

    def _path_to_claude_project_name(self, path: Path) -> str:
        """Convert a path to Claude's project directory name format.

        Claude stores projects with both / and _ replaced by -,
        e.g., /Users/kentgang/git/agent_services -> -Users-kentgang-git-agent-services
        """
        # Resolve and make absolute
        path = path.resolve()
        # Replace both / and _ with -
        return str(path).replace("/", "-").replace("_", "-")

    def _claude_project_name_to_path(self, name: str) -> Path:
        """Convert Claude's project directory name back to a path.

        Claude stores paths with both / and _ replaced by -.
        Dashes in original paths are preserved as dashes.
        We need to try various combinations to find the actual path.
        """
        # Remove leading dash
        if name.startswith("-"):
            name = name[1:]

        # Simple case: just replace - with /
        simple_path = Path("/" + name.replace("-", "/"))
        if simple_path.exists():
            return simple_path

        # Try intelligent reconstruction by checking each segment
        segments = name.split("-")
        reconstructed = self._reconstruct_path_greedy(segments)
        if reconstructed and reconstructed.exists():
            return reconstructed

        # Fallback to simple conversion
        return simple_path

    def _reconstruct_path_greedy(self, segments: list[str]) -> Path | None:
        """Greedily reconstruct a path from dash-separated segments.

        For each dash position, tries:
        1. Treat as path separator (/) - commit current segment as directory
        2. Treat as underscore (_) - extend current segment
        3. Treat as dash (-) - extend current segment with original dash

        Uses filesystem existence checks to determine the correct interpretation.
        """
        if not segments:
            return None

        # Build path one segment at a time, always checking filesystem
        current_path = ""
        current_segment = segments[0]

        for i in range(1, len(segments)):
            seg = segments[i]

            # Try treating dash as slash (new path segment)
            test_slash = current_path + "/" + current_segment if current_path else "/" + current_segment
            slash_test_path = Path(test_slash)

            if slash_test_path.exists() and slash_test_path.is_dir():
                # Current segment forms a valid directory, commit it
                current_path = test_slash
                current_segment = seg
            else:
                # Try extending with underscore first
                test_underscore = current_path + "/" + current_segment + "_" + seg if current_path else "/" + current_segment + "_" + seg
                # Try extending with dash
                test_dash = current_path + "/" + current_segment + "-" + seg if current_path else "/" + current_segment + "-" + seg

                # Check if extended path with underscore could be valid
                underscore_parent = Path(test_underscore).parent
                dash_parent = Path(test_dash).parent

                # Prefer underscore, then dash (keep segment growing)
                current_segment = current_segment + "_" + seg

        # Add the final segment and try underscore/dash variants
        base_path = current_path if current_path else ""

        # Try the final segment as-is (with underscores from our reconstruction)
        final_underscore = base_path + "/" + current_segment
        if Path(final_underscore).exists():
            return Path(final_underscore)

        # Try with remaining dashes converted to original dashes
        # This handles cases like zen-portal
        final_path = self._try_final_segment_variants(base_path, current_segment)
        return final_path or Path(final_underscore)

    def _try_final_segment_variants(self, base_path: str, segment: str) -> Path | None:
        """Try different interpretations of underscores in final segment.

        Some underscores might need to be dashes (like zen-portal).
        """
        # If there are underscores, try converting some to dashes
        if "_" in segment:
            # Try all-dash variant
            dash_variant = segment.replace("_", "-")
            test_path = base_path + "/" + dash_variant
            if Path(test_path).exists():
                return Path(test_path)

            # For each underscore position, try dash
            parts = segment.split("_")
            for i in range(len(parts) - 1):
                # Try dash at position i
                variant = "_".join(parts[:i+1]) + "-" + "_".join(parts[i+1:])
                test_path = base_path + "/" + variant
                if Path(test_path).exists():
                    return Path(test_path)

        return None

    def list_claude_sessions(
        self,
        project_path: Path | None = None,
        limit: int = 20,
    ) -> list[ClaudeSessionInfo]:
        """List Claude sessions for a specific project or all projects.

        Args:
            project_path: Specific project path to filter by (None = all)
            limit: Maximum number of sessions to return

        Returns:
            List of ClaudeSessionInfo sorted by modification time (newest first)
        """
        if not self.PROJECTS_DIR.exists():
            return []

        sessions = []

        # Filter by specific project or list all
        if project_path:
            project_name = self._path_to_claude_project_name(project_path)
            project_dirs = [self.PROJECTS_DIR / project_name]
        else:
            project_dirs = [
                d for d in self.PROJECTS_DIR.iterdir()
                if d.is_dir()
            ]

        for project_dir in project_dirs:
            if not project_dir.exists():
                continue

            # Get session files (UUIDs, not agent-* files)
            session_files = [
                f for f in project_dir.glob("*.jsonl")
                if not f.name.startswith("agent-")
                and self._is_valid_uuid(f.stem)
            ]

            for session_file in session_files:
                try:
                    stat = session_file.stat()
                    # Use st_birthtime on macOS for accurate creation time
                    created_at = None
                    if hasattr(stat, 'st_birthtime'):
                        created_at = datetime.fromtimestamp(stat.st_birthtime)
                    sessions.append(ClaudeSessionInfo(
                        session_id=session_file.stem,
                        project_path=self._claude_project_name_to_path(project_dir.name),
                        modified_at=datetime.fromtimestamp(stat.st_mtime),
                        file_path=session_file,
                        created_at=created_at,
                    ))
                except (OSError, ValueError):
                    continue

        # Sort by modification time (newest first) and limit
        sessions.sort(key=lambda s: s.modified_at, reverse=True)
        return sessions[:limit]

    def _is_valid_uuid(self, s: str) -> bool:
        """Check if string is a valid UUID format."""
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(s))

    def session_file_exists(self, session_id: str, project_path: Path | None = None) -> bool:
        """Check if a Claude session file exists and can be resumed.

        Args:
            session_id: Claude session ID (UUID)
            project_path: Optional project path to narrow search

        Returns:
            True if the session file exists and is readable
        """
        if not self.PROJECTS_DIR.exists():
            return False

        # If project path specified, check only that project
        if project_path:
            project_name = self._path_to_claude_project_name(project_path)
            session_file = self.PROJECTS_DIR / project_name / f"{session_id}.jsonl"
            return session_file.exists() and session_file.is_file()

        # Search all projects for the session
        for project_dir in self.PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue
            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists() and session_file.is_file():
                return True

        return False

    def list_sessions_for_current_project(self, limit: int = 10) -> list[ClaudeSessionInfo]:
        """List Claude sessions for the current working directory.

        Returns:
            List of ClaudeSessionInfo for the current project
        """
        return self.list_claude_sessions(project_path=self._working_dir, limit=limit)

    def find_session_for_zenportal(
        self,
        project_path: Path,
        zenportal_created_at: datetime,
    ) -> str | None:
        """Find the Claude session ID that best matches a zen-portal session.

        Uses created_at (st_birthtime on macOS) for accurate matching when available.
        Falls back to modified_at-based matching on other platforms.

        Args:
            project_path: Working directory of the zen-portal session
            zenportal_created_at: When the zen-portal session was created

        Returns:
            Best matching session ID or None
        """
        sessions = self.list_claude_sessions(project_path=project_path, limit=10)
        if not sessions:
            return None

        # Strategy 1: Use created_at if available (macOS)
        # Find sessions created AFTER zen-portal session, pick the one closest in time
        sessions_with_created = [s for s in sessions if s.created_at is not None]
        if sessions_with_created:
            candidates = [
                s for s in sessions_with_created
                if s.created_at >= zenportal_created_at
            ]
            if candidates:
                # Pick the one created closest to zen-portal creation time
                best = min(candidates, key=lambda s: s.created_at - zenportal_created_at)
                return best.session_id

        # Strategy 2: Fall back to modified_at
        # Find sessions modified after zen-portal creation, pick closest match
        candidates = [
            s for s in sessions
            if s.modified_at >= zenportal_created_at
        ]
        if candidates:
            # Among candidates, prefer one modified closest to creation time
            # (likely the one created around that time)
            best = min(candidates, key=lambda s: s.modified_at - zenportal_created_at)
            return best.session_id

        # Last resort: most recently modified session
        return sessions[0].session_id if sessions else None

    def list_all_projects(self) -> list[Path]:
        """List all projects that have Claude sessions.

        Returns:
            List of project paths sorted by recent activity
        """
        if not self.PROJECTS_DIR.exists():
            return []

        projects = []
        for project_dir in self.PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue

            # Get most recent session file modification time
            session_files = list(project_dir.glob("*.jsonl"))
            if not session_files:
                continue

            try:
                most_recent = max(f.stat().st_mtime for f in session_files)
                project_path = self._claude_project_name_to_path(project_dir.name)
                projects.append((project_path, most_recent))
            except (OSError, ValueError):
                continue

        # Sort by most recent activity
        projects.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in projects]

    def discover_worktrees_with_sessions(
        self,
        worktree_base_dir: Path,
    ) -> list[DiscoveredWorktree]:
        """Discover worktrees and check which have Claude sessions.

        Args:
            worktree_base_dir: Base directory where worktrees are stored

        Returns:
            List of DiscoveredWorktree with session information
        """
        if not worktree_base_dir.exists():
            return []

        discovered = []

        for worktree_path in worktree_base_dir.iterdir():
            if not worktree_path.is_dir():
                continue

            # Check if it's a git worktree (has .git file)
            git_file = worktree_path / ".git"
            if not git_file.exists():
                continue

            # Get branch name from .git file
            branch = ""
            if git_file.is_file():
                try:
                    content = git_file.read_text().strip()
                    # Format: gitdir: /path/to/repo/.git/worktrees/name
                    if content.startswith("gitdir:"):
                        worktree_git_path = Path(content.split(": ", 1)[1])
                        head_file = worktree_git_path / "HEAD"
                        if head_file.exists():
                            head_content = head_file.read_text().strip()
                            if head_content.startswith("ref: refs/heads/"):
                                branch = head_content[16:]
                except (OSError, IndexError):
                    pass

            # Check if there are Claude sessions for this worktree
            sessions = self.list_claude_sessions(project_path=worktree_path, limit=1)
            has_sessions = len(sessions) > 0
            recent_session_id = sessions[0].session_id if sessions else None

            discovered.append(DiscoveredWorktree(
                path=worktree_path,
                branch=branch,
                has_claude_sessions=has_sessions,
                recent_session_id=recent_session_id,
            ))

        return discovered

    def find_worktrees_in_common_locations(self) -> list[DiscoveredWorktree]:
        """Find worktrees in common locations.

        Searches:
        - ~/.zen-portal/worktrees (zen-portal default)
        - ~/worktrees
        - ./worktrees (relative to working dir)

        Returns:
            Combined list of discovered worktrees
        """
        locations = [
            Path.home() / ".zen-portal" / "worktrees",
            Path.home() / "worktrees",
            self._working_dir / "worktrees",
        ]

        all_worktrees = []
        seen_paths = set()

        for location in locations:
            if location.exists():
                worktrees = self.discover_worktrees_with_sessions(location)
                for wt in worktrees:
                    if wt.path not in seen_paths:
                        all_worktrees.append(wt)
                        seen_paths.add(wt.path)

        return all_worktrees

    def analyze_tmux_session(self, tmux_info: dict) -> ExternalTmuxSession:
        """Analyze a tmux session and detect if Claude is running.

        Args:
            tmux_info: Dict with name, command, cwd, is_dead, pid from TmuxService

        Returns:
            ExternalTmuxSession with Claude detection info
        """
        name = tmux_info.get("name", "")
        command = tmux_info.get("command")
        cwd = tmux_info.get("cwd")
        is_dead = tmux_info.get("is_dead", False)

        # Detect if Claude is running
        has_claude = command in ("claude", "node") if command else False

        # Try to find Claude session ID if Claude is running
        claude_session_id = None
        if has_claude and cwd:
            # Look for recent Claude sessions in this working directory
            sessions = self.list_claude_sessions(project_path=cwd, limit=1)
            if sessions:
                claude_session_id = sessions[0].session_id

        return ExternalTmuxSession(
            name=name,
            command=command,
            cwd=cwd,
            is_dead=is_dead,
            has_claude=has_claude,
            claude_session_id=claude_session_id,
        )
