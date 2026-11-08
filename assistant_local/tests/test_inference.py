from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user


class TestInference(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.user = new_test_user(
            cls.env,
            login="assistant_model_user",
            groups="base.group_user",
            context={"no_reset_password": True},
        )

    def test_unconfigured_model_is_reported(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(UserError):
                provider._chat([], [])

    def test_configured_transport_receives_local_model_request(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {"ASSISTANT_LOCAL_URL": "http://127.0.0.1:11434", "ASSISTANT_LOCAL_MODEL": "test"}
        reply = {"role": "assistant", "content": "Hi", "tool_calls": []}
        with patch.dict("os.environ", env, clear=True), patch(
            "odoo.addons.assistant_local.models.inference.chat", return_value=reply
        ) as transport:
            self.assertEqual(provider._chat([{"role": "user", "content": "Hi"}], []), reply)
        self.assertEqual(transport.call_args.args[:2], (env["ASSISTANT_LOCAL_URL"], "test"))

    def test_llama_cli_backend_missing_executable_or_model(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {"ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli"}
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(UserError):
                provider._chat([{"role": "user", "content": "¿Mis vacaciones?"}], [])

    def test_llama_cli_backend_no_user_message(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {
            "ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli",
            "MOLE_LLAMA_EXE": "llama-completion.exe",
            "MOLE_MODEL_PATH": "model.gguf",
        }
        with patch.dict("os.environ", env, clear=True):
            with self.assertRaises(UserError):
                provider._chat([{"role": "system", "content": "System prompt"}], [])

    def test_llama_cli_backend_dispatches_to_local_interpret(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {
            "ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli",
            "MOLE_LLAMA_EXE": "llama-completion.exe",
            "MOLE_MODEL_PATH": "model.gguf",
        }
        expected = {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "hr.vacation.balance.get_own", "arguments": {},
        }}]}
        with patch.dict("os.environ", env, clear=True), patch(
            "odoo.addons.assistant_local.models.inference._local_interpret", return_value=expected
        ) as mock_interpret:
            messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "¿Cuántos días de vacaciones me quedan?"},
            ]
            result = provider._chat(messages, [])
            self.assertEqual(result, expected)
            mock_interpret.assert_called_once_with(
                "¿Cuántos días de vacaciones me quedan?",
                "llama-completion.exe",
                "model.gguf",
            )

    def test_llama_cli_backend_wraps_errors_in_user_error(self):
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {
            "ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli",
            "MOLE_LLAMA_EXE": "llama-completion.exe",
            "MOLE_MODEL_PATH": "model.gguf",
        }
        for error_type in (ValueError, OSError, RuntimeError):
            with self.subTest(error_type=error_type):
                with patch.dict("os.environ", env, clear=True), patch(
                    "odoo.addons.assistant_local.models.inference._local_interpret",
                    side_effect=error_type("Inference failure"),
                ):
                    with self.assertRaises(UserError):
                        provider._chat([{"role": "user", "content": "test"}], [])

    def test_llama_cli_backend_with_real_local_model_binary(self):
        import os
        repo_root = Path(__file__).resolve().parents[2]
        exe = repo_root / ".runtime" / "llama-cpu" / "llama-completion.exe"
        model = repo_root / ".runtime" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
        if not exe.exists() or not model.exists() or os.name != "nt":
            return
        provider = self.env["assistant.inference"].with_user(self.user)
        env = {
            "ASSISTANT_LOCAL_BACKEND": "llama_cpp_cli",
            "MOLE_LLAMA_EXE": str(exe),
            "MOLE_MODEL_PATH": str(model),
        }
        with patch.dict("os.environ", env, clear=True):
            messages = [{"role": "user", "content": "¿Cuántos días de vacaciones me quedan?"}]
            reply = provider._chat(messages, [])
            self.assertEqual(reply["tool_calls"], [{"function": {
                "name": "hr.vacation.balance.get_own", "arguments": {},
            }}])

            messages_other = [{"role": "user", "content": "¿Cuántos días de vacaciones tiene Ana?"}]
            reply_other = provider._chat(messages_other, [])
            self.assertEqual(reply_other["tool_calls"], [])
