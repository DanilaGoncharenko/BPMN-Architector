import json, os
import streamlit as st
import streamlit.components.v1 as components
from pipeline import make_client, generate

st.set_page_config(page_title="Архитектор BPMN-диаграмм", page_icon="img/logo.jpg", layout="wide")

EXAMPLES = {
    "Заявка и договор (3 участника, ветвление, возврат)":
        "Клиент оставляет заявку. Менеджер получает заявку и проверяет её. Если заявка корректная, менеджер согласует договор. "
        "Если заявка некорректная, менеджер отправляет заявку клиенту на доработку. Клиент исправляет заявку и повторно отправляет её. "
        "После согласования договора система автоматически регистрирует договор.",
    "Технологическое присоединение (параллельные ветки)":
        "Заявитель подаёт заявку на технологическое присоединение. Диспетчер сетевой организации регистрирует заявку. "
        "Затем параллельно: инженер готовит технические условия, а юрист готовит проект договора. "
        "После завершения обеих работ диспетчер направляет пакет документов заявителю. "
        "Заявитель подписывает договор. Если оплата не поступила в срок, диспетчер аннулирует заявку, иначе инженер организует подключение.",
}

def viewer(xml: str, height=620):
    xml_js = json.dumps(xml).replace("</", "<\\/")
    html = f"""
<link rel="stylesheet" href="https://unpkg.com/bpmn-js@17.9.2/dist/assets/diagram-js.css">
<link rel="stylesheet" href="https://unpkg.com/bpmn-js@17.9.2/dist/assets/bpmn-js.css">
<link rel="stylesheet" href="https://unpkg.com/bpmn-js@17.9.2/dist/assets/bpmn-font/css/bpmn.css">
<div style="font-family:sans-serif;margin-bottom:6px">
  <button onclick="fit()">По размеру</button>
  <button onclick="save()">Скачать .bpmn (с правками)</button>
  <span id="err" style="color:#b00"></span>
</div>
<div id="c" style="height:{height - 50}px;border:1px solid #ccc;background:#fff"></div>
<script src="https://unpkg.com/bpmn-js@17.9.2/dist/bpmn-modeler.development.js"></script>
<script>
const m = new BpmnJS({{container:'#c'}});
function fit(){{m.get('canvas').zoom('fit-viewport','auto')}}
m.importXML({xml_js}).then(fit).catch(e=>document.getElementById('err').innerText='Ошибка импорта: '+e.message);
async function save(){{
  const {{xml}} = await m.saveXML({{format:true}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([xml],{{type:'application/xml'}}));
  a.download='process.bpmn'; a.click();
}}
</script>"""
    components.html(html, height=height, scrolling=False)

def secret(name, default=""):
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

with st.sidebar:
    st.image('img/logo.jpg')
    st.header("Модель")
    base_url = st.text_input("LLM BASE URL (OpenAI-совместимый)", secret("LLM_BASE_URL", "https://router.huggingface.co/v1"))
    model = st.text_input("LLM MODEL", secret("LLM_MODEL", "Qwen/Qwen3.6-35B-A3B"))
    api_key = st.text_input("LLM API KEY", secret("LLM_API_KEY"), type="password")
    temperature = st.slider("temperature", 0.0, 1.0, 0.2, 0.05)
    retries = st.slider("Авто-исправлений при ошибках", 0, 4, 2)
    st.caption("Замена модели = смена трёх полей. Для моделей Яндекса — их OpenAI-совместимый endpoint.")

st.title("Архитектор BPMN-диаграмм")
ex = st.selectbox("Пример", ["—"] + list(EXAMPLES))
text = st.text_area("Описание бизнес-процесса", EXAMPLES.get(ex, ""), height=200,
                    placeholder="Вставьте описание своего бизнес-процесса")

if st.button("Построить диаграмму", type="primary", disabled=not text.strip()):
    if not api_key:
        st.error("Укажите LLM_API_KEY (в боковой панели или в .env / secrets)."); st.stop()
    logs = []
    with st.status("Генерация…", expanded=True) as status:
        try:
            diagram, code, problems, attempts = generate(
                text, make_client(base_url, api_key), model, temperature, retries,
                log=lambda m: (logs.append(m), st.write(m)))
            xml = diagram.to_xml() if diagram else None
            status.update(label="Готово" if xml and not problems else "Готово с замечаниями", state="complete")
        except Exception as e:
            status.update(label="Ошибка", state="error"); st.exception(e); st.stop()
    st.session_state.result = dict(xml=xml, code=code, problems=problems, attempts=attempts)

r = st.session_state.get("result")
if r:
    if r["problems"]:
        st.warning("Остались замечания:\n- " + "\n- ".join(r["problems"]))
    if r["xml"]:
        t1, t2, t3 = st.tabs(["Диаграмма (редактируемая)", "BPMN XML", "Код от модели"])
        with t1:
            viewer(r["xml"])
        with t2:
            st.download_button("Скачать .bpmn", r["xml"], "process.bpmn", "application/xml")
            st.code(r["xml"], language="xml")
        with t3:
            st.caption(f"Попыток: {r['attempts']}")
            st.code(r["code"], language="python")
