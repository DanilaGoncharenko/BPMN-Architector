# BPMN-ассистент (Streamlit)

Текст → LLM → Python-код (DIAGRAM API) → AST-проверка → песочница → проверка графа (с авто-исправлением через LLM) → автолейаут → BPMN 2.0 XML + DI → редактор bpmn-js.

## Запуск локально
    python -m venv .venv
    source .venv\Scripts\activate
    pip install -r requirements.txt
    streamlit run app.py --server.port 8501 --server.headless true \
        --server.enableCORS false --server.enableXsrfProtection false

