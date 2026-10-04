# BPMN-ассистент (Streamlit)

Текст → LLM → Python-код (DIAGRAM API) → AST-проверка → песочница → проверка графа (с авто-исправлением через LLM) → автолейаут → BPMN 2.0 XML + DI → редактор bpmn-js.

## Запуск локально
    python -m venv .venv
    source .venv\Scripts\activate
    pip install -r requirements.txt
    streamlit run app.py --server.port 8501 --server.headless true \
        --server.enableCORS false --server.enableXsrfProtection false

## Выгрузка в сеть через Cloudflare
Быстрый вариант (временный URL вида https://xxxx.trycloudflare.com):
    # установка: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    cloudflared tunnel --url http://localhost:8501

Постоянный URL на своём домене:
    cloudflared tunnel login
    cloudflared tunnel create bpmn-app
    cloudflared tunnel route dns bpmn-app bpmn.example.com
    # ~/.cloudflared/config.yml:
    #   tunnel: bpmn-app
    #   credentials-file: ~/.cloudflared/<UUID>.json
    #   ingress:
    #     - hostname: bpmn.example.com
    #       service: http://localhost:8501
    #     - service: http_status:404
    cloudflared tunnel run bpmn-app

Streamlit работает по WebSocket — Cloudflare его проксирует без доп. настроек.
Ключ LLM не светите в интерфейсе: задавайте через окружение/secrets (сайдбар виден всем посетителям).
