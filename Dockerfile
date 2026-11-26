FROM python:3.10.11-slim
WORKDIR /opt/app/bizagent
COPY packaging/windows/requirements.lock /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY bizagent/ ./
COPY schema.sql ../schema.sql
COPY packaging/serve.py ../serve.py
CMD ["python", "../serve.py"]
