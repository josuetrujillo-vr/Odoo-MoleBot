{
    "name": "Local Assistant",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail", "calendar", "account"],
    "data": ["security/ir.model.access.csv", "security/assistant_security.xml",
             "views/assistant_client_action.xml", "views/conversation_views.xml"],
    "assets": {"web.assets_backend": [
        "assistant_local/static/src/chat/assistant_chat.js",
        "assistant_local/static/src/chat/assistant_chat.xml",
    ]},
    "installable": True,
}
