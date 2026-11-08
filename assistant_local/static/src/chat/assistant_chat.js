/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class AssistantChat extends Component {
    static template = "assistant_local.AssistantChat";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");

        const action = this.props.action || {};
        const params = action.params || {};
        const context = params.context || action.context || {};
        const rawConversationId = context.conversationId;
        this.conversationId = Number.isInteger(rawConversationId)
            ? rawConversationId
            : null;

        this.state = useState({
            messages: [],
            draft: "",
            loading: false,
            sending: false,
            error: "",
            unavailable: false,
        });

        onWillStart(async () => {
            await this.loadMessages();
        });
    }

    get canSend() {
        return (
            !this.state.loading &&
            !this.state.sending &&
            this.conversationId !== null &&
            this.state.draft.trim().length > 0 &&
            this.state.draft.length <= 4000
        );
    }

    async loadMessages() {
        if (this.conversationId === null) {
            this.state.error = _t("La conversación indicada no es válida.");
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            const messages = await this.orm.call(
                "assistant.conversation",
                "get_chat_messages",
                [[this.conversationId]]
            );
            this.state.messages = Array.isArray(messages) ? messages : [];
        } catch (error) {
            this.state.error = _t("No se pudieron cargar los mensajes.");
        } finally {
            this.state.loading = false;
        }
    }

    async submit() {
        if (!this.canSend) {
            return;
        }
        const text = this.state.draft.trim();
        this.state.sending = true;
        this.state.error = "";
        this.state.unavailable = false;
        try {
            const result = await this.orm.call(
                "assistant.conversation",
                "submit_chat_message",
                [[this.conversationId], text]
            );
            if (!result || !Array.isArray(result.messages) || !["ok", "unavailable"].includes(result.status)) {
                throw new Error("Invalid assistant response");
            }
            this.state.messages = result.messages;
            if (result.status === "unavailable") {
                this.state.unavailable = true;
            }
            this.state.draft = "";
        } catch (error) {
            this.state.error = _t("No se pudo enviar el mensaje.");
        } finally {
            this.state.sending = false;
        }
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.submit();
        }
    }
}

registry.category("actions").add("assistant_local.chat", AssistantChat);
