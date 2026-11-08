from odoo import api, models

from ..tool_validation import validate_call


class AssistantCapability(models.AbstractModel):
    _name = "assistant.capability"
    _description = "Registered Assistant Capabilities"

    @api.model
    def _get_capabilities(self):
        return {}

    @api.model
    def _execute_capability(self, name, arguments):
        capabilities = self._get_capabilities()
        schemas = {key: value[0] for key, value in capabilities.items()}
        validated = validate_call(schemas, name, arguments)
        return capabilities[name][1](self, validated)
