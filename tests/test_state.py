"""Profile parsing, path containment and release-signature binding."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "sdlc")
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))

import sdlc_state as S  # noqa: E402


class TestYamlSubset(unittest.TestCase):
    def test_shipped_template_parses(self):
        with open(os.path.join(PLUGIN, "templates", "profile.yml"), encoding="utf-8") as fh:
            profile = S.parse_yaml(fh.read())
        self.assertEqual("main", S.profile_get(profile, "branch.base"))
        self.assertEqual(["main"], S.profile_get(profile, "branch.protected"))
        self.assertEqual("feat", S.profile_get(profile, "branch.prefixes.feature"))
        self.assertIn("npm test", str(S.profile_get(profile, "commands.test")))
        self.assertTrue(S.profile_get(profile, "deny_patterns"))

    def test_scalars(self):
        parsed = S.parse_yaml(
            "a: 1\nb: true\nc: no\nd: null\ne: 1.5\nf: plain text\ng: \"quoted\"\n"
        )
        self.assertEqual(
            {"a": 1, "b": True, "c": False, "d": None, "e": 1.5,
             "f": "plain text", "g": "quoted"},
            parsed,
        )

    def test_comments_are_stripped_but_not_inside_quotes(self):
        parsed = S.parse_yaml('a: value  # trailing\nb: "has # inside"\n')
        self.assertEqual({"a": "value", "b": "has # inside"}, parsed)

    def test_utf8_survives_a_quoted_string(self):
        # `unicode_escape` used to turn these into mojibake.
        parsed = S.parse_yaml('brand:\n  name: "Ekip Çalışması — 東京"\n')
        self.assertEqual("Ekip Çalışması — 東京", parsed["brand"]["name"])

    def test_escapes_in_double_quotes(self):
        self.assertEqual({"a": "x\ty"}, S.parse_yaml('a: "x\\ty"'))
        self.assertEqual({"a": "x\\ty"}, S.parse_yaml("a: 'x\\ty'"))

    def test_regex_backslashes_round_trip(self):
        # deny_patterns are regexes; mangling a backslash silently breaks a rule.
        parsed = S.parse_yaml('deny_patterns:\n  - "^kubectl\\\\s+apply"\n')
        self.assertEqual(["^kubectl\\s+apply"], parsed["deny_patterns"])

    def test_inline_collections(self):
        parsed = S.parse_yaml("l: [ a, b ]\nm: { k: v, n: 2 }\n")
        self.assertEqual({"l": ["a", "b"], "m": {"k": "v", "n": 2}}, parsed)

    def test_garbage_does_not_raise(self):
        self.assertIsInstance(S.parse_yaml(":::\n\t\x00junk"), dict)


class TestIsInside(unittest.TestCase):
    def test_containment(self):
        self.assertTrue(S.is_inside("/repo/.aisdlc/work/x/plan.md", "/repo/.aisdlc"))
        self.assertTrue(S.is_inside("/repo/.aisdlc", "/repo/.aisdlc"))

    def test_sibling_prefix_is_not_inside(self):
        # A bare startswith would call this a match and skip the plan gate.
        self.assertFalse(S.is_inside("/repo/.aisdlcx/evil.py", "/repo/.aisdlc"))
        self.assertFalse(S.is_inside("/repo/src/main.py", "/repo/.aisdlc"))

    def test_traversal_is_normalised(self):
        self.assertFalse(S.is_inside("/repo/.aisdlc/../src/a.py", "/repo/.aisdlc"))

    def test_empty_inputs(self):
        self.assertFalse(S.is_inside("", "/repo/.aisdlc"))
        self.assertFalse(S.is_inside("/repo/a", ""))


class TestSlugify(unittest.TestCase):
    def test_path_traversal_cannot_escape_the_work_dir(self):
        # work_id is built from user text and used as a directory name.
        self.assertNotIn("/", S.slugify("../../etc/passwd"))
        self.assertNotIn("..", S.slugify("../../etc/passwd"))
        self.assertNotIn("/", S.slugify("feat/some-branch"))

    def test_fallback_and_length(self):
        self.assertEqual("work", S.slugify(""))
        self.assertEqual("work", S.slugify("!!!"))
        self.assertEqual("work", S.slugify(None))
        self.assertLessEqual(len(S.slugify("x" * 200)), 48)


class TestReleaseSignature(unittest.TestCase):
    def signed(self, **overrides):
        gate = {"approved": True, "branch": "feat/x", "head_sha": "a" * 40,
                "target": "main"}
        gate.update(overrides)
        return {"gates": {"release": gate}}

    def setUp(self):
        self._head = S.head_sha
        S.head_sha = lambda root=None: "a" * 40

    def tearDown(self):
        S.head_sha = self._head

    def test_valid_signature(self):
        self.assertIsNone(S.release_signature_error(self.signed(), "feat/x", "main"))

    def test_no_state_is_an_error(self):
        self.assertIsNotNone(S.release_signature_error(None, "feat/x"))

    def test_unsigned_is_an_error(self):
        self.assertIsNotNone(
            S.release_signature_error(self.signed(approved=False), "feat/x")
        )

    def test_branch_must_match(self):
        self.assertIsNotNone(S.release_signature_error(self.signed(), "feat/other"))

    def test_target_must_match(self):
        self.assertIsNotNone(
            S.release_signature_error(self.signed(), "feat/x", "production")
        )

    def test_new_commit_voids_the_signature(self):
        S.head_sha = lambda root=None: "b" * 40
        error = S.release_signature_error(self.signed(), "feat/x", "main")
        self.assertIn("invalidate", error)


class TestStateRoundTrip(unittest.TestCase):
    def test_tiers_set_the_right_required_gates(self):
        express = S.new_state("w", "feature", "express", "feat/x", "main")
        self.assertFalse(express["gates"]["plan"]["required"])
        self.assertTrue(express["gates"]["release"]["required"],
                        "the release gate is required at every tier")
        for tier in ("standard", "full"):
            state = S.new_state("w", "feature", tier, "feat/x", "main")
            for gate in ("plan", "implementation", "release"):
                self.assertTrue(state["gates"][gate]["required"])

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".aisdlc", "work", "w"))
            state = S.new_state("w", "feature", "standard", "feat/x", "main")
            self.assertTrue(S.save_state(state, root=tmp))
            self.assertTrue(S.set_active("w", root=tmp))
            self.assertEqual("w", S.active_id(tmp))
            self.assertEqual(state, S.load_state(root=tmp))

    def test_corrupt_state_returns_none_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, ".aisdlc", "work", "w")
            os.makedirs(work)
            with open(os.path.join(work, "state.json"), "w") as fh:
                fh.write("{not json")
            S.set_active("w", root=tmp)
            self.assertIsNone(S.load_state(root=tmp))

    def test_missing_profile_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(S.load_profile(tmp))


if __name__ == "__main__":
    unittest.main()
