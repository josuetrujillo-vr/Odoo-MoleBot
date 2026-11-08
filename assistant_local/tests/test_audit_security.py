from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, new_test_user


class TestAuditSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.alice = new_test_user(
            cls.env, login="assistant_audit_alice", groups="base.group_user", context={"no_reset_password": True}
        )
        cls.bob = new_test_user(
            cls.env, login="assistant_audit_bob", groups="base.group_user", context={"no_reset_password": True}
        )

    def test_user_cannot_forge_change_or_delete_audit(self):
        audits = self.env["assistant.audit"].with_user(self.alice)
        with self.assertRaises(AccessError):
            audits.create({"capability": "forged", "outcome": "ok"})
        audit = audits._record("test.echo", "ok")
        self.assertEqual(audit.user_id, self.alice)
        with self.assertRaises(AccessError):
            audit.write({"capability": "altered"})
        with self.assertRaises(AccessError):
            audit.unlink()
        with self.assertRaises(AccessError):
            get_public_method(audits, "_record")

    def test_user_cannot_read_other_users_audit(self):
        audit = self.env["assistant.audit"].with_user(self.alice)._record("test.echo", "ok")
        other = self.env["assistant.audit"].with_user(self.bob)
        self.assertFalse(other.search([("id", "=", audit.id)]))
        with self.assertRaises(AccessError):
            other.browse(audit.id).read(["capability"])
