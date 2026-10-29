"""
Comprehensive QA & Security Regression Test Suite for CVtoMatch (JobSpy).
Verifies fixes for SEC-01..SEC-05, BUG-01..BUG-04, and core search/deduplication logic.
Compatible with both `unittest` and `pytest`.
"""
import ast
import os
import sys
import types
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "web", "backend")
for p in (ROOT_DIR, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Provide lightweight module stubs if sqlalchemy is not installed in the current environment
try:
    import sqlalchemy  # noqa: F401
except ImportError:
    sa_mod = types.ModuleType("sqlalchemy")
    sa_orm = types.ModuleType("sqlalchemy.orm")
    sa_orm.Session = object
    sa_mod.orm = sa_orm
    sys.modules["sqlalchemy"] = sa_mod
    sys.modules["sqlalchemy.orm"] = sa_orm
    models_stub = types.ModuleType("web.backend.models")
    sys.modules["web.backend.models"] = models_stub

from web.backend import utils as utils_module
from web.backend import liveness as liveness_module
from web.backend.search_engine import (
    expand_queries,
    relevance_score,
    normalize_title_key,
    dedup_and_merge,
)


def _read_source(rel_path: str) -> str:
    full_path = os.path.join(ROOT_DIR, rel_path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


class TestQASecuritySuite(unittest.TestCase):
    # -----------------------------------------------------------------------
    # SEC-01: Admin Privilege Escalation, OAuth Email Verification & Cooldown
    # -----------------------------------------------------------------------

    def test_sec01_default_admin_emails_exclude_test_accounts(self):
        """Verify unverified test/demo accounts are removed from DEFAULT_ADMIN_EMAILS in auth.py."""
        src = _read_source("web/backend/auth.py")
        self.assertNotIn("yassine@test.com", src)
        self.assertNotIn("yassine.demo@cvtomatch.com", src)

    def test_sec01_google_oauth_verifies_email_and_forgot_password_rate_limits(self):
        """Verify Google OAuth checks email_verified and forgot-password enforces rate limiting."""
        src = _read_source("web/backend/routers/auth.py")
        self.assertIn("email_verified", src)
        self.assertIn("Google account email address is not verified", src)
        self.assertIn("_FORGOT_COOLDOWN", src)
        self.assertIn("429", src)

    # -----------------------------------------------------------------------
    # SEC-02 & SEC-04: Serverless SMTP Relay & Backend TLS Hardening
    # -----------------------------------------------------------------------

    def test_sec02_sec04_smtp_relay_and_tls_hardening(self):
        """Verify SMTP relay enforces TLS verification, host/port allowlist, and HMAC auth."""
        relay_src = _read_source("web/frontend/api/smtp-relay.js")
        self.assertIn("rejectUnauthorized: true", relay_src)
        self.assertNotIn("rejectUnauthorized: false", relay_src)
        self.assertNotIn("providedKey === RELAY_SECRET", relay_src)
        self.assertIn("isAllowedSmtpHost", relay_src)
        self.assertIn("ALLOWED_SMTP_PORTS", relay_src)
        self.assertIn("timingSafeEqual", relay_src)

        email_src = _read_source("web/backend/routers/email.py")
        self.assertNotIn("_create_unverified_context", email_src)
        self.assertIn("ssl.create_default_context()", email_src)
        self.assertIn("X-Relay-Timestamp", email_src)
        self.assertIn("X-Relay-Signature", email_src)

    # -----------------------------------------------------------------------
    # SEC-03 & BUG-03: Multi-Tenant Email Blacklist Isolation & Tracker GET
    # -----------------------------------------------------------------------

    def test_sec03_bug03_blacklist_isolation_and_non_destructive_tracker_get(self):
        """Verify manual blacklist entries are scoped to created_by_user_id and GET /api/tracker is read-only."""
        bounce_src = _read_source("web/backend/bounce_cleaner.py")
        self.assertIn("created_by_user_id", bounce_src)
        self.assertIn("manual", bounce_src)

        tracker_src = _read_source("web/backend/routers/tracker.py")
        tree = ast.parse(tracker_src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_applications":
                func_calls = [
                    getattr(c.func, "id", getattr(c.func, "attr", ""))
                    for c in ast.walk(node)
                    if isinstance(c, ast.Call)
                ]
                self.assertNotIn("purge_blacklisted_applications", func_calls)

    # -----------------------------------------------------------------------
    # SEC-05: SSRF & Redirect Hop Validation
    # -----------------------------------------------------------------------

    def test_sec05_ssrf_blocks_private_ips_and_redirect_hops(self):
        """Verify is_safe_public_url and safe_http_get block private IPs and 302 redirects to internal hosts."""
        self.assertFalse(utils_module.is_safe_public_url("http://127.0.0.1:8000/admin"))
        self.assertFalse(utils_module.is_safe_public_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(utils_module.is_safe_public_url("http://localhost:5432/"))

        mock_session = MagicMock()
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_session.get.return_value = redirect_resp

        with patch("web.backend.utils.is_safe_public_url", side_effect=lambda u: "169.254.169.254" not in u):
            with self.assertRaises(ValueError):
                utils_module.safe_http_get(mock_session, "https://example.com/job-redirect")

    def test_sec05_liveness_blocks_internal_urls(self):
        """Verify check_liveness immediately rejects internal/loopback URLs without making a request."""
        res = liveness_module.check_liveness("http://127.0.0.1:8000/api/health")
        self.assertEqual(res.get("code"), "blocked_url")
        self.assertIn("disallowed", res.get("reason", ""))

    # -----------------------------------------------------------------------
    # BUG-01: Extension Autofill Grounded in User Profile (No 'Xo Space')
    # -----------------------------------------------------------------------

    def test_bug01_extension_autofill_no_hardcoded_xo_space_or_flutter(self):
        """Verify extension router has no hardcoded 'Xo Space' or fabricated Flutter/BLE claims."""
        ext_src = _read_source("web/backend/routers/extension.py")
        self.assertNotIn("Xo Space", ext_src)
        self.assertNotIn("Bluetooth Low Energy", ext_src)

        tree = ast.parse(ext_src)
        ns = {
            "re": __import__("re"),
            "QuestionItem": Any,
            "Dict": Dict,
            "Any": Any,
            "List": List,
            "Optional": Optional,
        }
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_answer_custom_question":
                code = compile(ast.Module(body=[node], type_ignores=[]), "<extension>", "exec")
                exec(code, ns)
                break

        answer_fn = ns["_answer_custom_question"]
        profile = {
            "first_name": "Alice",
            "last_name": "Martin",
            "current_company": "DataSystems",
            "current_title": "Senior Python Backend Engineer",
            "years_experience": "5",
            "location": "Paris, France",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "experiences": [
                {
                    "role": "Senior Python Backend Engineer",
                    "company": "DataSystems",
                    "description": "Built high-throughput REST APIs using Python, FastAPI, and PostgreSQL.",
                }
            ],
            "summary": "Backend engineer specializing in distributed Python services.",
        }

        for idx, question_text in enumerate([
            "Tell us about a complex technical challenge you solved.",
            "What is your experience with mobile development and state management?",
            "Why do you want to work at Acme Corp?",
            "Describe your experience with hardware or IoT systems.",
        ]):
            q_obj = MagicMock(id=f"q{idx}", label=question_text, type="textarea", options=[], required=True)
            res = answer_fn(q_obj, profile, "Backend Developer", "Acme Corp", ["Python", "FastAPI"], "Backend engineer pitch.")
            answer = res["answer"] if isinstance(res, dict) else str(res)
            self.assertNotIn("Xo Space", answer)
            self.assertNotIn("Flutter", answer)
            self.assertNotIn("BLoC", answer)
            self.assertNotIn("Bluetooth Low Energy", answer)
            self.assertTrue(len(answer) > 20)

    # -----------------------------------------------------------------------
    # BUG-02 & BUG-04: SQLite Concurrency Lock & Exact Title Deduplication
    # -----------------------------------------------------------------------

    def test_bug02_bug04_sqlite_flock_and_exact_title_deduplication(self):
        """Verify database.py uses fcntl.flock + foreign_keys=ON and jobs.py uses exact title equality."""
        db_src = _read_source("web/backend/database.py")
        self.assertIn("fcntl.flock", db_src)
        self.assertIn("PRAGMA foreign_keys=ON", db_src)

        jobs_src = _read_source("web/backend/routers/jobs.py")
        self.assertNotIn("if j_nt in at or at in j_nt:", jobs_src)
        self.assertIn("if j_nt == at:", jobs_src)

        t1 = normalize_title_key("Engineer")
        t2 = normalize_title_key("QA Engineer")
        self.assertNotEqual(t1, t2)

        self.assertFalse(os.path.exists(os.path.join(ROOT_DIR, "jobsearcher.db")))
        self.assertFalse(os.path.exists(os.path.join(ROOT_DIR, "jobspy", "jobsearcher.db")))
        self.assertFalse(os.path.exists(os.path.join(ROOT_DIR, "web", "backend", "cvtomatch.db")))
        self.assertTrue(os.path.exists(os.path.join(ROOT_DIR, "web", "backend", "jobsearcher.db")))

    # -----------------------------------------------------------------------
    # Core Search & Deduplication Regression Checks
    # -----------------------------------------------------------------------

    def test_search_engine_regression(self):
        """Verify bilingual query expansion, relevance scoring, and job deduplication."""
        queries = expand_queries("développeur python", "France")
        self.assertTrue(len(queries) >= 1)

        score = relevance_score(
            "Python Backend Engineer",
            "Senior Python Backend Engineer",
            "FastAPI, PostgreSQL, Docker",
            "TechCo",
        )
        self.assertGreater(score, 50)

        merged = dedup_and_merge([
            {"id": "1", "title": "Python Engineer", "company": "Acme SAS", "job_url": "https://example.com/j/1"},
            {"id": "2", "title": "Python Engineer", "company": "Acme", "job_url": "https://example.com/j/1", "emails": ["hr@acme.com"]},
        ])
        self.assertEqual(len(merged), 1)
        emails = [e["email"] if isinstance(e, dict) else e for e in merged[0].get("emails", [])]
        self.assertIn("hr@acme.com", emails)


if __name__ == "__main__":
    unittest.main()
