"""Polyglot Conformance Platform -- HTTP API.

Route groups, in the order they appear:

* meta and authentication
* GitHub (entirely optional -- every project workflow below works without it)
* projects
* the virtual directory: create, read, edit, move, delete, upload, export
* UML models
* analysis, versions, metrics, and the research endpoints

Conventions used throughout: paths derived from user input are containment
checked, failures return an HTTP status with a human-readable `detail`, and any
endpoint that can spend money at a model provider is rate limited.
"""
import hashlib
import hmac
import json
import logging
import os
import shutil
import statistics
import traceback
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import ai_service
import auth
import models.user_model as user_model
from config import (
    ASSOCIATION_SCORING,
    CORS_ORIGINS,
    DEFAULT_GATE_STRATEGY,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_WEBHOOK_SECRET,
    LLM_MODEL,
    MAX_GRAPH_VERSIONS,
    MAX_UPLOAD_BYTES,
    WORKSPACE_DIR,
)
from core.archive import ArchiveError, extract_zip
from core.graph_builder import graph_to_payload
from core.graph_store import GraphVersionStore
from core.paths import UnsafePathError, resolve_within, sanitize_project_name
from core.pipeline import default_parse_source, run_analysis
from core.run_ledger import RunLedger
from core.workspace_fs import (
    Workspace,
    WorkspaceError,
    delete_uml_model,
    list_uml_models,
    uml_dir,
)
from database import Base, engine, get_db

app = FastAPI(
    title="Polyglot Conformance Platform API",
    version="3.0.0",
    description=(
        "Design/code conformance checking with incremental, gated re-analysis. "
        "GitHub is optional: projects can be created, filled, and edited entirely "
        "through the virtual-directory endpoints."
    ),
    openapi_tags=[
        {"name": "meta", "description": "Health and client configuration."},
        {"name": "auth", "description": "Registration and sessions."},
        {"name": "github", "description": "Optional GitHub import and webhooks."},
        {"name": "projects", "description": "Project lifecycle."},
        {"name": "files", "description": "The virtual directory: edit code without git."},
        {"name": "uml", "description": "StarUML model management."},
        {"name": "analysis", "description": "Conformance analysis, versions, metrics."},
        {"name": "research", "description": "Repeatability and cross-model agreement."},
        {"name": "statistics", "description": "Publication-ready statistics, CSV and LaTeX export."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("uvicorn.error")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Turn a crash into a normal JSON error response instead of a raw 500.

    Without a handler, an unhandled exception propagates past CORSMiddleware
    instead of through it, so the response it sends back carries no
    Access-Control-Allow-Origin header. The browser can then only report the
    whole request as a network failure -- indistinguishable from the backend
    being down -- which sent more than one debugging session chasing a
    "server unreachable" ghost that was actually a Python traceback sitting
    in the terminal the whole time. The traceback is still logged here, in
    full, exactly as it would be otherwise.
    """
    logger.error("Unhandled exception on %s %s\n%s", request.method, request.url.path,
                 "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


Base.metadata.create_all(bind=engine)

GATE_STRATEGIES = ("always", "content", "structural", "isomorphism")


# --- request models ----------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str
    github_repo_full_name: Optional[str] = None


class GitHubCode(BaseModel):
    code: str


class FileContextRequest(BaseModel):
    file_path: str


class FileWrite(BaseModel):
    path: str
    content: str = ""


class FileMove(BaseModel):
    source: str
    destination: str


class FolderCreate(BaseModel):
    path: str


class BatchWrite(BaseModel):
    files: List[FileWrite]


class AnalyzeRequest(BaseModel):
    gate_strategy: Optional[str] = None
    force: bool = False


class DeltaCommit(BaseModel):
    modified_files: List[str] = []
    commit_hash: Optional[str] = None
    gate_strategy: Optional[str] = None


class RepeatabilityRequest(BaseModel):
    runs: int = Field(default=3, ge=2, le=10)


class ModelComparisonRequest(BaseModel):
    models: List[str] = Field(default_factory=list, max_length=6)


class StatisticsRequest(BaseModel):
    """Which projects to include. Empty means all of them."""
    projects: List[str] = Field(default_factory=list)


# --- helpers -----------------------------------------------------------------


def user_workspace(username: str) -> str:
    path = resolve_within(WORKSPACE_DIR, username)
    os.makedirs(path, exist_ok=True)
    return path


def project_dir(username: str, project_name: str) -> str:
    """Resolve a project directory, rejecting traversal and missing projects."""
    try:
        safe = sanitize_project_name(project_name)
        path = resolve_within(user_workspace(username), safe)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail="Project not found.")
    return path


def workspace_for(username: str, project_name: str) -> Workspace:
    return Workspace(project_dir(username, project_name))


def validated_strategy(value: Optional[str]) -> str:
    strategy = (value or DEFAULT_GATE_STRATEGY).lower()
    if strategy not in GATE_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown gate strategy '{value}'. Expected one of: {', '.join(GATE_STRATEGIES)}.",
        )
    return strategy


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail=f"Upload exceeds the {MAX_UPLOAD_BYTES} byte limit."
        )
    return content


def workspace_guard(operation):
    try:
        return operation()
    except WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Filesystem error: {exc}")


# --- meta --------------------------------------------------------------------


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/config", tags=["meta"])
def public_config():
    """Configuration the frontend needs.

    The GitHub client ID is public by design; the secret never leaves the server.
    """
    return {
        "github_client_id": GITHUB_CLIENT_ID,
        "github_configured": bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET),
        "llm_enabled": ai_service.llm_available(),
        "llm_model": LLM_MODEL if ai_service.llm_available() else ai_service.OFFLINE_MODEL,
        "available_models": ai_service.available_models(),
        "default_gate_strategy": DEFAULT_GATE_STRATEGY,
        "gate_strategies": list(GATE_STRATEGIES),
        "max_versions": MAX_GRAPH_VERSIONS,
        "association_scoring": ASSOCIATION_SCORING,
        "exact_token_counts": ai_service.token_counts_are_exact(),
    }


# --- authentication ----------------------------------------------------------


@app.post("/register", response_model=user_model.UserResponse, tags=["auth"])
def register_user(user: user_model.UserCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(user_model.DBUser)
        .filter(
            (user_model.DBUser.username == user.username)
            | (user_model.DBUser.email == user.email)
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered.")

    new_user = user_model.DBUser(
        username=user.username,
        email=user.email,
        hashed_password=auth.get_password_hash(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/login", response_model=user_model.Token, tags=["auth"])
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = (
        db.query(user_model.DBUser)
        .filter(user_model.DBUser.username == form_data.username)
        .first()
    )
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": auth.create_access_token({"sub": user.username}),
        "token_type": "bearer",
    }


@app.get("/me", response_model=user_model.UserResponse, tags=["auth"])
def whoami(current: user_model.DBUser = Depends(auth.get_current_user)):
    return current


# --- GitHub (optional) --------------------------------------------------------


@app.post("/github/callback", tags=["github"])
async def github_callback(
    payload: GitHubCode,
    db: Session = Depends(get_db),
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        raise HTTPException(
            status_code=503,
            detail="GitHub integration is not configured on the server (missing client credentials).",
        )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": payload.code,
            },
        )

    try:
        token_data = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="GitHub returned an unreadable response.")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail=token_data.get("error_description") or "Failed to retrieve GitHub token.",
        )

    current.github_token = access_token
    db.commit()
    return {"status": "success", "message": "GitHub connected successfully"}


@app.post("/github/disconnect", tags=["github"])
def github_disconnect(
    db: Session = Depends(get_db), current: user_model.DBUser = Depends(auth.get_current_user)
):
    current.github_token = None
    db.commit()
    return {"status": "success"}


@app.get("/github/status", tags=["github"])
def github_status(current: user_model.DBUser = Depends(auth.get_current_user)):
    return {"is_connected": bool(current.github_token)}


@app.get("/github/repos", tags=["github"])
async def get_github_repos(current: user_model.DBUser = Depends(auth.get_current_user)):
    if not current.github_token:
        raise HTTPException(status_code=400, detail="GitHub is not connected.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            params={"per_page": 100, "sort": "updated"},
            headers={
                "Authorization": f"Bearer {current.github_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if response.status_code == 401:
        raise HTTPException(status_code=400, detail="GitHub token is no longer valid. Reconnect GitHub.")
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch repositories from GitHub.")

    return {
        "repos": [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "clone_url": repo["clone_url"],
                "default_branch": repo.get("default_branch", "main"),
                "private": repo.get("private", False),
            }
            for repo in response.json()
        ]
    }


async def import_github_repo(token: str, full_name: str, destination: str) -> Dict[str, Any]:
    """Download and unpack a repository, using its declared default branch."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        meta = await client.get(f"https://api.github.com/repos/{full_name}", headers=headers)
        if meta.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read repository metadata (HTTP {meta.status_code}).",
            )
        branch = meta.json().get("default_branch") or "main"

        archive = await client.get(
            f"https://api.github.com/repos/{full_name}/zipball/{branch}", headers=headers
        )
        if archive.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Could not download branch '{branch}' (HTTP {archive.status_code}).",
            )

    try:
        report = extract_zip(archive.content, destination, strip_root=True)
    except ArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    report["branch"] = branch
    return report


@app.post("/github/webhook", tags=["github"])
async def github_webhook_listener(request: Request):
    """Verify the delivery, then report the changed files.

    Signature verification is mandatory when a secret is configured: without it
    this endpoint accepts unauthenticated deliveries from anyone who can reach it.
    """
    raw_body = await request.body()

    if GITHUB_WEBHOOK_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            GITHUB_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    if request.headers.get("X-GitHub-Event") != "push":
        return {"status": "ignored", "reason": "Not a push event"}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Webhook payload was not valid JSON.")

    modified: set = set()
    for commit in payload.get("commits", []) or []:
        modified.update(commit.get("added", []) or [])
        modified.update(commit.get("modified", []) or [])
        modified.update(commit.get("removed", []) or [])

    return {
        "status": "webhook_received",
        "repository": (payload.get("repository") or {}).get("full_name"),
        "verified": bool(GITHUB_WEBHOOK_SECRET),
        "modified_files": sorted(modified),
        "message": (
            f"Tracked {len(modified)} file change(s). "
            "Call /projects/{name}/webhook/delta to run the incremental analysis."
        ),
    }


# --- projects ----------------------------------------------------------------


@app.get("/projects", tags=["projects"])
def list_projects(current: user_model.DBUser = Depends(auth.get_current_user)):
    workspace = user_workspace(current.username)
    projects = []
    for entry in sorted(os.listdir(workspace)):
        path = os.path.join(workspace, entry)
        if not os.path.isdir(path):
            continue
        store = GraphVersionStore(path)
        latest = store.latest()
        stats = Workspace(path).stats()
        projects.append(
            {
                "name": entry,
                "versions": len(store.list_versions()),
                "latest_version": latest["version"] if latest else None,
                "latest_score": latest.get("similarity_score") if latest else None,
                "last_analysed": latest.get("created_at") if latest else None,
                "file_count": stats["files"],
                "has_uml": bool(list_uml_models(path)),
            }
        )
    return {"projects": projects}


@app.post("/projects", tags=["projects"])
async def create_project(
    project: ProjectCreate,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    try:
        safe_name = sanitize_project_name(project.name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    workspace = user_workspace(current.username)
    path = resolve_within(workspace, safe_name)
    if os.path.exists(path):
        raise HTTPException(status_code=400, detail="Project already exists.")

    source_dir = os.path.join(path, "source")
    os.makedirs(source_dir, exist_ok=True)
    os.makedirs(os.path.join(path, "uml"), exist_ok=True)
    os.makedirs(os.path.join(path, "reports"), exist_ok=True)

    with open(os.path.join(path, "config.json"), "w", encoding="utf-8") as handle:
        json.dump({"github_repo_full_name": project.github_repo_full_name}, handle)

    import_report = None
    if project.github_repo_full_name:
        if not current.github_token:
            shutil.rmtree(path, ignore_errors=True)
            raise HTTPException(status_code=400, detail="GitHub is not connected.")
        try:
            import_report = await import_github_repo(
                current.github_token, project.github_repo_full_name, source_dir
            )
        except HTTPException:
            # Do not leave a half-created project behind on a failed import.
            shutil.rmtree(path, ignore_errors=True)
            raise

    return {"status": "success", "project_name": safe_name, "import": import_report}


@app.get("/projects/{project_name}", tags=["projects"])
def project_detail(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    path = project_dir(current.username, project_name)
    store = GraphVersionStore(path)
    latest = store.latest()
    return {
        "name": project_name,
        "source": Workspace(path).stats(),
        "uml_models": list_uml_models(path),
        "versions": len(store.list_versions()),
        "latest_version": latest["version"] if latest else None,
        "latest_score": latest.get("similarity_score") if latest else None,
    }


@app.delete("/projects/{project_name}", tags=["projects"])
def delete_project(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    path = project_dir(current.username, project_name)
    shutil.rmtree(path)
    return {"status": "success", "message": "Project deleted successfully."}


# --- the virtual directory -----------------------------------------------------


@app.get("/projects/{project_name}/tree", tags=["files"])
def get_project_tree(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    workspace = workspace_for(current.username, project_name)
    return {"tree": workspace.tree(), "stats": workspace.stats()}


@app.get("/projects/{project_name}/files", tags=["files"])
def read_file(
    project_name: str,
    path: str,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(lambda: workspace.read(path))


@app.post("/projects/{project_name}/files", tags=["files"])
def create_file(
    project_name: str,
    payload: FileWrite,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Create a new file. Fails if it already exists -- use PUT to overwrite."""
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(
        lambda: workspace.write(payload.path, payload.content, create_only=True)
    )


@app.put("/projects/{project_name}/files", tags=["files"])
def write_file(
    project_name: str,
    payload: FileWrite,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Create or overwrite a file. This is how the in-browser editor saves."""
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(lambda: workspace.write(payload.path, payload.content))


@app.delete("/projects/{project_name}/files", tags=["files"])
def delete_file(
    project_name: str,
    path: str,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(lambda: workspace.delete(path))


@app.post("/projects/{project_name}/files/move", tags=["files"])
def move_file(
    project_name: str,
    payload: FileMove,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Rename or move a file or folder within the project."""
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(lambda: workspace.move(payload.source, payload.destination))


@app.post("/projects/{project_name}/files/batch", tags=["files"])
def write_batch(
    project_name: str,
    payload: BatchWrite,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    workspace = workspace_for(current.username, project_name)
    items = [{"path": item.path, "content": item.content} for item in payload.files]
    return workspace_guard(lambda: workspace.write_many(items))


@app.post("/projects/{project_name}/folders", tags=["files"])
def create_folder(
    project_name: str,
    payload: FolderCreate,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    workspace = workspace_for(current.username, project_name)
    return workspace_guard(lambda: workspace.mkdir(payload.path))


@app.post("/projects/{project_name}/upload/source", tags=["files"])
async def upload_source(
    project_name: str,
    file: UploadFile = File(...),
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Upload one file, or a .zip whose folder structure is preserved."""
    path = project_dir(current.username, project_name)
    source_dir = resolve_within(path, "source")
    os.makedirs(source_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "upload")
    content = await read_upload(file)

    if filename.lower().endswith(".zip"):
        try:
            report = extract_zip(content, source_dir, strip_root=False)
        except ArchiveError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "success", "filename": filename, "extracted": report}

    target = resolve_within(source_dir, filename)
    with open(target, "wb") as handle:
        handle.write(content)
    return {"status": "success", "filename": filename}


@app.post("/projects/{project_name}/upload/source-batch", tags=["files"])
async def upload_source_batch(
    project_name: str,
    files: List[UploadFile] = File(...),
    paths: str = Form("[]"),
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Upload many files at once, preserving relative paths.

    This is what a whole-folder upload uses: the browser supplies each file's
    path within the chosen folder, and the structure is reproduced verbatim, so
    a project can be populated from a local directory with no archive and no git.
    """
    workspace = workspace_for(current.username, project_name)

    try:
        relative_paths = json.loads(paths) if paths else []
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="`paths` must be a JSON array of strings.")
    if relative_paths and len(relative_paths) != len(files):
        raise HTTPException(
            status_code=400, detail="`paths` must have one entry per uploaded file."
        )

    written: List[str] = []
    rejected: List[Dict[str, str]] = []
    total = 0

    for index, upload in enumerate(files):
        content = await upload.read()
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            rejected.append({"path": upload.filename or "?", "reason": "batch size limit reached"})
            break
        relative = (
            relative_paths[index]
            if index < len(relative_paths) and relative_paths[index]
            else os.path.basename(upload.filename or f"file-{index}")
        )
        try:
            result = workspace.write_bytes(relative, content)
            written.append(result["path"])
        except (WorkspaceError, OSError) as exc:
            rejected.append({"path": str(relative), "reason": str(exc)})

    return {"status": "success", "written": written, "rejected": rejected}


@app.delete("/projects/{project_name}/source", tags=["files"])
def clear_source(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    """Empty the virtual directory, keeping the project and its history."""
    workspace = workspace_for(current.username, project_name)
    return {"status": "success", "removed": workspace.clear()}


@app.get("/projects/{project_name}/export", tags=["files"])
def export_project(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    """Download the virtual directory as a zip."""
    workspace = workspace_for(current.username, project_name)
    payload = workspace.export_zip()
    safe = sanitize_project_name(project_name).replace(" ", "_")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}-source.zip"'},
    )


# --- UML models ---------------------------------------------------------------


@app.get("/projects/{project_name}/uml", tags=["uml"])
def list_models(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    path = project_dir(current.username, project_name)
    return {"models": list_uml_models(path)}


@app.post("/projects/{project_name}/upload/uml", tags=["uml"])
async def upload_uml(
    project_name: str,
    file: UploadFile = File(...),
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    path = project_dir(current.username, project_name)
    filename = os.path.basename(file.filename or "")
    if not filename.endswith(".mdj"):
        raise HTTPException(status_code=400, detail="Only StarUML (.mdj) files are supported.")

    content = await read_upload(file)
    try:
        parsed = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Reject at upload time rather than failing silently at analysis time.
        raise HTTPException(
            status_code=400,
            detail="That .mdj file is not valid JSON and cannot be read as a StarUML model.",
        )
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="A StarUML model must be a JSON object.")

    from parsers.uml_parser import StarUMLParser
    validator = StarUMLParser(filename)
    validator._index(parsed)
    validator._extract(parsed)
    if not validator.model.elements:
        raise HTTPException(status_code=400, detail="This model contains no UML classes or interfaces. Upload a class model; use-case and sequence diagrams cannot be compared.")

    target = resolve_within(uml_dir(path), filename)
    with open(target, "wb") as handle:
        handle.write(content)
    return {"status": "success", "filename": filename, "models": list_uml_models(path)}


@app.delete("/projects/{project_name}/uml/{filename}", tags=["uml"])
def remove_uml(
    project_name: str,
    filename: str,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    path = project_dir(current.username, project_name)
    removed = workspace_guard(lambda: delete_uml_model(path, filename))
    return {"status": "success", "removed": removed, "models": list_uml_models(path)}


# --- analysis -----------------------------------------------------------------


@app.post("/projects/{project_name}/analyze", tags=["analysis"])
def trigger_analysis(
    project_name: str,
    request: Optional[AnalyzeRequest] = None,
    current: user_model.DBUser = Depends(auth.rate_limit),
):
    options = request or AnalyzeRequest()
    path = project_dir(current.username, project_name)
    strategy = validated_strategy(options.gate_strategy)
    try:
        return run_analysis(path, gate_strategy=strategy, force=options.force)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"The source parser is unavailable ({exc}). Install tree-sitter grammars.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")


@app.post("/projects/{project_name}/webhook/delta", tags=["analysis"])
def incremental_delta_check(
    project_name: str,
    payload: DeltaCommit,
    current: user_model.DBUser = Depends(auth.rate_limit),
):
    """Run the incremental pipeline for a set of changed files.

    The changed-file list is informational: the gate recomputes the real delta
    from the source tree, so a caller cannot understate a change to skip analysis.
    """
    path = project_dir(current.username, project_name)
    strategy = validated_strategy(payload.gate_strategy)
    result = run_analysis(path, gate_strategy=strategy)
    result["reported_modified_files"] = payload.modified_files
    result["commit_hash"] = payload.commit_hash
    return result


@app.get("/projects/{project_name}/versions", tags=["analysis"])
def list_versions(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    path = project_dir(current.username, project_name)
    store = GraphVersionStore(path)
    return {
        "max_versions": MAX_GRAPH_VERSIONS,
        "versions": [
            {
                "version": record["version"],
                "created_at": record["created_at"],
                "parent_version": record.get("parent_version"),
                "reused_from": record.get("reused_from"),
                "similarity_score": record.get("similarity_score"),
                "gap_count": record.get("gap_count"),
                "node_count": record.get("node_count"),
                "edge_count": record.get("edge_count"),
                "gate": record.get("gate", {}),
                "llm": record.get("llm", {}),
            }
            for record in store.list_versions()
        ],
    }


@app.get("/projects/{project_name}/versions/{version}/graph", tags=["analysis"])
def get_version_graph(
    project_name: str,
    version: int,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    path = project_dir(current.username, project_name)
    graph = GraphVersionStore(path).load_graph(version)
    if graph is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} is no longer retained (only the last {MAX_GRAPH_VERSIONS} are kept).",
        )
    return {"version": version, "graph_data": graph_to_payload(graph)}


@app.get("/projects/{project_name}/versions/diff", tags=["analysis"])
def diff_versions(
    project_name: str,
    from_version: int,
    to_version: int,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    path = project_dir(current.username, project_name)
    try:
        return GraphVersionStore(path).diff(from_version, to_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/projects/{project_name}/metrics", tags=["analysis"])
def project_metrics(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    path = project_dir(current.username, project_name)
    ledger = RunLedger(path)
    return {"metrics": ledger.metrics(), "runs": ledger.rows(limit=100)}


@app.get("/projects/{project_name}/benchmark", tags=["analysis"])
def run_token_benchmark(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    """Static comparison: raw source tokens vs. extracted-structure tokens.

    This measures the *representation* saving only. The saving from skipping
    re-analysis entirely is measured separately, from real runs, at /metrics.
    """
    path = project_dir(current.username, project_name)
    source_dir = os.path.join(path, "source")

    raw_chunks: List[str] = []
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", "venv"}]
        for filename in files:
            if os.path.splitext(filename)[1].lower() in {".py", ".java", ".js", ".ts", ".tsx", ".jsx"}:
                try:
                    with open(os.path.join(root, filename), "r", errors="ignore") as handle:
                        raw_chunks.append(handle.read())
                except OSError:
                    continue

    raw_tokens = ai_service.count_tokens("\n".join(raw_chunks))
    architecture = default_parse_source(source_dir)
    optimized_tokens = ai_service.count_tokens(json.dumps(architecture))

    return {
        "raw_tokens": raw_tokens,
        "optimized_tokens": optimized_tokens,
        "token_reduction_percentage": round((1 - (optimized_tokens / max(raw_tokens, 1))) * 100, 2),
        "files_considered": len(architecture.get("files", [])),
        "exact_token_counts": ai_service.token_counts_are_exact(),
        "note": "Representation saving only; end-to-end saving from gating is at /metrics.",
    }


@app.post("/projects/{project_name}/explain", tags=["analysis"])
def explain_project_file(
    project_name: str,
    request: FileContextRequest,
    current: user_model.DBUser = Depends(auth.rate_limit),
):
    path = project_dir(current.username, project_name)
    try:
        target = resolve_within(path, "source", request.file_path)
    except UnsafePathError:
        # Without this check, `file_path="../../../../.env"` read any file the
        # server process could reach.
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found in project.")

    try:
        with open(target, "r", encoding="utf-8") as handle:
            content = handle.read()
    except (UnicodeDecodeError, OSError):
        raise HTTPException(status_code=400, detail="Cannot read binary or unsupported file.")

    return ai_service.explain_file(content, request.file_path)


# --- research -----------------------------------------------------------------


@app.post("/projects/{project_name}/repeatability", tags=["research"])
def repeatability_harness(
    project_name: str,
    request: RepeatabilityRequest,
    current: user_model.DBUser = Depends(auth.rate_limit),
):
    """Re-run the full analysis N times on identical input and report the spread.

    A single similarity score from a non-deterministic model is not a
    measurement. This endpoint produces the variance that has to accompany it.
    """
    path = project_dir(current.username, project_name)
    scores: List[float] = []
    gap_counts: List[float] = []
    node_counts: List[float] = []

    for _ in range(request.runs):
        result = run_analysis(path, gate_strategy="always", force=True)
        if result["similarity_score"] is None:
            raise HTTPException(status_code=422, detail=result["evaluation"]["issues"])
        score = result.get("model_score") if result["llm"]["invoked"] else result["similarity_score"]
        scores.append(float(score))
        gap_counts.append(float(len(result["ai_gaps"])))
        node_counts.append(float(result["networkx_nodes"]))

    return {
        "runs": request.runs,
        "llm_enabled": ai_service.llm_available(),
        "similarity_score": _spread(scores),
        "gap_count": _spread(gap_counts),
        "graph_node_count": _spread(node_counts),
        "note": (
            "Deterministic offline mode: zero variance is expected."
            if not ai_service.llm_available()
            else "Non-zero spread quantifies run-to-run instability at temperature 0."
        ),
    }


@app.post("/projects/{project_name}/model-comparison", tags=["research"])
def model_comparison(
    project_name: str,
    request: ModelComparisonRequest,
    current: user_model.DBUser = Depends(auth.rate_limit),
):
    """Run the same analysis under several models and report their agreement.

    Nothing is persisted: the comparison must not pollute the version history or
    the cost ledger it is measuring. Where the models disagree is the evidence
    for which findings are about the approach and which are about one model.
    """
    path = project_dir(current.username, project_name)
    specs = request.models or [entry["spec"] for entry in ai_service.available_models()]
    specs = list(dict.fromkeys(specs))[:6]

    outcomes = []
    for spec in specs:
        try:
            result = run_analysis(
                path, gate_strategy="always", force=True, model_spec=spec, persist=False
            )
        except Exception as exc:
            outcomes.append({"spec": spec, "error": str(exc)})
            continue
        outcomes.append(
            {
                "spec": spec,
                "model": result["llm"]["model"],
                "provider": result["llm"].get("provider"),
                "invoked": result["llm"]["invoked"],
                "similarity_score": (result.get("model_score") if result["llm"]["invoked"] else result["similarity_score"]),
                "structural_score": result["similarity_score"],
                "gap_count": len(result["ai_gaps"]),
                "gaps": result["ai_gaps"],
                "graph_nodes": result["networkx_nodes"],
                "grounded_node_ratio": result["graph_validation"].get("grounded_node_ratio"),
                "prompt_tokens": result["llm"]["prompt_tokens"],
                "completion_tokens": result["llm"]["completion_tokens"],
                "latency_ms": result["llm"]["latency_ms"],
            }
        )

    usable = [outcome for outcome in outcomes if "error" not in outcome and outcome.get("structural_score") is not None and outcome.get("similarity_score") is not None]
    agreement = []
    for index, left in enumerate(usable):
        for right in usable[index + 1:]:
            agreement.append(
                {
                    "pair": [left["spec"], right["spec"]],
                    "score_difference": abs(left["similarity_score"] - right["similarity_score"]),
                    "gap_jaccard": _jaccard(set(left["gaps"]), set(right["gaps"])),
                    "graph_node_difference": abs(left["graph_nodes"] - right["graph_nodes"]),
                }
            )

    scores = [outcome["similarity_score"] for outcome in usable]
    return {
        "models": outcomes,
        "agreement": agreement,
        "score_spread": _spread([float(score) for score in scores]) if len(scores) > 1 else None,
        "note": (
            "Rule-based structural findings are identical across models by construction; "
            "only the model-authored score, gaps, and graph can differ."
        ),
    }


# --- statistics ---------------------------------------------------------------


def _collect_rows(username: str, project_names: List[str]) -> List[Dict[str, Any]]:
    """Ledger rows across one or more projects, tagged with their project name.

    Pooling projects is what makes cluster bootstrapping and grouped
    cross-validation possible, so the statistics improve as more projects are
    analysed in the tool rather than only in the offline replay.
    """
    workspace = user_workspace(username)
    names = project_names or [
        entry for entry in sorted(os.listdir(workspace))
        if os.path.isdir(os.path.join(workspace, entry))
    ]

    rows: List[Dict[str, Any]] = []
    for name in names:
        try:
            path = project_dir(username, name)
        except HTTPException:
            continue
        for row in RunLedger(path).rows(limit=100000):
            enriched = dict(row)
            enriched.setdefault("project", name)
            rows.append(enriched)
    return rows


def _deviation_summary() -> Optional[Dict[str, Any]]:
    """The seeded-deviation confusion matrix, if it has been generated.

    `research/evaluate_deviations.py` writes it. It is the only table in the
    study with unambiguous ground truth, so the page shows it whenever it is
    there and tells the user how to produce it when it is not.
    """
    for candidate in (
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "results", "deviations_summary.json"),
        os.path.join(os.getcwd(), "results", "deviations_summary.json"),
    ):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, ValueError):
                continue
    return None


@app.post("/statistics", tags=["statistics"])
def workspace_statistics(
    request: Optional[StatisticsRequest] = None,
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Every statistic the paper needs, pooled across the selected projects."""
    from stats.report import build_report

    options = request or StatisticsRequest()
    rows = _collect_rows(current.username, options.projects)
    report = build_report(rows, deviations=_deviation_summary())
    report["source"] = "run ledger"
    report["projects_included"] = sorted({row.get("project") for row in rows if row.get("project")})
    return report


@app.get("/projects/{project_name}/statistics", tags=["statistics"])
def project_statistics(
    project_name: str, current: user_model.DBUser = Depends(auth.get_current_user)
):
    from stats.report import build_report

    path = project_dir(current.username, project_name)
    rows = [dict(row, project=project_name) for row in RunLedger(path).rows(limit=100000)]
    report = build_report(rows, default_project=project_name, deviations=_deviation_summary())
    report["source"] = "run ledger"
    report["projects_included"] = [project_name]
    return report


@app.post("/statistics/export", tags=["statistics"])
def export_statistics(
    request: Optional[StatisticsRequest] = None,
    fmt: str = "zip",
    current: user_model.DBUser = Depends(auth.get_current_user),
):
    """Download the statistics as CSV files (zip), a single CSV, or LaTeX tables."""
    from stats.exports import to_csv_bundle, to_latex, to_zip
    from stats.report import build_report, normalise_rows

    options = request or StatisticsRequest()
    rows = _collect_rows(current.username, options.projects)
    if not rows:
        raise HTTPException(status_code=400, detail="No runs recorded yet; nothing to export.")

    report = build_report(rows, deviations=_deviation_summary())
    normalised = normalise_rows(rows)

    if fmt == "latex":
        return Response(
            content=to_latex(report),
            media_type="text/x-tex",
            headers={"Content-Disposition": 'attachment; filename="conformance-tables.tex"'},
        )

    bundle = to_csv_bundle(report, normalised)
    if fmt == "csv":
        combined = "\n\n".join(f"# {name}\n{content}" for name, content in sorted(bundle.items()))
        return Response(
            content=combined,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="conformance-statistics.csv"'},
        )

    return Response(
        content=to_zip(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="conformance-statistics.zip"'},
    )


def _spread(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"values": [], "mean": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0, "range": 0.0}
    return {
        "values": values,
        "mean": round(statistics.mean(values), 3),
        "stdev": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
    }


def _jaccard(left: set, right: set) -> Optional[float]:
    if not left and not right:
        return None
    union = left | right
    return round(len(left & right) / len(union), 4) if union else None
