import os

from odoo import models
from odoo.exceptions import UserError

from ..local_model import chat as _local_chat
from ..mole_local import interpret as _local_interpret
from ..mole_local import interpret_general


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

    def _general_plan(self, question, catalog):
        if os.environ.get("ASSISTANT_LOCAL_BACKEND") != "llama_cpp_cli":
            base_url = os.environ.get("ASSISTANT_LOCAL_URL")
            model = os.environ.get("ASSISTANT_LOCAL_MODEL")
            if not base_url or not model:
                raise UserError(self.env._("No local model is configured."))
            import json
            message = {"role": "user", "content": "Propón un conteo estructurado; catálogo: " +
                       json.dumps(catalog, ensure_ascii=False) + "\nPregunta: " + question}
            schema = {"type": "function", "function": {"name": "general_count", "description": "Contar registros visibles",
                "parameters": {"type": "object", "properties": {"operation": {"type": "string"},
                "model": {"type": "string"}, "filters": {"type": "array"}},
                "required": ["operation", "model", "filters"], "additionalProperties": False}}}
            reply = chat(base_url, model, [message], [schema], timeout=30)
            if not isinstance(reply, dict):
                return None
            calls = reply.get("tool_calls")
            if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
                return None
            function = calls[0].get('function')
            if (not isinstance(function, dict) or function.get('name') != 'general_count'
                    or not isinstance(function.get('arguments'), dict)):
                return None
            return function['arguments']
        executable = os.environ.get("MOLE_LLAMA_EXE")
        model = os.environ.get("MOLE_MODEL_PATH")
        if not executable or not model:
            raise UserError(self.env._("No local model is configured."))
        try:
            return interpret_general(question, catalog, executable, model)
        except (ValueError, OSError, RuntimeError) as exc:
            raise UserError(self.env._("Local model inference failed: %s") % exc) from exc
