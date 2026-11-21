"""Build a new repository skeleton from the Project templates."""

from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from project_paths import ProjectError


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "项目骨架"
DIRECTORIES = ("src", "log", "config", "docs/01-原始资料", "docs/02-对接资料", "docs/03-开发资料", "infra/migrations")
FILES = (".gitignore", ".env.example", "infra/README.md")


def render_readme(name: str, summary: str | None = None) -> str:
    name = name.strip()
    if not name or "\n" in name or "\r" in name:
        raise ProjectError("项目名称应为一行非空文字")
    contents = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    if summary is not None:
        summary = summary.strip()
        if not summary or "\n" in summary or "\r" in summary:
            raise ProjectError("项目简介应为一行非空文字")
        contents = contents.replace("〔项目简介〕", summary, 1)
    return contents.replace("〔项目名称〕", name, 1)


def write_missing_readme(project_dir: Path, contents: str) -> None:
    """Create the repository introduction once, including on case-sensitive filesystems."""
    if any(p.name.partition(".")[0].casefold() == "readme" for p in project_dir.iterdir()):
        return
    try:
        with (project_dir / "README.md").open("x", encoding="utf-8", newline="\n") as readme:
            readme.write(contents)
    except FileExistsError:
        pass


def create_scaffold(name: str, project_dir: Path, *, summary: str | None = None) -> Path:
    contents = render_readme(name, summary)
    if project_dir.exists() or project_dir.is_symlink():
        raise ProjectError(f"骨架目标目录已存在：{project_dir}")

    destination = project_dir.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".luz-scaffold-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "project"
        for relative in DIRECTORIES:
            (staged / relative).mkdir(parents=True, exist_ok=True)
        for relative in FILES:
            copyfile(TEMPLATE / relative, staged / relative)
        write_missing_readme(staged, contents)
        staged.rename(destination)
    return destination
