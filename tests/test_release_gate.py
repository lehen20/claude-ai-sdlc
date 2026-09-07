"""Release gate classification tests.

Each case below corresponds to a way the gate could be walked around by
accident. They are regression tests: every one of them failed at least once.

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "sdlc")
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
sys.path.insert(0, os.path.join(PLUGIN, "hooks"))

import release_gate as G  # noqa: E402

PROFILE = {
    "branch": {"base": "main", "protected": ["main", "release"]},
    "deny_patterns": ["^kubectl\\s+apply", "^terraform\\s+apply"],
}


class GateCase(unittest.TestCase):
    """Classify against a fixed 'current branch' so no git repo is needed."""

    def verdicts(self, command, branch="feat/x"):
        original = G.S.current_branch
        G.S.current_branch = lambda root=None: branch
        try:
            return [G.classify(seg, PROFILE, None)[0] for seg in G.segments(command)]
        finally:
            G.S.current_branch = original

    def assertDenied(self, command, branch="feat/x"):
        self.assertIn("deny", self.verdicts(command, branch), "expected hard deny: " + command)

    def assertGated(self, command, branch="feat/x"):
        verdicts = self.verdicts(command, branch)
        self.assertNotIn("deny", verdicts, "unexpected hard deny: " + command)
        self.assertIn("gated", verdicts, "expected gated: " + command)

    def assertFree(self, command, branch="feat/x"):
        self.assertEqual(
            {"free"}, set(self.verdicts(command, branch)), "expected free: " + command
        )


class TestFreeCommands(GateCase):
    def test_reads_are_untouched(self):
        for command in ("ls -la", "npm test", "git status", "git diff HEAD",
                        "git log --oneline", "cat README.md", "gh pr list",
                        "gh api /repos/o/r", "git push --dry-run origin main"):
            self.assertFree(command)


class TestNormalGating(GateCase):
    def test_commit_and_push_are_gated(self):
        self.assertGated("git commit -m 'work'")
        self.assertGated("git push origin feat/x")
        self.assertGated("git push -u origin feat/x")
        self.assertGated("gh pr create --fill")


class TestProtectedBranch(GateCase):
    def test_direct_push_to_protected_is_denied(self):
        self.assertDenied("git push origin main")
        self.assertDenied("git push origin release")
        self.assertDenied("git push origin HEAD:main")
        self.assertDenied("git push origin refs/heads/main")

    def test_plus_refspec_does_not_hide_the_branch(self):
        # `+main` is a forced refspec; it must not read as a branch named "+main".
        self.assertDenied("git push origin +main")

    def test_bare_push_from_a_protected_branch_is_denied(self):
        self.assertDenied("git push", branch="main")

    def test_merge_into_protected_is_denied(self):
        self.assertDenied("git merge feat/x", branch="main")
        self.assertFree("git merge main", branch="feat/x")


class TestForcePush(GateCase):
    def test_long_and_short_forms(self):
        self.assertDenied("git push --force origin feat/x")
        self.assertDenied("git push -f origin feat/x")
        self.assertDenied("git push --force-with-lease origin feat/x")

    def test_clustered_short_flags(self):
        # `-uf` hid the force from a plain membership test.
        self.assertDenied("git push -uf origin feat/x")
        self.assertDenied("git push -fu origin feat/x")

    def test_lease_with_value(self):
        self.assertDenied("git push --force-with-lease=main origin feat/x")


class TestBroadcastPush(GateCase):
    def test_all_and_mirror_reach_protected_branches(self):
        # Neither names a branch, so the refspec check cannot see `main`.
        self.assertDenied("git push --all origin")
        self.assertDenied("git push --mirror origin")


class TestGitGlobalOptions(GateCase):
    def test_dash_C_does_not_hide_the_subcommand(self):
        self.assertDenied("git -C /elsewhere push origin main")
        self.assertGated("git -C /elsewhere push origin feat/x")
        self.assertDenied("git -c user.name=x push --force origin feat/x")
        self.assertGated("git --git-dir=/tmp/r/.git commit -m x")


class TestSegmentation(GateCase):
    def test_separators_split_every_command(self):
        for joiner in ("&&", ";", "||", "\n", " &\n"):
            command = "git status%s git push origin main" % joiner
            self.assertDenied(command)

    def test_newline_blocks(self):
        self.assertDenied("git add -A\ngit commit -m x\ngit push origin main")

    def test_pipeline_segments(self):
        self.assertDenied("echo hi | git push origin main")


class TestWrappers(GateCase):
    def test_env_assignments_and_wrappers_are_stripped(self):
        self.assertDenied("FOO=bar git push origin main")
        self.assertDenied("sudo git push origin main")
        self.assertDenied("env git push --force origin feat/x")
        self.assertDenied("nohup git push --mirror origin")


class TestGitHubCli(GateCase):
    def test_human_owned_gh_actions_are_denied(self):
        for command in ("gh pr merge 1", "gh pr merge --squash 1",
                        "gh pr review --approve 1", "gh pr close 1",
                        "gh release create v1.0.0", "gh release delete v1.0.0",
                        "gh workflow run deploy.yml", "gh run rerun 12345",
                        "gh repo delete o/r", "gh secret set TOKEN"):
            self.assertDenied(command)

    def test_api_writes_are_denied_reads_are_free(self):
        self.assertDenied("gh api -X PUT /repos/o/r/pulls/1/merge")
        self.assertDenied("gh api --method DELETE /repos/o/r")
        self.assertDenied("gh api --method=POST /repos/o/r/releases")
        self.assertFree("gh api /repos/o/r/pulls/1")
        self.assertFree("gh api -X GET /repos/o/r")


class TestProfileDenyPatterns(GateCase):
    def test_declared_deploy_commands_are_denied(self):
        self.assertDenied("kubectl apply -f deploy.yaml")
        self.assertDenied("terraform apply -auto-approve")
        self.assertFree("kubectl get pods")

    def test_invalid_regex_does_not_crash_the_gate(self):
        profile = dict(PROFILE, deny_patterns=["*broken["])
        self.assertEqual("free", G.classify("ls", profile, None)[0])


class TestParsingRobustness(GateCase):
    def test_unbalanced_quotes_fall_back_to_split(self):
        self.assertDenied("git push origin main --message 'unterminated")

    def test_empty_and_whitespace(self):
        self.assertEqual([], G.segments("   "))
        self.assertEqual("free", G.classify("", PROFILE, None)[0])


if __name__ == "__main__":
    unittest.main()
