"""Model provider selection, with the local Ollama path in mind.

None of these call a model. They cover the routing and failure handling around
it, which is where a local setup actually goes wrong: the wrong model name, a
daemon that is not running, a context window too small for the prompt, and a
small model that answers with prose instead of JSON.
"""
import time
import unittest
from unittest import mock

import ai_service


class ModelSpecTests(unittest.TestCase):
    """Ollama tags contain a colon, which is also the provider separator."""

    def test_provider_is_split_on_the_first_colon_only(self):
        self.assertEqual(
            ai_service.parse_model_spec("ollama:qwen2.5-coder:7b"),
            ("ollama", "qwen2.5-coder:7b"),
        )

    def test_a_tagless_ollama_model_still_parses(self):
        self.assertEqual(
            ai_service.parse_model_spec("ollama:llama3.1"), ("ollama", "llama3.1")
        )

    def test_a_bare_tagged_name_is_not_mistaken_for_a_provider(self):
        """`qwen2.5-coder` is not a provider, so the whole string is the model
        and the configured default provider is used."""
        provider, model = ai_service.parse_model_spec("qwen2.5-coder:7b")
        self.assertEqual(model, "qwen2.5-coder:7b")
        self.assertNotEqual(provider, "qwen2.5-coder")

    def test_the_other_providers_are_unaffected(self):
        self.assertEqual(
            ai_service.parse_model_spec("anthropic:claude-sonnet-4-5"),
            ("anthropic", "claude-sonnet-4-5"),
        )
        self.assertEqual(ai_service.parse_model_spec("openai:gpt-4o"), ("openai", "gpt-4o"))


class AvailabilityTests(unittest.TestCase):
    def test_ollama_needs_no_api_key(self):
        """Every other provider is gated on a key. Ollama has none to check, so
        it counts as configured whenever it has an address."""
        with mock.patch.object(ai_service, "LLM_MODE", "auto"), \
             mock.patch.object(ai_service, "OPENAI_API_KEY", ""), \
             mock.patch.object(ai_service, "ANTHROPIC_API_KEY", ""):
            self.assertTrue(ai_service.provider_available("ollama"))
            self.assertFalse(ai_service.provider_available("openai"))

    def test_availability_does_no_network_io(self):
        """`provider_available` sits on the analysis path and is called freely.

        A probe here would put a network round trip inside every decision about
        whether to attempt a call.
        """
        with mock.patch.object(ai_service, "_probe_ollama_once") as probe:
            ai_service.provider_available("ollama")
            probe.assert_not_called()

    def test_offline_mode_overrides_everything(self):
        with mock.patch.object(ai_service, "LLM_MODE", "offline"):
            self.assertFalse(ai_service.provider_available("ollama"))


class ReachabilityTests(unittest.TestCase):
    """The probe is read by GET /config on every page load, so it must not block.

    Probing a *stopped* daemon is the slow case, not the fast one: `localhost`
    resolves to both ::1 and 127.0.0.1, so a dead port costs two timeouts.
    """

    def setUp(self):
        # Wait out any probe thread still in flight from an earlier test before
        # resetting, or it lands on the next test's cache and makes this class
        # order-dependent.
        deadline = time.time() + 5
        while ai_service._ollama_probe["running"] and time.time() < deadline:
            time.sleep(0.02)
        ai_service._ollama_probe.update(
            {"checked_at": 0.0, "reachable": False, "running": False}
        )

    def test_a_cold_call_returns_immediately_and_does_not_wait(self):
        def slow_probe():
            time.sleep(2.0)
            return True

        with mock.patch.object(ai_service, "_probe_ollama_once", slow_probe):
            started = time.perf_counter()
            ai_service.ollama_reachable()
            elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.25, "ollama_reachable blocked the caller")

    def test_the_background_probe_updates_the_answer(self):
        """The first call may report either value -- the point is that the
        answer converges without anyone having waited for it."""
        with mock.patch.object(ai_service, "_probe_ollama_once", lambda: True):
            ai_service.ollama_reachable()
            deadline = time.time() + 5
            while time.time() < deadline and not ai_service._ollama_probe["reachable"]:
                time.sleep(0.05)
            self.assertTrue(ai_service.ollama_reachable())

    def test_forcing_probes_synchronously(self):
        """The diagnosis path needs a true answer more than a fast one."""
        with mock.patch.object(ai_service, "_probe_ollama_once", lambda: True):
            self.assertTrue(ai_service.ollama_reachable(force=True))

    def test_a_fresh_answer_is_not_re_probed(self):
        with mock.patch.object(ai_service, "_probe_ollama_once", lambda: True):
            ai_service.ollama_reachable(force=True)
        with mock.patch.object(ai_service, "_probe_ollama_once") as probe:
            ai_service.ollama_reachable()
            probe.assert_not_called()


class ContextWindowTests(unittest.TestCase):
    """Ollama truncates an over-long prompt silently rather than refusing it.

    A truncated run returns a normal-looking answer about a fragment of the
    project, so the only place to catch it is before the call.
    """

    def test_a_prompt_that_fits_produces_no_warning(self):
        with mock.patch.object(ai_service, "OLLAMA_NUM_CTX", 16384):
            self.assertEqual(ai_service._ollama_context_warning("ollama", "hello"), "")

    def test_an_oversized_prompt_warns_and_says_what_to_change(self):
        with mock.patch.object(ai_service, "OLLAMA_NUM_CTX", 64):
            warning = ai_service._ollama_context_warning("ollama", "word " * 4000)
        self.assertIn("truncated", warning)
        self.assertIn("OLLAMA_NUM_CTX", warning)

    def test_the_warning_says_the_structural_findings_are_unaffected(self):
        """Invariant: the parser's findings never depend on the model."""
        with mock.patch.object(ai_service, "OLLAMA_NUM_CTX", 64):
            warning = ai_service._ollama_context_warning("ollama", "word " * 4000)
        self.assertIn("unaffected", warning)

    def test_other_providers_are_not_warned_about(self):
        with mock.patch.object(ai_service, "OLLAMA_NUM_CTX", 64):
            self.assertEqual(ai_service._ollama_context_warning("openai", "word " * 4000), "")


class DiagnosisTests(unittest.TestCase):
    """"It did not work" is not actionable for a local setup."""

    def test_a_stopped_daemon_is_named_as_the_problem(self):
        with mock.patch.object(ai_service, "ollama_reachable", lambda force=False: False):
            notes = ai_service._ollama_diagnosis("qwen2.5-coder:7b")
        self.assertTrue(any("ollama serve" in note for note in notes))

    def test_a_wrong_model_name_lists_what_is_installed(self):
        """The commonest local mistake: the tag is part of the name."""
        with mock.patch.object(ai_service, "ollama_reachable", lambda force=False: True), \
             mock.patch.object(ai_service, "ollama_models", lambda: ["qwen2.5-coder:7b"]):
            notes = ai_service._ollama_diagnosis("qwen2.5-coder")
        self.assertTrue(any("qwen2.5-coder:7b" in note for note in notes))

    def test_a_correct_setup_produces_no_noise(self):
        with mock.patch.object(ai_service, "ollama_reachable", lambda force=False: True), \
             mock.patch.object(ai_service, "ollama_models", lambda: ["qwen2.5-coder:7b"]):
            self.assertEqual(ai_service._ollama_diagnosis("qwen2.5-coder:7b"), [])


class BadRequestTests(unittest.TestCase):
    """The retry-without-optional-parameters path.

    This used to match on the words "response_format" or "seed" appearing in the
    exception message, which no server promises to include.
    """

    def test_a_400_is_recognised_by_status_code(self):
        error = Exception("something the server did not like")
        setattr(error, "status_code", 400)
        self.assertTrue(ai_service._is_bad_request(error))

    def test_an_unrelated_failure_is_not_swallowed(self):
        self.assertFalse(ai_service._is_bad_request(ConnectionError("network down")))


class MalformedJsonTests(unittest.TestCase):
    """Small local models answer with prose. That should degrade, not fail."""

    def test_a_fenced_object_is_still_read(self):
        payload = ai_service._extract_json('```json\n{"similarity_score": 90}\n```')
        self.assertEqual(payload["similarity_score"], 90)

    def test_an_object_wrapped_in_prose_is_still_read(self):
        payload = ai_service._extract_json(
            'Sure! Here is the analysis you asked for:\n{"similarity_score": 42}\nHope that helps.'
        )
        self.assertEqual(payload["similarity_score"], 42)

    def test_prose_with_no_object_is_not_retried_at_temperature_zero(self):
        """At temperature 0 the next attempt returns the same tokens, so
        retrying spends local compute to arrive back where it started."""
        calls = {"n": 0}

        def answer_with_prose(provider, model, system, user):
            calls["n"] += 1
            return "I cannot help with that.", 10, 5

        with mock.patch.object(ai_service, "_call_openai", answer_with_prose), \
             mock.patch.object(ai_service, "LLM_TEMPERATURE", 0), \
             mock.patch.object(ai_service, "LLM_MAX_RETRIES", 3):
            with self.assertRaises(ai_service.LlmUnavailable):
                ai_service._chat_json("ollama", "qwen2.5-coder:7b", "sys", "user")

        self.assertEqual(calls["n"], 1, "a deterministic model was asked the same thing twice")

    def test_a_transport_failure_is_still_retried(self):
        """The early exit is for unparseable answers only; a dropped connection
        is exactly the case retries exist for."""
        calls = {"n": 0}

        def flaky(provider, model, system, user):
            calls["n"] += 1
            raise ConnectionError("connection reset")

        with mock.patch.object(ai_service, "_call_openai", flaky), \
             mock.patch.object(ai_service, "LLM_TEMPERATURE", 0), \
             mock.patch.object(ai_service, "LLM_MAX_RETRIES", 3), \
             mock.patch.object(ai_service.time, "sleep", lambda _: None):
            with self.assertRaises(ai_service.LlmUnavailable):
                ai_service._chat_json("ollama", "qwen2.5-coder:7b", "sys", "user")

        self.assertEqual(calls["n"], 3)


if __name__ == "__main__":
    unittest.main()
