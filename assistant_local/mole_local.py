"""Local Windows intent classifier for the first Mole vacation capability."""

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
    clean = question.replace("<|", "< |").replace("|>", "| >")
    prompt = (
        "<|im_start|>system\nClasifica la solicitud: VACACIONES si pregunta por sus "
        "propios días de vacaciones, OTRA para cualquier otra cosa.\n"
        "Ejemplos:\n¿Cuántos días de vacaciones me quedan? VACACIONES\n"
        "Dime mi saldo de vacaciones. VACACIONES\n¿Cuándo vence mi periodo de vacaciones? VACACIONES\n"
        "¿Cuántos días de vacaciones tiene Ana? OTRA\n¿Cuántas facturas hice? OTRA\n"
        "Hola. OTRA\nTransfiere productos. OTRA\n<|im_end|>\n<|im_start|>user\n"
        + clean + "<|im_end|>\n<|im_start|>assistant\n"
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

    cmd = [str(executable), "-m", str(model), "-f", pipe_name, "-n", "16", "-t", "4",
           "-c", "2048", "-ngl", "0", "--temp", "0", "--grammar",
           'root ::= "VACACIONES" | "OTRA"', "--no-display-prompt", "--simple-io",
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
    if output not in {"VACACIONES", "OTRA"}:
        raise ValueError("Invalid local model output")
    return output
