FROM python:3.12-slim

WORKDIR /locust

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /reports

EXPOSE 8089 5557

ENTRYPOINT ["python", "-m", "locust"]
