"""Central configuration. Everything that used to be hardcoded lives here and
reads from the environment, so no secret is committed to source control.
"""
import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------------

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
WORKSPACE_DIR = os.path.abspath(
    os.getenv("WORKSPACE_DIR", os.path.join(BACKEND_DIR, "..", "workspace"))
)
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# --- Auth --------------------------------------------------------------------

_secret = os.getenv("SECRET_KEY")
if not _secret:
    # Never fall back to a fixed literal: an attacker who reads the source could
    # otherwise forge a token for any user. An ephemeral key means tokens simply
    # do not survive a restart in dev, which is the safe failure mode.
    _secret = secrets.token_urlsafe(48)
    warnings.warn(
        "SECRET_KEY not set; generated an ephemeral key. "
        "Sessions will not survive a restart. Set SECRET_KEY in .env for real use.",
        RuntimeWarning,
    )

SECRET_KEY = _secret
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# --- GitHub ------------------------------------------------------------------

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# --- LLM ---------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# "openai"     -> the OpenAI API
# "compatible" -> any OpenAI-compatible endpoint (Azure, OpenRouter, Ollama,
#                 vLLM, LM Studio). Set LLM_BASE_URL; uses the OpenAI SDK.
# "anthropic"  -> the Anthropic API
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_SEED = int(os.getenv("LLM_SEED", "20260815"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# Extra models available for the cross-model agreement study, as
# "provider:model" entries, e.g. "anthropic:claude-sonnet-4-5,openai:gpt-4o-mini".
LLM_COMPARISON_MODELS = [
    entry.strip()
    for entry in os.getenv("LLM_COMPARISON_MODELS", "").split(",")
    if entry.strip()
]

# "auto"    -> use the API when a key is present, deterministic stub otherwise
# "offline" -> never call the API (reproducible runs, CI, and ablation studies)
# "api"     -> require the API; fail loudly if the key is missing
LLM_MODE = os.getenv("LLM_MODE", "auto").lower()

# Pricing used only for reporting estimated cost in the metrics endpoint.
USD_PER_1M_INPUT_TOKENS = float(os.getenv("USD_PER_1M_INPUT_TOKENS", "5.00"))
USD_PER_1M_OUTPUT_TOKENS = float(os.getenv("USD_PER_1M_OUTPUT_TOKENS", "15.00"))

# --- Incremental analysis ----------------------------------------------------

# How many historical graph snapshots to retain per project.
MAX_GRAPH_VERSIONS = int(os.getenv("MAX_GRAPH_VERSIONS", "3"))

# Default gate strategy: which signal decides whether the LLM runs at all.
#   always      - re-analyse unconditionally (the pre-existing behaviour/baseline)
#   content     - re-analyse when any file's raw bytes changed (naive baseline)
#   structural  - re-analyse when the AST-derived fingerprint changed
#   isomorphism - structural, but additionally skip changes that leave the design
#                 graph isomorphic (pure renames / reorderings)
DEFAULT_GATE_STRATEGY = os.getenv("GATE_STRATEGY", "structural")

# How many hops out from a changed node get included in the LLM's context.
IMPACT_RADIUS = int(os.getenv("IMPACT_RADIUS", "1"))

# Whether UML associations count toward the similarity score. Off by default:
# an association cannot be proven from an AST, only evidenced. Findings are
# reported either way, and the choice is recorded in every result.
ASSOCIATION_SCORING = os.getenv("ASSOCIATION_SCORING", "false").lower() in ("1", "true", "yes")

# --- Limits ------------------------------------------------------------------

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
MAX_ARCHIVE_MEMBERS = int(os.getenv("MAX_ARCHIVE_MEMBERS", "20000"))
MAX_ARCHIVE_UNCOMPRESSED_BYTES = int(
    os.getenv("MAX_ARCHIVE_UNCOMPRESSED_BYTES", str(500 * 1024 * 1024))
)
MAX_ANALYSES_PER_HOUR = int(os.getenv("MAX_ANALYSES_PER_HOUR", "60"))

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java"}
