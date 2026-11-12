"""Deterministic English/Spanish parsing for inventory questions.

This module only extracts user-provided names, quantities and intent. It never
touches Odoo records, so it cannot grant access or invent business data.
"""

import re
import unicodedata


CONFIRM_WORDS = frozenset({
    "confirm", "confirmed", "yes", "y", "ok", "okay", "proceed", "execute",
    "continue", "confirmo", "si", "adelante", "hazlo", "ejecuta", "continuar",
})
CANCEL_WORDS = frozenset({
    "cancel", "no", "stop", "discard", "cancelar", "no gracias",
})

_GENERIC_SUBJECTS = frozenset({
    "product", "products", "producto", "productos", "item", "items",
    "article", "articles", "articulo", "articulos", "contact", "contacts",
    "contacto", "contactos", "customer", "customers", "cliente", "clientes",
    "vendor", "vendors", "proveedor", "proveedores", "sale order", "sale orders",
    "order", "orders", "pedido", "pedidos", "purchase order", "purchase orders",
    "invoice", "invoices", "factura", "facturas", "employee", "employees",
    "empleado", "empleados", "task", "tasks", "tarea", "tareas", "project",
    "projects", "proyecto", "proyectos", "lead", "leads", "opportunity",
    "opportunities", "oportunidad", "oportunidades", "stock", "inventory",
    "inventario", "existence", "existencias", "quant", "quants", "location",
    "locations", "ubicacion", "ubicaciones", "warehouse", "warehouses",
    "almacen", "almacenes", "bodega", "bodegas", "unit", "units", "unidad",
    "unidades", "piece", "pieces", "pieza", "piezas", "time off", "vacation",
    "vacations", "vacacion", "vacaciones",
})

_GENERIC_PREFIXES = (
    r"the|a|an|el|la|los|las|un|una|unos|unas",
    r"products?|productos?|items?|articles?|articulos?|units?|unidades?|"
    r"pieces?|piezas?|boxes?|cajas?|of|de|del|for|para",
    r"locations?|ubicaciones?|ubicacion|warehouses?|almacenes?|almacen|"
    r"stock\s+locations?|bodegas?|from|desde|to|a|hacia|hasta",
)

_LEADING_PREFIX = re.compile(
    r"^(?:" + "|".join(_GENERIC_PREFIXES) + r")\s+", re.IGNORECASE
)
_LEADING_ARTICLE = re.compile(
    r"^(?:the|a|an|el|la|los|las|un|una)\s+", re.IGNORECASE
)
_LEADING_LOCATION_PHRASE = re.compile(
    r"^(?:the|a|an|el|la|los|las|un|una)\s+"
    r"(?:(?:stock\s+)?locations?|ubicaciones?|warehouses?|almacenes?|bodegas?)\s+",
    re.IGNORECASE,
)
_TRAILING_STOCK_WORDS = re.compile(
    r"\s+(?:in\s+stock|on\s*hand|available|left|located|stored|kept|"
    r"currently|en\s+stock|en\s+existencia|disponible|disponibles|"
    r"situado|situada|guardado|guardada)\s*$",
    re.IGNORECASE,
)
_STOCK_SIGNAL = re.compile(
    r"\b(?:stock|inventory|inventario|existencias?|existencia|on\s*hand|"
    r"units?|unidades?|pieces?|piezas?|boxes?|cajas?|warehouse|almacen|"
    r"locations?|ubicacion(?:es)?|quants?)\b",
    re.IGNORECASE,
)
_TIME_OFF = re.compile(
    r"\b(?:vacacion(?:es)?|vacations?|time\s+off|pto|holidays?|descanso)\b",
    re.IGNORECASE,
)

_EN_NUMBER_WORDS = {
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "eleven": 11.0, "twelve": 12.0, "fifteen": 15.0, "twenty": 20.0,
}
_ES_NUMBER_WORDS = {
    "un": 1.0, "una": 1.0, "uno": 1.0, "dos": 2.0, "tres": 3.0,
    "cuatro": 4.0, "cinco": 5.0, "seis": 6.0, "siete": 7.0, "ocho": 8.0,
    "nueve": 9.0, "diez": 10.0, "once": 11.0, "doce": 12.0,
    "quince": 15.0, "veinte": 20.0,
}

_EN_WORDS = frozenset({
    "the", "of", "how", "many", "much", "where", "what", "which", "who",
    "is", "are", "do", "does", "we", "i", "you", "in", "on", "from", "to",
    "with", "and", "there", "stock", "inventory", "product", "products",
    "location", "locations", "warehouse", "available", "transfer", "move",
    "relocate", "send", "take", "units", "unit", "quantity", "show", "list",
    "count", "have", "has", "left", "located", "stored", "please", "can",
    "could", "would", "tell", "me", "all", "current", "total", "number",
    "hello", "hi", "hey", "good", "morning", "afternoon", "evening", "help",
    "thanks", "thank", "contact", "contacts", "customer", "customers",
    "order", "orders", "sale", "purchase", "invoice", "invoices", "task",
    "tasks", "project", "projects", "employee", "employees", "confirm",
    "cancel", "yes", "no", "mole",
})
_ES_WORDS = frozenset({
    "el", "la", "los", "las", "de", "del", "cuanto", "cuanta", "cuantos",
    "cuantas", "donde", "esta", "estan", "que", "cual", "cuales", "hay",
    "producto", "productos", "inventario", "ubicacion", "ubicaciones",
    "almacen", "almacenes", "existencias", "existencia", "transferir",
    "transfiere", "mover", "mueve", "trasladar", "traslada", "enviar",
    "envia", "unidades", "unidad", "mostrar", "muestra", "lista", "cuenta",
    "tiene", "tienen", "disponible", "disponibles", "stock", "cantidad",
    "por", "favor", "puedes", "podrias", "dime", "para", "con", "desde",
    "hacia", "hasta", "piezas", "pieza", "hola", "buenos", "buenas", "dias",
    "tardes", "noches", "gracias", "ayuda", "saludos", "confirmar",
    "cancelar", "si", "mole",
})


def normalize(text):
    """Lowercase and remove accents so English/Spanish variants match."""
    if not isinstance(text, str):
        return ""
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def detect_language(text):
    """Return ``en`` for English-looking questions, otherwise ``es``."""
    normalized = normalize(text)
    if not normalized:
        return "es"
    if any(char in text for char in "¿¡ñÑáéíóúÁÉÍÓÚ"):
        spanish_hits = sum(1 for word in re.findall(r"[a-z]+", normalized) if word in _ES_WORDS)
        english_hits = sum(1 for word in re.findall(r"[a-z]+", normalized) if word in _EN_WORDS)
        if spanish_hits >= english_hits:
            return "es"
    words = re.findall(r"[a-z]+", normalized)
    english_hits = sum(1 for word in words if word in _EN_WORDS)
    spanish_hits = sum(1 for word in words if word in _ES_WORDS)
    return "en" if english_hits > spanish_hits else "es"


def parse_transfer_reply(question):
    """Return ``confirm`` or ``cancel`` only for an explicit short reply."""
    if not isinstance(question, str) or len(question) > 4000 or "\x00" in question:
        return None
    text = normalize(question).strip().strip("¿?¡! .,;:")
    text = re.sub(r"^(?:please|por\s+favor)\s+", "", text)
    text = re.sub(r"\s+(?:please|por\s+favor)$", "", text)
    if text in CONFIRM_WORDS:
        return "confirm"
    if text in CANCEL_WORDS:
        return "cancel"
    return None


def _clean_name(name):
    if not isinstance(name, str):
        return ""
    value = name.strip().strip("\"'“”‘’¿?¡!.,;:")
    previous = None
    while previous != value:
        previous = value
        value = _LEADING_PREFIX.sub("", value).strip()
        value = _TRAILING_STOCK_WORDS.sub("", value).strip()
    return re.sub(r"\s+", " ", value).strip()


def _is_generic(name):
    return normalize(name).strip() in _GENERIC_SUBJECTS


def _clean_location(name):
    """Keep location names intact, only dropping framing words.

    Stripping a bare "location"/"warehouse" word here would corrupt real names
    like "Location A" or "Almacén A". Only an article followed by a location
    descriptor is removed; the ORM lookup retries without a bare descriptor.
    """
    if not isinstance(name, str):
        return ""
    value = name.strip().strip("\"'“”‘’¿?¡!.,;:")
    previous = None
    while previous != value:
        previous = value
        value = _LEADING_LOCATION_PHRASE.sub("", value).strip()
        value = _LEADING_ARTICLE.sub("", value).strip()
    return re.sub(r"\s+", " ", value).strip()


def _slice(original, normalized, start, end):
    if len(original) == len(normalized):
        return original[start:end]
    return normalized[start:end]


_COURTESY = re.compile(
    r"^(?:hey\s+mole[,:\s]+|mole[,:\s]+|please\s+|por\s+favor\s+|"
    r"can\s+you\s+|could\s+you\s+|would\s+you\s+|puedes\s+|podrias\s+)"
)


def _prepare(text):
    """Return trimmed text plus the offset of its first character in ``text``."""
    match = _COURTESY.match(text)
    start = match.end() if match else 0
    while start < len(text) and text[start] in " \t\r\n¿¡":
        start += 1
    end = len(text)
    while end > start and text[end - 1] in " \t\r\n¿?¡!.,;:":
        end -= 1
    return text[start:end], start


def _quoted(question, normalized):
    """Return quoted values with their positions and preceding context."""
    items = []
    for match in re.finditer(r'"([^"\r\n]{1,120})"', question):
        value = match.group(1).strip()
        if not value:
            continue
        before = normalized[max(0, match.start() - 40):match.start()]
        items.append({"value": value, "start": match.start(), "end": match.end(),
                      "before": before})
    return items


def _quoted_location(items, role):
    pattern = (r"\b(?:from|desde|de|to|a|hacia|hasta)"
               r"(?:\s+(?:the|la|el|los|las))?"
               r"(?:\s+(?:location|ubicacion|warehouse|almacen|bodega))?\s*$")
    for item in items:
        if re.search(pattern, item["before"]):
            normalized_before = normalize(item["before"])
            match = re.search(pattern, normalized_before)
            if not match:
                continue
            word = match.group(0)
            if role == "origin" and re.search(r"\b(?:from|desde|de)\b", word):
                return item["value"], item
            if role == "destination" and re.search(r"\b(?:to|a|hacia|hasta)\b", word):
                return item["value"], item
    return None, None


def _take_quantity(text, leading_only=False):
    """Return ``(quantity, remaining_text, uom_name)`` for a leading amount."""
    if not isinstance(text, str):
        return None, text, None
    value = text.strip()
    number = r"(?P<number>\d+(?:[.,]\d+)?)"
    words = "|".join(sorted(set(_EN_NUMBER_WORDS) | set(_ES_NUMBER_WORDS), key=len, reverse=True))
    uom = (r"(?P<uom>units?|unidades?|pcs?|pieces?|piezas?|boxes?|cajas?|"
           r"kg|kgs?|kilograms?|kilogramos?|liters?|litros?|meters?|metros?)?")
    match = re.match(
        r"^(?:the\s+)?(?:" + number + r"|(?P<word>" + words + r"))\s*" + uom +
        r"\s*(?:of\s+|de\s+|del\s+)?", value, re.IGNORECASE,
    )
    if not match:
        if leading_only:
            return None, value, None
        match = re.search(
            r"\b(?:" + number + r"|(?P<word>" + words + r"))\s*" + uom +
            r"\b", value, re.IGNORECASE,
        )
        if not match:
            return None, value, None
        remaining = (value[:match.start()] + " " + value[match.end():]).strip()
    else:
        remaining = value[match.end():].strip()
    raw = match.group("number") or match.group("word")
    if match.group("number"):
        quantity = float(raw.replace(",", "."))
    else:
        quantity = _EN_NUMBER_WORDS.get(raw.casefold()) or _ES_NUMBER_WORDS.get(raw.casefold())
    if quantity is None or quantity <= 0:
        return None, value, None
    return quantity, remaining, (match.group("uom") or None)


def _parse_transfer(question, normalized):
    text, offset = _prepare(normalized)
    english = re.match(
        r"^(?:transfer|move|relocate|send|take)\s+(?P<body>.+)$", text,
    )
    spanish = re.match(
        r"^(?:transferir|transfiere|transfieras|mover|mueve|muevas|trasladar|"
        r"traslada|traslades|enviar|envia|envies|mandar|manda|mandes)\s+"
        r"(?P<body>.+)$", text,
    )
    if not english and not spanish:
        return None
    language = "en" if english else "es"
    body_start = offset + (english or spanish).start("body")
    body = (english or spanish).group("body")

    items = _quoted(question, normalized)
    origin, origin_item = _quoted_location(items, "origin")
    destination, destination_item = _quoted_location(items, "destination")
    product_quote = None
    for item in items:
        if item is not origin_item and item is not destination_item:
            product_quote = item["value"]
            break

    split = re.match(
        r"^(?P<product>.+?)\s+from\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+)$",
        body,
    )
    if not split:
        split = re.match(
            r"^(?P<product>.+?)\s+(?:de|desde)\s+(?P<origin>.+?)\s+"
            r"(?:a|hacia|hasta)\s+(?P<destination>.+)$",
            body,
        )
    if not split and not (origin and destination):
        return None

    product_is_quoted = product_quote is not None
    if product_is_quoted:
        product = product_quote
    elif origin_item is not None:
        # Quoted origin/destination let us locate the product prefix exactly,
        # even when the product name itself contains "de" or "from".
        prefix = normalized[body_start:origin_item["start"]]
        delimiters = list(re.finditer(r"\b(?:from|de|desde)\b", prefix))
        if delimiters:
            product = _slice(
                question, normalized, body_start, body_start + delimiters[-1].start()
            )
        elif split:
            product = _slice(
                question, normalized,
                body_start + split.start("product"), body_start + split.end("product"),
            )
        else:
            product = ""
    elif split:
        product = _slice(
            question, normalized,
            body_start + split.start("product"), body_start + split.end("product"),
        )
    else:
        product = ""

    if not origin and split:
        origin = _slice(
            question, normalized,
            body_start + split.start("origin"), body_start + split.end("origin"),
        )
    if not destination and split:
        destination = _slice(
            question, normalized,
            body_start + split.start("destination"), body_start + split.end("destination"),
        )

    quantity, _body_without_quantity, uom_name = _take_quantity(body, leading_only=True)
    if product_is_quoted:
        product = product.strip()
    else:
        product = _clean_name(product)
        parsed_quantity, product, parsed_uom = _take_quantity(product, leading_only=True)
        if quantity is None:
            quantity, uom_name = parsed_quantity, parsed_uom
        product = _clean_name(product)
    if not product and product_is_quoted:
        product = product_quote
    if not origin_item:
        origin = _clean_location(origin)
    if not destination_item:
        destination = _clean_location(destination)
    origin = origin.strip()
    destination = destination.strip()
    if not product or not origin or not destination:
        return None
    if _is_generic(product) and not product_is_quoted:
        return None
    return {
        "intent": "transfer",
        "language": language,
        "product": product,
        "origin": origin,
        "destination": destination,
        "quantity": quantity,
        "uom_name": uom_name,
    }


def _parse_quantity(question, normalized):
    text, offset = _prepare(normalized)
    patterns = (
        # How many units of Product X do we have?
        (r"^(?:how\s+(?:many|much)\s+)?(?:units?|pieces?|pcs|boxes?)\s+of\s+"
         r"(?P<name>.+?)(?:\s+(?:are\s+there|do\s+(?:we|i|you)\s+have|"
         r"is\s+there|exists?|are\s+available|is\s+available|in\s+stock|"
         r"on\s*hand|left|currently))?\s*$", "en"),
        # What is the stock/quantity/inventory of Product X?
        (r"^(?:what(?:'s|\s+is)?\s+the\s+(?:current\s+)?"
         r"(?:stock|quantity|inventory|on[\s-]*hand|qty)|"
         r"what\s+(?:quantity|stock|inventory)\s+(?:of|for)|"
         r"(?:total|current)\s+(?:stock|quantity|inventory)\s+(?:of|for)|"
         r"(?:stock|inventory|quantity)\s+(?:of|for))\s+"
         r"(?P<name>.+?)\s*$", "en"),
        # How much is left/available of Product X?
        (r"^(?:how\s+much)\s+(?:is\s+)?(?:left|available)\s+"
         r"(?:of\s+|for\s+)?(?P<name>.+?)\s*$", "en"),
        # How much (of) Product X do we have / is there / is in stock?
        (r"^(?:how\s+(?:much|many))\s+(?:of\s+|for\s+)?(?:the\s+)?"
         r"(?:product\s+|item\s+)?(?P<name>.+?)"
         r"(?:\s+(?:do\s+(?:we|i|you)\s+have(?:\s+(?:in\s+stock|"
         r"available|on\s*hand))?|does\s+(?:it|that)\s+have|"
         r"is\s+there|are\s+there|is\s+available|are\s+available|"
         r"is\s+in\s+stock|are\s+in\s+stock|is\s+on\s*hand|"
         r"are\s+on\s*hand|is\s+left|are\s+left|do\s+you\s+have|"
         r"exist|are\s+visible|is\s+visible|in\s+total|currently))?\s*$", "en"),
        # Do we have Product X in stock?
        (r"^(?:do|does)\s+(?:we|i|you)\s+have\s+(?P<name>.+?)\s+"
         r"(?:in\s+stock|available|on\s*hand)\s*$", "en"),
        # ¿Cuánto hay de Product X? / ¿Cuánto Product X hay?
        (r"^(?:cuanto|cuanta|cuantos|cuantas)\s+(?:hay\s+)?"
         r"(?:de\s+|del\s+|de\s+la\s+|de\s+el\s+)?"
         r"(?:el\s+|la\s+|los\s+|las\s+)?(?:producto\s+)?(?P<name>.+?)"
         r"(?:\s+(?:hay|existe|existen|tenemos|tengo|disponible|"
         r"disponibles|en\s+stock|en\s+existencia|actualmente))?\s*$", "es"),
        # ¿Cuántas unidades/existencias hay de Product X?
        (r"^(?:cuantas?)\s+(?:unidades?|existencias?|piezas?)\s+"
         r"(?:hay\s+)?(?:de\s+|del\s+)?(?P<name>.+?)\s*$", "es"),
        # ¿Qué cantidad hay de Product X?
        (r"^(?:que\s+cantidad|cuanto\s+stock|cuanta\s+existencia)\s+"
         r"(?:hay\s+)?(?:de\s+|del\s+)?(?P<name>.+?)\s*$", "es"),
    )
    for pattern, language in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        name = _clean_name(_slice(
            question, normalized, offset + match.start("name"), offset + match.end("name")
        ))
        if not name or _is_generic(name):
            continue
        return {
            "intent": "quantity",
            "language": language,
            "product": name,
            "origin": None,
            "destination": None,
            "quantity": None,
            "uom_name": None,
        }
    return None


def _parse_location(question, normalized):
    text, offset = _prepare(normalized)
    patterns = (
        (r"^where\s+(?:is|are)\s+(?:the\s+)?(?:stock\s+of\s+|inventory\s+of\s+)?"
         r"(?P<name>.+?)(?:\s+(?:located|stored|kept))?\s*$", "en"),
        (r"^where\s+(?:can|could|do)\s+i\s+(?:find|locate)\s+(?:the\s+)?"
         r"(?P<name>.+?)\s*$", "en"),
        (r"^where\s+is\s+the\s+(?:stock|inventory|quantity)\s+(?:of|for)\s+"
         r"(?P<name>.+?)\s*$", "en"),
        (r"^in\s+(?:which|what)\s+(?:location|warehouse|stock\s+location)\s+"
         r"(?:is|are)\s+(?:the\s+)?(?P<name>.+?)(?:\s+located)?\s*$", "en"),
        (r"^what\s+is\s+the\s+(?:location|warehouse)\s+(?:of|for)\s+"
         r"(?:the\s+)?(?P<name>.+?)\s*$", "en"),
        (r"^(?:location|warehouse)\s+(?:of|for)\s+(?:the\s+)?(?P<name>.+?)\s*$", "en"),
        (r"^donde\s+(?:esta|estan|se\s+encuentra|se\s+encuentran)\s+"
         r"(?:el\s+|la\s+)?(?:producto\s+)?(?P<name>.+?)\s*$", "es"),
        (r"^donde\s+puedo\s+(?:encontrar|ubicar)\s+(?:el\s+|la\s+)?"
         r"(?:producto\s+)?(?P<name>.+?)\s*$", "es"),
        (r"^en\s+(?:que|cual)\s+(?:ubicacion|almacen|bodega)\s+"
         r"(?:esta|estan|se\s+encuentra|se\s+encuentran)\s+"
         r"(?:el\s+|la\s+)?(?:producto\s+)?(?P<name>.+?)\s*$", "es"),
        (r"^ubicacion\s+(?:de|del)\s+(?:el\s+|la\s+)?(?:producto\s+)?"
         r"(?P<name>.+?)\s*$", "es"),
    )
    for pattern, language in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        name = _clean_name(_slice(
            question, normalized, offset + match.start("name"), offset + match.end("name")
        ))
        if not name or _is_generic(name):
            continue
        return {
            "intent": "location",
            "language": language,
            "product": name,
            "origin": None,
            "destination": None,
            "quantity": None,
            "uom_name": None,
        }
    return None


def _is_quoted(question, name):
    """Return True when ``name`` was written between quotes by the user."""
    target = normalize(name).strip()
    if not target:
        return False
    return any(
        normalize(item["value"]).strip() == target
        for item in _quoted(question, normalize(question))
    )


def parse_stock_intent(question):
    """Return a parsed inventory intent, or ``None`` when not recognized.

    Recognized intents are ``quantity``, ``location`` and ``transfer``. The
    returned names are still unresolved user text; callers must validate them
    against Odoo using the authenticated user's environment.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        return None
    if "\x00" in question:
        return None
    normalized = normalize(question)
    if _TIME_OFF.search(normalized) and not _STOCK_SIGNAL.search(normalized):
        # "How many vacation days do I have?" must reach the time-off handler,
        # not be read as a stock quantity question.
        return None
    transfer = _parse_transfer(question, normalized)
    if transfer:
        return transfer
    parsed = _parse_quantity(question, normalized) or _parse_location(
        question, normalized
    )
    if not parsed:
        return None
    parsed["product_quoted"] = _is_quoted(question, parsed["product"])
    parsed["explicit_stock"] = bool(_STOCK_SIGNAL.search(normalized))
    return parsed
