from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChatBrowser(HttpCase):
    def test_chat_opens_and_reports_unavailable(self):
        user = new_test_user(
            self.env,
            login="assistant_browser",
            password="assistant_browser",
            groups="base.group_user",
            context={"no_reset_password": True},
        )
        conversation = self.env["assistant.conversation"].with_user(user).create({"name": "Browser test"})
        self.browser_js(
            "/web#id=%s&model=assistant.conversation&view_type=form" % conversation.id,
            r"""
            (async () => {
                const waitFor = async (selector) => {
                    for (let i = 0; i < 160; i++) {
                        const element = document.querySelector(selector);
                        if (element) return element;
                        await new Promise((resolve) => setTimeout(resolve, 250));
                    }
                    throw new Error(`Missing ${selector}`);
                };
                (await waitFor('button[name="action_open_chat"]')).click();
                const input = await waitFor('.o_assistant_chat textarea');
                input.value = 'Hola desde la prueba local';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                (await waitFor('.o_assistant_chat button:not(:disabled)')).click();
                await waitFor('.o_assistant_chat .alert-warning');
                if (!document.querySelector('.o_assistant_chat_messages').textContent.includes('Hola desde la prueba local')) {
                    throw new Error('Message was not shown');
                }
                console.log('test successful');
            })().catch((error) => console.error(error));
            """,
            login="assistant_browser",
            timeout=90,
        )
