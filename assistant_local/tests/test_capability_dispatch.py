from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, new_test_user


class TestCapabilityDispatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.user = new_test_user(
            cls.env, login="assistant_dispatch_user", groups="base.group_user", context={"no_reset_password": True}
        )

    def test_unknown_tool_is_rejected(self):
        engine = self.env["assistant.capability"].with_user(self.user)
        with self.assertRaises(ValueError):
            engine._execute_capability("res.users.write", {"user_id": 1})

    def test_dispatch_is_not_available_via_public_rpc(self):
        engine = self.env["assistant.capability"].with_user(self.user)
        with self.assertRaises(AccessError):
            get_public_method(engine, "_execute_capability")

    def test_registered_handler_runs_as_requesting_user(self):
        engine = self.env["assistant.capability"].with_user(self.user)
        handler = lambda model, args: (model.env.uid, args["value"])
        catalog = {"test.echo": ({"value": str}, handler)}
        with patch.object(type(engine), "_get_capabilities", return_value=catalog):
            result = engine._execute_capability("test.echo", {"value": "ok"})
        self.assertEqual(result, (self.user.id, "ok"))

    def test_invalid_arguments_never_invoke_handler(self):
        engine = self.env["assistant.capability"].with_user(self.user)
        invoked = []
        catalog = {"test.echo": ({"value": str}, lambda model, args: invoked.append(args))}
        with patch.object(type(engine), "_get_capabilities", return_value=catalog):
            with self.assertRaises(ValueError):
                engine._execute_capability("test.echo", {"value": "ok", "user_id": 1})
        self.assertFalse(invoked)
