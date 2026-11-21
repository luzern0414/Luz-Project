"""Build a new repository skeleton from the Project templates."""

from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from project_paths import ProjectError


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "项目骨架"
DIRECTORIES = ("src", "log", "config", "docs/01-原始资料", "docs/02-对接资料", "docs/03-开发资料", "infra/migrations")
FILES = ("README.md", ".gitignore", ".env.example", "infra/README.md")


def create_scaffold(name: str, project_dir: Path) -> Path:
    name = name.strip()
    if not name or "\n" in name or "\r" in name:
        raise ProjectError("项目名称应为一行非空文字")
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
        readme = staged / "README.md"
        contents = readme.read_text(encoding="utf-8")
        readme.write_text(contents.replace("〔项目名称〕", name, 1), encoding="utf-8", newline="\n")
        staged.rename(destination)
    return destination
