import os
import unittest
from unittest import mock
import arc_core as core
import arc_wallet
import discord_bridge

class FakeInteraction:
    def __init__(self, guild, channel): self.guild_id, self.channel_id = guild, channel

class ArcTests(unittest.TestCase):
    def test_01_workspace_browser(self):
        result=core.workspace_browser("",1); self.assertIn("items",result); self.assertTrue(any(x["path"]=="arc.py" for x in result["items"]))
    def test_02_file_reader(self): self.assertIn("ARC local browser",core.file_reader("arc.py")["content"])
    def test_03_file_search(self): self.assertTrue(core.file_search("COMMAND CENTER","arc.py")["matches"])
    def test_04_calculator(self): self.assertEqual(core.calculator("(2+3)*4")["result"],20)
    def test_05_python_check(self):
        self.assertTrue(core.python_code_check("x = 1\n")["valid"]); self.assertFalse(core.python_code_check("x =\n")["valid"])
    def test_06_database_summary(self): self.assertIn("approvals_pending",core.database_summary())
    def test_07_text_asset_is_pending(self):
        result=core.text_to_asset("Alpha\nBeta","checklist","ARC Automated Test")
        self.assertEqual(result["status"],"pending_approval"); self.assertFalse(core.safe_path(result["proposed_filename"]).exists())
        core.reject_pending(result["pending_action_id"])
    def test_08_approved_writer(self):
        target="data/arc-approved-write-test.txt"; path=core.safe_path(target)
        before=path.read_text() if path.exists() else None; content=f"approved test content {core.now()}\n"
        result=core.propose_file_write(target,content,"automated smoke test")
        self.assertEqual(path.read_text() if path.exists() else None,before); core.apply_pending(result["pending_action_id"])
        self.assertEqual(path.read_text(),content)
    def test_09_rejected_writer(self):
        target="data/arc-rejected-write-test.txt"; self.assertFalse(core.safe_path(target).exists())
        result=core.propose_file_write(target,"must not exist","automated smoke test"); core.reject_pending(result["pending_action_id"])
        self.assertFalse(core.safe_path(target).exists())
    def test_10_privacy(self):
        sample="api_key=sk-example1234567890 user@example.com 555-123-4567 192.168.1.20 C:\\Users\\Example\\file.txt"
        clean=core.redact(sample)
        for value in ("sk-example1234567890","user@example.com","555-123-4567","192.168.1.20","C:\\Users\\Example"): self.assertNotIn(value,clean)
        self.assertIn("Privacy Mode blocks",core.file_reader(".env")["error"])
    def test_11_limits(self):
        with mock.patch.object(core,"OPENAI_CONFIGURED",True), mock.patch.object(core,"usage_today",return_value=(core.DAILY_API_CALL_LIMIT,0,0,0)):
            with self.assertRaisesRegex(RuntimeError,"request limit"): core.run_arc("test")
    def test_12_discord_optional_and_scope(self):
        with mock.patch.dict(os.environ,{},clear=True): self.assertFalse(discord_bridge.discord_config()["configured"])
        self.assertFalse(discord_bridge.allowed_interaction(FakeInteraction(None,123),123)); self.assertFalse(discord_bridge.allowed_interaction(FakeInteraction(1,456),123)); self.assertTrue(discord_bridge.allowed_interaction(FakeInteraction(1,123),123))
    def test_13_path_escape(self):
        with self.assertRaises(ValueError): core.safe_path("../outside.txt")
    def test_14_required_chat_routes(self):
        cases = [
            ("Calculate 425 * 17", "calculator"),
            ("Find README files in this project", "search_workspace"),
            ("Read README-COMMERCIAL.md and summarize it", "read_text_file"),
            ("Check arc.py for Python compile errors", "check_python_file"),
            ("How many tasks has ARC completed?", "arc_database_summary"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt): self.assertEqual(core.route_chat(prompt)["tool"], expected)
        self.assertEqual(core.route_chat("Calculate 425 * 17")["tool_result"]["result"], 7225)
    def test_15_chat_asset_requires_approval(self):
        existing = core.safe_path("assets/arc-checklist-checklist.md")
        before = existing.read_bytes() if existing.exists() else None
        result = core.route_chat("Turn this text into a checklist and save it: Alpha; Beta")
        self.assertEqual(result["tool"], "propose_text_asset")
        self.assertIsNotNone(result["pending_action_id"])
        proposed = core.safe_path(result["tool_result"]["proposed_filename"])
        self.assertEqual(proposed.read_bytes() if proposed.exists() else None, before)
        core.reject_pending(result["pending_action_id"])
    def test_16_chat_file_write_requires_approval(self):
        target = "data/chat-writer-test.txt"; path = core.safe_path(target)
        before = path.read_text() if path.exists() else None
        result = core.route_chat(f"Create file {target} with hello from chat")
        self.assertEqual(result["tool"], "propose_file_write")
        self.assertEqual(path.read_text() if path.exists() else None, before)
        core.reject_pending(result["pending_action_id"])
    def test_17_wallet_config_defaults_to_base_sepolia(self):
        with mock.patch.dict(os.environ, {"ARC_WALLET_NETWORK":"base-sepolia"}):
            self.assertEqual(arc_wallet.selected_chain_id(),84532)
        self.assertEqual(arc_wallet.NETWORKS[8453]["usdc"]["address"],"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        self.assertEqual(arc_wallet.NETWORKS[84532]["usdc"]["address"],"0x036CbD53842c5426634e7929541eC2318f3dCF7e")
    def test_18_wallet_chat_intents_never_submit(self):
        cases=[
            ("Open ARC wallet.","open"),("Connect my wallet.","connect"),
            ("Show my wallet balance.","balance"),("What is my receiving address?","receive"),
            ("Show my recent ARC transactions.","history"),("Switch to Base Sepolia.","switch"),
        ]
        for prompt,action in cases:
            with self.subTest(prompt=prompt):
                result=core.route_chat(prompt); self.assertEqual(result["tool"],"arc_wallet")
                self.assertEqual(result["tool_result"]["wallet_action"]["action"],action)
        pay=core.route_chat("Pay 5 USDC to 0x1111111111111111111111111111111111111111")
        self.assertEqual(pay["tool_result"]["wallet_action"]["amount"],"5")
        self.assertNotIn("submit",pay["tool_result"]["wallet_action"])

if __name__ == "__main__": unittest.main(verbosity=2)
