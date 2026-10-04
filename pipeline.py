"""LLM -> Python-код (DIAGRAM API) -> валидация -> выполнение в песочнице -> BPMN XML."""
import ast, os, re
from bpmn_diagram import Diagram

ALLOWED_METHODS = {"create_subprocess", "add_task", "add_user_task", "add_script_task", "add_pool", "add_link",
                   "add_exclusive_gateway", "add_parallel_gateway", "add_inclusive_gateway", "add_group"}
SAFE_BUILTINS = {"range": range, "len": len, "list": list, "enumerate": enumerate, "zip": zip,
                 "str": str, "dict": dict, "tuple": tuple}

SYSTEM_PROMPT = """Ты — генератор BPMN-диаграмм. По описанию процесса напиши Python-код для DIAGRAM API.
В песочнице уже есть: DIAGRAM, ROOT_PROCESS_ID, ROOT_START_TASK_ID, ROOT_END_TASK_ID.

API (других методов нет):
  pool_id, lanes = DIAGRAM.add_pool(ROOT_PROCESS_ID, ["Участник1", "Участник2"])  # lanes — список id дорожек
  t = DIAGRAM.add_user_task("Название", lane_id)    # действие человека
  t = DIAGRAM.add_script_task("Название", lane_id)  # автоматическое действие системы
  t = DIAGRAM.add_task("Название", lane_id)         # тип неизвестен
  g = DIAGRAM.add_exclusive_gateway("Вопрос?", lane_id)  # XOR: выполняется ровно одна ветка
  g = DIAGRAM.add_parallel_gateway("Название", lane_id)  # AND: все ветки параллельно
  g = DIAGRAM.add_inclusive_gateway("Название", lane_id) # OR: одна или несколько веток
  s = DIAGRAM.create_subprocess("Название", lane_id)
  grp = DIAGRAM.add_group("Название", lane_id)
  DIAGRAM.add_link(from_id, to_id)

Правила:
1. Верни ТОЛЬКО код, без Markdown и пояснений. Без import, без def/class, без своих функций.
2. Каждому участнику — своя дорожка (один add_pool в начале). Если участник один, пул не нужен: контейнер = ROOT_PROCESS_ID.
3. Каждый элемент создавай в дорожке того, кто его выполняет. Шлюз — в дорожке того, кто принимает решение.
4. Процесс начинается от ROOT_START_TASK_ID и заканчивается в ROOT_END_TASK_ID. Старт и конец не создавай.
5. Нет «висячих» узлов: каждый узел достижим от старта и ведёт к концу.
6. Условие ветвления пиши в названии шлюза вопросом («Заявка корректна?»). Add_link условий не принимает.
7. Названия задач — глагол + объект, коротко («Проверить заявку»).
8. Если после ветвления потоки продолжаются общим путём — добавь шлюз слияния того же типа.
   Для параллельных ветвей слияние (join) обязательно.
9. Возврат на доработку / повтор шага — это link назад на предыдущую задачу.
10. Не придумывай шаги, которых нет в описании.

Пример. Описание: «Клиент подаёт заявку. Менеджер проверяет её. Если корректна — согласует договор, иначе возвращает клиенту на доработку. Затем система регистрирует договор.»
pool_id, lanes = DIAGRAM.add_pool(ROOT_PROCESS_ID, ["Клиент", "Менеджер", "Система"])
client, manager, system = lanes
t1 = DIAGRAM.add_user_task("Подать заявку", client)
t2 = DIAGRAM.add_user_task("Проверить заявку", manager)
g1 = DIAGRAM.add_exclusive_gateway("Заявка корректна?", manager)
t3 = DIAGRAM.add_user_task("Согласовать договор", manager)
t4 = DIAGRAM.add_user_task("Доработать заявку", client)
t5 = DIAGRAM.add_script_task("Зарегистрировать договор", system)
DIAGRAM.add_link(ROOT_START_TASK_ID, t1)
DIAGRAM.add_link(t1, t2)
DIAGRAM.add_link(t2, g1)
DIAGRAM.add_link(g1, t3)
DIAGRAM.add_link(g1, t4)
DIAGRAM.add_link(t4, t2)
DIAGRAM.add_link(t3, t5)
DIAGRAM.add_link(t5, ROOT_END_TASK_ID)
"""


def make_client(base_url, api_key):
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=api_key)


def clean_code(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.S)
    return (m.group(1) if m else text).strip()


def validate_code(code):
    tree = ast.parse(code)
    banned = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
              ast.Global, ast.Nonlocal, ast.With, ast.Delete, ast.Try, ast.While)
    for n in ast.walk(tree):
        if isinstance(n, banned):
            raise ValueError(f"Запрещённая конструкция: {type(n).__name__}")
        if isinstance(n, ast.Name) and n.id.startswith("__"):
            raise ValueError("Запрещено обращаться к dunder-именам")
        if isinstance(n, ast.Attribute):
            ok_diag = isinstance(n.value, ast.Name) and n.value.id == "DIAGRAM" and n.attr in ALLOWED_METHODS
            if not ok_diag and n.attr not in ("append", "extend"):
                raise ValueError(f"Запрещённый атрибут: .{n.attr}")


def run_code(code):
    validate_code(code)
    d = Diagram()
    ns = {"__builtins__": SAFE_BUILTINS, "DIAGRAM": d, "ROOT_PROCESS_ID": d.ROOT_PROCESS_ID,
          "ROOT_START_TASK_ID": d.ROOT_START_TASK_ID, "ROOT_END_TASK_ID": d.ROOT_END_TASK_ID}
    exec(compile(code, "<llm>", "exec"), ns)
    return d


def generate(description, client, model, temperature=0.2, max_retries=2, log=None):
    log = log or (lambda *_: None)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Построй BPMN-процесс по описанию:\n" + description}]
    code, diagram, problems = "", None, []
    for attempt in range(max_retries + 1):
        log(f"Попытка {attempt + 1}: запрос к модели")
        r = client.chat.completions.create(model=model, messages=msgs, temperature=temperature, max_tokens=4000)
        raw = r.choices[0].message.content or ""
        code = clean_code(raw)
        try:
            diagram = run_code(code)
            problems = diagram.check()
        except Exception as e:  # синтаксис, запрещённый API, неверные id
            diagram, problems = None, [f"Ошибка выполнения кода: {type(e).__name__}: {e}"]
        if not problems:
            log("Проверки пройдены")
            return diagram, code, [], attempt + 1
        log("Найдены проблемы: " + "; ".join(problems))
        msgs += [{"role": "assistant", "content": code},
                 {"role": "user", "content": "Исправь код. Проблемы:\n- " + "\n- ".join(problems) +
                  "\nВерни полный исправленный код, только код."}]
    return diagram, code, problems, max_retries + 1
