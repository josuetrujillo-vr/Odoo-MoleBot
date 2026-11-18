"""Local Windows intent classifier for the first Mole vacation capability."""

import json
import os
import re
import subprocess
import threading
import unicodedata
import uuid
from pathlib import Path


VACATION_TOOL = "hr.vacation.balance.get_own"

_FIRST_PERSON = re.compile(
    r"\b(mi|mis|me|tengo|tendre|quedan|corresponden|tocan|yo|mio|mios|mia|mias|puedo)\b"
)

_OTHER_PERSON = re.compile(
    r"\b(companero|companera|companeros|companeras|"
    r"colega|colegas|empleado|empleada|empleados|empleadas|"
    r"trabajador|trabajadora|trabajadores|trabajadoras|"
    r"otra persona|otras personas|otro usuario|otros usuarios|"
    r"tercero|terceros|jefe|jefa|jefes|jefas|patron|patrona|"
    r"supervisor|supervisora|supervisores|supervisoras|"
    r"gerente|gerentes|director|directora|directores|directoras|"
    r"subordinado|subordinada|subordinados|subordinadas|"
    r"equipo|amigo|amiga|amigos|amigas|personal|"
    r"el|ella|ellos|ellas|otro|otra|otros|otras|alguien|nadie|"
    r"le|les)\b"
)

_BALANCE_INTENT = re.compile(
    r"\b(saldo|dia|dias|tiempo|periodo|fecha|aniversario|vencimiento|vence|vencen|"
    r"disponible|disponibles|restante|restantes|restan|cuanto|cuantos|cuanta|cuantas|"
    r"cuando|tengo|quedan|quede|corresponden|tocan|derecho|consultar|calcular|revisar|saber|ver)\b"
)

_OUT_OF_SCOPE_ACTION = re.compile(
    r"\b(pedir|solicitar|programar|aprobar|me voy|irme|enferme|incapacidad|permiso|"
    r"cumpleanos|factura|facturas|transferencia|transferir|stock|evento|eventos)\b"
)

_VACATION_KEYWORD = re.compile(r"\b(vacacion|vacaciones)\b")

_SAFE_DE_TARGETS = frozenset({
    "vacacion", "vacaciones", "descanso", "ley", "este", "esta", "ano", "anos",
    "periodo", "mi", "mis", "trabajo", "antiguedad", "dias", "saldo"
})

_PROPER_NAME_AFTER_PREP = re.compile(r"\b(?:de|del|para|a)\s+([A-ZÁÉÍÓÚ][a-zñáéíóú]+)\b")
_DE_WORD = re.compile(r"\b(?:de|del|para)\s+([a-z]+)\b")
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

_GREETING_WORDS = (
    r"hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches|que\s+tal|saludos|"
    r"ayuda|que\s+puedes\s+hacer|como\s+funcionas|que\s+puedes\s+responder|"
    r"que\s+sabes\s+hacer|que\s+haces|en\s+que\s+me\s+puedes\s+ayudar|"
    r"hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|help|"
    r"what\s+can\s+you\s+do|how\s+do\s+you\s+work|what\s+can\s+you\s+answer|"
    r"what\s+do\s+you\s+know|what\s+do\s+you\s+do|how\s+can\s+you\s+help"
)

_GRATITUDE_WORDS = (
    r"muchas\s+gracias|mil\s+gracias|muchisimas\s+gracias|gracias|te\s+agradezco|se\s+agradece|"
    r"thank\s+you(?:\s+very\s+much)?|thanks(?:\s+a\s+lot)?"
)

_FAREWELL_WORDS = (
    r"adios|hasta\s+luego|hasta\s+pronto|nos\s+vemos|chao|bye|goodbye|see\s+you(?:\s+later)?"
)

_ACK_WORDS = (
    r"perfecto|excelente|de\s+acuerdo|entendido|muy\s+bien|genial|ok|okay|great|awesome|understood|got\s+it"
)

_QUERY_COURTESY = re.compile(
    r"^(?:(?:hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches|saludos|que\s+tal|hey|hello|hi|good\s+morning|good\s+afternoon|good\s+evening)\b[,:\s]*)*"
    r"(?:(?:por\s+favor|please|disculpa|oye|mole)\b[,:\s]*)*"
    r"(?:(?:me\s+puedes\s+decir|me\s+podrias\s+decir|puedes\s+decirme|podrias\s+decirme|puedes\s+mostrarme|podrias\s+mostrarme|"
    r"can\s+you\s+tell\s+me|could\s+you\s+tell\s+me|can\s+you\s+show\s+me|could\s+you\s+show\s+me|would\s+you\s+show\s+me|"
    r"puedes\s+darme|podrias\s+darme|sabes\s+si\s+hay|sabes\s+si\s+tenemos|sabes|do\s+you\s+know)\b[,:\s]*)*",
    re.IGNORECASE,
)


def clean_courtesy(text):
    """Strip leading conversational courtesies and greetings from a query."""
    if not isinstance(text, str):
        return ""
    norm = _normalize(text).strip().strip("¿?¡! ,;:")
    return _QUERY_COURTESY.sub("", norm).strip().strip("¿?¡! ,;:")


def classify_social(text):
    """Return social intent: 'greeting', 'gratitude', 'farewell', 'acknowledgment', or None."""
    if not isinstance(text, str):
        return None
    norm = _normalize(text).strip().strip("¿?¡! ,;:")
    if not norm:
        return None
    norm_no_mole = re.sub(r"\bmole\b", "", norm).strip("¿?¡! ,;:")
    if not norm_no_mole:
        return "greeting"

    if re.fullmatch(r"(?:" + _GRATITUDE_WORDS + r")(?:[\s,;:]+(?:mole|por\s+favor|amigo|amiga))*", norm_no_mole):
        return "gratitude"
    if re.fullmatch(r"(?:" + _FAREWELL_WORDS + r")(?:[\s,;:]+(?:mole|amigo|amiga))*", norm_no_mole):
        return "farewell"
    if re.fullmatch(r"(?:" + _ACK_WORDS + r")(?:[\s,;:]+(?:mole|muchas\s+gracias|gracias))*", norm_no_mole):
        return "acknowledgment"
    if re.fullmatch(r"(?:" + _GREETING_WORDS + r")(?:[\s,;:]+(?:mole|a\s+todos))*", norm_no_mole):
        return "greeting"
    return None


_NAMED_QUERY = re.compile(
    r"^\s*(?:¿\s*)?(?:(?:[Cc]u[aá]l\s+es\s+el\s+)?[Ss]aldo\s+de\s+vacaciones\s+(?:de|para)|"
    r"(?:[Cc]u[aá]ntos?\s+d[ií]as\s+de\s+vacaciones\s+(?:tiene|le\s+tocan\s+a))"
    r")\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'\-]*(?:\s+(?:[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'\-]*|de|del|la|las|los|y|e))*?)\s*[?.¿]*\s*$",
    re.IGNORECASE,
)

_NAMED_TARGET_STOPWORDS = frozenset({
    "mi", "mis", "su", "sus", "tu", "tus", "nuestro", "nuestra",
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "alguien", "algun", "alguna", "algunos", "algunas",
    "jefe", "jefa", "jefes", "jefas", "companero", "companera",
    "companeros", "companeras", "colega", "colegas",
    "empleado", "empleada", "empleados", "empleadas",
    "trabajador", "trabajadora", "trabajadores", "trabajadoras",
    "supervisor", "supervisora", "gerente", "director", "directora",
    "subordinado", "subordinada", "equipo", "personal",
})


def named_vacation_target(question):
    """Extract only an explicitly named, literal target from a narrow question."""
    if not isinstance(question, str) or len(question) > 4000 or "\x00" in question:
        return None
    cleaned = re.sub(
        r"^\s*(?:hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches)[,:\s]*",
        "", question, flags=re.IGNORECASE
    ).strip()
    match = _NAMED_QUERY.fullmatch(cleaned)
    if not match:
        return None
    target = match.group(1)
    first_word = _normalize(target.split()[0]) if target.split() else ""
    if first_word in _NAMED_TARGET_STOPWORDS:
        return None
    return target


def _normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def is_safe_own_vacation_query(question):
    """Deterministically check if a question is safely restricted to the user's own vacation balance."""
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        return False
    if "\x00" in question:
        return False

    for match in _PROPER_NAME_AFTER_PREP.finditer(question):
        word = match.group(1).lower()
        if _normalize(word) not in _SAFE_DE_TARGETS:
            return False

    norm = _normalize(question)
    norm = _QUERY_COURTESY.sub("", norm).strip().strip("¿?¡! ")
    if not _VACATION_KEYWORD.search(norm):
        return False
    if _OUT_OF_SCOPE_ACTION.search(norm):
        return False
    if not _FIRST_PERSON.search(norm):
        return False
    if not _BALANCE_INTENT.search(norm):
        return False
    if _OTHER_PERSON.search(norm):
        return False

    for match in _DE_WORD.finditer(norm):
        target = match.group(1)
        if target not in _SAFE_DE_TARGETS:
            return False

    return True


def interpret(question, executable, model):
    """Return a single safe tool call, or decline when self-reference is unclear or asks for third parties."""
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        raise ValueError("Invalid question")
    if "\x00" in question:
        raise ValueError("Invalid question")

    if not is_safe_own_vacation_query(question):
        return {"role": "assistant", "content": "", "tool_calls": []}

    decision = classify(question, executable, model)
    if decision not in {"VACACIONES", "OTRA"}:
        raise ValueError("Invalid local model classification")
    calls = [{"function": {"name": VACATION_TOOL, "arguments": {}}}] if decision == "VACACIONES" else []
    return {"role": "assistant", "content": "", "tool_calls": calls}


def classify(question, executable, model):
    """Run a constrained local model; pass the question through a Windows named pipe."""
    prompt = (
        "<|im_start|>system\nClasifica la solicitud: VACACIONES si pregunta por sus "
        "propios días de vacaciones, OTRA para cualquier otra cosa.\n"
        "Ejemplos:\n¿Cuántos días de vacaciones me quedan? VACACIONES\n"
        "Dime mi saldo de vacaciones. VACACIONES\n¿Cuándo vence mi periodo de vacaciones? VACACIONES\n"
        "¿Cuántos días de vacaciones tiene Ana? OTRA\n¿Cuántas facturas hice? OTRA\n"
        "Hola. OTRA\nTransfiere productos. OTRA\n<|im_end|>\n<|im_start|>user\n"
        + question.replace("<|", "< |").replace("|>", "| >") + "<|im_end|>\n<|im_start|>assistant\n"
    )
    output = _complete(prompt, executable, model, 'root ::= "VACACIONES" | "OTRA"')
    return output


def _complete(prompt, executable, model, grammar):
    if os.name != "nt":
        raise RuntimeError("The local CLI prototype currently supports Windows only")
    executable = Path(executable).resolve(strict=True)
    model = Path(model).resolve(strict=True)
    if executable.name.lower() != "llama-completion.exe" or model.suffix.lower() != ".gguf":
        raise ValueError("Invalid local model paths")
    import win32file
    import win32pipe

    pipe_name = r"\\.\pipe\mole-" + uuid.uuid4().hex
    pipe = win32pipe.CreateNamedPipe(
        pipe_name, win32pipe.PIPE_ACCESS_OUTBOUND,
        win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT | 8, 1, 65536, 65536, 0, None,
    )
    errors = []

    def deliver():
        try:
            win32pipe.ConnectNamedPipe(pipe, None)
            win32file.WriteFile(pipe, prompt.encode("utf-8"))
        except Exception as exc:
            errors.append(exc)
        finally:
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass

    cmd = [str(executable), "-m", str(model), "-f", pipe_name, "-n", "160", "-t", "4",
           "-c", "2048", "-ngl", "0", "--temp", "0", "--grammar",
           grammar, "--no-display-prompt", "--simple-io",
           "--no-perf", "-no-cnv"]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        try:
            win32file.CloseHandle(pipe)
        except Exception:
            pass
        raise
    worker = threading.Thread(target=deliver, daemon=True)
    worker.start()
    try:
        stdout, _ = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            win32file.CloseHandle(pipe)
        except Exception:
            pass
        process.communicate()
        raise TimeoutError("Local model timed out") from None
    finally:
        worker.join(timeout=2)
    if process.returncode or errors or worker.is_alive():
        raise RuntimeError("Local model failed")
    raw = stdout.decode("utf-8", errors="replace")
    output = _ANSI_ESCAPE.sub("", raw).strip()
    output = output.removesuffix("[end of text]").removesuffix("<|im_end|>").removesuffix("<|endoftext|>").strip()
    return output



def supported_plans(question, catalog):
    """Match complete supported forms; never silently discard a user criterion."""
    if not isinstance(question, str) or len(question) > 4000 or not isinstance(catalog, dict) or '\x00' in question:
        raise ValueError('Invalid general query')
    quoted = re.findall(r'"([^"\r\n]{1,100})"', question)
    if len(quoted) > 1:
        return []
    text = re.sub(r'"([^"\r\n]{1,100})"', ' __literal__ ', question)
    normalized = re.sub(r'\s+', ' ', _normalize(text).strip().strip('¿?¡! '))
    normalized = _QUERY_COURTESY.sub('', normalized).strip().strip('¿?¡! ')

    count_prefixes = (
        r'(?:(?:how many|how much)\s+(?:records?\s+of\s+)?|'
        r'what is the (?:number|count|total) of\s+|'
        r'count\s+(?:the\s+|all\s+)?|'
        r'total\s+(?:number of\s+)?|'
        r'number of\s+|'
        r'tell me the (?:number|count|total) of\s+(?:the\s+)?|'
        r'show me the (?:number|count|total) of\s+(?:the\s+)?|'
        r'do we have\s+(?:any\s+)?|'
        r'are there\s+(?:any\s+)?|'
        r'(?:cuantos?|cuantas?)\s+(?:registros?\s+de\s+)?|'
        r'cual es\s+(?:el\s+)?numero de\s+|'
        r'cual es la cantidad de\s+|'
        r'cual es el total de\s+|'
        r'cuenta\s+(?:los\s+|las\s+|a los\s+|a las\s+)?|'
        r'dime\s+(?:el\s+)?(?:numero|total|la cantidad) de\s+(?:los\s+|las\s+)?|'
        r'dime\s+(?:cuantos?|cuantas?)\s+(?:registros?\s+de\s+)?|'
        r'dime si\s+(?:hay|tenemos|existen)\s+(?:algun|algunos|alguna|algunas)?\s*|'
        r'sabes\s+(?:cuantos?|cuantas?|si hay|si tenemos)\s+(?:registros?\s+de\s+)?|'
        r'total de\s+(?:los\s+|las\s+)?|'
        r'cantidad de\s+(?:los\s+|las\s+)?|'
        r'numero de\s+(?:los\s+|las\s+)?|'
        r'tenemos\s+(?:algun|algunos|alguna|algunas)?\s*|'
        r'hay\s+(?:algun|algunos|alguna|algunas)?\s*)'
    )
    count_suffixes = (
        r'(?: with name __literal__| named __literal__| called __literal__|'
        r' con nombre __literal__| llamados? __literal__| de nombre __literal__)?'
        r'(?: hay| existen| tengo| tenemos| disponibles| registrados?| dados? de alta|'
        r' do we have| are there| exist| are available| is available)?'
        r'(?: en el sistema| en la empresa| en la compania| en total|'
        r' in the system| in the company| in total| currently)?'
    )

    list_prefixes = (
        r'(?:(?:which|what) are (?:the |all )?|'
        r'(?:which|what) (?:the |all )?|'
        r'(?:cuales|que) son (?:los |las )?|'
        r'(?:cuales|que) (?:los |las )?|'
        r'show (?:me )?(?:the |all )?|'
        r'display (?:the |all )?|'
        r'list (?:the |all )?|'
        r'give me (?:the list of |the )?|'
        r'view (?:the )?|'
        r'who are the |'
        r'muestra (?:los |las |el |la )?|'
        r'muestrame (?:los |las |el |la )?|'
        r'dame (?:los |las |la lista de |el listado de )?|'
        r'listar? (?:los |las |el |la )?|'
        r'lista de (?:los |las )?|'
        r'listado de (?:los |las )?|'
        r'ver (?:los |las |el |la )?|'
        r'consultar (?:los |las |el |la )?|'
        r'quienes son (?:los |las )?)'
    )
    list_suffixes = (
        r'(?: with name __literal__| named __literal__| called __literal__|'
        r' con nombre __literal__| llamados? __literal__| de nombre __literal__)?'
        r'(?: hay| existen| tengo| tenemos| disponibles| registrados?| dados? de alta|'
        r' do we have| are there| exist| are available| is available)?'
        r'(?: en el sistema| en la empresa| en la compania| en total|'
        r' in the system| in the company| in total| currently)?'
    )

    read_prefixes = (
        r'(?:(?:information|info|details?|data) (?:about|on|for|of) (?:the )?|'
        r'(?:who is|what is) (?:the )?|'
        r'(?:informacion|info|detalles?|datos?) de(?:l)? (?:los |las |el |la )?|'
        r'(?:quien es|que es) (?:el |la )?)'
    )
    read_suffixes = (
        r'(?: with name __literal__| named __literal__| called __literal__|'
        r' con nombre __literal__| llamados? __literal__| de nombre __literal__| __literal__)'
    )

    plans = []
    for name, entry in sorted(catalog.items()):
        labels = [entry.get('label', '')] + entry.get('aliases', [])
        for label in labels:
            if not isinstance(label, str) or not label or len(label) > 100:
                continue
            subject = re.escape(_normalize(label).strip())

            # Check COUNT
            count_pat = count_prefixes + subject + r'(?:s|es)?' + count_suffixes
            if re.fullmatch(count_pat, normalized):
                filters = []
                if quoted:
                    if 'name' not in entry.get('fields', {}):
                        continue
                    filters = [{'field': 'name', 'op': 'equals', 'value': quoted[0]}]
                elif '__literal__' in normalized:
                    continue
                plan = {'operation': 'count', 'model': name, 'filters': filters}
                if plan not in plans:
                    plans.append(plan)

            # Check LIST
            list_pat = list_prefixes + subject + r'(?:s|es)?' + list_suffixes
            if re.fullmatch(list_pat, normalized):
                filters = []
                if quoted:
                    if 'name' not in entry.get('fields', {}):
                        continue
                    filters = [{'field': 'name', 'op': 'equals', 'value': quoted[0]}]
                elif '__literal__' in normalized:
                    continue
                plan = {'operation': 'list', 'model': name, 'filters': filters}
                if plan not in plans:
                    plans.append(plan)

            # Check READ
            read_pat = read_prefixes + subject + r'(?:s|es)?' + read_suffixes
            if re.fullmatch(read_pat, normalized):
                if quoted and 'name' in entry.get('fields', {}):
                    filters = [{'field': 'name', 'op': 'equals', 'value': quoted[0]}]
                    plan = {'operation': 'read', 'model': name, 'filters': filters}
                    if plan not in plans:
                        plans.append(plan)

    return plans


def general_candidates(question, catalog):
    return [(p['model'], catalog[p['model']]['label']) for p in supported_plans(question, catalog)]


def interpret_general(question, catalog, executable, model):
    """Ask the model to select a structured plan from the allowed catalog.

    A separate conservative verifier rejects plans whose full meaning cannot be
    established from the question, even if the model selected them.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 512 or '\x00' in question:
        raise ValueError('Invalid general query')
    if not isinstance(catalog, dict) or len(catalog) > 64:
        raise ValueError('Invalid catalog')
    values = re.findall(r'"([^"\r\n]{1,100})"', question)
    options = []
    for name, entry in sorted(catalog.items()):
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_.]{0,99}', name):
            raise ValueError('Invalid model identifier')
        options.append({'operation': 'count', 'model': name, 'filters': []})
        options.append({'operation': 'list', 'model': name, 'filters': []})
        if len(values) == 1 and 'name' in entry.get('fields', {}):
            options.append({'operation': 'count', 'model': name,
                            'filters': [{'field': 'name', 'op': 'equals', 'value': values[0]}]})
            options.append({'operation': 'list', 'model': name,
                            'filters': [{'field': 'name', 'op': 'equals', 'value': values[0]}]})
            options.append({'operation': 'read', 'model': name,
                            'filters': [{'field': 'name', 'op': 'equals', 'value': values[0]}]})
    possible = [json.dumps(plan, ensure_ascii=False, separators=(',', ':')) for plan in options]
    grammar = 'root ::= ' + ' | '.join(json.dumps(value, ensure_ascii=False) for value in ['null'] + possible)
    public_catalog = {name: {'label': item['label'], 'aliases': item.get('aliases', []),
                             'fields': [field for field in item.get('fields', {}) if field == 'name']}
                      for name, item in catalog.items()}
    prompt = ('<|im_start|>system\nSelecciona el modelo y operación del catálogo que corresponda a la pregunta. '
              'Devuelve un objeto JSON con operation (count, list o read), model y filters, o null si no entiendes. '
              'Para nombre entre comillas usa field=name, op=equals, value=el texto literal. '
              'No ignores ningún criterio. Si no puedes expresarlo, devuelve null. '
              'Catálogo: ' + json.dumps(public_catalog, ensure_ascii=False).replace('<|', '< |') +
              '\n<|im_end|>\n<|im_start|>user\n' + question.replace('<|', '< |').replace('|>', '| >') +
              '<|im_end|>\n<|im_start|>assistant\n')
    output = _complete(prompt, executable, model, grammar)
    try:
        plan = json.loads(output)
    except (TypeError, ValueError):
        return None
    verified = supported_plans(question, catalog)
    return plan if len(verified) == 1 and plan == verified[0] else None
