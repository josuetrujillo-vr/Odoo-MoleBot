import os

from odoo import models
from odoo.exceptions import UserError

from ..local_model import chat as _local_chat
from ..mole_local import interpret as _local_interpret


chat = _local_chat


class AssistantInference(models.AbstractModel):
    _name = "assistant.inference"
    _description = "Local Assistant Inference"

    def _chat(self, messages, tools):
        if os.environ.get("ASSISTANT_LOCAL_BACKEND") == "llama_cpp_cli":
            executable = os.environ.get("MOLE_LLAMA_EXE")
            model = os.environ.get("MOLE_MODEL_PATH")
            if not executable or not model:
                raise UserError(self.env._("No local model is configured."))
            user_messages = [item.get("content", "") for item in messages if item.get("role") == "user"]
            if not user_messages:
                raise UserError(self.env._("No user message is available."))
            try:
                return _local_interpret(user_messages[-1], executable, model)
            except (ValueError, OSError, RuntimeError) as exc:
                raise UserError(self.env._("Local model inference failed: %s") % exc) from exc
        base_url = os.environ.get("ASSISTANT_LOCAL_URL")
        model = os.environ.get("ASSISTANT_LOCAL_MODEL")
        if not base_url or not model:
            raise UserError(self.env._("No local model is configured."))
        if not isinstance(messages, list) or not isinstance(tools, list):
            raise UserError(self.env._("Invalid model request."))
        return chat(base_url, model, messages, tools, timeout=30)
